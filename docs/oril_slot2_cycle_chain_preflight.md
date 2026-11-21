# ORIL slot 2: cycle-chain structural preflight (2026-11-21)

This standalone **read-only** preflight checks consecutive cycle IDs, predecessor linkage, source→candidate SHA handoff, and distinct claimed model/independent Actions run URLs. It is deliberately not an independent verifier or evidence authenticator.

Run: `python -m unittest discover -s tests -p 'test_oril_slot2_cycle_chain_preflight.py'`

Run on a JSON array: `python scripts/oril_slot2_cycle_chain_preflight.py path/to/cycles.json`

**Security boundaries:** A submitter can fabricate all input fields. A passing check cannot prove actual model calls, independent evaluation, GPU optimizer steps, LoRA adapter creation, hidden-set performance, or quality gain. It always sets `promotion_allowed=false` and `independent_provenance=UNVERIFIED`. No production gates, workflows, or deployment are modified.

**Next falsifiable experiment:** feed actual PR #330 cycle ledger (not synthetic fixtures); verify every run URL via GitHub API and download raw artifacts with immutable SHA-256; mutate predecessor, candidate SHA, memory SHA and run URL independently. Expected: intact structural ledger PASS; each mutation FAIL; provenance remains UNVERIFIED until independently attested. Then freeze held-out grader and evaluate the candidate under existing approval controls. No automatic merge.
