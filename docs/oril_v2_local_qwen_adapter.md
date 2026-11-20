# ORIL v2 slot 3 — local Qwen adapter (experimental)

This PR supplies the **missing executable model-adapter bridge** for Draft #289–#294, which previously only used synthetic subprocess stubs. It is deliberately **not** an assertion of actual Qwen execution, GPU LoRA, student improvement or independent evaluation. The optional `torch` and `transformers` packages are **not installed in CI**. CI exercises mocked protocol and rejection behavior only.

## Real inference (operator environment only)

Install a compatible pinned `torch` and `transformers` in a dedicated environment. Pre-download a trusted Qwen checkpoint into a local directory with `config.json`; verify the checkpoint's actual source and revision out of band. Avoid executing arbitrary model repository code. Only local files are loaded (`local_files_only=True`, `trust_remote_code=False`, Hub offline flags). No weights are trained or downloaded by this script.

Use the existing probe (from #294 head) with **the same private frozen heldout dataset** and two adapter commands, e.g. (substitute real local directories):

```bash
python3 scripts/oril_v2_student_real_inference_probe.py \
 --heldout /secure/heldout.jsonl \
 --baseline-cmd-json '["python3","scripts/oril_v2_local_qwen_adapter.py","--model-dir","/models/qwen-baseline","--device","cpu"]' \
 --candidate-cmd-json '["python3","scripts/oril_v2_local_qwen_adapter.py","--model-dir","/models/qwen-candidate","--device","cpu"]' \
 --timeout 3600 --report /secure/paired-probe.json
```

Use actual GPU only when available; `--device cuda` fails closed without CUDA. **Do not upload the heldout dataset or private answers.** The adapter prints only protocol JSON on stdout and the harness captures it under an output limit. Prompt never contains expected answers.

## Current limitations

- **Cold-start per case**: loads model for each request. This is expensive and unsuitable for performance claims without separating model load vs generation time. It is an integration bridge, not an optimized production inference server.
- **Token counts** come from tokenizer lengths within this adapter but remain *self-reported claims* from the perspective of the independent evaluator. Model ID is a local directory basename, not a cryptographic model identity. For trustworthy comparison pin model weight file hashes and tokenizer revision externally.
- Deterministic `do_sample=False` is used. GPU execution may still vary across platforms. Local directories could contain malicious checkpoint artifacts; run under restricted permissions and trusted sources. The script is not a sandbox.
- Model may not fit in memory or require a specific `transformers` version. An unsupported architecture should fail rather than enabling remote code.
- **No GPU training, optimizer steps, adapter bytes, independent heldout scoring, actual cost reduction, or intelligence improvement is demonstrated by this PR.**
- Existing strict report/approval gates remain untouched; do not merge or deploy without human approval.

## Next P0–P6 cycle, falsifiable experiment

P0: pin actual model+tokenizer revision and separate private heldout SHA, collect environment RAM/GPU and dependency versions. P1–P2: use externally reviewed teacher examples from #274, max 16 cases / 6000 chars, check split leakage. P3: run **at least 30 unique heldout groups** on same frozen Qwen baseline with verbose vs compact prompts. Log cold-start time separately, actual tokenizer tokens, paired correctness and task IDs. P4: if authorized GPU is present, optionally train LoRA and prove optimizer steps >0 and actual adapter file SHA/bytes. P5: independent evaluator checks paired group bootstrap CI; target token savings CI lower bound >=20% and accuracy delta CI lower bound >=-2 percentage points. P6: approve only with independent review and explicit user authorization; otherwise **개선 없음**, record failure mode and revise next hypothesis.

## Evidence and safety

No changes to protected verifier, deployment or approval. The CI workflow only checks 14 synthetic/mock tests. Report exact SHA and Actions URL, but do not label these as model accuracy or training evidence.
