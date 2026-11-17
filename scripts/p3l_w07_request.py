#!/usr/bin/env python3
"""Prepare an immutable W07 request only; does NOT execute Ouroboros or promote code.

GPT-6 coordinator bootstrap, NOT a Harness-Ouroboros model-authored output.
Missing W05 independent replay and W06 full CI must block actual promotion.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SPEC = "docs/p3l/W07-promotion-rollback.ko.md"
BRIDGE = "scripts/model_task_queue_bridge.py"
ALLOWED = ["scripts/ledger_candidate_promotion.py", "tests/test_ledger_candidate_promotion.py"]
MAX_SPEC_BYTES = 12_000
MAX_BRIDGE_BYTES = 20_000


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def safe_read(root, relative, maximum):
    path = root / relative
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
        raise ValueError(f"unsafe or missing input: {relative}")
    data = path.read_bytes()
    if not data or len(data) > maximum:
        raise ValueError(f"input byte limit violation: {relative}")
    data.decode("utf-8", errors="strict")
    return data


def build_request(root, commit):
    root = Path(root).resolve(strict=True)
    if not isinstance(commit, str) or SHA40.fullmatch(commit) is None:
        raise ValueError("review commit must be exact lowercase 40-hex SHA")
    spec = safe_read(root, SPEC, MAX_SPEC_BYTES)
    bridge = safe_read(root, BRIDGE, MAX_BRIDGE_BYTES)
    prompt = (
        "W07 Harness-Ouroboros worker request (awaiting prerequisite evidence). "
        "Implement ONLY scripts/ledger_candidate_promotion.py and "
        "tests/test_ledger_candidate_promotion.py; open a Draft PR to "
        "codex/p3l-eight-worker-plan. Existing files/workflows must remain unchanged. "
        "A candidate is eligible ONLY with SHA-bound W05 independent replay "
        "and 25/25 tests plus whole-Harness CI for the SAME candidate commit. "
        "Never activate, merge or promote: dry-run/isolated rollback only. "
        "Verify idempotent retries, crash recovery, prior SHA preservation, "
        "tampered/missing proofs, and correct W08 handoff. "
        "Report exact model-call provenance, tests and URLs; mocks are not execution proof."
    )
    request = {
        "schema": "p3l-worker-request-v1",
        "worker": "W07", "issue": 44, "review_commit": commit,
        "spec_path": SPEC, "spec_sha256": digest(spec),
        "bridge_path": BRIDGE, "bridge_sha256": digest(bridge),
        "allowed_output": ALLOWED, "prompt": prompt,
        "prompt_sha256": digest(prompt.encode("utf-8")),
        "prerequisites": {
            "W05_independent_replay": "NOT_ATTESTED",
            "W06_candidate_25_of_25": "NOT_ATTESTED",
            "W06_exact_candidate_commit_full_harness_ci": "NOT_ATTESTED",
        },
        "model_calls": 0, "executor_connected": False,
        "candidate_verified": False, "promotion_eligible": False,
        "promotion_authorized": False, "merge_authorized": False,
        "active_executor_modified": False,
        "status": "PREPARED_BLOCKED_ON_W05_W06",
        "generated_by": "GPT-6 infrastructure coordinator (NOT Harness-Ouroboros model)",
    }
    request["request_sha256"] = digest(canonical(request))
    return request


def verify_head(root, sha):
    proc = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                          capture_output=True, text=True, timeout=10, check=True)
    if proc.stdout.strip() != sha:
        raise ValueError("checkout HEAD mismatch")
    proc = subprocess.run(["git", "-C", str(root), "diff", "--quiet", "HEAD", "--", SPEC, BRIDGE],
                          check=False, timeout=10)
    if proc.returncode != 0:
        raise ValueError("input differs from review HEAD")


def save_request(root, path, request):
    root = Path(root).resolve(strict=True)
    path = Path(path)
    if path.is_absolute() or ".." in path.parts or path.parts[:2] != ("artifacts", "p3l-w07"):
        raise ValueError("output must be inside artifacts/p3l-w07")
    destination = root / path
    for part in (destination, *destination.parents):
        if part == root:
            break
        if part.is_symlink():
            raise ValueError("output symlink forbidden")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.resolve().is_relative_to(root):
        raise ValueError("output escapes checkout")
    contents = json.dumps(request, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if destination.exists():
        if destination.read_text(encoding="utf-8") == contents:
            return
        raise ValueError("refusing to overwrite changed request")
    with destination.open("x", encoding="utf-8") as stream:
        stream.write(contents)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--out", type=Path, default=Path("artifacts/p3l-w07/request.json"))
    args = parser.parse_args()
    try:
        root = args.root.resolve(strict=True)
        verify_head(root, args.head_sha)
        request = build_request(root, args.head_sha)
        save_request(root, args.out, request)
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError) as exc:
        print(f"BLOCK: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"worker": request["worker"], "status": request["status"],
                      "request_sha256": request["request_sha256"],
                      "model_calls": 0, "executor_connected": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
