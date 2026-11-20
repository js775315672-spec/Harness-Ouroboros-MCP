# ORIL v2 slot 4/5 — raw latency sidecar audit (experimental)

## Baseline and non-duplication

At start: main `8fbecb5e813b653213d6c8d95ce7151868779512`. Prior slot 3 PR #305 `8a7f71e1a7d62320575b99472207af29370ce38a` passed independent arithmetic audit [Actions #44819774037](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44819774037). PR #304 observed order and PR #303 ran 6 paired / 12 real CPU subprocess generations using **tiny randomly initialized Qwen2**, not pretrained Qwen or LoRA. No real heldout tasks or GPU training evidence.

PR #305 explicitly leaves `compact_elapsed_seconds_median` and `verbose_elapsed_seconds_median` **unverified** because its report only includes paired elapsed differences. A malicious or erroneous report can fabricate both individual medians without altering the differences. This PR does not modify another slot's benchmark or protected validator. It adds an **opt-in, separate sidecar auditor** for future reports.

## Implemented change

`scripts/oril_v2_cpu_raw_latency_sidecar_audit.py` independently reconstructs individual compact/verbose median times, paired median differences, and tokenizer-input saving from per-call raw sidecar. The sidecar contains `schema_version=1`, `measurement_kind=synthetic_random_weight_qwen2_cpu_subprocess`, `report_sha256` (SHA256 of canonical JSON report with sorted keys, compact separators, UTF-8), and `pairs` with actual order, per-variant raw seconds and input token counts. It fails closed on missing pairs, inconsistent summary medians, invalid order, forged token vectors, invalid numbers, or unsupported pretrained/GPU/LoRA/quality claims.

`tests/test_oril_v2_cpu_raw_latency_sidecar_audit.py` has 15 regression methods, including forged compact and verbose latency medians. The new independent Ubuntu workflow executes those tests.

**No actual new CPU measurement was performed by this PR**. A valid sample sidecar is synthetic test data. Existing PR #303/#304 report artifacts **do not contain** the required raw per-call times; they cannot be retrospectively attested or audited with this new tool. Do not fabricate them.

## Hypothesis, minimal reproducible experiment and next cycle

- H: A report can pass PR #305's summary arithmetic audit despite having fabricated individual latency medians. Minimal repro: create 2 valid synthetic pairs, edit only the compact median, preserve token vectors and paired differences; existing summary audit cannot reconstruct individual median, while new raw-sidecar audit must reject. Pass: test `test_compact_median_forgery` and `test_verbose_median_forgery` fail closed, and valid raw sidecar passes.
- Next real experiment: modify future benchmark runner in its own new PR to emit raw per-invocation times **at measurement time**, not inferred from summary, and upload report+sidecar as one immutable artifact. Include workflow run ID, runner image, model config/tokenizer hash, input prompt SHA, pair execution order, and a separately pinned artifact digest. Run the raw audit in CI on **the same newly generated artifact**.
- P0–P6: independent pretrained Qwen checkpoint and private frozen heldout >=30 groups remain absent; do not claim precision gain. GPU LoRA requires actual optimizer steps, adapter bytes+SHA, GPU logs and independent evaluation. Reviewer/owner approval is required for any protected gate/deployment changes.

## Explicit limits

The sidecar SHA is self-calculated and cannot authenticate a source. This script does not prove timestamps were actually measured, or that execution occurred on a GPU or a pretrained model. No weights were updated. Synthetic tests are evidence-integrity regression tests only.

### Cycle speed and quality

The prior #305 arithmetic CI finished in about 7 seconds wall time (from 21:22:36Z to 21:22:43Z); it is not comparable to CPU inference jobs because it does not install Torch or generate tokens. Total development time, model call time, independent heldout evaluation time, operational followup, cost, comparable 5–12-cycle medians and improvement rates remain unmeasured. Speed: **판단불가**; intelligence quality: **판단불가**. This work is a bounded evidence-integrity extension, not model improvement.
