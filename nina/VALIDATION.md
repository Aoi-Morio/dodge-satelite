# NINA validation record

Target: official stable NINA 3.2.0.9001, .NET 8, Windows x64. The installed NINA
version and its .NET 8 runtime configuration were verified. Build references use
the matching official `NINA.Plugin` 3.2.0.9001 NuGet package.

Local Windows checks passed: 64 Python tests, 22 C# gate tests and 18 NINA SDK
tests. The packaged executable also passed its offline synthetic smoke test.
The public [NINA build workflow](https://github.com/Aoi-Morio/dodge-satelite/actions/workflows/nina.yml)
repeats these tests and builds the release package from its recorded source commit.

- Python bridge regression tests: protocol errors, UTF-8, size limits, epoch and
  download-age rejection, blocked intervals and original engine regressions.
- C# gate tests: full-exposure/guard fit, malformed and stale responses, context
  changes, cache reuse, timeout and cancellation of child processes.
  Actual C# to Python prediction/JSON round trip includes sub-microsecond .NET
  clock values; timestamps use shared microsecond precision. Maximum wait also
  cancels an in-progress engine query.
- NINA SDK tests: MEF discovery, manifest metadata, compiled WPF resource loading,
  independent cloning and automatic bundled-engine path.
  The compiled settings template is instantiated and the standard exposure
  template selector is checked against NINA's implicit DataTemplateKey convention.
  Site coordinates, RA degrees and physical sensor size are checked against a
  mocked NINA target/profile/camera, including binned capture settings.
- Frozen engine: offline synthetic request over actual stdin/stdout; no Qt DLLs.
- Plugin execution boundary tests (12 additional cases): forecast errors,
  no-window timeout and cancellation never request capture/save/history; valid
  windows pass exposure/gain/offset/binning to NINA's standard capture exactly
  once. Capture is intercepted by a mock; successful image processing/saving is
  not exercised by that boundary test. DARK/FLAT or engine-path changes during
  prediction are rejected before capture; target changes trigger a new forecast.
  The same instruction can run again after cancellation. NINA's actual
  SequenceJsonConverter restores the plugin/settings and its parent reference.
- Regression discovered and fixed: 0.1.1 checked LIGHT-only/prerequisites only at
  entry, allowing a changed image type during prediction/wait to reach capture.
  Version 0.1.2 revalidates immediately before handoff and rejects changed engine
  paths. The regression failed before the fix and passed afterward.
- Cache lifecycle: a child process killed while holding the catalog lock is
  followed by a successful fetch; live/legacy lock files are not removed.
- Naming migration: current package/assembly namespaces compile and run; four
  saved-sequence migration cases preserve originals/references/unrelated data,
  allow explicit engine reset, and reject malformed input/overwrites.

No physical camera, mount, roof or other observatory hardware has been operated
by this development/test process. No on-sky false-negative rate, position/timing
accuracy or improvement in usable integration has been measured. Full NINA GUI
operation and a separate clean-machine trial remain distinct from SDK/MEF tests.
These automated checks do not constitute a human maintainer's review or official
NINA plugin-list acceptance.

Known upstream build warnings: the NINA SDK references legacy ToastNotifications
and FreeImage packages that restore with NU1701 compatibility warnings. They are
host-provided references, not shipped as plugin dependencies. Do not treat a clean
plugin compile or its metadata test as proof that every NINA/nightly version works.
