# ORIL v2.0 slot 2/5 — pretrained Qwen paired prompt diagnostic

## Baseline and collision avoidance

main: `8fbecb5e813b653213d6c8d95ce7151868779512`. PR #313 (actual pretrained Qwen2.5 0.5B CPU, Actions #44831770472) established real checkpoint execution, but only two smoke prompts. PR #314 (Actions #44832970981) added explicit attention masks and 18 mocked offline tests. PR #311 audits timing noise; PR #312 audits Actions runtime. This experiment builds on #314 and does not alter any protected verifier, approval gate or deployment.

## What this adds

Run the *same actual pretrained model* with four **public** arithmetic questions. For each question, compare a verbose system instruction and a short compact system instruction; alternate execution order (2 verbose-first, 2 compact-first). Measure actual tokenizer input tokens, output tokens, elapsed generation time, and public exact answer match, retaining raw per-pair data, model resolved revision and safetensors SHA256. All-ones explicit attention mask inherited from PR #314.

This is **not knowledge-distilled weights**, a secret heldout evaluation, or a statistical performance claim. Four public examples are deliberately too few for an accuracy noninferiority claim; measured speed is confounded by CPU noise and caching. No inference outcome can be counted as LoRA or independent intelligence improvement. All report gain flags must remain false/null.

## Reproduction and acceptance

```bash
python3 -m unittest discover -s tests -p 'test_oril_v2_slot2_pretrained_paired_diagnostic.py' -v
python3 scripts/oril_v2_slot2_pretrained_paired_diagnostic.py --output pretrained_paired_diagnostic.json
```

Requires `torch==2.5.1` CPU, `transformers==4.46.3`, `huggingface_hub==0.26.5`, `safetensors==0.4.5`, and public Hugging Face model download. Independent GitHub-hosted runner must produce 4 complete pairs/8 model calls, exact 40-hex model revision, actual weight bytes and SHA, 15/15 new protocol tests, and 18/18 inherited proof+mask tests. On any failure, report **개선 없음** and the specific failing step, never infer success.

## P0–P6 next handoff

- P0 freeze real model revision and record evidence SHA.
- P1 obtain independently verified, non-sensitive teacher examples with provenance and disjoint task groups; never put private heldout answers in public artifacts.
- P2 compare real tokenizer token counts and elapsed CPU times against verbose/compact prompts; retain every observation.
- P3 reject if missing mask, nonfinite latency, zero generated tokens or mismatched order.
- P4 do **not** claim GPU LoRA: no GPU optimizer steps or adapter produced here.
- P5 future separately frozen hidden evaluation, >=30 independent task groups and paired noninferiority analysis; no hidden eval artifacts in this public repository.
- P6 no merge, model promotion or deployment without explicit approval.

### Falsifiable next hypothesis

On >=30 independent heldout tasks with independently verified model execution, compact teacher context may reduce **actual** input token count by >=20% without heldout correctness lower confidence bound worse than -2 percentage points. If no approved heldout exists, stop at public descriptive CPU diagnostics and mark **판단불가**. Compare same model, exact checkpoint SHA, prompts, fixed seeds, and balanced order. Actual GPU LoRA requires logged GPU steps and real adapter bytes/hash and separate independent evaluation.

### Time and quality measurement

This new workflow should record Actions job start/completion and local inference durations. Do not treat CI duration as inference duration. Compare only like-for-like runs; n=1 cannot establish speed trends. Report unknown metrics as 미측정.
