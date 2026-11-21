"""Select the canonical Actions run for one workflow, source and base revision."""
import json
import os
import re
from pathlib import Path
import sys
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


def claim_slot(experiment, owner_id, source):
    # The isolated producer can read checkpoints without receiving this writer token.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from p3l_hydra_shared_dispatch import request
    if not re.fullmatch(r"[a-f0-9]{64}", experiment) or not re.fullmatch(r"[a-zA-Z0-9-]{1,100}", owner_id):
        raise ValueError("invalid experiment or worker ID")
    if not re.fullmatch(r"[a-f0-9]{40}", source):
        raise ValueError("invalid source commit")
    ref = f"refs/tags/oril-checkpoints/{experiment}"
    tag = dict(tag="oril-worker", message=owner_id, object=source, type="commit",
               tagger={"name":"ORIL coordinator","email":"oril@users.noreply.github.com",
                       "date":"2026-01-01T00:00:00Z"})
    status, body = request("POST","tags",json.dumps(tag).encode())
    if status != 201:
        raise RuntimeError(f"GitHub tag object creation failed ({status})")
    target = json.loads(body)["sha"]
    status, body = request("POST","refs",json.dumps(dict(ref=ref,sha=target)).encode())
    if status == 201:
        return "acquired"
    if status not in (409,422):
        raise RuntimeError(f"GitHub checkpoint claim failed ({status})")
    status, body = request("GET","ref/" + ref.removeprefix("refs/"))
    if status != 200 or json.loads(body)["ref"] != ref:
        raise RuntimeError("conflicting checkpoint ref could not be read")
    obj = json.loads(body)["object"]
    if obj["type"] != "tag":
        raise ValueError("invalid ownership record")
    return "resumed" if obj["sha"] == target else "busy"


def main():
    if len(sys.argv) == 5 and sys.argv[1] == "claim":
        print(claim_slot(*sys.argv[2:]))
        return
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
