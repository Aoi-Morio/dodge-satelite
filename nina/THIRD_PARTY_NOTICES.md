# NINA plugin dependency notices

The original C# plugin, gate and Python bridge are MIT licensed (root `LICENSE`).
No upstream NINA implementation or template source is copied into this plugin;
it subclasses the published NINA 3.2 API and calls the stock exposure pipeline.

NINA is MPL-2.0 licensed. Its SDK is a build reference and its host libraries are
provided by the user's NINA installation; NINA, ASCOM and test-framework assemblies
are not redistributed in the plugin ZIP.

The private headless engine redistributes Python, NumPy, Skyfield, SGP4, Astropy
and their runtime dependencies. Those components retain their upstream licenses
and notices, collected under `LICENSES/` together with a dependency/version list.
PyInstaller's bootloader carries its upstream distribution exception; its license
is also included. NumPy's wheel notices cover its bundled numerical libraries.

The NINA engine excludes Qt/PySide6 and does not link to or ship Qt DLLs. The
standalone DodgeSatelite desktop app has its own separate Qt-related notices.

Primary upstreams:
- https://github.com/isbeorn/nina (NINA 3.2 tag `Version-3.2`)
- https://numpy.org/
- https://rhodesmill.org/skyfield/
- https://github.com/brandon-rhodes/python-sgp4
- https://www.astropy.org/
- https://pyinstaller.org/

CelesTrak data remains subject to its provider's usage policy. No live catalog is
bundled. The included synthetic historical sample is original project data.
