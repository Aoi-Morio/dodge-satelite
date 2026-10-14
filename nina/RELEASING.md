# Publishing the experimental NINA plugin

The standalone desktop release and NINA plugin have separate tags and assets.
For this plugin use `nina-v0.2.0`, plugin assembly version `0.2.0.0` and NINA
minimum version `3.2.0.9001`. Keep the manifest GUID unchanged between releases.

1. Review source, license/provenance notices, documented limits and changes. Run
   the tests in README.md. Do not claim on-sky validation without recorded data.
2. Push the reviewed source commit. Require both the existing test workflow and
   **Build NINA plugin** to pass. The latter builds and smoke-tests a Qt-free
   engine on Windows and uploads the ZIP, SHA-256 file and registry manifest.
3. Download the artifact from that exact commit. Check the SHA-256 against both
   the sidecar file and manifest. Inspect `BUILD-PROVENANCE.json` inside the ZIP:
   `source_commit` must match the tested commit. There must be no NINA SDK/test
   DLLs or Qt runtime; root DLLs are only DodgeSatelite.NINA and DodgeSatelite.Gate.
4. Tag that commit. Create a **prerelease** with the ZIP, sidecar and manifest;
   GitHub's tag source archives contain the complete plugin and engine sources.
   State manual installation, unsigned binaries, target NINA version and the
   untested real-camera/GUI/on-sky limits. Keep the standalone release intact.
5. Verify the public downloads and checksums. Link installation instructions.

## Official registry is a separate step

Material AI assistance was used. Before submitting a manifest PR to the official
Beta channel, an accountable human maintainer must actually review, understand
and test this code and satisfy the registry's
[AI-assisted development policy](https://github.com/isbeorn/nina.plugin.manifests#ai-assisted-development).
Do not assert that automated checks satisfy a human review requirement. Public
manual distribution does not imply NINA endorsement or registry acceptance.
