# Contributing

Use Python 3.12+, install `.[dev]`, run pytest and Ruff before proposing a change.
Keep tests offline and deterministic; live service checks belong in an explicit
manual validation run. Preserve source/epoch/coverage warnings and never label
predicted exposure windows as guaranteed clear. Changes to geometry need numerical
and edge-case evidence; changes to precision claims need independent measurements.

Bug reports should include the version, sanitized JSON profile, catalog hash and
epochs, error text, expected behavior and a minimal reproducible example. Do not
include private observing locations or credentials without intending to share them.

Report issues at https://github.com/Aoi-Morio/dodge-satelite/issues.
Follow the release checklist before uploading binaries.
