# Portable Linux Qt5/WebKit build

## Target and runtime requirements

Build natively on **Ubuntu 24.04 x86_64**. Deploy `wkhtmltopdf` and
`wkhtmltoimage` on **Debian 13 x86_64**, without Qt5, QtWebKit, X11, a display
server, a plugin directory, or an `LD_LIBRARY_PATH` wrapper. Each executable
contains Qt5, QtWebKit and its offscreen/image plugins. This is static Qt
linkage with shared system libraries, not a fully static libc executable.
The portable application build requires **CMake 3.24 or newer** to preserve
static archive link groups; Ubuntu 24.04's packaged CMake meets this requirement.

The release check rejects dynamic Qt, WebKit, ICU, JPEG and libxml2 dependencies,
unapproved SONAMEs, RPATH/RUNPATH, GLIBC newer than 2.39, and GLIBCXX newer than
3.4.33. Later Debian releases are eligible while they provide the same required
system ABIs; a version number alone is not a compatibility guarantee. The
release's `runtime-dependencies.json` lists the exact ELF requirements.

Install the runtime prerequisites on Debian 13 (apt also resolves transitive
dependencies such as zlib, libpng, expat, Brotli and bzip2):

```sh
sudo apt-get update
sudo apt-get install --no-install-recommends \
  ca-certificates libstdc++6 libfontconfig1 libfreetype6 libssl3t64 \
  libpcre2-16-0 libzstd1 liblzma5 fonts-dejavu-core fonts-noto-cjk
./bin/wkhtmltopdf input.html output.pdf
./bin/wkhtmltoimage --format png input.html output.png
```

`fonts-noto-cjk` supplies Chinese/Japanese/Korean glyphs; use other installed
fonts if your documents require them. Font selection and layout can change
between systems with different fonts. CA certificates and OpenSSL come from
the target distribution so they can be updated independently of this program.
The existing loader's handling of certificate errors is unchanged; the HTTPS
regression verifies TLS loading, not strict certificate rejection.

## Build the static toolchain

Allow several GB of disk and memory for QtWebKit; start with two parallel jobs
on a small builder. All compilation happens in a separate directory. No system
Qt installation is overwritten. Do not use `-march=native` for release builds.

```sh
sudo bash tools/portable/install-deps.sh
JOBS=2 bash tools/portable/build-toolchain.sh "$PWD/static-build"
cmake -S . -B build/portable -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_TOOLCHAIN_FILE=cmake/toolchains/qt5-static.cmake \
  -DQT5_STATIC_PREFIX="$PWD/static-build/qt"
cmake --build build/portable --parallel 2
ctest --test-dir build/portable --output-on-failure
python3 tests/portable_smoke.py --bin-dir build/portable/bin
```

The source packages are pinned to Ubuntu's QtBase `5.15.13+dfsg-1ubuntu1`,
QtSvg `5.15.13-1`, and QtWebKit `5.212.0~alpha4-36`. Distribution patches are
applied by `dpkg-source`. These are standard Qt5 APIs, without the old
wkhtmltopdf patched-Qt extensions. Qt5 internally still builds with qmake;
this application's build and QtWebKit use CMake.

The toolchain also copies installed Ubuntu static archives for ICU, JPEG,
libxml2, WebP, SharpYUV, SQLite and Hyphen. Their **exact matching sources** are
downloaded using dpkg's source-package/version metadata, verified against .dsc
SHA-256 checksums, and retained for distribution. Their package versions are
recorded along with all builder packages. Missing or corrupt sources stop the
build or packaging. The SDK belongs to this builder and should not be moved;
only the final executable package is intended to be portable.

The offscreen platform and JPEG/GIF/ICO/SVG plugins are explicitly registered
in the final executables. PNG support is built into QtGui. PDF printing is
enabled. WebKit2/QML, audio/video, geolocation, device orientation, OpenGL,
X11, inspector UI and XSLT are disabled in this render-only toolchain. HTML,
CSS, JavaScript, network loading, image decoding, WOFF/WOFF2 fonts and paginated
PDF output remain enabled. In particular **do not disable WebKit print support**.

QtWebKit's static configuration is not supported upstream; this repository
qualifies its chosen configuration with builds and regression/deployment tests.
The engine remains the existing old QtWebKit baseline, not a browser-engine
security upgrade. See the [upstream static build notes](https://github.com/qtwebkit/qtwebkit/wiki/Building-static-libraries).

## Release and license materials

Keep the project's LGPL-3.0-or-later license. The third-party components retain
their own licenses. A commercial Qt license is not selected by these scripts
and would not remove the obligations of wkhtmltopdf or other dependencies.

After committing the application and build-script changes:

```sh
python3 tools/portable/package.py --work "$PWD/static-build"
```

Publish all three matching files from `build/packages/` together:

- `wkhtmltox-linux-x86_64-<commit>.tar.xz`: two executables, complete component
  notices, LGPL/GPL texts, dependency list, builder package versions and guide.
- `wkhtmltox-linux-x86_64-<commit>-sources.tar.xz`: application source at that
  commit, exact dependency source archives/patches, expanded source trees as
  built (including local changes), source versions and build scripts.
- `wkhtmltox-linux-x86_64-<commit>.sha256`: checksums for both archives.

The C API test executable, Qt SDK and compiler objects are not in the
binary package. Complete application source is supplied for rebuilding and
relinking with modified libraries. Never distribute only a binary with links
to someone else's upstream source hosting in place of its matching source
archive. Do not restrict debugging/relinking or running modified executables.
See [the distribution notice](../THIRD_PARTY_NOTICES.md) for the license policy.

## Rebuild or modify the delivered sources

Extract the matching source archive on Ubuntu 24.04 x86_64. Its `application/`
directory contains the build scripts. Copy `dependencies/` to
`application/static-build/sources/`, preserving the expanded package trees and
`.wkhtmltox-extracted` stamps. Source fetching reuses verified local archives,
so retained packages need not be fetched again. Install the build prerequisites
and the versions listed in `build-packages.tsv` (Ubuntu snapshots may be needed
for old versions). Build using the commands above.

For a modified Qt or WebKit, edit its expanded directory before the build.
For modified static system dependencies, rebuild their delivered Ubuntu source
package using `debian/rules`/`dpkg-buildpackage`, install the resulting development
package on the builder, then rebuild the toolchain. Their original packaging
records how the static archives were compiled. Using a new work directory avoids
mixing stale configuration with a changed compiler or dependency version.
No proprietary application objects or authorization keys are needed to replace
and run the resulting programs.

## Qualification

`.github/workflows/portable.yml` builds on Ubuntu 24.04, runs all existing C API
and CLI regressions, relocates just the executables, then runs them in a clean
Debian 13 container. The runtime job installs only the base libraries/fonts and
test tools, explicitly rejects installed Qt/WebKit packages, audits ELF
dependencies and checks PDF pagination, CJK text, JPEG/SVG input, PNG/JPEG/SVG
output, localhost DNS/HTTPS, and HTTP cookies/authentication/JavaScript. Docker
is used only by CI for isolation; it is not a deployment requirement.
