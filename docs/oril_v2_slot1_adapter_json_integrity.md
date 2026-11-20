# ORIL v2.0 slot 1/5 — untrusted adapter response JSON integrity

## Baseline
Stacked on PR #292 exact SHA `49807c2ec4d42f850b182dfdcb7cc72533faf00d`. Main remains `8fbecb5e813b653213d6c8d95ce7151868779512`. The earlier heldout reader already rejected repeated JSON keys and NaN, but adapter stdout was parsed with permissive `json.loads`. A malicious or faulty adapter could emit repeated `answer`, `model_id`, or `input_tokens` keys; the last value would silently win. Python also accepts `NaN` by default. This is a *measurement integrity* issue, not a claim that any model has trained.

## Change
Reuse the existing `strict_json_pairs` and `reject_nonfinite_json` hooks when parsing adapter stdout, and make diagnostics input-neutral. A new seven-test synthetic subprocess suite exercises duplicate answer/token/model fields, nested duplicates, NaN, valid compatibility, and a failed candidate leaving no published report. All tests use Python fixtures, never actual Qwen, GPU or LoRA.

## Verification
CI: `.github/workflows/oril-v2-slot1-adapter-json-integrity.yml`. Run new adversarial suite, existing real-inference suite, heldout strict JSON suite and private-report preflight suite at the same exact SHA. No protected verifier, approval gate or deployment changes. A successful CI is independent *execution* of developer-authored synthetic tests, not independent hidden evaluation.

## Hypothesis / falsification
H1: strict adapter JSON parsing prevents ambiguous or nonfinite adapter responses from producing paired evaluation reports, while normal JSON still works. Falsified by any malformed fixture accepted, any valid fixture rejected, or any failed candidate producing a published report.

## Known limitations and next P0–P6 work
- P0: capture baseline SHA, exact CI logs, failure counts and true task wall time.
- P1: verify real reviewed teacher-example provenance and independent dataset source; do not export hidden answers.
- P2: freeze student model identifier, tokenizer, long and distilled prompts, adapter command hashes.
- P3: actually run baseline and distilled student adapters on the same heldout tasks. Token counts and model IDs are currently adapter **claims**, not independently authenticated.
- P4: if GPU exists and approval permits, train LoRA with real optimizer steps and adapter bytes/SHA. Otherwise mark **GPU/LoRA unverified**.
- P5: independent reviewer scores paired heldout accuracy and tokenizer-measured tokens with uncertainty, not synthetic unit tests.
- P6: promotion requires quality noninferiority, measured savings, and approval; never auto-merge or deploy.

Outstanding issues: adapter stdout/stderr are buffered in memory by `subprocess.run(capture_output=True)` before the 200 KB output check; add bounded streaming/spool capture. Report parent path replacement race and untrusted adapter-provided token/model identity remain. These must not be called solved.

**No actual model intelligence improvement proven; baseline/quality/latency unknown until real paired inference.**
