# dodge satelite 0.2.0

[![Tests and Windows build](https://github.com/Aoi-Morio/dodge-satelite/actions/workflows/ci.yml/badge.svg)](https://github.com/Aoi-Morio/dodge-satelite/actions/workflows/ci.yml)

[日本語](README.ja.md) · [Architecture and limits](docs/ALGORITHM.md) · [Release guide](docs/RELEASING.md)

[GitHub repository](https://github.com/Aoi-Morio/dodge-satelite) · [Releases](https://github.com/Aoi-Morio/dodge-satelite/releases)

A Windows desktop and command-line tool for planning astrophotography exposures around predicted satellite crossings. Enter your observing site, a fixed celestial target and camera/telescope dimensions; inspect the timeline and export a proposed schedule.

**N.I.N.A. users:** the experimental **dodge satelite plugin for NINA 3.2** can wait for a predicted
window before each light exposure in Advanced Sequencer. See the
[plugin installation and usage guide](nina/README.md). It is distributed separately
from the desktop app and is not yet listed in NINA's official plugin manager.

![Desktop demo showing a predicted crossing and exposure timeline](docs/images/desktop.png)

**An experimental planning assistant, with no observation-validated accuracy claim. A green exposure is a proposed time slot, not a guarantee of a clean frame.** Coverage is limited to the satellites in the supplied catalog. Read the warning/data tab and the report exported with every plan.

## Quick start on Windows

[Download the Windows x64 ZIP](https://github.com/Aoi-Morio/dodge-satelite/releases/download/v0.2.0/Dodge-Satelite-0.2.0-windows-x64.zip) from the experimental [v0.2.0 Release](https://github.com/Aoi-Morio/dodge-satelite/releases/tag/v0.2.0).

For a packaged build, extract the **entire** `Dodge-Satelite` folder. Start `Dodge-Satelite-GUI.exe`. Keep `_internal` beside the executable; its replaceable Qt libraries and other runtime files are required. Builds are unsigned. No administrator permissions or Python installation are required for that build.

From source, install Python 3.12 or newer (64-bit; 3.12 is the locally tested version), then in PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m dodge_satelite gui
```

The GUI opens a clearly marked **synthetic historical demo**. Click **Calculate / 計算** to see a crossing and its avoidance. Choose **Export CSV + report / 結果保存** to save results. The demo is not a prediction for tonight. Dates accept ISO 8601 with an explicit offset, e.g. `2026-10-14T21:00:00+09:00` or `2026-10-14T12:00:00Z`. All result times are UTC.

## What is included

- CelesTrak GP/OMM CSV download, validated cache, local CSV and offline cache use.
- Site latitude/longitude/elevation, ICRS target RA/Dec in **degrees**, focal length and sensor dimensions; JSON profile load/save.
- Skyfield/SGP4 topocentric propagation; Astropy built-in solar positions, geometric Earth shadow and solar altitude.
- Conservative field-of-view crossing intervals, timing/angular margins and target/solar altitude constraints.
- A fixed-exposure scheduler, baseline comparison, desktop timeline, CSVs, JSON provenance and SVG timeline.
- A responsive PySide6 worker, progress and cooperative cancellation; Japanese/English labels.
- Offline synthetic sample, tests, a repeatable Windows packaging script and GitHub Actions configuration.

## CLI

With an activated environment use `dodge-satelite`; without activation use `python -m dodge_satelite`. In a packaged build use `dodge-satelite.exe`.

```powershell
dodge-satelite demo --out reports/demo
dodge-satelite fetch --group visual
dodge-satelite plan examples/observation.json --group visual --out reports/tonight
dodge-satelite plan examples/observation.json --group visual --offline --out reports/offline
dodge-satelite plan examples/observation.json --catalog my-satellites.csv --out reports/local
dodge-satelite gui
```

**Edit the date, site, target and equipment in the example before planning a real session.** `visual` and `stations` are incomplete subsets; `stations` mostly tests the space-station workflow. Missing satellites are never implicitly covered. Large catalogs (e.g. `active`) may exceed the v0.1 workload limit; shorten the session or use a purpose-selected local catalog. No automatic filtering silently discards satellites. No name resolver, catalog merging, moving targets, camera control or FITS processing is included.

The options `--cache-dir PATH` and `--offline` are available for CelesTrak sources. Normal exits return 0; invalid data or calculation errors return 2. Propagation failure for any selected satellite aborts the whole plan; partial results are not presented as complete.

## Data freshness and cache behavior

The app sends HTTPS requests only to CelesTrak, on explicit online use. It does not send your site or target, collect telemetry, download planetary kernels or fetch IERS data in the background. Cache defaults to `%LOCALAPPDATA%\DodgeSatelite\cache` on Windows and `~/.cache/DodgeSatelite/cache` otherwise.

- Minimum two hours between requests for the same group, including failed requests. No redirects or automatic retries. Concurrent requests using the same cache/group are locked.
- A successful response is parsed and checked before atomic cache replacement; a SHA-256 validates stored content.
- If a refresh fails, a valid older cache can be used with a prominent **STALE CACHE FALLBACK** warning. Offline use reports an old download age. Download time and element epoch are distinct.
- Each satellite's epoch and maximum absolute epoch distance across the entire session are exported. The default 7-day warning is a **heuristic warning threshold**, not an accuracy guarantee or a validity cutoff. Fresh elements can still be wrong, particularly after maneuvers.
- Local CSV acquisition time is unknown and marked as such. Keep the original CSV for reproducibility. The report stores a hash and epochs, not a full copy of the catalog.
- `catalog_sha256` identifies parsed UTF-8 CSV text; BOM removal and local newline normalization can make it differ from an operating-system hash of the original file.
- A crashed process can leave a `.lock` file. Close all instances before removing that specific lock. A damaged cache/history causes a readable error; do not bypass cooldowns to retry a service error.

See [CelesTrak GP formats](https://celestrak.org/NORAD/documentation/gp-data-formats.php) and [usage policy](https://celestrak.org/usage-policy.php). Data remains subject to its provider's terms; it is not relicensed under this project's MIT license.

## Interpreting a plan

The sensor rectangle is enclosed by a circular cone derived from the sensor diagonal and focal length, then enlarged by the angular margin. This tolerates camera rotation but can block passes outside the actual rectangle. It does not model optical distortion.

Default sampling is 0.5 s. The engine checks line segments between unit direction samples to catch crossings that endpoint-only checks miss, and blocks the whole intersected sample interval plus a default 3 s on each side. This is **not a rigorous bound on trajectory curvature or orbital uncertainty**. Reduce the step and increase margins for demanding use. The angular and time margins have no calibrated confidence level.

Sunlit mode treats penumbra as a risk and excludes full geometric umbra. It does not predict magnitude, reflections or flares. Disable it to avoid crossings in all illumination states. Twilight is independently constrained by maximum solar altitude (default −12°); target altitude defaults to at least 25°. The synthetic demo intentionally uses different thresholds.

The scheduler maximizes the **number of equal-length exposures** under the computed blocked intervals and fixed readout time by placing each exposure at the earliest feasible time. Readout can overlap a blocked interval; exposure cannot. This is not a general optimizer for signal-to-noise, multiple targets, variable exposure times or telescope slews. The baseline uses the same observing constraints but ignores satellites; its predicted-risk count is not an observed contamination count.

Outputs in the chosen folder (existing files with the same names are replaced):

| File | Contents |
|---|---|
| `exposures.csv` | Proposed UTC start/end and duration; explicitly labeled not guaranteed clear |
| `transits.csv` | Satellite ID/name, full sample-cell crossing interval, illumination policy, epoch and padding |
| `blocked.csv` | Conditions and padded satellite-risk intervals, with reasons |
| `report.json` | Input snapshot, warnings, metadata, hash, epochs, baseline and complete results |
| `timeline.svg` | Shareable static timeline with a limitations notice |

Microsecond timestamp formatting preserves input values; it is **not** a claim of microsecond prediction accuracy. CSVs use UTF-8 BOM for Excel. External satellite names are protected against spreadsheet formula interpretation.

## Development and tests

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m build
python scripts/build_windows.py
```

Use `-c constraints-windows-py312.txt` on the install command to reproduce the locally tested Python 3.12 Windows dependency versions. GitHub CI passed on Python 3.12/3.13 on Windows and 3.12 on Ubuntu, and the Windows packaging job passed. GUI tests run with Qt's offscreen platform. The Windows build produces a folder with CLI/GUI executables and licenses, checks CLI demo output and verifies GUI startup. See [validation](docs/VALIDATION.md) for the tested commit, workflow and planned observing experiments.

## License and attribution

Original code and synthetic sample: [MIT](LICENSE). Dependencies retain their licenses. [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) describes Qt/PySide6's LGPL/commercial licensing and the generated third-party license bundle. Skyfield, SGP4, Astropy and their upstream scientific references are credited in [the algorithm notes](docs/ALGORITHM.md). Do not infer affiliation with CelesTrak, Skyfield, Astropy or Qt.

GitHub publication, tagging and release upload are deliberately separate manual steps. No external repository is created or published by building this project.
