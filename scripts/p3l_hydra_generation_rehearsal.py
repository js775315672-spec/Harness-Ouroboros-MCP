"""Rehearse two verified generations using the same durable state across runners."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from p3l_hydra_completion_rehearsal import CompletionRegistry
from p3l_hydra_fast_lane_gate import SCHEMA
from p3l_hydra_github_completion import verify_completion

WORKFLOW = ".github/workflows/hydra-next-generation.yml"
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
    main()
