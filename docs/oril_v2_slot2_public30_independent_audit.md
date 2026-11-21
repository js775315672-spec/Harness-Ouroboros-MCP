# ORIL v2.0 P0–P6 slot2: independently audit 30 public Qwen pairs

## Baseline and nonoverlap
Base PR #319 (head e9322a40c47826d02b816feece9241b8b3c0a933) produced 30 **public** arithmetic pairs and 60 claimed pretrained CPU calls. Slots 3–4 (#316–#317) own heldout frozen plans and observation binding; slot 5 (#318) audited the earlier 4 public tasks. This PR independently checks the *new 30-group raw report* without importing the experiment's summarizer. No protected validators or deployment changes.

## Improvement and falsifiable experiment
Experiment-side totals can be accidentally inconsistent or tampered with while appearing plausible. Hypothesis: an independent pure-standard-library audit detects any changed task, answer label, order, timing, token count, raw/summary discrepancy or false model-training claim. Test using 15 offline mutations, and optionally run the CLI against the exact SHA #319 artifact `public_30_pairs.json` to compare the independently reconstructed totals. A passing mutation suite is **not** evidence that the raw artifact is authentic.

```sh
python3 scripts/oril_v2_slot2_public30_independent_audit.py \
  --input public_30_pairs.json --output public_30_independent_audit.json
```

The audit separately reports compact-only vs verbose-only correct public pairs (paired discordance) rather than treating 60 responses as 60 independent questions. It reconstructs descriptive input-token savings, correctness, median CPU timings and the public task digest. Weight file hashes are **metadata claims** until compared with actual weight bytes. CPU execution and latency are **not independently attested**. No confidence interval, noninferiority or intelligence gain is claimed on public arithmetic.

## Required next steps
P0 pin PR #319 exact SHA, original artifact URL, model revision and weight bytes. P1 download and hash actual artifact bytes (do not replace it with fixtures). P2 run independent audit; fail closed on mismatches. P3 compare with 4-group #315 only as descriptive results, without claiming statistical generalization. P4 keep GPU LoRA training as **not performed** until actual GPU optimizer steps and adapter SHA/bytes are recorded. P5 independent frozen heldout evaluation >=30 task groups, including task families beyond arithmetic, with group-level paired accuracy and token CI. P6 require human approval for any promotion. Report missing evidence as **미측정** and actual intelligence improvement as **개선 없음(미입증)**.

No trainer, reviewer, heldout dataset, protected verifier, deployment or model weights are changed by this PR.
