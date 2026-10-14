# dodge satelite v0.2.0

First experimental release of a Windows satellite-aware astrophotography planner.

Includes a PySide6 desktop UI and CLI, CelesTrak GP CSV cache, geometric crossing
and illumination checks, equal-exposure scheduling, timeline/CSV/JSON exports,
and an offline synthetic demonstration. Documentation is available in English
and Japanese. Original project code is MIT licensed.

## Windows / 起動方法

Download `Dodge-Satelite-0.2.0-windows-x64.zip`, extract the entire folder,
and open `Dodge-Satelite-GUI.exe`. Keep `_internal` beside it. Python is not required.
Start with the bundled synthetic historical demo, then enter your own site,
target, equipment and session dates. All output times are UTC.

Windows版ZIPをフォルダー全体が残るように展開し、`Dodge-Satelite-GUI.exe` を開いてください。
最初は架空の過去データによるサンプルです。実際の観測には入力と衛星データを変更してください。

## Validation and sources

The current [Windows/cross-platform workflow](https://github.com/Aoi-Morio/dodge-satelite/actions/workflows/ci.yml)
and [NINA workflow](https://github.com/Aoi-Morio/dodge-satelite/actions/workflows/nina.yml)
record tests and build results for the published source commit. Inspect the
workflow result and packaged provenance rather than assuming accuracy from a build.

Assets include the Windows application, DodgeSatelite source, SHA-256 checksums and
unmodified corresponding Qt/PySide/Shiboken source archives with upstream hashes.
Qt libraries remain replaceable and dependency licenses/notices are included.

Limitations: selected-catalog coverage only; no measured on-sky accuracy claim;
sampled trajectories and user margins are not confidence bounds; no magnitude,
weather, camera control, moving targets or FITS processing. The Windows folder
must be extracted in full. Executables are unsigned.

日本語: 人工衛星の通過を考慮した天体撮影計画を作る最初の実験版です。
GUI・CLI・オフラインサンプルを収録しています。写り込み回避や予測精度は保証せず、
実写での精度検証は今後行います。
