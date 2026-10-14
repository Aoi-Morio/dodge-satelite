# Validation record / 検証記録

Date: 2026-10-14 (Asia/Tokyo). Local Windows 11 x64, Python 3.12.10.
This is a software validation record, not measured astronomical accuracy.

## Verified locally

- Automated tests: 46 passed (pytest, 6.86 s for the recorded full run).
- GUI tests: offline demo calculation on a worker, results/timeline/table display,
  export, input-change invalidation, bad-file recovery and profile round trip.
- Numerical checks: RA wrap/poles/stationary directions, crossing between samples,
  geometric sunlight/umbra/penumbra, dense 0.01 s synthetic reference and 0.1 s
  versus 0.5 s step comparison for one synthetic pass.
- Solar altitude agrees with an Astropy AltAz comparison within the test's 0.03°
  tolerance for the demo endpoints. This is an implementation consistency check,
  not a real-world error bound.
- Scheduler: 100 deterministic randomized small integer cases agree with exhaustive
  maximum-count search; intervals, readout gaps and boundaries are tested.
- Cache: hit/offline behavior, HTTP failure fallback, cooldown, malformed responses,
  checksum corruption, missing cache, duplicate IDs, nine-digit IDs and lock tested.
- CLI: end-to-end offline sample, malformed profile failure, CSV and provenance output.
- Real CelesTrak `stations` request succeeded: 21 records acquired at
  `2026-10-13T22:29:30.075Z` (2026-10-14 07:29 JST), then reused offline.
- Real-data calculation for the example's one-hour Tokyo/M31 session completed in
  1.66 s on this machine, with 0 predicted crossings and 58 proposed exposures.
  This is only 21 catalog entries; it does not establish complete satellite coverage.
- Synthetic demo: one crossing, 18 exposures, one of 18 baseline exposures at
  predicted risk; 0.21 s for the recorded in-process call. Timing varies by machine
  and initialization state and is not a throughput guarantee.

## Packaging status

The source distribution/wheel and Windows CLI/GUI bundle are built locally.

- Frozen CLI version command: passed, reports `0.1.0`.
- Frozen offline demo: passed, one crossing and 18 proposed exposures.
- Frozen GUI startup with Qt's offscreen platform: passed.
- ZIP integrity check: passed. The entire bundle was extracted to a different
  directory on this computer, and its CLI demo again produced one crossing and
  18 exposures.
- Relocated GUI startup using the native Windows platform plugin: passed.
- The bundle includes the original license, dependency notices, installed
  dependency manifest, LGPLv3 and GPLv3 texts. No live catalog is bundled.

These are checks on this developer computer. They do not replace the separate
clean-machine test listed below. The build script creates a ZIP only after its
CLI and offscreen GUI checks pass; a SHA-256 file accompanies each archive.

## Not yet verified

- Measured trail timing/position, false-negative rate, brightness, maneuver error
  and real improvements in usable integration time.
- A separate clean Windows machine without a Python installation.
- Execution on macOS, Windows ARM64, Python 3.14 or every allowed dependency
  version. Windows x64/Python 3.12 is the local target; other CI targets are below.
- Full active-catalog performance across a whole night or every edge geometry.

## GitHub validation

The current [Windows/cross-platform workflow](https://github.com/Aoi-Morio/dodge-satelite/actions/workflows/ci.yml)
and [NINA workflow](https://github.com/Aoi-Morio/dodge-satelite/actions/workflows/nina.yml)
repeat checks and build the release from its recorded source commit. Historical
development checks above are not measurements of astronomical accuracy.

## Fixes found during validation

- SGP4's Alpha-5 identifier encoder rejected the nine-digit synthetic catalog ID;
  full GP IDs are now preserved separately from the propagation identifier.
- Profile serialization originally truncated microseconds; it now round-trips
  full Python datetime precision without implying that prediction accuracy.
- A test used the Windows locale codec for a UTF-8 SVG; explicit UTF-8 is now used.
- Astropy 8 packaging scanned unused visualization imports that raised pytest's
  `Skipped` exception. A project hook excludes visualization while retaining the
  test-runner module needed by Astropy's normal initialization.
- An unrelated Poppler directory on the host PATH caused PyInstaller to collect
  an incompatible `icuuc.dll`. The Windows build now limits its child process's
  PATH to Python and Windows directories, preventing that DLL contamination.

日本語: 上記は実装・配布物の動作確認です。実写での精度・見逃し率は未測定です。
サンプルの検出成功、ゼロ通過、テスト成功を実観測の精度保証に読み替えないでください。
