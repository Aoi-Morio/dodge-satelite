# NINA plugin changelog

## 0.2.0.0 — consistent project naming (experimental)

- Use DodgeSatelite namespaces/DLLs and dodge-satelite-engine.exe. Repository,
  Python package, CLI, desktop app, docs and screenshots use the current name.
- Keep the plugin GUID. Saved sequences using previous assembly-qualified type
  references require migration or re-adding this instruction. A copy-only
  `dodge-satelite migrate-nina` command is provided in the desktop/source CLI.
- Keep the capture-handoff fix and all prediction limitations from 0.1.2.

## 0.1.2.0 — capture handoff validation (experimental)

- Revalidate LIGHT-only and NINA prerequisites immediately before capture after
  waiting/prediction. Version 0.1.1 could pass a changed DARK/FLAT setting through
  to the standard exposure pipeline because validation happened only at entry.
- Reject prediction-engine path changes during waiting; restart is required to
  use the replacement engine.
- Add 12 plugin execution/serialization scenarios: failure/no-window/cancellation
  prevent capture; cancellation recovery, retarget/recompute, valid capture
  settings, mid-wait changes and real NINA sequence JSON save/load.
- No change to satellite prediction geometry or accuracy claims. No completed
  human maintainer review or real-camera/full-GUI test is claimed.

## 0.1.1.0 — dodge satelite (experimental)

- Rename the plugin, sequence category/instruction, settings and progress labels
  to **dodge satelite**, as requested by its maintainer.
- Preserve the plugin GUID, managed assembly names and serialized instruction
  types so existing sequences keep their identity.
- Prepare a schema-valid Beta-channel manifest and a human-review handoff for
  official listing. Submission and acceptance are separate from this release.
- No changes to the prediction algorithm or accuracy claims.

## 0.1.0.0 — experimental

- NINA 3.2 Advanced Sequencer instruction with standard NINA LIGHT capture/save.
- Automatic target/site/field inputs, bounded waits, context-aware cache and
  conservative full-exposure checks with an explicit camera handoff guard.
- Epoch/download-age rejection, cancellation, process timeout and default abort.
- Private Qt-free engine, bilingual UI/docs, automated tests, Windows ZIP and manifest.
- Substantial AI-assisted development, disclosed for human review. No on-sky
  accuracy claim and no official plugin-list acceptance claimed.
