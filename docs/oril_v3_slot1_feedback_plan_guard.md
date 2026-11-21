# ORIL v3 slot 1 — fail-closed P5→P6 prompt planner (2026-11-21)

Base: PR #330, SHA `957dcad940b875ced2ba3270f52014907d53a1f8`. The integrated three-cycle public Qwen workflow is already in progress, so this change is isolated in a stacked draft PR; do not rewrite its running evidence or touch protected graders, approval gates, or deployment.

## Falsifiable defect and patch

Prior `plan(memory)` used `next(...)` without a default. A repeated, unknown, non-list or exhausted `tried` history could produce an opaque `StopIteration` or silently reuse invalid feedback; a boolean/negative error count could alter priority. The patch validates exactly three named strategies, unique history, and integer public errors in 0..30; exhaustion fails with an explicit `ValueError`. This is a P5→P6 reliability guard, not proof of intelligence or a model-weight change.

## Minimal verification

Run `python3 -m unittest discover -s tests -p test_oril_v3_slot1_plan_guard.py -v`. Eleven deterministic offline cases cover clean selection, error priority, remaining candidate, exhausted history, duplicate, unknown, string history, negative/overflow/bool error count, and missing fields. Separate GitHub-hosted CI is required before claiming success. Existing three public Qwen cycles are not replayed in this patch; no GPU, adapter, held-out data, cost, or accuracy claims.

## Handoff

Review the completed Actions for PR #330, including cycle 3 and artifacts. If the end-to-end loop fails, classify whether the issue is candidate selection, model inference, independent public grading, or memory handoff. Next run should compare source SHA and raw artifact digests, independently validate held-out quality, and retain protected promotion as pending. Only merge after owner review and regression checks.
