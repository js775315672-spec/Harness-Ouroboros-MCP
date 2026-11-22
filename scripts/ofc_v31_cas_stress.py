"""30-round, 5/10/20 worker isolated Git CAS stress campaign.

Run as a dedicated CI job. The target is always a newly created local bare
Git repository, never the production registry. Emits JSON evidence per round.
"""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from agent import cycle_registry as registry

LEVELS = (5, 10, 20)
ROUNDS = 30

def git(*args, cwd=None):
    return subprocess.run(["git", *map(str, args)], cwd=cwd,
        check=True, capture_output=True, text=True).stdout.strip()

def campaign(level, round_no, script, source_root):
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="ofc-cas-stress-") as temp:
        root = Path(temp)
        remote = str(root / "isolated.git")
        checkout = root / "seed"
        git("init", "--bare", remote)
        git("init", checkout)
        git("config", "user.name", "stress-test", cwd=checkout)
        git("config", "user.email", "stress@example.invalid", cwd=checkout)
        (checkout / "seed.txt").write_text("pinned", encoding="utf-8")
        git("add", ".", cwd=checkout)
        git("commit", "-m", "seed", cwd=checkout)
        git("branch", "-M", "main", cwd=checkout)
        git("remote", "add", "origin", remote, cwd=checkout)
        git("push", "origin", "main", cwd=checkout)
        source = git("rev-parse", "HEAD", cwd=checkout)
        previous = os.getcwd()
        try:
            os.chdir(checkout)
            owner = "stress-dev"
            pending = "artifact:stress"
            acquired = registry.transact(remote, "acquire", owner=owner,
                                         source=source, ttl=3600)
            generation = acquired["generation"]
            registry.transact(remote, "reserve", owner=owner,
                              generation=generation, source=source, value=pending)
        finally:
            os.chdir(previous)

        def run_worker(index):
            work = root / ("worker-" + str(index))
            # Independent checkout, Python interpreter, and Git state.
            git("clone", "--quiet", remote, work)
            git("checkout", "-q", "main", cwd=work)
            p = subprocess.run([sys.executable, str(script), source_root, remote,
                owner, str(generation), source, pending], cwd=work,
                capture_output=True, text=True, timeout=120)
            return {"exit": p.returncode, "stdout": p.stdout.strip(),
                    "stderr": p.stderr[-500:]}

        with concurrent.futures.ThreadPoolExecutor(max_workers=level) as pool:
            outcomes = list(pool.map(run_worker, range(level)))
        previous = os.getcwd()
        try:
            os.chdir(checkout)
            final = registry.transact(remote, "inspect")
        finally:
            os.chdir(previous)
        winners = sum(x["exit"] == 0 and x["stdout"] == "WIN" for x in outcomes)
        blocked = sum(x["exit"] == 0 and x["stdout"] == "BLOCKED" for x in outcomes)
        errors = level - winners - blocked
        correct = (winners == 1 and blocked == level-1 and errors == 0
                   and final["pending"] is None
                   and final["results"].get(pending) == '{"verified":true}')
        evidence = {"workers":level,"round":round_no,"winners":winners,
            "blocked":blocked,"errors":errors,"cas_conflicts":blocked,
            "duration_ms":round((time.perf_counter()-started)*1000,2),
            "registry_consistent":correct}
        print("CAS_STRESS_EVIDENCE "+json.dumps(evidence,sort_keys=True),flush=True)
        if not correct:
            print("CAS_STRESS_FAILURE "+json.dumps(outcomes),flush=True)
            raise AssertionError("CAS invariants violated")
        return evidence

def main():
    source_root = str(Path(__file__).resolve().parents[1])
    with tempfile.TemporaryDirectory(prefix="ofc-cas-worker-") as temp:
        script = Path(temp) / "worker.py"
        script.write_text("""
import subprocess,sys,time
sys.path.insert(0,sys.argv[1])
from agent import cycle_registry as registry
from agent.pending_reconcile import Observation
from agent.verified_pending_cas import reconcile_to_isolated_remote
remote,owner,generation,source,pending=sys.argv[2:]
observation=Observation(pending,source,"confirmed",'{"verified":true}')
try:
    reconcile_to_isolated_remote(remote,owner=owner,generation=int(generation),
        source=source,now=time.time(),lookup=lambda _:observation,
        verify=lambda _:True,expected_pending=pending)
    print("WIN")
except (registry.Blocked,subprocess.CalledProcessError):
    print("BLOCKED")
""",encoding="utf-8")
        for level in LEVELS:
            rows = [campaign(level,i+1,script,source_root)
                    for i in range(ROUNDS)]
            summary = {"workers":level,"rounds":len(rows),
                "winners":sum(x["winners"] for x in rows),
                "blocked":sum(x["blocked"] for x in rows),
                "errors":sum(x["errors"] for x in rows),
                "conflict_rate":sum(x["cas_conflicts"] for x in rows)/(level*len(rows)),
                "median_duration_ms":sorted(x["duration_ms"] for x in rows)[len(rows)//2],
                "total_duration_ms":round(sum(x["duration_ms"] for x in rows),2)}
            print("CAS_STRESS_SUMMARY "+json.dumps(summary,sort_keys=True),flush=True)

if __name__=="__main__":
    main()
