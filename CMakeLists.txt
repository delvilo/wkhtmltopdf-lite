cmake_minimum_required(VERSION 3.17)

if(NOT DEFINED WKHTMLTOX_VERSION)
    if(DEFINED ENV{WKHTMLTOX_VERSION} AND NOT "$ENV{WKHTMLTOX_VERSION}" STREQUAL "")
        set(WKHTMLTOX_VERSION "$ENV{WKHTMLTOX_VERSION}")
    else()
        set(WKHTMLTOX_VERSION "0.12.7")
    endif()
endif()
set(WKHTMLTOX_VERSION "${WKHTMLTOX_VERSION}" CACHE STRING "Version shown by the converters")
string(REGEX REPLACE "-.*$" "" WKHTMLTOX_BASE_VERSION "${WKHTMLTOX_VERSION}")
project(wkhtmltopdf VERSION "${WKHTMLTOX_BASE_VERSION}" LANGUAGES CXX)

if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux")
    message(FATAL_ERROR "Linux is the only supported platform")
endif()

include(GNUInstallDirs)
include(CTest)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
set(CMAKE_BUILD_RPATH_USE_ORIGIN ON)
set(CMAKE_INSTALL_RPATH "$ORIGIN/../${CMAKE_INSTALL_LIBDIR}")

find_package(Qt5 5.3 REQUIRED COMPONENTS Core Gui Widgets Network PrintSupport Svg WebKit WebKitWidgets)

set(wkhtmltox_sources
    src/lib/resourceloader.cc src/lib/renderbackend.cc src/lib/webkitpage.cc
    src/lib/loadsettings.cc src/lib/logging.cc src/lib/multipageloader.cc
    src/lib/tempfile.cc src/lib/converter.cc src/lib/websettings.cc
    src/lib/reflect.cc src/lib/utilities.cc
    src/lib/pdfsettings.cc src/lib/pdfconverter.cc
    src/lib/imagesettings.cc src/lib/imageconverter.cc src/lib/imageoutput.cc
    src/lib/pdf_c_bindings.cc src/lib/image_c_bindings.cc
)
set(wkhtmltox_headers
    src/lib/rendering.hh src/lib/resourceloader.hh src/lib/renderbackend.hh src/lib/webkitpage.hh
    src/lib/converter.hh src/lib/multipageloader.hh src/lib/loadsettings.hh
    src/lib/websettings.hh src/lib/utilities.hh src/lib/multipageloader_p.hh
    src/lib/converter_p.hh src/lib/pdfconverter.hh src/lib/pdfsettings.hh
    src/lib/pdfconverter_p.hh src/lib/imageconverter.hh src/lib/imagesettings.hh
    src/lib/imageconverter_p.hh src/lib/imageoutput.hh src/lib/pdf_c_bindings_p.hh
    src/lib/image_c_bindings_p.hh src/lib/pdf.h src/lib/image.h
)
set(wkhtmltox_qt
    Qt5::Core Qt5::Gui Qt5::Widgets Qt5::Network Qt5::PrintSupport
    Qt5::Svg Qt5::WebKit Qt5::WebKitWidgets
)

add_library(wkhtmltox SHARED ${wkhtmltox_sources} ${wkhtmltox_headers} wkhtmltopdf.qrc)
target_include_directories(wkhtmltox PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/src/lib>
    $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}/wkhtmltox>
)
target_compile_definitions(wkhtmltox PRIVATE
    BUILDING_WKHTMLTOX BUILDING_DLL
    VERSION=${WKHTMLTOX_BASE_VERSION} FULL_VERSION=${WKHTMLTOX_VERSION}
)
target_link_libraries(wkhtmltox PUBLIC ${wkhtmltox_qt})
set_target_properties(wkhtmltox PROPERTIES VERSION "${PROJECT_VERSION}" SOVERSION "${PROJECT_VERSION_MAJOR}")

set(wkhtmltox_cli_sources
    src/shared/outputter.cc src/shared/manoutputter.cc src/shared/textoutputter.cc
    src/shared/arghandler.cc src/shared/commondocparts.cc
    src/shared/commandlineparserbase.cc src/shared/commonarguments.cc
    src/shared/progressfeedback.cc src/shared/cliapplication.cc
    src/shared/progressfeedback.hh src/shared/cliapplication.hh
)

add_executable(wkhtmltopdf
    src/pdf/wkhtmltopdf.cc src/pdf/pdfarguments.cc
    src/pdf/pdfcommandlineparser.cc src/pdf/pdfdocparts.cc
    ${wkhtmltox_cli_sources} wkhtmltopdf.qrc
)
add_executable(wkhtmltoimage
    src/image/wkhtmltoimage.cc src/image/imagearguments.cc
    src/image/imagecommandlineparser.cc src/image/imagedocparts.cc
    ${wkhtmltox_cli_sources} wkhtmltopdf.qrc
)
foreach(app IN ITEMS wkhtmltopdf wkhtmltoimage)
    target_include_directories(${app} PRIVATE src/shared)
    target_compile_definitions(${app} PRIVATE BUILDING_WKHTMLTOX
        VERSION=${WKHTMLTOX_BASE_VERSION} FULL_VERSION=${WKHTMLTOX_VERSION})
    target_link_libraries(${app} PRIVATE wkhtmltox)
endforeach()

install(TARGETS wkhtmltox wkhtmltopdf wkhtmltoimage
    RUNTIME DESTINATION "${CMAKE_INSTALL_BINDIR}"
    LIBRARY DESTINATION "${CMAKE_INSTALL_LIBDIR}"
    ARCHIVE DESTINATION "${CMAKE_INSTALL_LIBDIR}")
install(FILES src/lib/pdf.h src/lib/image.h src/lib/dllbegin.inc src/lib/dllend.inc
    DESTINATION "${CMAKE_INSTALL_INCLUDEDIR}/wkhtmltox")

find_program(GZIP_EXECUTABLE gzip REQUIRED)
foreach(app IN ITEMS wkhtmltopdf wkhtmltoimage)
    set(manpage "${CMAKE_CURRENT_BINARY_DIR}/${app}.1.gz")
    add_custom_command(OUTPUT "${manpage}"
        COMMAND "${CMAKE_COMMAND}" "-DAPP=$<TARGET_FILE:${app}>"
            "-DOUTPUT=${manpage}" "-DGZIP=${GZIP_EXECUTABLE}"
            -P "${CMAKE_CURRENT_SOURCE_DIR}/cmake/GenerateManPage.cmake"
        DEPENDS ${app} "${CMAKE_CURRENT_SOURCE_DIR}/cmake/GenerateManPage.cmake"
        VERBATIM)
    list(APPEND wkhtmltox_manpages "${manpage}")
endforeach()
add_custom_target(manpages ALL DEPENDS ${wkhtmltox_manpages})
install(FILES ${wkhtmltox_manpages} DESTINATION "${CMAKE_INSTALL_MANDIR}/man1")

if(BUILD_TESTING)
    find_package(Python3 REQUIRED COMPONENTS Interpreter)
    find_package(Qt5 5.3 REQUIRED COMPONENTS Test)
    foreach(suite IN ITEMS image_entry_smoke option_removal_smoke rendering_backend_smoke)
        add_test(NAME ${suite}
            COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/${suite}.py"
                --bin-dir "$<TARGET_FILE_DIR:wkhtmltopdf>")
        set_tests_properties(${suite} PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
    endforeach()

    add_executable(rendering_interfaces
        tests/rendering_interfaces.cc src/lib/webkitpage.cc src/lib/resourceloader.cc
        src/lib/rendering.hh src/lib/resourceloader.hh src/lib/webkitpage.hh
        wkhtmltopdf.qrc)
    target_include_directories(rendering_interfaces PRIVATE src/lib)
    target_compile_definitions(rendering_interfaces PRIVATE BUILDING_WKHTMLTOX)
    target_link_libraries(rendering_interfaces PRIVATE wkhtmltox ${wkhtmltox_qt} Qt5::Test)
    add_test(NAME rendering_interfaces COMMAND rendering_interfaces)
    set_tests_properties(rendering_interfaces PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
endif()
