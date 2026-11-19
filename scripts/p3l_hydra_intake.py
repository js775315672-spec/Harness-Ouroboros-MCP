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
    commands.add_parser("pause")
    commands.add_parser("resume")
    args = parser.parse_args()
    approval = json.loads(args.approval.read_bytes())
    plan = approval["plan"]
    if type(plan["max_parallel"]) is not int or not 1 <= plan["max_parallel"] <= 2:
        raise ValueError("approved operation is limited to two lanes")
    producer = approval["producer"]
    registry = CompletionRegistry(args.ledger, plan, approved_tasks=approval["tasks"])
    if args.command != "admit":
        paused = args.command == "pause"
        registry.set_paused(paused)
        print(json.dumps({"paused": paused}))
        return

    event = dict(task=producer["task"], head=plan["head_sha"], run_id=args.run, job_id=args.job)

    def verify(item):
        return verify_completion(item, repository=REPOSITORY, workflow=producer["workflow"],
                                 job_name=producer["job"], required_step=producer["step"],
                                 fetch=fetch, trusted_push=(producer["branch"], plan["head_sha"],
                                                            producer["workflow_id"]))

    print(json.dumps(registry.complete(event, verify)))


if __name__ == "__main__":
    main()
