# Open source notices

wkhtmltopdf-lite (wkhtmltopdf, wkhtmltoimage and libwkhtmltox) is distributed
under **LGPL-3.0-or-later**, as stated in its source file headers. Copyright
2010–2020 wkhtmltopdf authors and subsequent contributors. The existing
copyrights and license terms are retained. See `LICENSE` and `COPYING.GPLv3`.

Portable Linux binaries contain statically linked Qt5 and QtWebKit. Their
copyrights and individual file licenses still apply; this document does not
relicense those components. The build also incorporates third-party code,
including ICU, libjpeg-turbo, libxml2, WebP, SQLite and Qt/WebKit's bundled
components. Exact versions and complete notices are recorded in the release's
`licenses/` and `source-packages.txt`, and in the matching source package.

The open source licensing route is used for Qt Core, Gui, Widgets, Network,
PrintSupport, Svg and the included platform/image plugins. QtWebKit contains
LGPL and BSD-licensed code, among other notices. Build tools and tests can have
different licenses from the libraries linked into the delivered executables.
Refer to the original license headers and the source-package `debian/copyright`
files included with the matching source archive for component-level terms.

## Distribution and rebuilding

Distribute the binary archive **together with its matching source archive** on
the same download page. The source archive contains this application's source,
the exact Qt/WebKit source packages including distribution patches, the sources
of the system archives linked statically, build scripts, package versions and
checksums. Do not substitute links to third-party upstream servers for these
copies. Preserve them for as long as these binaries are distributed.

Users may modify the libraries and rebuild/relink these command-line programs.
Full application source is supplied as the Corresponding Application Code;
there is no proprietary object-only application in this release. Follow
`docs/portable-linux.md` to rebuild the toolchain and executables, including with
modified dependency sources. Do not impose restrictions on debugging changes,
reverse engineering for that purpose, replacing the executables, or running
rebuilt versions. No activation, signing service or installation key is needed.

System shared libraries, fonts, font configuration and CA certificates are
provided by the target distribution, rather than copied into the binary archive.
Keep their licenses when redistributing those items separately.

These packaging instructions implement the project's open source distribution
policy. The individual license texts govern; downstream distributors must also
meet the terms applicable to their own additions and distribution method.

References: https://www.gnu.org/licenses/lgpl-3.0.html and
https://www.qt.io/development/open-source-lgpl-obligations.
