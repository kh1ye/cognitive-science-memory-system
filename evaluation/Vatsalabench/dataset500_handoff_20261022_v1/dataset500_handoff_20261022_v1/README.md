# Dataset handoff: 500 samples

Date: 2026-10-22. Data-only review handoff, not an experiment-results release.

## Start here

Open REVIEW_STATUS.html in a browser to inspect all 500 samples in original table order, filter by group, and follow package/review links. index.json is the machine-readable inventory. Resolve its relative paths against this folder, not the current working directory. This handoff index is not a replacement for the experiment runner's suite.json schema.

## Contents and review meaning

- reviewed_umrr/: 66 packages with UMRR content-review support.
- pending_umrr/: 434 packages still requiring UMRR semantic review.
- review_records/: archived review findings; locate a sample by its sample_id.
- index.json / review_status.json: current handoff membership and review status.
- provenance.json / checksums.json / VALIDATION.json: origin and integrity checks.

The 66 comprise 34 targeted-context reviews, 29 explicitly scoped text reviews, 2 explicitly scoped utterance reviews and 1 full-history content review. Targeted review uses local lexical scans and relevant-context reading; it is not exhaustive full-history reading. None of these group labels grants independent acceptance or final approval of all eleven metrics. The 434 pending cases are not failures. Both groups contain the current prepared sample packages.

## Inside each package

- suite.json: package entry point and public file hashes.
- samples/<sample_id>/history.json: preserved original dialogue history.
- samples/<sample_id>/probes.json: test questions and checkpoints.
- samples/<sample_id>/branches.json: appended experimental branches.
- samples/<sample_id>/sample.json: sample metadata.
- protocol.json and configuration files: existing experiment specifications.
- private/<sample_id>/gold.json: current scoring labels and evidence, for evaluators only.
- private/**/legacy_reference/: historical provenance only, not current gold.

Never send private gold, review records, answer examples or evaluation evidence to the tested memory system. Keep these outside its retrieval index and prompts. Review records supplement rather than silently overwrite package gold. Existing per-package approval flags are preserved and may remain pending.

## Review workflow for the recipient

Start with pending_umrr in source_order. Check whether the requested unknown detail can actually be determined from the visible history, including indirect references and valid date inference. Do not confuse a suggested item with user adoption or a message timestamp with an event date. Read relevant context around local search hits; expand when ambiguous. Record sample_id, verdict, evidence session/turn, rationale, review scope and proposed corrections. Do not modify original dialogue history. Do not call a lexical no-hit result an exhaustive semantic review.

## Running experiments later

This archive contains datasets and specifications, not Python environments, MemoryBank installation, API keys, model caches, experiment outputs or the runner. The preserved adapter_config.json includes a machine-specific MemoryBank installation path; it must be configured on the recipient's computer before execution, with a new configuration/version and updated public hashes as required by the runner. Do not assume that extracting this archive immediately enables a live run. Do not bypass independent-review gates. Any batch runner should iterate package entries from index.json and use each package's suite.json.

## Preservation

All files in the 500 copied packages are byte-identical to the indexed source packages. Only handoff inventories, review copies, documentation and integrity reports were added. No paid calls were made. The original input workbook and full source JSON are not duplicated; their provenance hashes are retained. The full preserved histories needed for these samples are present in the packages.
