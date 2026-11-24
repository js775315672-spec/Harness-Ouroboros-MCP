"""Cycle 006: real registry CAS stress against disposable Git remotes."""
import concurrent.futures
import json
import pathlib
import tempfile
import threading
import time
import cycle_registry as r

def trial(workers, iteration):
    with tempfile.TemporaryDirectory(prefix="ofc-c006-") as tmp:
        remote = str(pathlib.Path(tmp) / "fixture.git")
        r.git("init", "--quiet", "--bare", remote)
        source = r.git("commit-tree", r.git("mktree", stdin=""), "-m", "isolated baseline")
        r.git("push", remote, source + ":refs/heads/main")
        first = r.transact(remote, "acquire", "worker", 0, source)
        op = json.dumps({"protocol": r.R1_PROTOCOL, "agent": r.AGENT,
                         "cycle_id": first["cycle"], "operation_id": "operation-00001",
                         "effect_id": "external-effect-00001", "source": source}, sort_keys=True)
        barrier = threading.Barrier(workers, timeout=120)
        def contender(i):
            barrier.wait()
            try:
                state = r.transact(remote, "reserve", "worker", 1, source, op)
                if state["pending"] != op:
                    raise AssertionError("unexpected accepted state")
                return "accepted"
            except r.Blocked:
                return "blocked"
        start = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            outcomes = list(pool.map(contender, range(workers)))
        elapsed = time.monotonic() - start
        state = r.transact(remote, "inspect")
        winners = outcomes.count("accepted")
        blocked = outcomes.count("blocked")
        valid = (state["pending"] == op and len(state["r1_guard"]["operations"]) == 1
                 and len(state["r1_guard"]["effects"]) == 1)
        print(json.dumps({"workers": workers, "iteration": iteration,
                          "winners": winners, "blocked": blocked,
                          "ledger_valid": valid, "seconds": elapsed}), flush=True)
        if winners != 1 or blocked != workers - 1 or not valid:
            raise AssertionError("CAS invariant failed")

if __name__ == "__main__":
    for workers in (5, 10, 20):
        for iteration in range(1, 31):
            trial(workers, iteration)
    print("CYCLE006 CAS PASS: 90 trials", flush=True)
