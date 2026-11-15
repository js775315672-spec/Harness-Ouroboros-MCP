# Hybrid Qwen CPU benchmark (review-only)

## Scope
- Keep existing `transformers` inference and its cloud workflow unchanged.
- Add optional `llama.cpp` CPU inference using official Qwen2.5-Coder 0.5B and 1.5B `Q4_K_M` GGUF.
- Both engines send model responses to the **same** `qwen_semantic_repair_loop.run_loop`, `qwen_semantic_source_guard`, and `qwen_semantic_disposable_compare.compare_line` gate.
- The Python source checkout stays unchanged. Candidate code is executed only in disposable, no-network, read-only Docker containers. No automated merging or approvals.

## 3B licensing gate
The official `Qwen/Qwen2.5-Coder-3B-Instruct-GGUF` is marked `qwen-research` and is **not permitted by this benchmark**. A separate license assessment and explicit approval are required before adding it. This benchmark does not download or run 3B.

Official source/license references:
- https://huggingface.co/Qwen/Qwen2.5-Coder-0.5B-Instruct-GGUF
- https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF
- https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct-GGUF/blob/main/LICENSE
- https://github.com/ggml-org/llama.cpp

## Running in GitHub Actions
The `.github/workflows/gguf-cpu-comparison.yml` workflow uses read-only permissions, a pinned `llama.cpp` source commit, a fixed official model allowlist, an explicit public-model Apache-2.0 license check, and model revisions pinned from Hugging Face metadata. Two jobs run sequentially (0.5B then 1.5B); the model files are never committed or uploaded to artifacts.

Each job writes metadata and a JSON result as GitHub artifacts. The JSON records model/runner hashes, AST rejection categories, Docker pass/fail statuses, wall-clock time, peak child RSS, number of attempts and whether the first attempt passed. A **passing workflow is not proof of a successful model repair**: failures are legitimate, explicitly reported experimental results.

For this pilot there is one narrowly scoped bug-fix task. A first-attempt pass is a binary result, **not** a statistically meaningful first-attempt success rate. Expanding to multiple independent tasks and repetitions is required before success rates can be compared.

## Safety and follow-up
1. Keep all source/tests/policy boundaries identical across inference engines.
2. Model-proposed code must first pass constrained AST validation, then preexisting Docker regression and new negative-control tests.
3. Only fixed, structured failure categories enter follow-up prompts; raw model text and Docker logs are never used as instructions.
4. Limit retries to three, stop repeated identical candidates and require human review for any passing patch.
5. If the Q4 GGUF runtime has an infrastructure failure, treat it as a blocked experiment, not model success.
6. Before expansion to 3B, complete license compliance review and require explicit authorization.
