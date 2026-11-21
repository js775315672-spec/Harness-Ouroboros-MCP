"""Public, bounded experiments on the pinned repository target."""
import hashlib
import json
import math
import pathlib
import random
import subprocess
import sys

TARGET = pathlib.Path("target").resolve()
sys.path.insert(0, str(TARGET))


def evaluate(agent, index, cycle):
    rng = random.Random(int(cycle, 16))
    if agent == "ouroboros":
        from scripts.oril_slot2_cycle_chain_preflight import check
        sha = "a" * 40
        row = dict(cycle_id="alpha", predecessor_id=None, source_sha=sha,
                   candidate_sha=sha, memory_sha=sha,
                   model_run_url="https://github.com/a/b/actions/runs/123",
                   independent_run_url="https://github.com/a/b/actions/runs/124")
        suite = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p",
                                "test_oril_slot2_cycle_chain_preflight.py"], cwd=TARGET, capture_output=True, text=True)
        if suite.returncode or "Ran 12 tests" not in suite.stderr:
            raise RuntimeError(suite.stderr)
        # Proposed public data-quality contract: identifiers have no outer whitespace.
        # Interior spaces and Unicode are valid; existing preflight must still pass.
        ids = [rng.choice(["", " ", "\t", "\n"]) + rng.choice(["alpha", "가 나", "id-2", "a b"]) +
               rng.choice(["", " ", "\t"]) for _ in range(12)] + ["valid", "a b", "가", " bad", "bad "]
        def accepts(s):
            try:
                check([dict(row, cycle_id=s)])
                return True
            except ValueError:
                return False
        baseline = [accepts(s) for s in ids]
        expected = [s == s.strip() for s in ids]
        options = {"unchanged": baseline, "strip_equal": [b and s == s.strip() for b,s in zip(baseline, ids)],
                   "ascii_only": [b and s.isascii() for b,s in zip(baseline, ids)],
                   "single_word": [b and len(s.split()) == 1 for b,s in zip(baseline, ids)]}
        return "Choose an additional identifier predicate for the proposed no-outer-whitespace contract; preserve valid Unicode and interior spaces.", ids, expected, options, "unchanged"
    if agent == "cerberus":
        workflow = (TARGET / ".github/workflows/pr346-fenrir.yml").read_text()
        # Extract the exact metadata predicate; invoke jq directly without a shell.
        import re
        predicate = re.search(r"(?m)^\s*jq -e --arg run .*? --arg attempt .*? '([^'\n]+)' FENRIR_REPORT.json$", workflow)[1]
        fields = dict(re.findall(r'\.(\w+)=="([^"]+)"', predicate))
        reference = dict(fields, run_id="101", attempt="1", model="model-A", model_revision="rev-A",
                         prompt_sha256=hashlib.sha256(b"public fixture").hexdigest())
        keys = ["model", "model_revision", "prompt_sha256"]
        samples = [[], *[[k] for k in keys], ["run_id"], ["attempt"]] + [rng.sample(keys, rng.randrange(4)) for _ in range(8)]
        options = {k: [] for k in ["unchanged", "model_identity", "prompt_identity", "all_three"]}
        for changed in samples:
            obj = dict(reference)
            for k in changed:
                obj[k] = "different"
            p = subprocess.run(["jq", "-e", "--arg", "run", "101", "--arg", "attempt", "1", predicate],
                               input=json.dumps(obj), text=True, capture_output=True)
            if p.returncode not in (0, 1):
                raise RuntimeError(p.stderr)
            old = p.returncode == 0
            for key, checks in zip(options, [[], keys[:2], keys[2:], keys]):
                options[key].append(old and all(obj[k] == reference[k] for k in checks))
        return "For already-authenticated test fixtures, select the extra metadata equality checks that bind model, revision and prompt. Measure the jq layer only.", samples, [not s for s in samples], options, "unchanged"
    from fixtures.demo_candidate import average
    n = rng.randint(3, 1000)
    groups = {"empty": [], "integers": [n, n+2], "mixed_sign": [-n, n], "single": [n]}
    claims = [
        ("average returns a finite value on every list of integers including empty lists", lambda a,y: math.isfinite(y)),
        ("average of any nonempty integer list is strictly positive", lambda a,y: y > 0),
        ("average on any nonempty integer list equals its first item", lambda a,y: y == a[0]),
        ("average on any nonempty integer list is nonzero", lambda a,y: y != 0),
    ]
    claim, holds = claims[index % len(claims)]
    outcomes = {}
    for key, values in groups.items():
        if not values and index % len(claims):
            outcomes[key] = [False]
            continue
        try:
            outcomes[key] = [not holds(values, average(values))]
        except ZeroDivisionError:
            outcomes[key] = [True]
    return "Select an in-domain counterexample to: " + claim, groups, [True], outcomes, "single"
