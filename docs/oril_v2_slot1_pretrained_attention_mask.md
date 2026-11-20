# ORIL v2 Slot 1/5 — actual pretrained Qwen attention-mask correctness

## Baseline / actual evidence

- main SHA: `8fbecb5e813b653213d6c8d95ce7151868779512`.
- Slot 5 Draft PR #313 head: `d3fcc66ab8964eb93b23a6d71b6f355e2061d0a3`.
- Actual pretrained Qwen2.5-0.5B-Instruct CPU run: https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44831770472, job 136618200051, successful.
- Observed public model revision: `7ae557604adf67be50417f59c2c2f167def9a775`, checkpoint bytes 988097824, generated 16 tokens for each of 2 prompts, elapsed [1.544934, 1.242526] seconds. Those are two smoke samples, **not** latency comparison or model quality evidence.
- Observed warning in original job: *attention mask is not set and cannot be inferred from input because pad token is same as eos token*. This is a correctness/reproducibility issue, not a proven wrong answer.

## Actual change

- Keep single-sample unpadded chat template, construct an all-ones attention mask of identical shape and pass it explicitly as a keyword argument to `model.generate`.
- Fail closed on empty, unbatched, multi-sample or mask-shape mismatch.
- Record `attention_mask_explicit=true` for each inference; reject reports that omit the field. This is a program-generated claim, not independent cryptographic attestation.
- Preserve the existing exact pretrained model revision and weight SHA proof behavior; do not modify protected verifier, approval gate, or deployment.
- Add six offline mocked tests, retaining 12 prior proof tests. The existing pretrained CPU smoke workflow on this stacked PR should also execute real inference on a GitHub runner. It may incur another public model download.

## Falsifiable acceptance

1. Exact SHA independent CI: 18/18 offline tests pass (12 existing + 6 new), no skip.
2. Real pretrained CPU smoke on exact SHA: two generated responses, explicit mask fields, **no 'attention mask is not set' warning** in raw log. If it appears, mark improvement not verified.
3. No claim of quality gain: heldout correctness, actual distilled token savings, GPU LoRA optimizer steps and adapter bytes remain unknown or unproven.
4. Follow-on P0–P6: freeze real Qwen revision and independent heldout tasks, run same prompts with and without condensed teacher examples, compare actual tokenizer token counts and paired correctness. Only with GPU and authorization attempt real LoRA, record adapter SHA, optimizer steps and independent heldout scores.

## Risk

Unpadded single-sample inputs justify all-ones attention mask; do not reuse this shortcut for padded batches. CI and model loading cost may dominate; compare identical run conditions only. The previous unmasked run is not a speed baseline for a quality claim.
