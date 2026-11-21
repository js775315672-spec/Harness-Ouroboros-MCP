# ORIL slot 1 — public LoRA receipt consistency audit

Scope: `experiments/hydra-lora/run-01` BERT Tiny LoRA artifact, **not Qwen**. This offline checker binds the actual safetensors bytes to the receipt SHA256, checks the header rank and model revision, checks train/eval CSV digests, and recomputes accuracy/recovered/regressed from stored per-example predictions. It rejects mismatches without requiring a GPU or model download.

Run: `python3 scripts/oril_slot1_lora_receipt_audit.py experiments/hydra-lora`
Tests: `python3 -m unittest discover -s tests -p test_oril_slot1_lora_receipt_audit.py -v`

**Trust boundary:** Matching a self-reported receipt does not independently attest hardware GPU use, optimizer execution, correct model predictions, private evaluation, or intelligence improvement. The adapter exists and the receipt claims 100 SGD steps on a DirectML Radeon device; an independently controlled GPU job, its original logs, and heldout evaluator are still required. Public fixture 6/12→8/12 includes three regressions, so automatic promotion remains blocked.

Falsifiable next hypothesis: replaying the frozen adapter on a separate runner against the pinned pretrained model reproduces all 12 public predictions. Minimum experiment: fetch pinned model files, verify base SHA, run `scripts/hydra_gpu_lora.py --verify`, and compare predictions and adapter digest. Pass: exact 12/12 prediction reproduction and 0 evidence mismatches; this still does not count as hidden evaluation. Independent heldout evaluation must be conducted by separately authorized verifier before promotion.

This work does not modify protected verifiers, approval gates, or deployment.
