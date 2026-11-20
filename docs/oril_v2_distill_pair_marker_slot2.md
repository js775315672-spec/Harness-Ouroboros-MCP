# ORIL v2.0 slot 2 — pair completion marker for distilled examples

Baseline: `main=8fbecb5e813b653213d6c8d95ce7151868779512`. Stacked on Draft PR #283 (`cc8e857308c6e19cc18d09c64919e66ff9b7522e`), which already handles failed second output open. Do not duplicate #274–#283.

## Failure hypothesis
A downstream student trainer might ingest an orphan or partially written `train.jsonl` if the compiler fails while creating or writing the second report. An output pair is not automatically atomic. **A separate, exclusive completion marker** provides a fail-closed consumption contract.

## Producer / consumer
After the compiler has exited successfully and closed its files:

```bash
python3 scripts/oril_v2_teacher_distillation_pack.py --input reviewed.jsonl --output-train train.jsonl --output-report report.json
python3 scripts/oril_v2_distill_pair_marker.py publish --train train.jsonl --report report.json --marker pair.commit.json
python3 scripts/oril_v2_distill_pair_marker.py verify --train train.jsonl --report report.json --marker pair.commit.json
```

The downstream trainer **must not consume** a train export until `verify` succeeds immediately before reading it. The marker contains SHA-256 and byte length for both outputs and no private heldout answers. A missing marker, mismatched bytes, changed file, symlink or pre-existing marker fails closed. Marker creation is exclusive, owner-only. The marker itself is not a signature or independent trust anchor.

## Acceptance
- 15 synthetic subprocess/unit cases including missing marker, missing report, changed train/report, malformed marker, duplicate JSON keys, symlinks, exclusive output, owner permissions, CLI and positive pair
- Existing #274–#283 tests remain green at exact stacked SHA, skip=0
- No changes to protected verifier, approval gate, deployments or model weights
- No GPU, adapter, token or heldout performance claim from these tests

## Limits and next falsifiable experiment
This is a **cooperative local producer/consumer contract**, not a cryptographically authenticated provenance statement or a fully atomic two-file transaction. Inode substitution, directory swap, malicious same-user writer and post-verification TOCTOU are not fully solved. Next cycle: hold input file descriptors open through verification and training consumption, test concurrent replacement of marker and train file 1000 times, require no mismatched bytes consumed; independently freeze trusted manifest SHA. Do not accept a synthetic log as GPU proof. Real LoRA requires actual GPU optimizer steps and adapter bytes SHA plus external heldout evaluation.
