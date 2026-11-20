# ORIL v2 slot 1 — second output open failure cleanup

**Baseline:** stacked on Draft PR #282 SHA `8282755aa3f87720166a3a9342d3d6b8139c01e4`, not main; no overlap with other slots' paired quality/token evaluation PRs. Main SHA `8fbecb5e813b653213d6c8d95ce7151868779512`.

## Reproducible defect
The #282 exclusive output creation fix avoids overwriting existing files but can leave an **empty first train export** when opening the second report output raises FileExistsError, ENOENT, or other OSError. A downstream process may misinterpret this empty file as a completed dataset. The second output remains unchanged.

## Minimal patch
On second output open failure, compare the first output file descriptor's device and inode to the current path and best-effort unlink the just-created first file, then re-raise the original error. Never delete a path when the inode differs. This cleanup is not a fully atomic two-file commit; a malicious concurrent rename/unlink between lstat and unlink remains a possible race. A write-time disk-full error may still leave partial outputs. Do not claim full transaction safety.

## Test contract
Six subprocess tests: preexisting report, symlink report, dangling symlink report, nonexistent parent, successful two-file export, and repeated-run no-clobber. Inherited curation and output-safety suites must also pass at exact HEAD SHA on independent GitHub runner. If a suite is skipped or fails, report **개선 없음** and do not merge.

## Follow-up hypothesis
If exports are staged in a private pinned directory and published via a single immutable manifest/commit marker after fsync, consumers can reject incomplete pairs. Minimum experiment: 20 injected failures at each stage and 20 success cases; consumer must accept 20/20 success and reject 100% incomplete exports. Preserve existing data and avoid protected verifier/approval/deployment changes.

## Model claims
This changes only the offline teacher-example exporter. No real teacher provenance verification, GPU LoRA training, adapter generation, heldout model evaluation, token/latency savings, or intelligence improvement is demonstrated. Those remain **미측정/미입증**. Do not compare differing task types' CI durations as development speed gains.
