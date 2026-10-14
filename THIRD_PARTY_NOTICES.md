# Third-party notices

DodgeSatelite's original source is MIT licensed. That does not replace dependency
licenses or CelesTrak's data terms. This project is not affiliated with those projects.

| Component | Upstream |
|---|---|
| Python | https://www.python.org/ |
| NumPy | https://numpy.org/ |
| Skyfield / JPL ephemeris reader | https://rhodesmill.org/skyfield/ / https://github.com/brandon-rhodes/python-jplephem |
| SGP4 | https://github.com/brandon-rhodes/python-sgp4 |
| Astropy / PyERFA / IERS data | https://www.astropy.org/ |
| PySide6 / Shiboken6 / Qt | https://doc.qt.io/qtforpython-6/ |
| PyInstaller bootloader | https://pyinstaller.org/ |

The Windows build places license/notice files from installed distributions in
`LICENSES/`, including embedded dependency notices supplied by NumPy, Astropy and
Qt. `installed-dependencies.json` records versions and upstream links. The manifest
also lists build/test dependencies, some of which are not in the executable.

Qt for Python and Qt offer LGPL/GPL/commercial licensing choices; this open-source
distribution uses the applicable LGPL terms for Qt Core, GUI, Widgets, Network,
OpenGL, SVG and image-format plugins. Unused PDF, QML, Quick and virtual-keyboard
libraries/plugins are excluded from the Windows package. See the complete texts shipped in `LICENSES/`, the
[Qt licensing overview](https://doc.qt.io/qt-6/licensing.html), and
[Qt for Python third-party notices](https://doc.qt.io/qtforpython-6/licenses.html).
Qt and its component authors retain all their copyright notices.

Qt DLLs and PySide6 libraries are kept as replaceable files in `_internal`, not
statically linked. Recipients may modify/replace LGPL libraries and reverse
engineer the combined work to debug those modifications under the applicable
license terms. DodgeSatelite adds no restriction on those rights. Rebuild this MIT
source with a compatible alternative PySide6 installation if ABI changes require it.

Matching Qt/PySide sources are available from
https://download.qt.io/official_releases/QtForPython/ and
https://download.qt.io/official_releases/qt/ (older versions: the corresponding
`archive` directories). The release maintainer must preserve the exact versions,
license notices, source availability and relinking/replacement rights when
redistributing. Do not strip `LICENSES`, this notice, or the runtime libraries from
the bundle. The release checklist includes checking these artifacts.

The v0.1.0 GitHub Release provides a `Qt-6.12.0-corresponding-sources.zip`
alongside the executable, containing the unmodified official PySide/Shiboken,
qtbase, qtsvg and qtimageformats source archives, upstream URLs and SHA-256 hashes.
Rebuild instructions are in those archives and in this project's Windows build
script. Replace interface-compatible DLLs in `_internal`, or rebuild DodgeSatelite
from source with your chosen compatible PySide6/Qt libraries. There is no signature
or activation check preventing those replacements.

The supplied orbital CSV is explicitly synthetic, authored for this project.
No downloaded live CelesTrak catalog is bundled in the source or Windows release.
