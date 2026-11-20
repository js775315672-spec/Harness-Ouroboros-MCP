"""Read-only audit of stacked ORIL pull requests against supplied GitHub snapshots.

Inputs are GitHub REST-shaped JSON objects, not authenticated evidence.
CI green, Draft state, and GitHub merge authorization are deliberately separate.
No merging, dispatching, secrets, model training, or network access.
"""
import argparse
import json
import re
from pathlib import Path

SHA40 = re.compile(r"[0-9a-fA-F]{40}\Z")


def _sha(value):
    return isinstance(value, str) and SHA40.fullmatch(value) is not None


def _pr_ref(pr, side, field):
    part = pr.get(side)
    if not isinstance(part, dict):
        raise ValueError("pull request must include " + side)
    value = part.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError("missing " + side + "." + field)
    return value


def audit(snapshot):
    """Report integration blockers without claiming CI is independent verification."""
    if not isinstance(snapshot, dict):
        raise ValueError("snapshot object required")
    prs = snapshot.get("pull_requests")
    runs = snapshot.get("workflow_runs")
    required = snapshot.get("required_workflows")
    default = snapshot.get("default_branch", "main")
    if not isinstance(prs, list) or not isinstance(runs, list) or not isinstance(required, dict):
        raise ValueError("pull_requests, workflow_runs, required_workflows required")
    if not isinstance(default, str) or not default:
        raise ValueError("default_branch required")
    repository = snapshot.get("repository_full_name")
    if repository is not None and (not isinstance(repository, str) or
                                   re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None):
        raise ValueError("invalid repository_full_name")
    by_number = {}
    by_head = {}
    for pr in prs:
        if not isinstance(pr, dict) or type(pr.get("number")) is not int or pr["number"] <= 0:
            raise ValueError("invalid PR number")
        num = pr["number"]
        if num in by_number:
            raise ValueError("duplicate PR number")
        head = _pr_ref(pr, "head", "ref")
        sha = _pr_ref(pr, "head", "sha")
        _pr_ref(pr, "base", "ref")
        if not _sha(sha) or head in by_head:
            raise ValueError("invalid SHA or duplicated head branch")
        by_number[num] = pr
        by_head[head] = num
    for run in runs:
        if not isinstance(run, dict):
            raise ValueError("invalid workflow_run")
    out = []
    for num in sorted(by_number):
        pr = by_number[num]
        sha = pr["head"]["sha"]
        base = pr["base"]["ref"]
        reasons = []
        if pr.get("state") not in ("open", "closed"):
            raise ValueError("PR state must be open or closed")
        merged = pr.get("merged_at") is not None
        if merged:
            stage = "merged_to_base"
        elif pr["state"] == "closed":
            stage = "closed_unmerged"
            reasons.append("closed_unmerged")
        else:
            stage = "draft" if pr.get("draft") is True else "open_review"
            if pr.get("draft") is True:
                reasons.append("draft")
        if not merged and base != default:
            parent_number = by_head.get(base)
            reasons.append("non_default_base")
            if parent_number is None:
                reasons.append("parent_not_in_snapshot")
            elif parent_number == num:
                reasons.append("self_dependency")
            elif by_number[parent_number].get("merged_at") is None:
                reasons.append("unmerged_parent:" + str(parent_number))
            else:
                reasons.append("parent_merged_but_base_not_updated")
        names = required.get(str(num))
        if names is None or not isinstance(names, list) or not names or not all(isinstance(n, str) and n for n in names):
            ci = "unverified"
            reasons.append("required_ci_unconfigured")
            checks = []
        else:
            checks = []
            for name in sorted(set(names)):
                candidates = [r for r in runs if r.get("head_sha") == sha and
                              r.get("name") == name and r.get("event") == "pull_request" and
                              isinstance(r.get("html_url"), str) and
                              r["html_url"].startswith("https://github.com/") and
                              (repository is None or r["html_url"].startswith(
                                  "https://github.com/" + repository + "/actions/runs/"))]
                # Never allow an old successful attempt to mask a newer failure.
                # Multiple runs without comparable timestamps are ambiguous: fail closed.
                latest = None
                if len(candidates) == 1:
                    latest = candidates[0]
                elif len(candidates) > 1 and all(
                        isinstance(r.get("created_at"), str) and
                        re.fullmatch(r"\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z", r["created_at"])
                        and type(r.get("run_attempt", 1)) is int and r.get("run_attempt", 1) > 0
                        for r in candidates):
                    order = sorted(candidates, key=lambda r: (r["created_at"], r.get("run_attempt", 1)))
                    if (order[-1]["created_at"], order[-1].get("run_attempt", 1)) != (
                            order[-2]["created_at"], order[-2].get("run_attempt", 1)):
                        latest = order[-1]
                success = (latest is not None and latest.get("status") == "completed"
                           and latest.get("conclusion") == "success")
                checks.append({"name": name, "matching_success_runs": int(success)})
            ci = "snapshot_success" if all(c["matching_success_runs"] for c in checks) else "unverified"
            if ci == "unverified":
                reasons.append("ci_missing_or_stale")
        out.append({
            "pr_number": num, "head_sha": sha, "base_ref": base, "stage": stage,
            "ci_snapshot_status": ci, "ci_checks": checks,
            "blockers": sorted(set(reasons)), "merge_approved": False,
            "independent_model_evaluation": "unmeasured",
            "snapshot_authenticity": "unverified",
        })
    return {
        "schema_version": 1, "default_branch": default,
        "snapshot_authenticity": "unverified",
        "count": len(out),
        "draft_count": sum(x["stage"] == "draft" for x in out),
        "ci_snapshot_success_count": sum(x["ci_snapshot_status"] == "snapshot_success" for x in out),
        "merged_to_base_count": sum(x["stage"] == "merged_to_base" for x in out),
        "pull_requests": out,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("snapshot", type=Path)
    args = p.parse_args()
    result = audit(json.loads(args.snapshot.read_text(encoding="utf-8")))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2))


if __name__ == "__main__":
    main()
