"""Select one next review task from unresolved Hydra production failures."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

REPO = "js775315672-spec/Harness-Ouroboros-MCP"
WORKFLOW = "hydra-standing.yml"
WORKER = re.compile(r"Worker ([A-Za-z0-9][A-Za-z0-9_-]{0,63})\Z")
EVENTS = {"push", "schedule", "workflow_dispatch"}
TASKS = {
    "admit": (0, "Investigate why Hydra could not admit approved tasks."),
    "worker": (1, "Investigate the failed approved Hydra worker."),
}


def select(runs, jobs_by_run):
    latest = {}
    for run in sorted(runs, key=lambda item: item["id"], reverse=True):
        if (run["event"] not in EVENTS or run["head_branch"] != "main"
                or run["status"] != "completed" or run["run_attempt"] != 1):
            continue
        for job in jobs_by_run[run["id"]]:
            name, conclusion = job["name"], job["conclusion"]
            match = WORKER.fullmatch(name)
            if name != "admit" and match is None:
                continue
            if conclusion not in {"success", "failure", "timed_out"}:
                continue
            if name not in latest:
                latest[name] = run, job, ("admit" if match is None else "worker")
    failures = [entry for entry in latest.values() if entry[1]["conclusion"] != "success"]
    if not failures:
        return {"decision": "no_unresolved_failure", "proposal": None}
    run, job, kind = min(failures, key=lambda item: (TASKS[item[2]][0], -item[0]["id"], item[1]["name"]))
    identity = f"{run['head_sha']}:{job['name']}"
    proposal = {
        "id": "hydra-problem-" + hashlib.sha256(identity.encode()).hexdigest()[:20],
        "task": TASKS[kind][1], "job_name": job["name"],
        "run_id": run["id"], "job_id": job["id"], "head": run["head_sha"],
        "evidence": f"https://github.com/{REPO}/actions/runs/{run['id']}/job/{job['id']}",
        "state": "proposed",
    }
    return {"decision": "needs_approval", "proposal": proposal}


def fetch(path):
    return json.loads(subprocess.check_output(["gh", "api", path], timeout=15))


def main(output):
    path = f"repos/{REPO}/actions"
    runs = fetch(f"{path}/workflows/{WORKFLOW}/runs?branch=main&status=completed&per_page=12")["workflow_runs"]
    runs = [run for run in runs if run["event"] in EVENTS and run["head_branch"] == "main"
            and run["status"] == "completed" and run["run_attempt"] == 1]
    jobs = {}
    for run in runs:
        page = fetch(f"{path}/runs/{run['id']}/attempts/1/jobs?per_page=100")
        if page["total_count"] != len(page["jobs"]):
            raise ValueError("incomplete Hydra production job evidence")
        jobs[run["id"]] = page["jobs"]
    result = select(runs, jobs)
    Path(output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1])
