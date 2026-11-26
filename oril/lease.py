"""Select the canonical Actions run for one workflow, source and base revision."""
import json
import os
import subprocess


def owner(runs, source, base, current):
    eligible = []
    for run in runs:
        if run["head_sha"] != source or run["event"] != "pull_request":
            continue
        if any(pr["base"]["sha"] == base for pr in run["pull_requests"]):
            eligible.append(run["id"])
    if current not in eligible:
        raise ValueError("current run absent from GitHub ownership ledger")
    return min(eligible)


def api(path):
    return json.loads(subprocess.check_output(["gh", "api", path], timeout=20))


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    run = int(os.environ["GITHUB_RUN_ID"])
    source, base = os.environ["SOURCE_SHA"], os.environ["BASE_SHA"]
    info = api(f"repos/{repo}/actions/runs/{run}")
    path = f"repos/{repo}/actions/workflows/{info['workflow_id']}/runs?event=pull_request&head_sha={source}&per_page=100"
    response = api(path)
    if len(response["workflow_runs"]) != response["total_count"]:
        raise ValueError("incomplete GitHub ownership ledger")
    canonical = owner(response["workflow_runs"], source, base, run)
    print(f"Owner https://github.com/{repo}/actions/runs/{canonical}")
    if canonical != run:
        raise SystemExit("Duplicate experiment. Resume failed jobs on the owner run.")
    if info["run_attempt"] > 3:
        raise SystemExit("Campaign retry budget exhausted")


if __name__ == "__main__":
    main()
