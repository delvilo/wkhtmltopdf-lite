#!/usr/bin/env bash
# Build a native Ubuntu 24.04 x86_64 Qt5/WebKit SDK. LGPL-3.0-or-later.
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
work=$(realpath -m "${1:-$root/static-build}")
prefix="$work/qt"
jobs=${JOBS:-4}
source /etc/os-release
[[ "$ID:$VERSION_ID:$(uname -m)" == ubuntu:24.04:x86_64 ]] || {
    echo 'This toolchain is qualified only on Ubuntu 24.04 x86_64.' >&2; exit 1;
}
for tool in cmake ninja pkg-config g++ python3 perl ruby bison flex gperf dpkg-source; do
    command -v "$tool" >/dev/null || { echo "Missing build tool: $tool" >&2; exit 1; }
done
[[ "$work" != *' '* ]] || { echo 'Use a build path without spaces (Qt5 qmake limitation).' >&2; exit 1; }
mkdir -p "$work/sources" "$work/licenses" "$prefix/lib/portable-deps" "$prefix/lib/cmake/wkhtmltox"
recipe_hash=$(sha256sum "$root/tools/portable/build-toolchain.sh" | cut -d' ' -f1)
if [[ -f "$work/toolchain-recipe.sha256" ]] &&
   [[ "$(cut -d' ' -f1 "$work/toolchain-recipe.sha256")" != "$recipe_hash" ]]; then
    echo 'Toolchain recipe changed; use a fresh work directory to avoid stale Qt configuration.' >&2
    exit 1
fi

# Pin Ubuntu-maintained source packages, including their compiler/security fixes.
# These are upstream Qt5 APIs; no wkhtmltopdf patched-Qt functionality is added.
specs=(qtbase-opensource-src=5.15.13+dfsg-1ubuntu1
       qtsvg-opensource-src=5.15.13-1
       qtwebkit-opensource-src=5.212.0~alpha4-36)
multiarch=$(gcc -print-multiarch)
libdir="/usr/lib/$multiarch"
archives=(icuuc icui18n icudata jpeg xml2 webp sharpyuv sqlite3 hyphen)
for name in "${archives[@]}"; do
    file="$libdir/lib$name.a"
    [[ -f "$file" ]] || { echo "Missing $file; install the documented build dependencies." >&2; exit 1; }
    owner=$(dpkg-query -S "$file" | head -1 | sed 's/: \/.*//')
    specs+=("$(dpkg-query -W -f='${source:Package}=${source:Version}' "$owner")")
done
source_specs=$(printf '%s\n' "${specs[@]}" | sort -u)
if [[ -f "$work/source-packages.txt" ]] &&
   [[ "$(cat "$work/source-packages.txt")" != "$source_specs" ]]; then
    echo 'Dependency versions changed; use a fresh work directory.' >&2; exit 1
fi
python3 "$root/tools/portable/sources.py" "$work/sources" "${specs[@]}" --licenses "$work/licenses"
qtbase_source=$(realpath "$work/sources/qtbase-opensource-src")
qtsvg_source=$(realpath "$work/sources/qtsvg-opensource-src")
qtwebkit_source=$(realpath "$work/sources/qtwebkit-opensource-src")
for name in "${archives[@]}"; do
    cp "$libdir/lib$name.a" "$prefix/lib/portable-deps/"
done
dpkg-query -W -f='${binary:Package}\t${Version}\n' > "$work/build-packages.tsv"
printf '%s\n' "$source_specs" > "$work/source-packages.txt"
printf '%s  tools/portable/build-toolchain.sh\n' "$recipe_hash" > "$work/toolchain-recipe.sha256"

mkdir -p "$work/qtbase" "$work/qtsvg"
if [[ ! -f "$work/qtbase/Makefile" ]]; then
    (cd "$work/qtbase" && "$qtbase_source/configure" \
        -prefix "$prefix" -release -static -opensource -confirm-license \
        -nomake examples -nomake tests -no-opengl -no-xcb -no-dbus -no-cups \
        -no-gtk -no-glib -no-icu -no-feature-sql \
        -system-zlib -system-libpng -system-libjpeg -system-freetype \
        -fontconfig -system-pcre -qt-harfbuzz -openssl-linked \
        "QMAKE_LIBS_LIBJPEG=$prefix/lib/portable-deps/libjpeg.a")
fi
make -C "$work/qtbase" -j"$jobs"
make -C "$work/qtbase" install
(cd "$work/qtsvg" && "$prefix/bin/qmake" "$qtsvg_source/qtsvg.pro")
make -C "$work/qtsvg" -j"$jobs"
make -C "$work/qtsvg" install

deps="$prefix/lib/portable-deps"
cmake -S "$qtwebkit_source" -B "$work/qtwebkit" -G Ninja \
    -DPORT=Qt -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$prefix" \
    -DCMAKE_PREFIX_PATH="$prefix" -DCMAKE_POSITION_INDEPENDENT_CODE=ON \
    -DENABLE_WEBKIT2=OFF -DENABLE_TOOLS=OFF -DENABLE_TEST_SUPPORT=OFF -DENABLE_API_TESTS=OFF \
    -DUSE_THIN_ARCHIVES=OFF -DENABLE_ALLINONE_BUILD=OFF \
    -DENABLE_VIDEO=OFF -DENABLE_WEB_AUDIO=OFF -DUSE_GSTREAMER=OFF \
    -DUSE_QT_MULTIMEDIA=OFF -DENABLE_GEOLOCATION=OFF -DENABLE_DEVICE_ORIENTATION=OFF \
    -DENABLE_OPENGL=OFF -DENABLE_X11_TARGET=OFF -DENABLE_PRINT_SUPPORT=ON \
    -DENABLE_XSLT=OFF -DENABLE_INSPECTOR_UI=OFF \
    -DCMAKE_DISABLE_FIND_PACKAGE_WOFF2Dec=ON \
    -DICU_LIBRARY="$deps/libicuuc.a;$deps/libicudata.a" \
    -DICU_I18N_LIBRARY="$deps/libicui18n.a" -DJPEG_LIBRARY="$deps/libjpeg.a" \
    -DLIBXML2_LIBRARY="$deps/libxml2.a" -DWEBP_LIBRARIES="$deps/libwebp.a;$deps/libsharpyuv.a" \
    -DSQLITE_LIBRARIES="$deps/libsqlite3.a" -DHYPHEN_LIBRARIES="$deps/libhyphen.a"
# QtWebKit's old top-level "all" also builds unused JSC test executables even
# with ENABLE_TOOLS=OFF. Build the installed library targets explicitly.
cmake --build "$work/qtwebkit" --target WebKit WebKitWidgets --parallel "$jobs"
cmake --install "$work/qtwebkit"

# libxml2.a needs lzma and ICU. Keep all non-Qt archives in a linker group,
# since WebKit's old export format does not fully encode their dependencies.
cat > "$prefix/lib/cmake/wkhtmltox/PortableDependencies.cmake" <<'CMAKE'
add_library(wkhtmltox_portable_dependencies INTERFACE)
get_filename_component(_deps "${CMAKE_CURRENT_LIST_DIR}/../../portable-deps" ABSOLUTE)
target_link_libraries(wkhtmltox_portable_dependencies INTERFACE
    "-Wl,--start-group"
    "${_deps}/libicui18n.a" "${_deps}/libicuuc.a" "${_deps}/libicudata.a"
    "${_deps}/libjpeg.a" "${_deps}/libxml2.a" "${_deps}/libwebp.a"
    "${_deps}/libsharpyuv.a" "${_deps}/libsqlite3.a" "${_deps}/libhyphen.a"
    "-Wl,--end-group" lzma z dl pthread m)
unset(_deps)
CMAKE
cp "$work/source-packages.txt" "$work/build-packages.tsv" "$work/toolchain-recipe.sha256" "$prefix/"
printf '\nStatic Qt5/WebKit installed: %s\n' "$prefix"
