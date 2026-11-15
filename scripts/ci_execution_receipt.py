#!/usr/bin/env python3
"""Produce a truthful GitHub Actions execution receipt for autonomous-loop research.

This receipt records only the current CI job's observable facts. It is NOT
proof of autonomous coding, source edits, or continuous activity.
"""
import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

def receipt(env, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("timezone required")
    repo = env.get("GITHUB_REPOSITORY", "")
    sha = env.get("GITHUB_SHA", "")
    run = env.get("GITHUB_RUN_ID", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("invalid repository provenance")
    if not re.fullmatch(r"[a-f0-9]{40}", sha):
        raise ValueError("invalid workflow SHA")
    if not re.fullmatch(r"[1-9][0-9]*", run):
        raise ValueError("invalid workflow run id")
    return {
        "kind": "verification", "observed_at": now.astimezone(timezone.utc).isoformat(),
        "repository": repo, "workflow_sha": sha,
        "run_url": f"https://github.com/{repo}/actions/runs/{run}",
        "source_changed_by_this_step": False,
        "coding_model_invoked_by_this_step": False,
        "continuous_autonomous_development_verified": False,
        "independent_github_attestation": False,
        "note": "GitHub environment variables are provenance claims, not independent API verification"
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = receipt(os.environ)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    except (ValueError, OSError) as exc:
        print("BLOCK:", str(exc))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
