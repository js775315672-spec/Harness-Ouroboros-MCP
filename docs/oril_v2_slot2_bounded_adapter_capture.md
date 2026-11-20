# ORIL v2.0 slot 2/5 — bounded model-adapter subprocess capture

## Starting point
- main: `8fbecb5e813b653213d6c8d95ce7151868779512`
- stack on #293: `d160e62ac731aad67c81c12f112b5a554a5ab976`
- #293 strict JSON rejects ambiguous adapter fields but uses `subprocess.run(..., capture_output=True)`, buffering **all stdout and stderr before checking 200,000 characters**. A malicious or buggy adapter can exhaust memory; the previous post-hoc limit does not prevent that.
- #293 exact-SHA CI: https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44798927087 (success), plus related successful suites. Earlier #293 failed attempts exist and must not be hidden.

## Change
Use `Popen` with nonblocking POSIX selector streaming. Limit **stdout bytes** to 200,000 *during* execution, discard stderr (to avoid uncontrolled buffer), use one monotonic deadline for stdin/write/read/process wait, and terminate the subprocess process group on overflow/timeout. Preserve duplicate JSON/nonfinite rejection and response schema. Enforce request <=64 KiB.

The adapter subprocess and descendants run with current user's permissions; **not a sandbox**. The runner is POSIX-only and does not validate model identity, adapter tokens, GPU usage, training steps, weights or heldout independence. The process-group kill is best effort; subprocesses that escape the group are out of scope. A single giant process can still consume memory outside stdout. No deployment or protected verifier changes.

## Reproducible independent execution
```bash
python3 -m unittest discover -s tests -p test_oril_v2_slot2_bounded_adapter_capture.py -v
python3 -m unittest discover -s tests -p test_oril_v2_student_real_inference_probe.py -v
python3 -m unittest discover -s tests -p test_oril_v2_slot1_adapter_json_integrity.py -v
```

## Next experiment / falsifiable hypothesis
H1: streaming bounded capture rejects 4 MiB stdout before buffering it, within 3 seconds; timeout at 0.2s returns within 2s; normal JSON and existing regressions pass. If any fails, classify **개선 없음** and investigate selector/pipe behavior. Synthetic subprocess tests are **not actual Qwen inference**.

H2: actual student Qwen evaluation is still blocked until approved inference environment and independently frozen heldout dataset are supplied. Once available, run >=30 paired groups with exact model revisions and external tokenizer; require token-savings CI lower bound >=20% and quality-delta CI lower bound >=-2 percentage points. LoRA needs real GPU log, optimizer steps >0, adapter bytes and SHA, and independent evaluation. Until then: `model_quality_gain=unmeasured`.

## P0–P6 handoff
P0 freeze evidence, P1 read strict heldout, P2 preflight output, P3 bound real adapter process, P4 verify returned JSON, P5 independent heldout scoring (not in this PR), P6 human approval only. Compare task-equivalent end-to-end time across >=5 runs; do not infer cycle speed from CI test time alone.
