"""C2 offline attestation of a real, read-only checkout of the operational ledger.

No network API calls and no writes to the operational ref. The independent
checkout is pinned by actions/checkout to the actual GitHub registry branch.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from audit_operational_history import (
    AGENT, errors, warnings, validate_history, check_active_registry_path)

DIR = Path("c2-ledger")
SHA = re.compile(r"^[0-9a-f]{40}$")
EXPECT_MAIN = os.environ["OFC_EXPECTED_MAIN"]


def git(*args):
    return subprocess.check_output(
        ["git", "-C", str(DIR), *args], stderr=subprocess.PIPE)


def main():
    report = {"kind": "OFC_C2_GIT_OBJECT_ATTESTATION", "agent": AGENT,
              "repository": os.environ["GITHUB_REPOSITORY"],
              "source": "actions/checkout@v6 pinned registry ref, read-only",
              "errors": errors, "warnings": warnings}
    try:
        tip = git("rev-parse", "HEAD").decode().strip()
        shas = git("rev-list", "--first-parent", "HEAD").decode().splitlines()
        if not SHA.fullmatch(tip) or not 1 <= len(shas) < 256:
            raise ValueError("missing or truncated operational Git history")
        records = []
        for sha in shas:
            commit = git("cat-file", "-p", sha)
            header = commit.split(b"\n\n", 1)[0]
            parents = [s for s in header.split(b"\n") if s.startswith(b"parent ")]
            if len(parents) > 1:
                errors.append("unexpected merge commit in registry: " + sha)
            entries = [x for x in git("ls-tree", "-z", sha).split(b"\0") if x]
            if len(entries) != 1 or b"\t" not in entries[0]:
                errors.append("unexpected Git tree structure: " + sha)
                break
            meta, path = entries[0].split(b"\t", 1)
            fields = meta.split()
            if (len(fields) != 3 or fields[:2] != [b"100644", b"blob"]
                    or path not in (b"state.json", b"state.json\r")):
                errors.append("unexpected Git path: " + sha + " " + repr(path))
                break
            state = json.loads(git("cat-file", "blob", fields[2].decode()))
            records.append({"sha": sha, "path": path.decode("utf-8"),
                            "state": state})
        if not records or len(records) != len(shas):
            raise RuntimeError("incomplete Git ledger traversal")
        records.reverse()
        check_active_registry_path(records)
        report["history"] = validate_history(records, EXPECT_MAIN)
        legacy = [x["sha"] for x in records if x["path"] == "state.json\r"]
        report["legacy_carriage_return_commits"] = legacy
        if legacy:
            warnings.append("historical CR file recorded without rewriting Git history")
        report["registry_sha"] = tip
        report["git_commit_count"] = len(records)
        report["all_commits_pinned"] = all(SHA.fullmatch(x["sha"]) for x in records)
        report["current_source_equals_expected_main"] = (
            records[-1]["state"].get("source") == EXPECT_MAIN)
    except Exception as exc:
        errors.append(type(exc).__name__ + ": " + str(exc))
    report["pass"] = not errors
    out = Path("artifacts/ofc-c2-live-git-audit.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("OFC_C2_LIVE_GIT_AUDIT=" + json.dumps(report, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
