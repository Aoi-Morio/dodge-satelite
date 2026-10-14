# dodge satelite for N.I.N.A. (experimental)

[日本語](README.ja.md) · [Validation](VALIDATION.md) · [Changelog](CHANGELOG.md)

Adds **dodge satelite: Satellite-aware Exposure** to the Advanced Sequencer in the
current stable **N.I.N.A. 3.2.0.9001, Windows x64**. The instruction checks a
catalog-predicted window before taking **one LIGHT frame through NINA's standard
capture, history and image-save pipeline**. Put it in a normal repeat instruction
set for multiple frames. It uses NINA's active site, target, focal length and
camera dimensions. A private prediction engine is included; Python and a separately
running DodgeSatelite desktop app are not required.

**Experimental. No on-sky accuracy or clean-frame guarantee.** Catalog coverage,
element age, sampling, margins and camera-start latency all limit the result.
Read [the numerical assumptions](../docs/ALGORITHM.md). NINA 3.3/nightly and other
architectures are not claimed compatible.

## Install

Version 0.2.0 uses new assembly/type names. Close NINA and remove the previous
plugin installation before extracting this version; do not mix old and new DLLs.
The plugin GUID is unchanged. Previously saved sequence files may need migration:
Use the desktop CLI bundle (or an installed source environment) for this command:

```powershell
dodge-satelite migrate-nina previous.json --out updated.json --bundled-engine
```

This creates a new JSON file without overwriting the original or executing its
contents. Only instruction type references ending in `.NINA.SatelliteAwareExposure`
are changed. Open and inspect the copy in NINA before use. The optional
`--bundled-engine` resets engine-path overrides to the newly bundled executable.
Alternatively remove and re-add this instruction in the NINA sequence editor.

1. Download `Dodge-Satelite-NINA-0.2.0-windows-x64.zip` from
   [the plugin Release](https://github.com/Aoi-Morio/dodge-satelite/releases/tag/nina-v0.2.0).
2. Close NINA when no observation is running. Open
   `%LOCALAPPDATA%\NINA\Plugins\3.0.0\` and create `dodge satelite`.
   The `3.0.0` folder is NINA 3.2's plugin compatibility folder, not its app version.
3. Extract the **contents** of the ZIP into that folder. `DodgeSatelite.NINA.dll`,
   `DodgeSatelite.Gate.dll` and the `Engine` folder must be alongside each other.
   Avoid an extra nested archive-name folder. Keep all files, notices and libraries.
4. Restart NINA and open the Advanced Sequencer. Find
   **dodge satelite → dodge satelite: Satellite-aware Exposure**.

This beta is available by manual installation. It is **not yet in NINA's official
plugin list**; its manifest is provided for review/submission, not as evidence of
acceptance. Remove only the `dodge satelite` folder while NINA is closed to
uninstall. Existing NINA profiles or other plugins do not need modification.

## Use

- Place the instruction inside a **Deep Sky Object** sequence with fixed stellar
  coordinates. Use the normal exposure-time, gain, offset and binning controls.
  Calibration frames and non-sidereal/moving targets are rejected.
- Connect the imaging camera and enter accurate observatory, focal length and
  unbinned pixel-size information in NINA. The full sensor dimensions are computed
  from pixel counts × pixel size; optional mm overrides are available. ROI/cropping
  and pointing error require care; the model uses the target center and a circular
  enclosure, not a plate-solved detector footprint.
- Default catalog is **visual**, a deliberately small **incomplete subset**.
  It does not cover all Starlink or all active satellites. You may choose `starlink`
  or `active`, but missing/uncatalogued satellites are still not covered.
- First use downloads the chosen CelesTrak group. Further requests honor the
  two-hour cooldown. Cache-only mode requires an existing valid cache. No site,
  target, images or telemetry are sent; only the group query reaches CelesTrak.
- Elements exceeding the configured epoch difference (default 2 days, maximum
  7 days), a download older than 24 hours, propagation failure, missing engine,
  protocol error or timeout **does not authorize a frame**. An old object in a
  large group can therefore stop the entire instruction. Choose a documented
  appropriate group/threshold; the software never silently drops stale satellites.
- When no complete exposure fits, the instruction waits and refreshes forecasts
  for up to the configured wait time (default 10 minutes), then fails. Its default
  NINA error behavior is **Abort on Error**. If you change NINA's error behavior,
  later instructions may continue, but this item still does not take that frame.
- Forecasts are reused for at most two minutes, only for an unchanged target,
  site, field, exposure and prediction settings. The next exposure and handoff
  buffer must fit entirely in an eligible interval. Target/context and time are
  checked again immediately before handing off to NINA. Cancellation kills the
  child prediction process and stops the wait.

Default look-ahead is 5 minutes, sampling 1 second, angular margin 0.1°, transit
padding 3 seconds and camera handoff guard 3 seconds. These are **uncalibrated user
margins**, not error bounds. NINA/camera delays longer than the guard can still
move an exposure into a predicted crossing. No exposure already in progress is
aborted merely because a satellite appears. Do not treat this as a weather/safety
monitor or a replacement for NINA's normal safety, flip and observatory handling.
Waiting increases the sequence duration; consider time/meridian constraints.

## Build and test

Use Windows x64, .NET 8 SDK and Python 3.12+. From the repository root:

```powershell
python -m pip install -e ".[dev]" -c constraints-windows-py312.txt
$env:DODGE_SATELITE_TEST_PYTHON = (Get-Command python).Source
dotnet test nina/DodgeSatelite.Gate.Tests/DodgeSatelite.Gate.Tests.csproj -c Release
dotnet test nina/DodgeSatelite.NINA.Tests/DodgeSatelite.NINA.Tests.csproj -c Release
python -m pytest -q
python scripts/build_nina_plugin.py
```

The output ZIP and SHA-256 are in `dist/`. The packager also creates an
`Dodge-Satelite-NINA-0.2.0.manifest.json` with the final ZIP checksum. It contains only
our two managed assemblies, a Qt-free headless engine and documentation/licenses;
NINA's SDK assemblies and test libraries are **not redistributed**.

The upstream NINA NuGet dependencies currently produce NU1701 warnings for its
legacy ToastNotifications/FreeImage references. Host-facing MEF/resource tests
exercise the real NINA 3.2 SDK; the warnings are not a claim of universal runtime
compatibility. See the recorded verification and remaining limits.

## Official plugin-list submission

The prepared manifest targets the official **Beta** channel. It has not been
submitted or accepted. See [the submission handoff](REGISTRY_SUBMISSION.md).

The [official registry](https://github.com/isbeorn/nina.plugin.manifests) requires
an accountable human maintainer, disclosure of material AI assistance, and human
review/understanding/testing of the implementation. This feature was developed
with substantial AI assistance. Automated tests do not satisfy or impersonate
that human attestation. A maintainer must review the source and validate the
plugin in NINA before submitting the prepared manifest in the Beta channel.

Original plugin/bridge code: MIT. [Dependency notices](THIRD_PARTY_NOTICES.md).
