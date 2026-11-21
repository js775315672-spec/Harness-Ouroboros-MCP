"""Freeze the first research target from evidence owned by this repository."""
import json
import os
import subprocess

from cycle_registry import AGENT, REMOTE, Blocked, git, transact


def api(path):
    return json.loads(subprocess.check_output(["gh", "api", path], text=True))


def select_goal(repo):
    # Rank local research PRs by domain relevance, then by most recent PR number.
    terms, task, metric = {
        "ouroboros": (["regression", "regressions", "failure", "replay"], "Select a failing case and compare a code candidate with the pinned baseline", "held-out task pass rate and regression count"),
        "cerberus": (["authenticate", "receipt", "verifier", "evidence"], "Measure false acceptance on mutations of the selected evidence contract", "false accepts and false rejects"),
        "fenrir": (["qwen", "reviewer", "counterexample", "contract"], "Reproduce the selected reviewer's baseline outcome before testing a counterexample", "reproduced counterexamples per evaluated claim and false alarms"),
    }[AGENT]
    candidates = []
    for pr in api(f"repos/{repo}/pulls?state=open&per_page=100"):
        title = pr["title"].lower()
        if title.startswith(("docs", "[draft]")) and "research" in title:
            continue
        matches = [term for term in terms if term in title]
        if matches:
            candidates.append((len(matches), pr["number"], pr, matches))
    if not candidates:
        raise Blocked("no matching repository evidence")
    _, _, pr, matches = max(candidates, key=lambda item: item[:2])
    sha = pr["head"]["sha"]
    checks = api(f"repos/{repo}/commits/{sha}/check-runs?per_page=100")["check_runs"]
    return dict(task=task, metric=metric, target=pr["html_url"], target_title=pr["title"],
                target_sha=sha, selection_terms=matches, candidate_count=len(candidates),
                observed_checks=[dict(name=c["name"], conclusion=c["conclusion"], url=c["html_url"]) for c in checks],
                quality_baseline=None, gain="NOT_RUN", next="run domain baseline on frozen target")


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    run = os.environ["GITHUB_RUN_ID"]
    stage = os.environ["STAGE"]
    owner = f"{run}/{os.environ['GITHUB_RUN_ATTEMPT']}/{stage}"
    source = git("rev-parse", "refs/remotes/origin/main")
    current = transact(REMOTE, "inspect")
    if stage == "select" and current:
        raise Blocked("first-cycle initialization already performed")
    if stage == "handoff":
        receipt = json.loads(current["checkpoint"])
        if receipt["run"] != run or current["cycle"] != os.environ["EXPECTED_CYCLE"]:
            raise Blocked("checkpoint does not belong to this handoff")
    lease = transact(REMOTE, "acquire", owner, source=source)
    args = owner, lease["generation"], source
    try:
        if stage == "select":
            if lease["checkpoint"]:
                raise Blocked("existing checkpoint")
            report = select_goal(repo)
            report.update(run=run, run_url=f"https://github.com/{repo}/actions/runs/{run}", main_sha=source)
            transact(REMOTE, "checkpoint", *args, value=json.dumps(report))
            with open(os.environ["GITHUB_OUTPUT"], "a") as output:
                print("cycle=" + lease["cycle"], file=output)
        elif lease["cycle"] != current["cycle"] or lease["checkpoint"] != current["checkpoint"]:
            raise Blocked("handoff mismatch")
        print(json.dumps(json.loads(transact(REMOTE, "inspect")["checkpoint"]), indent=2))
    finally:
        transact(REMOTE, "release", *args)


if __name__ == "__main__":
    main()
