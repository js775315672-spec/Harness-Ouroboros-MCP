# ORIL v2.0 slot 5/5 — independent recomputation of public Qwen diagnostic labels

## Baseline / non-overlap

Main SHA `8fbecb5e813b653213d6c8d95ce7151868779512`. Slot 2 PR #315 (SHA `c2887611`) actually runs 8 pretrained Qwen2.5-0.5B CPU generations over four **public** arithmetic questions and stores per-call `output`, `exact_public_answer_match`, input tokens and elapsed seconds. Slot 3 PR #316 builds a balanced A/B+A/A plan; slot 4 PR #317 checks planned vs observed calls. Neither independently recomputes the **semantic public-answer match** of the #315 report. This change stacks on #315 and adds only that narrow integrity check, without touching #316/#317.

## Problem and falsifiable hypothesis

A generator can emit `"output": "wrong"` while asserting `"exact_public_answer_match": true`. The existing #315 schema validator checks only that the field is boolean, not that it matches the raw text. A false success can pollute later distillation memory and model comparison.

**H1:** Independently recomputing exact matches from immutable public expected digits `5,3,9,4` rejects both false-positive and false-negative labels. 19 tests include mismatched output, order drift, malformed token/timing/weight metadata, and no false GPU/heldout claims. This is an **offline independent arithmetic audit**, not independently authenticated GPU/CPU execution or hidden evaluation.

## How to run

```bash
python3 -m unittest discover -s tests -p 'test_oril_v2_slot5_public_answer_independent_audit.py' -v
python3 scripts/oril_v2_slot2_pretrained_paired_diagnostic.py --output pretrained_pairs.json
python3 scripts/oril_v2_slot5_public_answer_independent_audit.py --input pretrained_pairs.json --output public_answer_audit.json
```

The read-only CI runs the 19 offline tests and, on the same pinned #315 stack, actual pretrained CPU Qwen diagnostic then audits the resulting report. The model run requires network and CPU; do not count it until the exact SHA Actions succeeds and logs the 8 calls. Public-answer recomputation does not validate the truth of the checkpoint hash (it only checks its format), model execution, or answer quality on hidden tasks.

## P0–P6 and next handoff

- **P0:** Pin PR #315 checkpoint revision and input report SHA, preserve the exact Actions URL and run ID.
- **P1:** Keep public arithmetic expected digits separate from teacher-training examples; do not expose private heldout answers.
- **P2:** Recompute exact matches from raw outputs; independently sum tokenizer input/output token counts.
- **P3:** Reject false self-reported match flags, nonfinite timing, wrong order, and missing observations.
- **P4:** LoRA is **not** executed. No GPU optimizer steps, adapter bytes or SHA have been collected; no weight gain claim.
- **P5:** Require 30+ genuinely independent heldout groups and trusted evaluator for accuracy noninferiority. Public n=4 is not sufficient.
- **P6:** Draft only; no auto-merge, approval, deployment or protected gate modifications.

## Decision rule

Passing the offline audit means only **public-label arithmetic integrity** improved. Do not claim accuracy improvement, LoRA training, or speed gain. If CI fails, record `개선 없음` and exact failing run/step, then fix the smallest reproduction. Compare like-for-like CPU Actions runtime only after n>=5 with task type, hardware, model SHA and dependency versions held constant. The next valuable step is independent heldout evaluation with a real pretrained student and genuine teacher-distilled examples, not more synthetic tests.
