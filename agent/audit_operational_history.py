"""Read-only audit of the operational Git ledger, its commit ancestry, and PR receipts.

Run in a PR CI checkout with GITHUB_TOKEN, GITHUB_REPOSITORY and OFC_AGENT set.
All HTTP operations are GET. No production branch or ledger mutations.
"""
import base64
import json
import os
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen

REPO = os.environ["GITHUB_REPOSITORY"]
AGENT = os.environ["OFC_AGENT"]
TOKEN = os.environ.get("GITHUB_TOKEN", "")
API = "https://api.github.com/repos/" + REPO + "/"
SHA = re.compile(r"^[0-9a-f]{40}$")
RECEIPT = re.compile(r"^https://github\.com/([^/]+/[^/]+)/pull/([1-9]\d*)@([0-9a-f]{40})$")
errors = []
warnings = []


def fail(msg):
    errors.append(msg)


def get(path):
    headers = {"Accept": "application/vnd.github+json",
               "User-Agent": "OFC-operational-ledger-audit"}
    if TOKEN:
        headers["Authorization"] = "Bearer " + TOKEN
    request = Request(API + path, headers=headers)
    with urlopen(request, timeout=25) as response:
        return json.load(response)


def tip(name):
    return get("git/ref/heads/" + name)["object"]["sha"]


def traverse():
    sha = tip("ofc-cycle-registry-v1")
    latest = sha
    records = []
    seen = set()
    for _ in range(256):
        if sha in seen or not SHA.fullmatch(sha):
            raise RuntimeError("invalid or cyclic registry commit ancestry")
        seen.add(sha)
        commit = get("git/commits/" + sha)
        parents = [p["sha"] for p in commit.get("parents", [])]
        if len(parents) > 1:
            fail("registry contains a merge commit at " + sha)
        tree = get("git/trees/" + commit["tree"]["sha"])
        entries = tree.get("tree", [])
        # 2026-11-21 legacy Windows text-mode mktree wrote state.json + CR.
        # Preserve that immutable evidence; audit it without repairing history.
        if (len(entries) != 1 or entries[0].get("path") not in
                ("state.json", "state.json\r") or entries[0].get("type") != "blob"):
            fail("unexpected registry tree contents at " + sha +
                 ": " + repr([e.get("path") for e in entries]))
            break
        path = entries[0]["path"]
        blob = get("git/blobs/" + entries[0]["sha"])
        if blob.get("encoding") != "base64":
            raise RuntimeError("unsupported Git blob encoding")
        state = json.loads(base64.b64decode(blob["content"]).decode("utf-8"))
        records.append({"sha": sha, "state": state, "path": path})
        if not parents:
            break
        sha = parents[0]
    else:
        fail("registry ancestry exceeded 256 commits")
    records.reverse()
    return latest, records


def validate_history(records, main_sha):
    cycle_ids = []
    generation_increments = 0
    completed_cycles = 0
    result_additions = 0
    receipt_values_seen = {}
    operation_keys_seen = {}
    repeated_values = []
    repeated_keys = set()
    prior = None
    for item in records:
        s = item["state"]
        short = item["sha"][:10]
        if s.get("agent") != AGENT or s.get("schema") != 1:
            fail("ledger identity/schema mismatch: " + short)
        if not isinstance(s.get("generation"), int) or s["generation"] < 1:
            fail("invalid generation: " + short)
            continue
        if s.get("cycle") not in cycle_ids:
            cycle_ids.append(s.get("cycle"))
        if s.get("phase") not in ("open", "complete", "blocked"):
            fail("invalid phase: " + short)
        if not isinstance(s.get("results"), dict):
            fail("invalid results shape: " + short)
            continue
        if s.get("pending") is not None and not isinstance(s["pending"], str):
            fail("invalid pending type: " + short)
        if prior is not None:
            p = prior
            delta = s["generation"] - p["generation"]
            if delta not in (0, 1):
                fail("non-monotonic or skipped generation at " + short)
            if delta == 1:
                generation_increments += 1
            if s["cycle"] != p["cycle"] and p.get("phase") != "complete":
                fail("cycle changed without completed predecessor at " + short)
            if s["cycle"] == p["cycle"]:
                if s.get("source") != p.get("source"):
                    fail("source changed inside a cycle at " + short)
                for key, value in p["results"].items():
                    if key not in s["results"] or s["results"][key] != value:
                        fail("receipt removed or overwritten at " + short)
                new = set(s["results"]) - set(p["results"])
                result_additions += len(new)
                if p.get("pending") and s.get("pending") is None:
                    if (p["pending"] not in s["results"]
                            and s["phase"] != "blocked"):
                        fail("pending operation disappeared without receipt: " + short)
            if s["phase"] == "complete" and p["phase"] != "complete":
                completed_cycles += 1
        else:
            result_additions += len(s["results"])
        if s.get("pending") in s["results"]:
            fail("pending operation already appears in results: " + short)
        if len(set(s["results"].values())) != len(s["results"]):
            fail("duplicate receipt values at " + short)
        added = (set(s["results"]) if prior is None or
                 s["cycle"] != prior["cycle"]
                 else set(s["results"]) - set(prior["results"]))
        for key in added:
            value = s["results"][key]
            if value in receipt_values_seen and receipt_values_seen[value] != s["cycle"]:
                repeated_values.append({"key": key, "commit": item["sha"]})
            if key in operation_keys_seen and operation_keys_seen[key] != s["cycle"]:
                repeated_keys.add(key)
            receipt_values_seen.setdefault(value, s["cycle"])
            operation_keys_seen.setdefault(key, s["cycle"])
        prior = s

    if repeated_values:
        fail("exact external evidence duplicated across distinct cycles: " +
             repr(repeated_values))
    if repeated_keys:
        warnings.append("operation names reused across distinct cycles; only cycle-qualified identity and independent receipts can authorize effects: " + repr(sorted(repeated_keys)))
    latest = records[-1]["state"]
    if latest.get("source") != main_sha:
        fail("operational ledger source does not match current main")
    if latest.get("pending") is not None:
        warnings.append("unresolved pending operation in latest ledger")
    if latest.get("expires") == 0 and latest.get("phase") == "open":
        warnings.append("open ledger is released; not an active lease")
    return {"git_commits": len(records), "first_sha": records[0]["sha"],
            "latest_state_generation": latest.get("generation"),
            "generation_increments": generation_increments,
            "distinct_cycle_ids": len(cycle_ids),
            "completed_cycle_transitions": completed_cycles,
            "result_additions_within_cycles": result_additions,
            "cross_cycle_duplicate_receipt_values": len(repeated_values),
            "reused_operation_names_across_cycles": sorted(repeated_keys),
            "current_phase": latest.get("phase"),
            "current_pending": latest.get("pending"),
            "current_result_count": len(latest.get("results", {})),
            "current_source": latest.get("source"),
            "current_checkpoint": latest.get("checkpoint")}


def audit_receipts(results):
    checked = []
    for key, value in results.items():
        match = RECEIPT.fullmatch(value) if isinstance(value, str) else None
        if not match or match.group(1) != REPO:
            fail("receipt is not a same-repository PR@SHA reference: " + key)
            continue
        _, number, pinned = match.groups()
        pr = get("pulls/" + number)
        if pr.get("number") != int(number) or pr.get("base", {}).get("repo", {}).get("full_name") != REPO:
            fail("PR receipt repository identity mismatch: " + key)
        actual_head = pr.get("head", {}).get("sha")
        match_status = actual_head == pinned
        if not match_status:
            # Older pinned heads can remain valid after later PR commits.
            commits = get("pulls/" + number + "/commits?per_page=100")
            match_status = any(item.get("sha") == pinned for item in commits)
        if not match_status:
            fail("receipt pinned SHA not confirmed in PR commit history: " + key)
        checked.append({"operation": key, "pr": int(number), "pinned_sha": pinned,
                        "head_matches": actual_head == pinned,
                        "seen_in_pr_commits": match_status,
                        "merged": pr.get("merged") is True,
                        "draft": pr.get("draft") is True,
                        "state": pr.get("state")})
    return checked


def check_active_registry_path(records):
    """Legacy CR paths are historical evidence, never valid active refs."""
    if not records or records[-1]["path"] != "state.json":
        fail("active registry tip has noncanonical path; manual repair required")



def main():
    report = {"repository": REPO, "agent": AGENT,
              "scope": "READ_ONLY_REAL_GIT_HISTORY_AND_PR_RECEIPTS",
              "errors": errors, "warnings": warnings}
    try:
        main_sha = tip("main")
        tip_sha, records = traverse()
        if not records:
            raise RuntimeError("empty operational registry history")
        legacy = [item["sha"] for item in records if item["path"] == "state.json\r"]
        report["legacy_cr_filename_commit_shas"] = legacy
        if legacy:
            warnings.append("historical CR-suffixed state.json filename in " + str(len(legacy)) + " commits; not silently normalized")
        check_active_registry_path(records)
        report["registry_tip_sha"] = tip_sha
        report["main_sha"] = main_sha
        report["history"] = validate_history(records, main_sha)
        report["receipts"] = audit_receipts(records[-1]["state"].get("results", {}))
        if tip("ofc-cycle-registry-v1") != tip_sha or tip("main") != main_sha:
            fail("registry or main ref moved during the read-only audit")
        report["chain_shas_oldest_first"] = [item["sha"] for item in records]
        report["claim"] = ("Generation is a lease fencing counter; "
                           "AI self-improvement completion count cannot be inferred from it.")
    except Exception as exc:
        fail(type(exc).__name__ + ": " + str(exc))
    report["status"] = "PASS" if not errors else "FAIL"
    output = Path("artifacts") / "ofc-operational-ledger-audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    print("OFC_LEDGER_AUDIT=" + json.dumps(report, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
