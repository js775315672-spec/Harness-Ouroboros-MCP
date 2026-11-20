# ORIL v2 slot 3 — Balanced A/B and A/A experiment plan

**Purpose:** eliminate a scheduling gap before real Qwen inference. Prior PR #311 introduces CPU noise diagnostics, but without a fixed balanced execution order, prompt variants can be confounded by model warmup, load, and drift. This tool creates a deterministic **plan only**; it does not infer, fine-tune, access heldout answers, or assert model improvements.

Input is a JSON array containing >=30 independently selected **group identifiers only**. No teacher responses, evaluation answers, personal data, or credentials. Example invocation:

```bash
python3 scripts/oril_v2_balanced_prompt_run_plan.py --groups heldout_group_ids.json --output paired_run_plan.jsonl --seed 20261121
python3 -m unittest discover -s tests -p 'test_oril_v2_balanced_prompt_run_plan.py' -v
```

Each group receives two A/B calls (one verbose A and one distilled B) and two A/A control calls (same verbose A twice), four calls total. A/B order alternates A→B and B→A evenly; A/A block placement alternates to mitigate order effects. Group order is seeded and independent of input order. The CLI prints a SHA256 digest of the plan. For 30 groups, output contains 120 planned calls (60 A/B, 60 A/A). This is **not** 120 completed model calls.

**P0–P6:** P0 freeze actual pretrained Qwen model and tokenizer hashes, hardware, environment and heldout group SHA; P1 independently verify teacher reviews and split provenance (PR #274 and successors); P2 prepare <=16 cases / <=6000 characters and verify actual tokenizer counts; P3 create this immutable plan and measure actual per-call prompt/response tokens, wall latency, model loading latency separately, hardware utilization and exact output; P4 only claim LoRA if GPU execution, positive optimizer steps and adapter bytes/SHA exist; P5 independent evaluator scores unchanged heldout tasks, uses paired group-level confidence intervals and A/A noise; P6 report promote/reject/undetermined and require human approval before protected changes.

**Falsifiable hypothesis:** balanced interleaving will reduce spurious apparent latency advantage from order compared with an unbalanced all-A-then-all-B experiment. Minimal real experiment: >=30 independently heldout groups with fixed checkpoint, 120 calls, per-call raw timing/token records, and predeclared group-level bootstrap intervals. Accept only if heldout correctness CI lower bound >=-2 percentage points and token reduction CI lower bound >=20%, with A/A variability reported. Without those records mark speed and quality **판단불가**.

**Limitations:** alternating order does not eliminate cache effects, task difficulty, thermal drift or time-dependent interference. A/A duplicates can create cache advantages; disable prompt caching or log cache hits. Do not put heldout answers in public logs. No model weights or approval gates modified. Coordinate with PR #311 rather than duplicating its diagnostic implementation.
