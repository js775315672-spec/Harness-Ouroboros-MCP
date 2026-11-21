# ORIL v2 슬롯 5 — 원본 공개 Qwen A/B+A/A 아티팩트 독립 취득 감사 (2026-11-21 11:49 KST)

## 기준선 및 출처
- main: `8fbecb5e813b653213d6c8d95ce7151868779512` (GitHub commit search)
- A/B: [Actions #44841372111](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44841372111), HEAD `e9322a40c47826d02b816feece9241b8b3c0a933`, artifact ID `14680858021`, name `slot1-pretrained-public-30-pairs`, ZIP SHA256 `189a686cc088b807568bc2789e36f4689d73fc194f857037636d58b136f1b6bc`, JSON `public_30_pairs.json` SHA256 `99376656a4c4a7df737d54d9da36f9743b4ede02bc73d54461c379db69860a09`.
- A/A: [Actions #44843133109](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44843133109), HEAD `7cc6d2b61531507ce6db2ea1310577b7429da1c4`, artifact ID `14682535046`, name `slot3-pretrained-public30-aa-null`, ZIP SHA256 `bde62ab49085bd49be1b284da02d843dcc88e0b4f35d32e20b8abca8d496628c`, JSON `public30_pretrained_aa.json` SHA256 `998919940b881646236a48646d81b2a4408c700869545288dcfb5524a4c414d3`.
- GitHub Actions artifact API digest and downloaded ZIP SHA256 agree for **both** artifacts. Downloaded and inspected ZIP contents, not merely PR prose.
- Both report model `Qwen/Qwen2.5-0.5B-Instruct`, revision `7ae557604adf67be50417f59c2c2f167def9a775`, checkpoint filename `model.safetensors`, declared size 988097824 bytes and declared SHA256 `fdf756fa7fcbe7404d5c60e26bff1a0c8b8aa1f72ced49e7dd0210fe288fb7fe`; public task SHA256 `da01e3d2e6d4d484f9dfa166e298e22d29979d5360bb93ce93510e8f18101cdd`. **Checkpoint bytes were not independently downloaded**, so model identity is still self-reported within artifacts.

## Independently recalculated from 30 rows per artifact
- A/B: 30 public arithmetic groups, 60 reported calls. Verbose exact output matches **11/30**, compact **20/30**. Exact-match flags agree with literal `output.strip() == expected` for all 60 observations.
- A/B input tokens verbose **1860**, compact **1020**, descriptive reduction **45.161%**. Per-variant median observed elapsed: verbose **0.635185 s**, compact **0.5127275 s**.
- A/A: 30 public groups, 60 reported calls, each repetition **20/30** exact matches, input tokens **1020** per repetition. Median per-call elapsed **0.5510885 s**; per-repetition medians **0.5538385 s** and **0.542145 s**. Exact-match flags agree with outputs for all 60 observations.
- This is **120 reported model calls inspected**, not 120 independently witnessed model invocations. Independent download/hash/row arithmetic verifies report integrity and consistency, **not** the runner's actual model execution, model weight provenance, held-out generalization, or causal latency gains.

## Fail-closed verdict and next experiment
**PUBLIC_ARTIFACT_INTEGRITY_RECONCILED; NO_DEMONSTRATED_GAIN** for independent held-out quality, model learning, GPU LoRA, or autonomous P0–P6 closed-loop.
- Next: run pinned #320/#322/#323 cross-auditors against these exact JSON bytes in a clean independent environment; save CLI exit codes and logs. Do not claim this occurred in this audit.
- Run same-session, balanced-order A/B+A/A with independently held-out 30+ groups and pre-frozen scorer; require noninferior accuracy, zero critical regressions and repeatable speed/token gains.
- GPU LoRA only with device identity, optimizer steps, actual adapter bytes + SHA and independent evaluation. No protected verifier, approval gate, or deployment edits.
- If raw files disappear after 2026-11-28 UTC, archived SHA and artifact ID remain the reference; artifact access alone is not a permanent external trust anchor.

## Cycle timing
Artifact download/inspection performed, but end-to-end start/end, model wall time, independent evaluator wall time, operations, queue wait and monetary cost were **not instrumented**. Comparable 5–12 cycle medians, hourly independently verified gains, retry/failure/regression/rollback rates and percentage changes are **판단불가**. This audit made no fresh model calls or GPU training.
