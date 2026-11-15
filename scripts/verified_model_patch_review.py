#!/usr/bin/env python3
"""Review an archived model-authored candidate without mutating its source.

Offline mode proves source/candidate hashes and AST guard; Docker mode repeats
baseline, negative controls, and candidate regression in disposable containers.
Neither mode commits, pushes, merges, deploys or authorizes a live trade.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from qwen_source_guard import TARGET
from qwen_semantic_source_guard import inspect_semantic_line
from qwen_semantic_disposable_compare import compare_line

FIELDS = {
    "schema_version", "task_id", "engine", "model", "model_repo",
    "source_sha256", "candidate_line_sha256", "candidate_line",
    "model_response_sha256", "successful_run", "outcome", "model_calls",
    "docker_comparisons", "baseline_regression_tests",
    "candidate_regression_tests", "candidate_negative_tests",
    "source_checkout_modified", "merge_authorized", "human_review_required"
}
HASH = re.compile(r"[0-9a-f]{64}\Z")
RUN = re.compile(
    r"https://github\.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/[1-9][0-9]*\Z"
)


def inspect_proposal(root, evidence_path):
    root = Path(root).resolve(strict=True)
    path = Path(evidence_path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16_384:
        raise ValueError("unsafe proposal evidence")
    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict) or set(record) != FIELDS:
        raise ValueError("invalid proposal evidence schema")
    if (type(record["schema_version"]) is not int or record["schema_version"] != 1
            or record["task_id"] != "feedback_cycle_guard"
            or record["model"] != "7b"
            or record["model_repo"] != "Qwen/Qwen2.5-Coder-7B-Instruct-GGUF"
            or record["engine"] != "llama.cpp"
            or record["outcome"] != "isolated_source_repair_passed"
            or record["source_checkout_modified"] is not False
            or record["merge_authorized"] is not False
            or record["human_review_required"] is not True):
        raise ValueError("proposal scope or safety mismatch")
    if not all(type(record[k]) is int and record[k] >= 1 for k in (
            "model_calls", "docker_comparisons", "baseline_regression_tests",
            "candidate_regression_tests", "candidate_negative_tests")):
        raise ValueError("invalid evidence counters")
    for key in ("source_sha256", "candidate_line_sha256", "model_response_sha256"):
        if not isinstance(record[key], str) or not HASH.fullmatch(record[key]):
            raise ValueError("invalid evidence digest")
    if not isinstance(record["successful_run"], str) or not RUN.fullmatch(record["successful_run"]):
        raise ValueError("invalid referenced workflow run")
    src = root / TARGET
    if src.is_symlink() or not src.is_file():
        raise ValueError("unsafe target source")
    data = src.read_bytes()
    if hashlib.sha256(data).hexdigest() != record["source_sha256"]:
        raise ValueError("source baseline does not match model evidence")
    line = record["candidate_line"]
    if not isinstance(line, str) or len(line) > 350 or "\n" in line:
        raise ValueError("invalid archived candidate")
    if hashlib.sha256(line.encode("utf-8")).hexdigest() != record["candidate_line_sha256"]:
        raise ValueError("candidate digest does not match model evidence")
    inspection = inspect_semantic_line(line, data.decode("utf-8"))
    if (inspection["source_sha256"] != record["source_sha256"] or
            inspection["line_sha256"] != record["candidate_line_sha256"] or
            inspection["merge_authorized"] is not False):
        raise ValueError("trusted AST inspection mismatch")
    return record, inspection


def replay(root, evidence_path, docker=False):
    record, inspected = inspect_proposal(root, evidence_path)
    if not docker:
        return {"status": "static_review_only", "ast_inspected": True,
                "docker_replayed": False, "merge_authorized": False,
                "candidate_line_sha256": inspected["line_sha256"]}
    result = compare_line(root, record["candidate_line"])
    checks = [
        result.get("status") == "isolated_source_repair_passed",
        result.get("source_sha256") == record["source_sha256"],
        result.get("candidate_line_sha256") == record["candidate_line_sha256"],
        result.get("source_checkout_modified") is False,
        result.get("merge_authorized") is False,
        result.get("network_disabled") is True,
        result.get("filesystem_read_only") is True,
        isinstance(result.get("baseline_regression"), dict)
            and result["baseline_regression"].get("passed") is True
            and result["baseline_regression"].get("tests_run") == record["baseline_regression_tests"],
        isinstance(result.get("baseline_negative_control"), dict)
            and result["baseline_negative_control"].get("passed") is False
            and result["baseline_negative_control"].get("tests_run") == record["candidate_negative_tests"],
        isinstance(result.get("candidate_regression"), dict)
            and result["candidate_regression"].get("passed") is True
            and result["candidate_regression"].get("tests_run") == record["candidate_regression_tests"],
        isinstance(result.get("candidate_negative_control"), dict)
            and result["candidate_negative_control"].get("passed") is True
            and result["candidate_negative_control"].get("tests_run") == record["candidate_negative_tests"]
    ]
    if not all(checks):
        raise ValueError("independent Docker replay failed")
    return {"status": "isolated_replay_passed", "ast_inspected": True,
            "docker_replayed": True, "merge_authorized": False,
            "candidate_line_sha256": inspected["line_sha256"],
            "baseline_regression_tests": record["baseline_regression_tests"],
            "candidate_regression_tests": record["candidate_regression_tests"],
            "candidate_negative_tests": record["candidate_negative_tests"]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--evidence", type=Path,
                   default=Path("proposals/feedback_cycle_guard_7b.json"))
    p.add_argument("--docker", action="store_true")
    p.add_argument("--report", type=Path, required=True)
    args = p.parse_args()
    result = {"status": "blocked", "merge_authorized": False}
    try:
        result = replay(args.root, args.evidence, docker=args.docker)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError,
            json.JSONDecodeError) as exc:
        result["error_type"] = type(exc).__name__
        result["error_code"] = "verification_blocked"
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in ("static_review_only", "isolated_replay_passed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
