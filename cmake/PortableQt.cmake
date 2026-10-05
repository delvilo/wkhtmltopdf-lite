# LGPL-3.0-or-later
function(wkhtmltox_group_static_dependencies target)
    # The SDK exports GNU linker markers, but CMake does not understand their
    # boundaries. WebKit's transitive ICU entries can therefore be deduplicated
    # outside the group. A native CMake group preserves every archive, including
    # occurrences inherited from QtWebKit's imported targets. Keep system
    # dependencies in the group too: --as-needed must see them after the
    # archives that reference them (notably libxml2 -> lzma).
    get_target_property(dependencies ${target} INTERFACE_LINK_LIBRARIES)
    list(REMOVE_ITEM dependencies "-Wl,--start-group" "-Wl,--end-group")
    list(JOIN dependencies "," dependencies)
    set_property(TARGET ${target} PROPERTY INTERFACE_LINK_LIBRARIES
        "$<LINK_GROUP:RESCAN,${dependencies}>")
endfunction()

function(wkhtmltox_check_static_qt)
    if(NOT QT5_STATIC_PREFIX)
        message(FATAL_ERROR "Portable builds require QT5_STATIC_PREFIX and cmake/toolchains/qt5-static.cmake")
    endif()
    get_filename_component(prefix "${QT5_STATIC_PREFIX}" REALPATH)
    foreach(target IN LISTS ARGN)
        if(NOT TARGET ${target})
            message(FATAL_ERROR "Required static Qt target is missing: ${target}")
        endif()
        get_target_property(type ${target} TYPE)
        # Qt5 describes imported plugins as MODULE_LIBRARY even when their
        # imported location is a .a. Check the archive path for both kinds.
        if(NOT type STREQUAL "STATIC_LIBRARY" AND NOT type STREQUAL "MODULE_LIBRARY")
            message(FATAL_ERROR "${target} is ${type}; use the static Qt5/WebKit toolchain in a clean build directory")
        endif()
        get_target_property(configs ${target} IMPORTED_CONFIGURATIONS)
        set(properties IMPORTED_LOCATION)
        foreach(config IN LISTS configs)
            string(TOUPPER "${config}" config)
            list(APPEND properties "IMPORTED_LOCATION_${config}")
        endforeach()
        set(found FALSE)
        foreach(property IN LISTS properties)
            get_target_property(location ${target} ${property})
            if(location)
                get_filename_component(location "${location}" REALPATH)
                string(FIND "${location}" "${prefix}/" in_prefix)
                if(NOT in_prefix EQUAL 0 OR NOT location MATCHES "\\.a$" OR NOT EXISTS "${location}")
                    message(FATAL_ERROR "${target} must use an existing .a under ${prefix}: ${location}")
                endif()
                set(found TRUE)
            endif()
        endforeach()
        if(NOT found)
            message(FATAL_ERROR "No installed archive found for ${target}")
        endif()
    endforeach()
endfunction()

function(wkhtmltox_no_default_plugins target)
    qt5_import_plugins(${target}
        EXCLUDE_BY_TYPE platforms platforminputcontexts platformthemes
            egldeviceintegrations xcbglintegrations imageformats iconengines
            styles generic printsupport sqldrivers bearer)
endfunction()

function(wkhtmltox_import_plugins target)
    # Register plugins in each final ELF; a registration object in an ordinary
    # static archive can otherwise be discarded by the linker.
    set(plugins Qt5::QOffscreenIntegrationPlugin Qt5::QJpegPlugin
        Qt5::QGifPlugin Qt5::QICOPlugin Qt5::QSvgPlugin Qt5::QSvgIconPlugin
        Qt5::QGenericEnginePlugin)
    wkhtmltox_check_static_qt(${plugins})
    wkhtmltox_no_default_plugins(${target})
    qt5_import_plugins(${target} INCLUDE ${plugins})
endfunction()
