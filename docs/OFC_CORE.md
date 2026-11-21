# OFC Independent Evolution Core — P0 implementation note

- This branch is **P0 only**: typed contracts, agent-scoped append-only logical ledger,
  resource cap, fail-closed evaluator/gate, and a README dashboard with explicit unknowns.
- The six logical responsibilities (Planner, Runner, Evaluator, Resource Governor,
  Knowledge Ledger, Growth Gate) are Python modules. They do **not** turn an existing
  unit-test result into a claim of model improvement.
- `Runner.execute` deliberately fails until a real Qwen invocation, pinned weights,
  model receipt, output digest, and isolation are wired in P1.
- Existing `agent/cycle_registry.py` provides the separate Git CAS lease, fencing,
  pending external operations, and crash recovery tests. It is **not** replaced here.
- Gate outcomes are HOLD/REJECT/REVIEW_REQUIRED/HALT. No promotion or main merge
  operation exists in this package.
- The evaluator check here is a **provenance/contract gate**, not yet a protected
  independent model evaluation service. P1 must separate evaluator trust, hide
  private test answers and execute independently; an attestation boolean alone
  does not provide that isolation.
- SQLite rows and a derived JSONL hash chain are logically append-only. Admins
  can still rewrite the entire file. P1 requires retained external checkpoints.
- A repeated passing unit test does not prove improvement, generalization, or
  lower runtime. README displays UNKNOWN and NOT_MEASURED until external evidence
  is verified, and must not be overwritten from untrusted candidate output.
- All changes require separate review in each repository. **No main auto-merge**.

## P0 local checks

```sh
python3 -m unittest discover -s tests -p 'test_ofc_core.py' -v
python3 agent/test_cycle_registry.py -v
python3 scripts/build_dashboard.py --check
```

## P1 next cycle

1. Wire the pinned Qwen model invoker with explicit run IDs and hashed raw outputs.
2. Invoke on a branch protected by existing per-agent registry reservations.
3. Submit to an isolated evaluator that does not share candidate writes or secrets.
4. Store run URL, candidate Git SHA, artifact digest, environment and results.
5. Only then present verified evidence for human review.
