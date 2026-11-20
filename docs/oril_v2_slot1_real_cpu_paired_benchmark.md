# ORIL v2 slot 1 — balanced actual CPU forward measurement, NOT intelligence improvement

## Baseline and conflict prevention
- main: `8fbecb5e813b653213d6c8d95ce7151868779512`
- Stacked on PR #302 SHA `51f927b7bacd99b03f9b3a065244d7704866dfce` (actual 2-run CPU forward smoke). Other slots #299–#301 are untouched.
- The first actual CPU forward smoke used only one short and one long synthetic prompt. A single ordering cannot estimate latency trends or detect cold-start effects.

## What changed
Run six paired comparisons (12 real subprocess Qwen2 generations) using the same deterministic tiny random-weight checkpoint, tokenizer and seed, reversing compact/verbose order every other pair. Record measured input/output tokens and elapsed time per invocation, paired latency differences and medians. The measured times include model loading, Python startup, and CPU inference, so **do not interpret them as isolated token generation latency**. Use an independent GitHub runner, a separate report artifact, and fail-closed checks for schema, counts, false quality claims and order.

This is a **synthetic systems benchmark**: it does not show a pretrained Qwen can solve a task, a LoRA adapter was trained, hidden evaluation accuracy, actual API token cost, GPU usage or model intelligence gain. The toy tokenizer does not generalize to a production tokenizer.

## Falsifiable hypothesis and follow-up
H1: balancing short/long prompt execution order yields six paired actual input-token measurements and quantifies median measured input-token reduction without falsely asserting quality. Pass only if exact SHA CI completes 12 real CPU generations, all pair order checks pass, all seven unit tests pass and the JSON artifact records the expected flags.

H2: once an operator-approved pretrained checkpoint and independently frozen private heldout tasks are available, compare >=30 grouped paired heldout tasks using identical model/seed, real tokenizer and no data leakage. Require token savings >=20%, paired quality difference 95% CI lower bound >= -2pp, and latency/cost logs before claiming quality-preserving acceleration. If sample too small, report `판단불가`.

H3: GPU LoRA is NOT active. Only count actual optimizer steps, GPU execution evidence, adapter bytes/SHA and independent frozen heldout evaluation as proof. A synthetic CPU smoke or manifest cannot satisfy this.

## Limits
CPU runner availability and installation may dominate CI wall time. Report elapsed timings by source and avoid comparing this task with unrelated security-regression CI as if they were equivalent. No protected validators, approval gates or deployment were changed.
