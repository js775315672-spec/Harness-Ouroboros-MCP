"""Admit a verified completion to an operator-approved Hydra ledger."""
import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen

from p3l_hydra_completion_rehearsal import CompletionRegistry
from p3l_hydra_github_completion import verify_completion

REPOSITORY = "js775315672-spec/Harness-Ouroboros-MCP"


def fetch(path):
    request = Request("https://api.github.com/" + path, headers={"Accept": "application/vnd.github+json"})
    with urlopen(request, timeout=15) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval", type=Path, required=True, help="operator-controlled configuration")
    parser.add_argument("--ledger", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    admit = commands.add_parser("admit")
    admit.add_argument("--run", type=int, required=True)
    admit.add_argument("--job", type=int, required=True)
    delivery = commands.add_parser("workflow-run")
    delivery.add_argument("--event", type=Path, required=True)
    commands.add_parser("pause")
    commands.add_parser("resume")
    args = parser.parse_args()
    approval = json.loads(args.approval.read_bytes())
    plan = approval["plan"]
    if type(plan["max_parallel"]) is not int or not 1 <= plan["max_parallel"] <= 2:
        raise ValueError("approved operation is limited to two lanes")
    producer = approval["producer"]
    registry = CompletionRegistry(args.ledger, plan, approved_tasks=approval["tasks"])
    if args.command in {"pause", "resume"}:
        paused = args.command == "pause"
        registry.set_paused(paused)
        print(json.dumps({"paused": paused}))
        return

    if args.command == "workflow-run":
        payload = json.loads(args.event.read_bytes())
        run = payload["workflow_run"]
        if (payload.get("action") != "completed"
                or payload.get("repository", {}).get("full_name") != REPOSITORY
                or run.get("head_sha") != plan["head_sha"]
                or run.get("head_branch") != producer["branch"]
                or run.get("workflow_id") != producer["workflow_id"]
                or run.get("event") != "push" or run.get("conclusion") != "success"
                or type(run.get("id")) is not int or not 0 < run["id"] <= 2**63 - 1):
            raise ValueError("completion event does not match operator approval")
        run_id = run["id"]
        page = fetch(f"repos/{REPOSITORY}/actions/runs/{run_id}/attempts/1/jobs?per_page=100")
        jobs = page["jobs"]
        if len(jobs) != page.get("total_count"):
            raise ValueError("incomplete producer job list")
        matches = [job["id"] for job in jobs if job["name"] == producer["job"]]
        if len(matches) != 1:
            raise ValueError("producer must have exactly one approved job")
        job_id = matches[0]
    else:
        run_id, job_id = args.run, args.job

    event = dict(task=producer["task"], head=plan["head_sha"], run_id=run_id, job_id=job_id)

    def verify(item):
        return verify_completion(item, repository=REPOSITORY, workflow=producer["workflow"],
                                 job_name=producer["job"], required_step=producer["step"],
                                 fetch=fetch, trusted_push=(producer["branch"], plan["head_sha"],
                                                            producer["workflow_id"]))

    print(json.dumps(registry.complete(event, verify)))


if __name__ == "__main__":
    main()
