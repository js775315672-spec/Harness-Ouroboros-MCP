# ORIL v2 slot5: report no-clobber preflight (experimental)

## Baseline
Stacked on PR #291 SHA `7e4176d5b0bd891f73225faa6185b6834aa0f9c9`, itself stacked on PR #290 and #289. `main` remains `8fbecb5e813b653213d6c8d95ce7151868779512`. PR #291 strict heldout JSON preflight has successful Actions #44793898052/#44793897870/#44793897791 after an earlier failed run #44793832911.

## Reproducible failure hypothesis
Before this PR, `Path(report).write_text(...)` after subprocess inference could truncate an existing JSON report, including a sensitive non-heldout file reached via an attacker-created symlink. A second execution could overwrite a valid prior report. Missing output directory was detected only **after** model execution. A fixed comparison of resolved report vs heldout only prevented one target and did not protect arbitrary existing files.

## Change and verification
Reserve the report with `os.open(O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW, 0600)` **before** calling either model adapter; retain the file descriptor for the final JSON and fsync. Existing paths, symlinks and missing parent directories fail before model subprocesses. Added eight real subprocess regression tests: existing report no-clobber, arbitrary symlink target, manifest symlink, missing parent, normal private output, second-run refusal, adapter failure leaves no valid JSON, malformed heldout creates no output. Read-only Ubuntu CI runs inherited student probe tests, strict heldout JSON tests, and the new suite.

## Explicit limitations
- This is an output safety fix, **not** a real Qwen run, GPU LoRA training, adapter artifact, tokenizer attestation or independent heldout quality gain.
- If an adapter fails after report reservation, an **empty private report may remain**. Consumers must reject it; no success marker is emitted. No automatic deletion because a concurrent attacker could swap the pathname. Retry requires a new output name or an explicitly authorized cleanup.
- This change does not defend against hostile *parent directory rename/symlink swaps* or malicious file descriptor access, and cannot atomically commit a report and other artifacts. Next experiment should pin parent directory descriptors and inject 1,000 rename races; acceptance: victim files changed 0, successful reports always valid, invalid/empty reports never accepted.
- CLI adapter token/model fields remain untrusted assertions. The heldout manifest is private and must not be committed.
- Approval/deployment/protected verifiers untouched; Draft only.

## Next-cycle priority
Run the exact-SHA CI and compare against the parent baseline. Then collect independent heldout >=30 groups and real Qwen adapter evidence, using frozen source SHA and measured tokenizer tokens/latency; only if GPU training actually occurs may optimizer steps, adapter SHA/bytes and independent model quality be reported. If no real model evidence: **모델 지능 개선 없음(미입증)**.

## Speed/quality accounting
Measure total cycle wall time, model invocation time, independent evaluation time, postprocessing time, failed/retried runs, and exact Actions SHA/job duration. Avoid comparing dissimilar workflow jobs. CI success is regression coverage, not intelligence improvement.
