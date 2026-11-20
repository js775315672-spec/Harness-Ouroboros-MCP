# ORIL v2.0 — slot 5/5 local Qwen config preflight

## Baseline and isolation

Main SHA `8fbecb5e813b653213d6c8d95ce7151868779512`. Stacked on slot 4 PR #296 SHA `46aa4daa6fc9324baf44f8a8a5386a3bdba3de64`, itself stacked on #295. Other slots #293/#294 work on adapter protocol/output bounds; this change modifies only Qwen local checkpoint config preflight.

Slot 4 independently verified its final SHA in Actions #44803238563 and #44803238444; earlier candidate SHA `e68482e...` failed and was repaired. These CI runs are **synthetic** and not real Qwen inference.

## Problem / falsifiable hypothesis

A local model checkpoint with a normal directory and non-symlinked `config.json` was accepted even if config contents were invalid JSON, ambiguous duplicate keys, nonfinite numbers, or unbounded size. The program would then import expensive ML dependencies before the loader failed. This wastes work and obscures the failure. A bounded JSON preflight should reject these inputs before importing torch.

## Change

`ensure_local_model` reads at most 1 MiB + 1 byte of `config.json`, rejects oversized content, invalid UTF-8/JSON, duplicate JSON object keys and NaN/Infinity, and requires a JSON object. It does not assert model architecture correctness or verify weight files, external trust anchors or any GPU work.

10 synthetic regression tests cover normal config, malformed/ambiguous inputs, 1 MiB boundary and fail-before-import. CI runs all 3 local-Qwen suites in a GitHub-hosted runner.

## Next falsifiable cycle

- If final SHA tests pass: checkpoint metadata rejection coverage improved. **No model intelligence improvement** is implied.
- If tests fail: capture failing case, minimize input and amend this PR before any promotion.
- Next priority: actual local Qwen checkpoint + paired frozen heldout tasks with independently pinned provenance. Record exact model checkpoint digest, tokenizer identity, actual token counts, latency and task-level paired accuracy. If no GPU/model artifacts are available, state **개선 없음 (모델 학습 미입증)**.
- LoRA is separate: require GPU run/job ID, optimizer steps >0, actual adapter file bytes/size/SHA, independent heldout score and approval. A synthetic filesystem or CI test does not satisfy this gate.
- No changes to protected validators, deployment or user approval gates.

## Measurement contract

Report actual cycle start/end, model execution time, independent verification, operational follow-up, failure/retry/rollback and comparable last 5–12 cycle median with n and SHA/Actions URL. Missing fields must be **미측정**. Do not compare a new metadata preflight test to an unrelated GPU evaluation as though task difficulty matched.
