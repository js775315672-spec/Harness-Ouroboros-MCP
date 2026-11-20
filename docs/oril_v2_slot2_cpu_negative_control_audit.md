# ORIL v2 slot 2/5: independent raw negative-control audit

## Starting point
- main: `8fbecb5e813b653213d6c8d95ce7151868779512`
- upstream PR #309: `3ec661e73aacccd8d9cffc4689e1190b82a5751e`
- PR #309 has 6 balanced same-prompt pairs (12 CPU generations) from a **tiny random-weight Qwen2**, not pretrained model performance.
- Earlier #306–#308 audited other paired reports. This addition audits #309's **same-prompt null control** specifically and never imports the candidate's summary implementation.

## Falsifiable hypothesis
H: An upstream negative-control report can have a valid-looking median while its raw order labels, raw times, or model improvement flags are corrupted. An independent arithmetic reader should reject all of these. Unit tests mutate the median, per-order median, absolute paired noise, counts, order, invalid elapsed time, and unsupported model claims. Acceptance: all new tests pass at the exact SHA, no skipped tests; tampered cases fail closed.

Run:
```bash
python3 -m unittest discover -s tests -p test_oril_v2_cpu_negative_control_independent_audit.py -v
python3 scripts/oril_v2_cpu_negative_control_independent_audit.py --input negative_control.json
```

## Limits and P0–P6 handoff
This is arithmetic verification of a self-reported JSON file, not independent attestation of GPU, actual CPU executions, model checkpoints, quality, or timing improvement. It must never set `speed_gain_verified` or `negative_control_passed` true. P0: freeze runtime and exact checkpoint. P1–P2: keep provenance-verified examples separate from heldout. P3: run #309 actual same-prompt control and independently audit its raw JSON. P4: optional actual GPU LoRA with optimizer steps and adapter bytes/SHA, not synthetic evidence. P5: independent pretrained checkpoint with frozen heldout cases. P6: approval-gated promotion only after quality noninferiority and actual measured token/latency improvement. Do not merge or change protected validation/production gates.

**Next minimal experiment:** read the exact SHA #309 Actions artifact, verify all six raw pairs and compare noise with #307 only after runner/runtime/checkpoint equivalence is established. If not comparable, report `판단불가`. If actual pretrained checkpoint or hidden evaluation is unavailable, explicitly record `모델 개선 없음(미입증)`, do not repeat random-weight smoke tests as intelligence improvement.
