# ORIL v2.0 slot 1 — public A/B+A/A evidence bundle (P0–P6)

## Baseline and non-overlap
Main SHA `8fbecb5e813b653213d6c8d95ce7151868779512`; stacked on slot5 PR #323 SHA `80648a9333a2b0ede930cc3638abc4962f971749`. Slot1 #319 and slot3 #321 own actual Qwen CPU generation; slots 2/4 #320/#322 own independent raw audits; slot5 #323 owns reconciliation. This change does not modify any of them.

## What this closes
The previous reconciler accepts raw JSON paths but leaves the provenance of those files outside its output. The new wrapper binds the two local raw byte SHA256 digests, claimed exact source head SHAs and Actions URLs to the existing independently recomputed public cross-run audit. It rejects symlinks, oversized, duplicate, or identical raw files, and does not overwrite outputs. The supplied run IDs and SHAs are **claims, not API-attested evidence**.

## Run
After **independently** downloading actual raw JSON from source Actions #44841372111 (A/B) and #44843133109 (A/A), and independently retrieving their exact head SHAs:
```bash
python3 scripts/oril_v2_slot1_public_evidence_bundle.py \
  --ab ab-raw.json --aa aa-raw.json \
  --ab-run 44841372111 --aa-run 44843133109 \
  --ab-sha <ACTUAL_40_CHAR_HEAD_SHA> --aa-sha <ACTUAL_40_CHAR_HEAD_SHA> \
  --output public-evidence-bundle.json
```
Run `python3 -m unittest discover -s tests -p test_oril_v2_slot1_public_evidence_bundle.py -v` for offline regressions.

## Evidence gate and falsifiable hypothesis
Hypothesis: A/B and A/A source reports might be inconsistent despite separate successful Actions. Minimal test: retrieve both actual raw artifacts and source-run head SHAs; run the wrapper; verify the resulting digest matches independently computed raw SHA256; compare revision, weights, task digest and prompt tokens. Success is valid public provenance bookkeeping only, **not** causal speed, heldout quality or LoRA training. Failure or inaccessible artifacts = **개선 없음** and do not promote. The next step must implement authenticated Actions metadata retrieval/archived-artifact digest checking, then one-session frozen heldout A/B+A/A (>=30 task groups). Actual GPU LoRA requires CUDA, optimizer steps and adapter SHA. Approval gates and deployment are untouched.

## Handoff
Review PR #323 before merging this stacked branch. Source runs #44841372111 and #44843133109 are referenced, not fetched by this wrapper. Do not mark `source_run_sha_verified_via_github_api` true without an independent API read. CI only runs synthetic adversarial unit tests; no pretrained model inference or model improvement is claimed. No protected verification, approval or production files changed.
