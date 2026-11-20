# ORIL v2 — slot 1 metadata syntax boundary (2026-11-21 KST)

## Baseline and reason
- main SHA: `8fbecb5e813b653213d6c8d95ce7151868779512`
- stacked parent: Draft PR #287 SHA `286e26f09aff5e272ea2f06db0c27177f7564f0a`, Actions #44786167178 and #44786166823 succeeded.
- PR #287 rejects malformed student conversations but still accepts arbitrary nonempty provenance URL and arbitrary candidate SHA. A malformed claim can pass the signed-by-no-one marker digest because digest integrity is not authenticity.
- PR #284–#287 and protected approval/deployment gates are not edited.

## Narrow change
Require curator-compatible ASCII IDs (1–80 chars), lowercase 40-hex candidate commit SHA, and an anchored HTTPS GitHub PR/Actions reference. The field name deliberately remains `review_assertion_url`, because a syntactically valid URL does **not** mean the review occurred or was independent.

## Minimal falsifiable experiment
Five synthetic tests check valid metadata and GitHub Actions claims, non-SHA candidate strings, lookalike URLs and path/query tricks, and hidden control characters in group identifiers. Execute them alongside the parent PR #287 consumer and dataset regressions on an independent Ubuntu GitHub Actions runner at the exact PR SHA. Require no failures and no skips. If the new CI fails, label **개선 없음** and debug the exact failed case before making further changes.

## Remaining risks and handoff
This cannot attest that a reviewer approved a teacher example or that a GitHub URL resolves to the claimed commit. Independent externally pinned provenance and privacy review are still required before feeding any dataset to a trainer. Existing source URL regex is deliberately aligned with the teacher curator; neither code path authenticates provenance. No actual Qwen inference, GPU LoRA training, adapter bytes, or heldout model quality measurement occurred.

**Next priority:** stop adding overlapping synthetic validators unless there is a concrete exploitable gap. Freeze an independently reviewed non-sensitive teacher sample and real heldout groups; compare compact vs verbose Qwen prompts using actual tokenizer tokens and paired correctness, then record run URL, latency and exact SHA. If GPU is unavailable, report that rather than claiming LoRA. Protect validator and user approval gates.
