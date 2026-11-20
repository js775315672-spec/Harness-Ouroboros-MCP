# ORIL v2 slot 4/5 — strict heldout manifest preflight

**Start:** `main` SHA `8fbecb5e813b653213d6c8d95ce7151868779512`; stacked on PR #290 head `1e6ffa838c4f2cc73bc5f8b48d74cc36a2a7a86d`. PR #289 adds an adapter invocation harness, PR #290 normalizes heldout group aliases. Neither changes the Python JSON decoder's last-value-wins handling of duplicate object keys or caps the input file size. PR #290's existing CI succeeded at https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44791980624.

## Reproducible failure hypothesis

A heldout JSONL row can contain two `split` or `group_id` keys. Python `json.loads` silently takes the last value. This makes the frozen source ambiguous to other JSON consumers, potentially bypassing cross-implementation consistency. An oversized file can also exhaust memory before any model subprocess is started.

## Narrow, falsifiable patch

- Reject repeated keys at any JSON nesting level, nonfinite `NaN`/`Infinity` literals, files over 4 MiB, more than 1000 cases, and lines over 24000 characters.
- Read at most 4 MiB + 1 bytes rather than an unbounded `read_bytes`.
- Seven new tests verify rejection of repeated `split`/`group_id`, nonfinite values, oversize file/line/case count, and preservation of valid 2-group manifest SHA.
- Existing 15 synthetic adapter protocol/group alias tests must continue to pass, with no skips.
- **No hidden heldout data, real Qwen invocation, GPU LoRA, model adapter, independent evaluator, or protected gate was touched.**

## Next experiment and acceptance

1. Confirm exact SHA on GitHub Actions: new 7/7 and inherited 15/15 tests, no skips. Any failure means **개선 없음** until corrected.
2. Verify the *real* privately frozen heldout manifest (>=30 independently sourced groups), its SHA, provenance and valid JSON schema, without publishing answers.
3. Run actual Qwen baseline vs distilled context with pinned tokenizer/model revision, record actual inference wall times and independently measured tokens. Require paired noninferiority and token reduction confidence bounds; no performance claim from synthetic tests.
4. If GPU LoRA becomes available, record actual optimizer steps, adapter bytes/SHA and independent evaluation. Otherwise explicitly record GPU/LoRA **미실행**.
5. Do not merge or deploy without approval. Current trust gap: self-reported adapter model/token fields are not attested.

**Limitations:** 4 MiB/1000 cases are explicit experimental resource limits, not scientifically justified dataset sizing; users may need an approved streaming protocol for larger private heldout datasets. The parser does not attest dataset ownership, semantic group independence, or the safety of operator-provided subprocess commands.
