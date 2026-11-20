# ORIL v2 slot 3 — verified in-memory consumer for compact distillation

**Start:** main `8fbecb5e813b653213d6c8d95ce7151868779512`, stacked on Draft #284 (`39c7cc87b24597ab072d4dd5fb9fac7c4a639f52`), which implements the producer's train/report completion marker. This follow-up changes only consumer code/tests/docs/CI, not the existing compiler, marker publisher, protected gates, or deployments.

## Distinct failure mode
A consumer that calls `verify(train, report, marker)` and **then reopens `train.jsonl` by pathname** can consume a different file after a rename or symlink swap. A marker alone cannot close this verification-to-use window.

## Contract
Use `consume(train, report, marker)` from `scripts/oril_v2_distill_pinned_consumer.py`. It opens each path with no-follow, snapshots bounded bytes once from a pinned descriptor, validates metadata schema, SHA-256, byte length, report claims and JSONL shape, then returns **immutable training bytes**. Downstream training must consume the returned bytes, not reopen the filename. The CLI prints only hashes and size, not training content.

```bash
python3 scripts/oril_v2_distill_pinned_consumer.py --train train.jsonl --report report.json --marker pair.commit.json
python3 -m unittest discover -s tests -p test_oril_v2_distill_pinned_consumer.py -v
```

### Evidence/limitations
- New tests include deterministic path swap during descriptor-held read, stale same-size digest, changed marker, FIFO, symlink, report false-claim, and immutable byte snapshot after pathname replacement. All fixtures synthetic; no actual teacher review, student inference, GPU training, LoRA adapter, or heldout performance claim.
- This does **not** defend against an attacker changing a file in place *after* snapshot while a trainer later reopens its path; such reopening is forbidden. Same-user malicious writers, compromised parent directories, filesystem-level races, signature-less markers and missing externally frozen provenance remain untrusted.
- Verification of local bytes is not a third-party attestation. Exact tokenizer tokens, latency, GPU training time, adapter SHA, independent quality are **미측정**.

## Next falsifiable experiment
1. Use independently reviewed teacher examples (5–16), freeze dataset SHA and a separate heldout evaluator. Reject invented reviews.
2. Consume immutable bytes through this API and compare fixed Qwen/student baseline vs compact examples on the same heldout cases (>=30 groups preferred); measure actual tokenizer tokens, p50/p95 latency and paired correctness CI. Accept only if savings CI lower bound >=20% and quality change CI lower bound >=-2pp.
3. Stress 1,000 real concurrent path swaps with a consumer that uses returned bytes; require 0 mismatched accepted samples, log actual run times and failure counts.
4. Only claim weight learning with real GPU job logs, optimizer steps>0, adapter file bytes/SHA, and independently frozen heldout evaluation.

**Merge/deploy:** remain Draft, no protected validator or production changes; independent review required. Report '모델 학습 미실행·품질 판단불가' until real evidence exists.
