# dodge satelite: official Beta listing handoff

Status: prepared, **not submitted or accepted**. The public manual-install
release is separate from acceptance into NINA's official community plugin list.
Acceptance would not make this an application-core or NINA-authored plugin.

## Candidate

- Name (intentional spelling): **dodge satelite**
- Publisher/maintainer candidate: Morio Aoi (`Aoi-Morio`); human acceptance of the
  responsibilities below must be confirmed before submission.
- Plugin version: **0.2.0.0**; minimum NINA: **3.2.0.9001**, Windows x64.
- Stable identity: `ecb4f88d-f91a-4c0a-b7a5-a0eb028a3782`.
- Manifest: `Dodge-Satelite-NINA-0.2.0.manifest.json` in the plugin release assets.
- Channel: **Beta**. Installation ZIP contains two own assemblies, a private
  Qt-free engine and dependency notices. Its final SHA-256 is in the manifest.
- Proposed registry path:
  `manifests/d/dodge satelite/3.2.0.9001/0.2.0.0/manifest.json`.

## Why human confirmation is required

The [official registry policy](https://github.com/isbeorn/nina.plugin.manifests#ai-assisted-development)
says: “every plugin must have an accountable human maintainer.” Submitting a
manifest also confirms actual review, understanding and testing of all code,
including security, privacy, licensing and provenance, and ability to explain,
debug and maintain the implementation. Material AI assistance was used and must
be disclosed. Automated tests and an instruction to publish do not establish
that a human has performed this review. Do not submit until those facts are true.

## Concrete review scope

1. Review `DodgeSatelite.NINA/`: NINA target/site/equipment input, LIGHT-only gate,
   inherited capture pipeline, WPF template, serialization/clone, GUID/metadata.
2. Review `DodgeSatelite.Gate/` and `../src/dodge_satelite/nina_bridge.py`: JSON validation,
   explicit UTC microseconds, request IDs, timeout/cancellation, process limits,
   full-exposure window fit, stale-data rejection and cache/context reuse.
3. Review the shared `../src/dodge_satelite/` engine, especially prediction/sunlight,
   cache freshness/throttling/lock recovery, configuration and geometric limits.
4. Review build scripts, CI, MIT/dependency notices and bundled license files.
   Only CelesTrak group requests leave the machine; site/target/images are not
   uploaded. EnginePath permits the user to select a local executable.
5. Run the documented tests and package. Test installation and complete NINA
   UI operation with a simulator before any live equipment; validate saved
   sequences, normal capture/save, cancellation, stale-data failure and removal.
   Record what was actually tested, and any untested hardware or on-sky limits.

The current automated evidence is in [VALIDATION.md](VALIDATION.md). It does not
claim a completed human review, full GUI/hardware validation or measured accuracy.

## Submission after review

1. Confirm the human maintainer and the completed review/tests above. If changes
   are needed, publish a new tested package and regenerate its manifest/checksum.
2. Recheck the latest official contribution policy. Fork the official registry;
   add only the final manifest at the candidate path. Validate against the current
   upstream `manifest.schema.json` and verify the public installer checksum.
3. Submit a PR titled `Add dodge satelite 0.2.0.0 (Beta)`. Disclose substantial AI
   assistance, link the exact source/release/CI evidence, accurately report the
   human maintainer's actual review/test work, and retain experimental limits.
   Do not fabricate attestations or imply listing before the PR is accepted.
4. Respond to maintainers' review. Only after acceptance verify the actual Beta
   feed entry and installation through NINA's plugin manager, then update status.
