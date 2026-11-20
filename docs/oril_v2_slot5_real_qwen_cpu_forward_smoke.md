# ORIL v2 slot 5 — first actual Qwen2 CPU forward/generation smoke

Baseline main SHA `8fbecb5e813b653213d6c8d95ce7151868779512`; stacked on PR #301 SHA `ca84d01ec1e743fbc9780adfb327bb20fae9b26f`. Earlier #299 readiness check had no real model execution. #300–#301 implement the prompt-variant bridge and secure prefix. This PR deliberately **does not modify** those scripts or protected gates.

## Scope
`scripts/oril_v2_tiny_qwen_cpu_forward_smoke.py` constructs a tiny, deterministic **random-weight** Qwen2 architecture (1 layer, hidden size 48) and a local 20-word WordLevel tokenizer. It saves actual config/tokenizer/safetensors checkpoint to a temporary directory, invokes the *existing* `oril_v2_local_qwen_adapter.py` subprocess twice, and checks measured tokenizer input token counts for short vs verbose synthetic questions. Model generation runs through real `torch` and `transformers`, not a fake adapter.

The smoke report records actual input/output token counts and per-call wall clock times. It explicitly states pretrained_weights=false, GPU=false, optimizer_steps=0, LoRA=false, heldout=false, model_intelligence_gain=null. **A random model producing tokens is not a useful trained model or evidence of intelligence gain.**

## CI acceptance
A dedicated Ubuntu workflow installs CPU torch, pinned transformers and tokenizers; runs the script, saves a JSON artifact, and validates that both real CPU generations happened and compact prompt input tokens are fewer. Any dependency/install/import/model load failure must fail the workflow, never be silently marked success. The JSON artifact contains only synthetic prompts and no private evaluation data.

## Next useful work
1. Obtain operator-approved **real pretrained** local Qwen checkpoint with full pinned weight hashes, and independent heldout dataset SHA. Do not upload hidden answers to public CI.
2. Run the *same model* with fixed verbose and compact contexts on >=30 independently grouped unseen tasks. Record actual input/output tokens, wall clock latency, correct answers and paired confidence intervals. Do not infer actual cost reduction from character count or synthetic smoke.
3. If GPU approved and available, run LoRA with real optimizer steps >0, record GPU execution log and actual adapter bytes/hash; independently compare against frozen heldout baseline. Until then **no LoRA trained**.
4. Measure CI runner start/finish timestamps for comparable tasks before claiming speed trend. Keep all PRs Draft until independently approved.

## Limits
The smoke depends on upstream pip packages and hosted runner resources. Synthetic tokens are only a protocol/compute-path check; CPU generation speed is not representative of production Qwen. No external evaluator, user approval, production merge or deployment is changed.
