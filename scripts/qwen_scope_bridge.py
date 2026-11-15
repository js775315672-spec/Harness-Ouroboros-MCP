#!/usr/bin/env python3
"""Bridge the new Qwen path allowlist into real model patch review.

The existing model task is still a single-string fixture change. This gate
verifies model provenance, source-anchored AST constraints, and exact allowed
paths before any disposable Docker regression begins. It NEVER executes,
applies to checkout, commits, or merges generated content.
"""
import argparse
import json
import sys
from pathlib import Path

try:
    from .qwen_task_scope_gate import validate_task as validate_qwen_scope
    from .real_repo_task import prepare
    from .cloud_real_repo_proposal import assess, TARGET
    from .disposable_regression_compare import verify_inference_provenance, _unique_json_pairs
except ImportError:
    from qwen_task_scope_gate import validate_task as validate_qwen_scope
    from real_repo_task import prepare
    from cloud_real_repo_proposal import assess, TARGET
    from disposable_regression_compare import verify_inference_provenance, _unique_json_pairs

MAX_EVIDENCE_BYTES = 120000

def verify_scoped_model_candidate(task, candidate, source):
    """Cross-check independently maintained task and Qwen allowlist contracts."""
    if not isinstance(task, dict) or not isinstance(candidate, dict):
        raise ValueError("invalid task or candidate")
    scope = validate_qwen_scope({
        "task_id": task["task_id"],
        "goal": task["goal"],
        "files": task["allowed_files"],
        "requires_human_review": True,
    })
    if scope["execution_authorized"] is not False or scope["merge_authorized"] is not False:
        raise ValueError("scope unexpectedly authorizes execution")
    assessed = assess(candidate.get("patch"), task, source)
    if assessed["status"] != "accepted_for_review":
        raise ValueError("source-anchored model diff rejected: " + str(assessed["reason"])[:160])
    paths = assessed["inspection"]["files"]
    if sorted(paths) != sorted(scope["files"]):
        raise ValueError("candidate files must exactly match the current task")
    if len(paths) != 1 or paths[0] != TARGET.as_posix():
        raise ValueError("current execution path only supports single fixture target")
    return {
        "status": "scoped_candidate_review_ready",
        "task_id": scope["task_id"],
        "touched_files": paths,
        "source_anchor_and_ast_checked": True,
        "qwen_file_allowlist_checked": True,
        "model_generated_code_executed_by_gate": False,
        "patch_applied_to_checkout": False,
        "merge_authorized": False,
        "next_action": "disposable_regression_only",
    }

def _read(path):
    payload = Path(path).read_bytes()
    if not payload or len(payload) > MAX_EVIDENCE_BYTES:
        raise ValueError("invalid evidence size")
    value = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_json_pairs)
    if not isinstance(value, dict):
        raise ValueError("evidence must be object")
    return value

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("."))
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = {"status": "blocked", "merge_authorized": False,
              "patch_applied_to_checkout": False}
    try:
        root = args.source.resolve(strict=True)
        target = root / TARGET
        if not root.is_dir() or args.source.is_symlink() or target.is_symlink() or not target.is_file():
            raise ValueError("unsafe source location")
        if not target.resolve().is_relative_to(root):
            raise ValueError("source escapes checkout")
        source = target.read_text(encoding="utf-8")
        if len(source.encode("utf-8")) > 12000:
            raise ValueError("source exceeds budget")
        provenance = verify_inference_provenance(args.inference, args.candidate, root)
        candidate = _read(args.candidate)
        report = verify_scoped_model_candidate(prepare()["task"], candidate, source)
        report["provenance"] = provenance
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
        report = {"status": "blocked", "reason": str(exc)[:200],
                  "merge_authorized": False, "patch_applied_to_checkout": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "scoped_candidate_review_ready" else 2

if __name__ == "__main__":
    sys.exit(main())
