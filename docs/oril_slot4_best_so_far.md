# ORIL slot4: public best-so-far candidate advisory

## Observed regression in exploratory candidate ranking

In the integrated public campaign 44853120822, candidate 2 scored 27/30 public exact matches while candidate 3 scored 25/30. The existing planner explores a new hypothesis but does not retain a best-so-far recommendation. This does not mean the model's intelligence regressed: these are public, repeatedly reused tasks.

## Change

`scripts/oril_slot4_best_so_far.py` accepts an explicitly constructed list of *public reviewed* candidate records, rejects duplicate cycles, missing evidence hashes, malformed scores, nonfinite savings, and unreviewed records, and recommends the best non-regressing public candidate. The result is advisory only: `protected_grade=pending` and `promotion_allowed=false` unconditionally.

Usage: `python -m scripts.oril_slot4_best_so_far reviewed_public_candidates.json`

Do not feed untrusted user-supplied summary metrics as if they were verified evidence. The caller must obtain these records from independently recomputed public review artifacts, validate artifact digests against GitHub run metadata, and keep private heldout results outside this file.

## Next experiment and falsification

Hypothesis: preserving a public best-so-far recommendation prevents a worse exploratory candidate from being treated as the strongest candidate for independent evaluation. Minimal reproduction: three reviewed public records with 20/30, 27/30, 25/30 and valid evidence hashes. Expected: cycle 2 recommended, promotion denied. Counterexample: any run where cycle 3 is recommended or a public recommendation grants promotion.

Independent heldout evaluation remains required before claiming quality improvement or changing an approved baseline. Do not change protected verifier, approval gate, or deployment.
