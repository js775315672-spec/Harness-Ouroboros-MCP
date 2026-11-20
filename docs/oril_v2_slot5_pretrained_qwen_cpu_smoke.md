# ORIL v2.0 P0–P6 slot 5 — actual pretrained Qwen CPU smoke

## Baseline and collision check

Main SHA: `8fbecb5e813b653213d6c8d95ce7151868779512`. Prior slot #307 SHA `673aedac` real CPU random-weight Qwen benchmark: Actions https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44824055220 success. #309–#311 evaluate negative-control timing confounding, and #312 separately analyzes homogeneous Actions CI durations. This PR deliberately avoids all of their files, and **does not** repeat random-weight model smoke.

## Distinct missing evidence

Earlier Qwen2 CPU benchmarks used a tiny *randomly initialized* model. They establish that PyTorch execution is possible, **not that a real pretrained Qwen model runs**. This new workflow downloads `Qwen/Qwen2.5-0.5B-Instruct` at its resolved 40-character Hugging Face commit SHA, verifies safetensors bytes and SHA256, loads real pretrained weights, and generates two fixed public prompts on CPU. It records input tokens, output tokens, model execution latency, and the checkpoint's actual weight file SHA.

This is **pretrained inference only**. It does not train LoRA, generate an adapter, evaluate heldout task correctness, prove any speed gain, or certify independent provenance. Model provider is an external trust boundary: the downloaded weights are SHA-recorded but the model owner is not cryptographically attested.

## Reproduction

```bash
python3 -m unittest discover -s tests -p test_oril_v2_pretrained_qwen_cpu_smoke.py -v
pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu
pip install transformers==4.46.3 huggingface_hub==0.26.5 safetensors==0.4.5
python3 scripts/oril_v2_pretrained_qwen_cpu_smoke.py --output pretrained_qwen_cpu_evidence.json
```

The workflow runs on GitHub-hosted CPU and uploads a 7-day evidence artifact. It does not store any private prompts, keys, training examples, or hidden evaluation data. External downloads may fail due to network/rate limits or runner disk constraints; failure is explicitly **not** evidence of a model improvement.

## Falsifiable minimal experiment and acceptance

- H1: public pretrained Qwen2.5-0.5B loads on the CPU runner and produces nonempty output for **both** fixed prompts. Acceptance: exact SHA Actions success, two generated-token counts >0, elapsed_seconds >0, at least one safetensors file >0 bytes with SHA256, report downloadable and schema-valid.
- H2 (next cycle): compare the pretrained baseline against a genuinely compressed/distilled prompt on a frozen independent heldout task set, grouped to prevent contamination, with paired token/latency/accuracy and same-prompt negative control. Require >=30 independent task groups and uncertainty-aware noninferiority; no quality claim if not measured.
- H3 (future, GPU): execute actual Qwen LoRA optimizer steps on an authorized GPU, persist real adapter bytes+SHA and GPU log, and independently evaluate the heldout baseline and candidate. A synthetic manifest is not proof.

## Security and governance

The workflow has read-only repository permission, no deployment, no approval flag mutation, no protected evaluator changes, no auto-merge. `main` is untouched. Only Draft PR review can promote. Logs must separate setup/download time from measured forward time; neither is total cycle duration. If the runner cannot download the checkpoint, next cycle should try a pinned artifact cache or approved CPU-compatible checkpoint rather than generating fake metrics.
