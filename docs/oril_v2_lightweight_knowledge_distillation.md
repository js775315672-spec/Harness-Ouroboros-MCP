# ORIL v2.0 — lightweight knowledge distillation, next-cycle experiment

**Objective:** replace oversized repeated teacher explanations with small, independently reviewed task-specific examples, allowing a smaller student model to attempt similar ORIL review and code-repair tasks. This change prepares a **data curation pipeline**, not a weight update. It does not assert that LoRA is running.

## Two layers that must never be confused

1. **Context/example distillation (implemented in this PR):** take existing concise teacher examples from a JSONL ledger and select high-quality, bounded examples for a student fine-tuning dataset. Avoid redundant samples and all train/validation/heldout group leakage. Actual student training is not performed.
2. **Parameter distillation (future gated step):** run student LoRA/SFT on actual GPU, record measured optimizer steps and adapter bytes+SHA, evaluate baseline/student independently on a separately held-out task set, and only promote after user approval.

The teacher should provide concise **final answers**, actionable checks, and verifiable fixes; do not store hidden reasoning, long transcripts, credentials, private user data, or proprietary code fragments.

## Required inputs

Each teacher-example JSONL row has: `case_id`, `group_id`, `split` (`train|validation|heldout`), `task_type`, `question`, `teacher_answer`, `checks` (bounded public verification criteria), `quality` (0–1), `review_accepted` (boolean), `review_url` (GitHub PR/Actions record), and `candidate_sha` (40-hex exact SHA).

**Important:** the review URL, boolean and quality are only input claims; the compiler cannot prove an external reviewer independently accepted them. A separate operator must verify provenance before feeding the records to a student trainer.

The grouping contract prevents shared task family and identical normalized question from being split across train and heldout. **Hidden evaluator answers must never enter the train export.** No automatic retrieval of private eval answers.

Example:

```bash
python3 scripts/oril_v2_teacher_distillation_pack.py \
  --input reviewed_teacher_examples.jsonl \
  --output-train candidate_student_train.jsonl \
  --output-report distillation_report.json \
  --max-cases 16 --max-total-chars 6000 \
  --max-answer-chars 650 --min-quality 0.9
```

These character limits are **proxy budgets**, not tokenizer-exact tokens, GPU cost or actual execution speed. The report explicitly leaves token count, model learning, independent evaluation and quality gain unknown.

## Minimal next cycle (P0–P6 aligned)

| Gate | Action | Must measure |
|---|---|---|
| P0 | Freeze student and teacher model IDs, trusted evaluator/heldout dataset SHA, task types, baseline latency and token usage | Baseline n and source SHA; do not fabricate |
| P1 | Choose teacher examples with verified provenance; run offline group leakage, duplicates, quality gates | reviewed sources, rows before/after, rejected rows |
| P2 | Limit to 16 high-value cases, short teacher responses, cross-task coverage; save deterministic student training JSONL | char budget proxy and actual tokenizer tokens when connected |
| P3 | Run baseline student without new examples, then with distilled few-shot context; keep tasks and samples fixed | request tokens, response tokens, latency, exact error rates |
| P4 | **Only if GPU actually available:** optional small Qwen LoRA/SFT with logged steps/optimizer, adapter file SHA/size and immutable run/job ID | actual GPU/adapter evidence; otherwise no claim of trained model |
| P5 | Independently held-out evaluator compares baseline with candidate on exact same unseen tasks and seeds | exact-match/pass rate, regression count, CI95 or task-level paired comparison |
| P6 | Accept only if noninferior heldout quality and actual per-task token/latency savings are demonstrated; log what failed | status “향상/유지/악화/판단불가”, rollback and reviewer approval |

### Hypothesis and falsifiable acceptance

- H1: selecting 16 reviewed examples within 6000 total characters reduces candidate context bytes vs all reviewed training examples **without leaking heldout answers**. Acceptance: leakage tests all green, output reproducible, selected character budget enforced.
- H2: on **the same independent heldout tasks** student prompts with distilled examples reduce *actual tokenizer tokens* >=20% relative to a fixed verbose-example baseline while heldout correctness changes by >= -2 percentage points. Use paired samples (prefer >=30 tasks), explicitly record CI and uncertainty; if insufficient evidence, mark **판단불가**. This is **not yet tested**.
- H3 (optional real LoRA): actual GPU fine-tuning outputs an adapter with positive size and recorded SHA, optimizer steps >0, independent fixed heldout score no worse than baseline. A training manifest without GPU execution does **not** pass.

### Operational risk controls

This PR adds only `scripts/`, `tests/`, `docs/`, and a read-only CI workflow. It never merges protected validators, changes deployment, trains weights, or auto-approves its own results. No independent eval datasets are uploaded into a public repository. If examples cannot be independently verified, record **“개선 없음”** for training readiness and post a minimal next experiment to issue #251.

**Next-slot handoff:** obtain legitimate teacher example sources; run the script and attach input manifest SHA, output SHA, report, CI logs. If no real examples, start with an offline synthetic negative-test validation **labeled as synthetic only**, then request independently verified examples rather than inventing teacher approval or model performance.
