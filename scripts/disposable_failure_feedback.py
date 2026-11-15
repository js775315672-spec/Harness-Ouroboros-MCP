#!/usr/bin/env python3
"""Classify disposable test failures for a bounded next-run Qwen repair request.

Read-only: no model call, no code execution, no patch application. A failed
container test cannot be rerun with a fresh model proposal inside this job.
"""
import argparse
import json
from pathlib import Path
from qwen_repair_request import repair_request

def classify(inference, regression):
    if not isinstance(inference, dict) or not isinstance(regression, dict):
        raise ValueError("malformed evidence")
    if inference.get("status") != "accepted_for_review":
        return {"decision": "stop", "reason": "inference_not_accepted",
                "model_called": False, "patch_applied": False}
    if regression.get("status") == "isolated_regression_passed":
        return {"decision": "no_repair_needed", "model_called": False,
                "patch_applied": False}
    if regression.get("status") not in ("regression_failed", "error"):
        raise ValueError("unknown regression status")
    if regression.get("merge_authorized") is not False or regression.get("patch_applied_to_checkout") is not False:
        raise ValueError("unsafe regression evidence")
    attempts = inference.get("real_model_calls")
    if type(attempts) is not int or not 1 <= attempts <= 2:
        raise ValueError("invalid model call count")
    kind = "disposable_regression"
    if regression.get("error_type") in ("ValueError", "SyntaxError"):
        kind = "source_context"
    reason = regression.get("error_type") or regression.get("status")
    task = {"task_id": "feedback_parser_regression",
            "allowed_files": ["tests/test_model_feedback_loop.py"],
            "goal": "Repair a source-anchored regression fixture"}
    result = repair_request(task, {"kind": kind, "reason": str(reason)}, attempts)
    result["executed_repair_model_call"] = False
    result["next_run_only"] = result["decision"] == "request_repair"
    return result

def read_json(path):
    data = Path(path).read_bytes()
    if not data or len(data) > 120000:
        raise ValueError("evidence size out of bounds")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result
    obj = json.loads(data.decode("utf-8"), object_pairs_hook=unique)
    if not isinstance(obj, dict):
        raise ValueError("evidence must be object")
    return obj

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--regression", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = classify(read_json(args.inference), read_json(args.regression))
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        result = {"decision": "blocked", "reason": str(exc)[:200],
                  "model_called": False, "patch_applied": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["decision"] in ("no_repair_needed", "request_repair", "stop") else 2

if __name__ == "__main__":
    raise SystemExit(main())
