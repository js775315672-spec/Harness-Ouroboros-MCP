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
    return select_from(runs, jobs_by_run.__getitem__)


def select_from(runs, get_jobs):
    latest = {}
    for run in sorted(runs, key=lambda item: item["id"], reverse=True):
        if (run["event"] not in EVENTS or run["head_branch"] != "main"
                or run["status"] != "completed" or run["run_attempt"] != 1):
            continue
        for job in get_jobs(run["id"]):
            name, conclusion = job["name"], job["conclusion"]
            match = WORKER.fullmatch(name)
            if name != "admit" and match is None:
                continue
            if conclusion not in {"success", "failure", "timed_out"}:
                continue
            if name not in latest:
                latest[name] = run, job, ("admit" if match is None else "worker")
        # Admission takes priority, and older runs cannot supersede this result.
        if "admit" in latest and latest["admit"][1]["conclusion"] != "success":
            break
    failures = [entry for entry in latest.values() if entry[1]["conclusion"] != "success"]
    if not failures:
        return {"decision": "no_unresolved_failure", "proposal": None}
    run, job, kind = min(failures, key=lambda item: (TASKS[item[2]][0], -item[0]["id"], item[1]["name"]))
    identity = f"{run['id']}:{job['id']}"
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


def run_jobs(run_id):
    endpoint = f"repos/{REPO}/actions/runs/{run_id}/attempts/1/jobs?per_page=100"
    page = fetch(endpoint)
    jobs = list(page["jobs"])
    total = page["total_count"]
    for number in range(2, (total + 99) // 100 + 1):
        page = fetch(f"{endpoint}&page={number}")
        if page["total_count"] != total:
            raise ValueError("inconsistent Hydra production job evidence")
        jobs.extend(page["jobs"])
    if len(jobs) != total or len({job["id"] for job in jobs}) != total:
        raise ValueError("incomplete Hydra production job evidence")
    return jobs


def main(output):
    path = f"repos/{REPO}/actions"
    runs = fetch(f"{path}/workflows/{WORKFLOW}/runs?branch=main&status=completed&per_page=12")["workflow_runs"]
    result = select_from(runs, run_jobs)
    if result["decision"] == "no_unresolved_failure":
        source = "docs/evolution/cycle-01-dispatch-preflight.json"
        preflight = json.loads((Path(__file__).resolve().parents[1] / source).read_text(encoding="utf-8"))
        if preflight["status"].startswith("blocked_") and preflight["dispatch_count"] == 0:
            result["next_review"] = {
                "cycle": preflight["cycle"], "status": preflight["status"],
                "task": preflight["required_next_evidence"], "source": source,
            }
    Path(output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1])
