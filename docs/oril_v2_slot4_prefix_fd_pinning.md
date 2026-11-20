# ORIL v2.0 slot 4/5 — pinned prompt prefix safety

Baseline: main `8fbecb5e813b653213d6c8d95ce7151868779512`, PR #300 head `fd37d3469b4796775cbc072a393ce5793ebed791`. The prior prompt wrapper checks symlink ancestry using `Path.is_symlink()`, then separately opens the path. This permits a directory rename/symlink swap between the check and open. A FIFO prompt could also block before any model call.

## Change

Use POSIX `openat`-style directory-fd traversal from `/`, `O_NOFOLLOW|O_DIRECTORY` for each ancestor, and `O_NOFOLLOW|O_NONBLOCK` on the final file. Reject non-regular files using `fstat`, then read at most 3001 bytes from the pinned descriptor. Keep SHA-256 and UTF-8 validation unchanged. No protected validator, approvals or deployment modifications. On unsupported platforms fail closed instead of silently falling back.

Seven new tests cover: FIFO early rejection, symlinked parent, deterministic parent swap after ancestor fd open (must read original SAFE), final file swap to symlink (must reject), missing path, wrong hash, and Unicode prefix. Existing 18 synthetic protocol tests must continue passing. These are not actual Qwen or GPU tests.

## Limitations and next hypothesis

- `openat` pins directory objects against *path redirection*, but a hostile process with write permission to the opened regular file can still mutate its bytes during the read. SHA verification against an externally trusted expected digest detects mismatches but cannot prove the operator's expected digest is trustworthy.
- On Windows this reader intentionally fails closed until an equivalent handle-pinned implementation is reviewed.
- No actual Qwen checkpoint or heldout data was supplied. Model accuracy, actual tokens, GPU LoRA optimizer steps, adapter SHA, and quality gains remain **미측정/미입증**.

Next falsifiable experiment: use an approved, actual local Qwen checkpoint and independently frozen heldout set (>=30 task groups) to run same-checkpoint verbose vs compact prompts; capture true tokenizer counts, model load and generation time separately, paired quality/CI and provenance. If missing, report **모델 지능 개선 없음** and prioritize acquiring approved model/data, not more synthetic tests.

Speed reporting: task-level development, model call, independent evaluation and operation timings not yet instrumented; report `판단불가`, not invented rates.
