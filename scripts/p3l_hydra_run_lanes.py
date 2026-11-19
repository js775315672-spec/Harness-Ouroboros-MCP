"""Run and independently attest two bounded Hydra rehearsal suites."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from p3l_hydra_completion_rehearsal import CompletionRegistry
from p3l_hydra_fast_lane_gate import select_lanes

SUITES = {"w06_public_probe": "test_p3l_w06_public_contract_lint.py",
          "w05_receipt_gate": "test_p3l_w05_replay_evidence.py"}
FIXTURE = Path("tests/fixtures/p3l_hydra_fast_lane_plan.json")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def run_suite(key):
    t = time.monotonic()
    result = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests",
                             "-p", SUITES[key], "-v"], capture_output=True, timeout=60, check=False)
    output = result.stdout + result.stderr
    found = re.findall(rb"(?m)^Ran ([1-9][0-9]*) tests? ", output)
    if result.returncode != 0 or len(found) != 1 or b"skipped=" in output:
        sys.stderr.buffer.write(output[-8000:])
        raise ValueError("rehearsal suite failed or lacked a test count")
    return output, int(found[0]), round(time.monotonic()-t, 6)


def identity():
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], timeout=10).decode().strip()
    if head != os.environ["GITHUB_SHA"]:
        raise ValueError("runner checkout differs from the workflow SHA")
    return head, int(os.environ["GITHUB_RUN_ID"])


def produce(key, directory):
    head, run_id = identity()
    output, count, elapsed = run_suite(key)
    directory.mkdir()
    (directory / "suite.log").write_bytes(output)
    receipt = {"lane": key, "head": head, "run_id": run_id, "tests": count,
               "log_sha256": sha(output), "elapsed_seconds": elapsed,
               "runner": os.environ["RUNNER_NAME"], "model_calls": 0}
    (directory / "receipt.json").write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))


def verify(directory, jobs_file):
    head, run_id = identity()
    jobs = json.loads(jobs_file.read_bytes())["jobs"]
    plan = json.loads(FIXTURE.read_bytes())
    plan["head_sha"] = head
    for task in plan["tasks"]:
        task["base_sha"] = head
    lanes = select_lanes(plan)["eligible"]
    if set(lanes) != set(SUITES):
        raise ValueError("unexpected rehearsal lane selection")
    for task in plan["tasks"]:
        if task["key"] in lanes:
            task["state"] = "running"
    registry = CompletionRegistry(directory / "state.sqlite3", plan)
    passed = []
    for key in lanes:
        job_name = "lane (" + key + ")"
        matches = [j for j in jobs if j["name"] == job_name]
        if len(matches) != 1:
            raise ValueError("missing exact lane job")
        job = matches[0]
        evidence = directory / ("hydra-" + key)
        raw = (evidence / "receipt.json").read_bytes()
        data = json.loads(raw)
        output = (evidence / "suite.log").read_bytes()
        if (job["conclusion"] != "success" or job["run_id"] != run_id or job["head_sha"] != head
                or data["lane"] != key or data["head"] != head or data["run_id"] != run_id
                or data["runner"] != job["runner_name"] or data["runner"] == os.environ["RUNNER_NAME"]
                or data["log_sha256"] != sha(output) or type(data["tests"]) is not int
                or type(data["model_calls"]) is not int or data["model_calls"] != 0):
            raise ValueError("lane receipt does not match its GitHub job")
        _, count, _ = run_suite(key)
        if count != data["tests"]:
            raise ValueError("independent suite test count differs")
        event = {"task": key, "head": head, "run_id": run_id, "job_id": job["id"]}
        proof = {**event, "passed": True, "sha256": sha(raw)}
        if not registry.complete(event, lambda _: proof)["accepted"]:
            raise ValueError("verified first receipt did not advance")
        if registry.complete(event, lambda _: proof)["accepted"]:
            raise ValueError("verified receipt fired twice")
        passed.append({"lane": key, "tests": count, "job_id": job["id"],
                       "runner": job["runner_name"], "receipt_sha256": sha(raw)})
    if len({item["runner"] for item in passed}) != 2:
        raise ValueError("lane jobs were not independent")
    print(json.dumps({"head": head, "run_id": run_id, "verified": passed, "model_calls": 0,
                      "duplicate_events_blocked": 2, "verifier_runner": os.environ["RUNNER_NAME"]},
                     sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--lane", choices=SUITES)
    parser.add_argument("--jobs", type=Path)
    args = parser.parse_args()
    if args.lane and args.jobs is None:
        produce(args.lane, args.directory)
    elif args.jobs and args.lane is None:
        verify(args.directory, args.jobs)
    else:
        parser.error("select one lane or supply GitHub job evidence")
