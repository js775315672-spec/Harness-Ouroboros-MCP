# Qwen Evolve — optional experiment utilities

These Python modules were adapted from the user's uploaded files.zip. They are intentionally NOT connected to the frozen Qwen 7B benchmark or the existing Ouroboros production runner.

## Scope

- grammar.py — builds GBNF to constrain a very specific expression format. It measures format compliance, **not open-ended coding ability**. Confirm the exact grammar works in the pinned llama.cpp binary before using it for a real model experiment.
- repair_loop.py — bounded verifier-driven retry with sanitised feedback, changed temperature/seed after a failure. This must be measured as a SEPARATE experimental condition; do not silently change the frozen benchmark.
- llama_server.py — opt-in client for a local HTTP llama-server. It does not launch or download a model. Numeric loopback only; no proxies, cross-origin redirects or unrestricted responses. CLI flags such as --cache-reuse / --model-draft require real compatibility verification against the pinned binary before use.
- passk.py — Wilson intervals and Chen-style pass@k estimator. Do not apply pass@k to deterministic same-seed repeats and imply independent samples.

## Validation

Run the offline regression and adversarial tests:

    python3 -m unittest discover -s tests -p 'test_qwen_evolve*.py' -v

The original uploaded tests cover grammar, feedback retries, a mocked local HTTP endpoint and pass@k (13 methods). An additional security test file checks loopback origin restrictions, redirect handling, response budgets and unsupported syntax. These tests do not establish actual Qwen inference or performance improvement.

## Isolation and approval requirements

No existing model backend, benchmark, AST gate, Docker verifier or task queue is replaced by this package. Do not use grammar restrictions or dynamic retries to inflate the frozen benchmark pass rate. Before enabling server-mode comparisons: verify model weights and pinned llama-server flags, measure memory/time under identical tasks, use independent held-out tests, and preserve all failures. No network request leaves loopback. No secrets, paid APIs, trading, automated PR merges, or deployment are needed for these tests.
