# ORIL v2 slot 5: prevent silent overwrite of heldout data by distillation export

Baseline: PR #281 SHA `28861791f39b3ab87d653972354f9620efbd32ce`; latest CI https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44775205315. Main SHA `8fbecb5e813b653213d6c8d95ce7151868779512`. This PR is stacked on #281, not main. No changes to the separate grouped evaluation PR #279 or protected deployment/approval/verifier.

## Reproducible defect
`Path(...).resolve()` only checked output *path identity* against the input and the other output. It did **not** prohibit an output path already containing valuable unrelated data, or a symlink to a heldout dataset. `write_text()` follows the symlink and truncates the target. This is a data integrity risk even if the heldout answers never enter the student train JSONL.

## Change
Create train and report files using `O_CREAT|O_EXCL|O_WRONLY` (plus `O_NOFOLLOW` where available) and mode 0600. Open both outputs before writing either. Refuse to overwrite any existing output including symlinks. Seven subprocess tests cover existing train/report preservation, symlink target preservation, dangling symlink, file modes, parseability, and repeated invocation.

## Remaining risks
This is not an atomic two-file transaction. If opening the report fails after creating the train output, an empty train file can remain. A late write/disk failure can leave partial outputs; do not treat them as valid without explicit manifest validation. Parent-directory symlink or replacement attacks and cross-platform differences are not fully addressed. A later approved cycle should use directory-fd-pinned outputs and atomic publish with manifest checks; avoid touching protected verification gates. No GPU LoRA, adapter or real heldout model improvement is claimed.

## Next falsifiable experiment
- Run inherited teacher curation tests plus seven subprocess tests on the exact PR SHA, skip=0.
- Inject an existing heldout file at either output, including symlink and dangling symlink; expect nonzero return and unchanged victim SHA.
- Independently collect real teacher review evidence and actual Qwen paired heldout >=30 distinct groups. Record tokenizer-exact tokens, latency, quality lower CI >= -2pp, token savings lower CI >=20%.
- Only claim parameter learning with actual GPU optimizer steps and nonempty adapter bytes/SHA. Otherwise report **모델 지능 개선 없음**.

No protected verifier, approval gate or production deployment changes.
