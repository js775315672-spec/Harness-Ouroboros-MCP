"""Rehearse two verified generations using the same durable state across runners."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time

from p3l_hydra_completion_rehearsal import CompletionRegistry
from p3l_hydra_fast_lane_gate import SCHEMA
from p3l_hydra_github_completion import verify_completion

WORKFLOW = os.environ.get("HYDRA_WORKFLOW", ".github/workflows/hydra-next-generation.yml")
STEPS = {"source": "Run exact Hydra tests", "first": "Execute first approved generation",
         "second": "Resume and execute second approved generation"}
SUITES = {"first": "test_p3l_hydra_fast_lane_gate.py",
          "second": "test_p3l_hydra_completion_rehearsal.py"}


def make_plan(head):
    def task(key, state, deps, path):
        return {"key": key, "base_sha": head, "state": state, "deps": deps,
                "paths": [path], "evidence_sha": None}
    return {"schema": SCHEMA, "head_sha": head, "max_parallel": 1,
            "tasks": [task("source", "running", [], "scripts/p3l_hydra_github_completion.py"),
                      task("first", "pending", ["source"], "tests/" + SUITES["first"]),
                      task("second", "pending", ["first"], "tests/" + SUITES["second"])]}


def run_offline(suite):
    env = {key: val for key, val in os.environ.items() if key not in {"GH_TOKEN", "GITHUB_TOKEN"}}
    with tempfile.TemporaryDirectory(prefix="hydra-generation-") as parent:
        root = Path(parent)
        root.chmod(0o755)
        snapshot = subprocess.check_output(["git", "archive", "HEAD", "scripts", "tests"], timeout=20)
        subprocess.run(["tar", "-x", "-C", str(root)], input=snapshot, timeout=20, check=True)
        command = ["docker", "run", "--rm", "--pull=never", "--network=none", "--read-only",
                   "--cap-drop=ALL", "--security-opt=no-new-privileges", "--user=65534:65534",
                   "--cpus=1", "--memory=256m", "--pids-limit=64", "--tmpfs=/tmp:rw,nosuid,nodev,size=16m",
                   "--mount", f"type=bind,src={root},dst=/work,readonly", "-w", "/work",
                   "python:3.11-slim", "python", "-B", "-m", "unittest", "discover",
                   "-s", "tests", "-p", suite]
        subprocess.run(command, env=env, timeout=45, check=True)


def interrupt_before_commit(database, event, binding):
    """Stop a worker after its SQLite writes, before the transaction commits."""
    with tempfile.TemporaryDirectory(prefix="hydra-interrupt-") as folder:
        ready = Path(folder) / "ready"
        env = {key: value for key, value in os.environ.items() if key not in {"GH_TOKEN", "GITHUB_TOKEN"}}
        with subprocess.Popen([sys.executable, "-B", __file__, "interrupt", str(database),
                               json.dumps([event, binding, str(ready)])], env=env) as worker:
            deadline = time.monotonic() + 10
            try:
                while not ready.exists() and worker.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.02)
                if not ready.exists() or worker.poll() is not None:
                    raise ValueError("worker did not reach the transaction boundary")
            finally:
                if worker.poll() is None:
                    worker.kill()
                worker.wait(timeout=10)
            if worker.returncode != -signal.SIGKILL:
                raise ValueError("worker was not interrupted by SIGKILL")
    print(json.dumps({"interrupted": "before_commit", "exit_code": worker.returncode}))


def interrupted_worker(database, payload):
    event, binding, ready = json.loads(payload)
    registry = CompletionRegistry(database, make_plan(event["head"]), approved_tasks=("first", "second"))
    connect = sqlite3.connect

    class PausedCommit(sqlite3.Connection):
        def __exit__(self, *exc):
            if exc[0] is not None or not self.in_transaction:
                raise ValueError("worker did not stage its transaction")
            Path(ready).touch()
            time.sleep(30)
            raise ValueError("worker was not stopped")

    sqlite3.connect = lambda *args, **kwargs: connect(*args, factory=PausedCommit, **kwargs)
    registry.consume("first", event, observed_head=event["head"], completion=tuple(binding))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("first", "second", "close"))
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    repo, run, head = os.environ["GITHUB_REPOSITORY"], int(os.environ["GITHUB_RUN_ID"]), os.environ["REVIEW_HEAD"]
    if subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, timeout=10).strip() != head:
        raise ValueError("generation checkout differs from reviewed HEAD")
    if args.phase != "first":
        actual = hashlib.sha256(args.database.read_bytes()).hexdigest()
        if actual != os.environ["EXPECTED_STATE_SHA"]:
            raise ValueError("generation state handoff digest mismatch")

    def fetch(path):
        return json.loads(subprocess.check_output(["gh", "api", path], timeout=15))
    jobs = fetch(f"repos/{repo}/actions/runs/{run}/attempts/1/jobs")["jobs"]

    def event(name):
        matches = [j["id"] for j in jobs if j["name"] == name]
        if len(matches) != 1:
            raise ValueError("missing exact generation job")
        return {"task": name, "head": head, "run_id": run, "job_id": matches[0]}

    def verify(item):
        return verify_completion(item, repository=repo, workflow=WORKFLOW, job_name=item["task"],
                                 required_step=STEPS[item["task"]], fetch=fetch)

    registry = CompletionRegistry(args.database, make_plan(head), approved_tasks=("first", "second"))
    predecessor = {"first": "source", "second": "first", "close": "second"}[args.phase]
    if args.phase == "second":
        if registry.consume("first", event("source"), observed_head=head):
            raise ValueError("interrupted handoff reopened a spent execution slot")
    done = event(predecessor)
    completed = registry.complete(done, verify)
    desired = [] if args.phase == "close" else [args.phase]
    if not completed["accepted"] or completed["reserved"] != desired or registry.complete(done, verify)["accepted"]:
        raise ValueError("unexpected generation reservation or duplicate completion")
    if desired:
        current = event(args.phase)
        binding = (run, current["job_id"])
        if args.phase == "first" and WORKFLOW in {
            ".github/workflows/hydra-recovery-pilot.yml", ".github/workflows/hydra-shared-recovery.yml"
        }:
            interrupt_before_commit(args.database, done, binding)
        if not registry.consume(args.phase, done, observed_head=head, completion=binding):
            raise ValueError("generation execution already spent")
        run_offline(SUITES[args.phase])
        state = hashlib.sha256(args.database.read_bytes()).hexdigest()
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
            output.write("state_sha=" + state + "\n")
    else:
        state = hashlib.sha256(args.database.read_bytes()).hexdigest()
    print(json.dumps({"phase": args.phase, "run": run, "head": head,
                      "verified_job": done["job_id"], "reserved": desired,
                      "duplicate_blocked": True, "state_sha256": state, "model_calls": 0}, sort_keys=True))


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "interrupt":
        interrupted_worker(Path(sys.argv[2]), sys.argv[3])
    else:
        main()
