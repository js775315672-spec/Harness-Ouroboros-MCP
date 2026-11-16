#!/usr/bin/env python3
"""Fail-closed anti-stagnation contract for bounded CPU coding-model retries.

Pure evidence checker: makes no LLM calls, invokes no subprocess, touches no
source, and has NO permission to create commits, branches or PRs.

Important limitation: caller-supplied "independent_replay" is a declaration,
not proof. A separate exact-SHA GitHub CI attestor must verify the underlying
raw records before passing them to this gate. Never label this planner a CI
attestor or evidence of an autonomous model developer.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

SHA = re.compile(r"[a-f0-9]{64}\Z")
MAX_RESPONSE_BYTES = 6000
MAX_ATTEMPTS = 5
FIELDS = frozenset((
    "attempt", "task_sha256", "model_sha256", "baseline_source_sha256",
    "raw_response", "response_sha256", "candidate_source_sha256",
    "outcome", "rejection_reason", "independent_replay"
))
OUTCOMES = frozenset(("static_rejected", "candidate_failed",
                      "candidate_passed"))
NO_OP_REASONS = frozenset(("model source changed nothing",
                           "candidate AST unchanged", "source unchanged"))


def _sha(value):
    return type(value) is str and SHA.fullmatch(value) is not None


def _record(row, attempt, task, model, baseline):
    if type(row) is not dict or frozenset(row) != FIELDS:
        raise ValueError("missing or unexpected model evidence fields")
    if type(row["attempt"]) is not int or row["attempt"] != attempt:
        raise ValueError("model attempts must be contiguous and sequential")
    if (row["task_sha256"] != task or row["model_sha256"] != model
            or row["baseline_source_sha256"] != baseline):
        raise ValueError("model evidence belongs to another task/model/source")
    raw = row["raw_response"]
    if (type(raw) is not str
            or not 1 <= len(raw.encode("utf-8")) <= MAX_RESPONSE_BYTES
            or any(c in raw for c in ("\x00", "\x1b", "\r"))):
        raise ValueError("missing, oversized or dangerous raw model response")
    if (not _sha(row["response_sha256"]) or
            hashlib.sha256(raw.encode("utf-8")).hexdigest()
            != row["response_sha256"]):
        raise ValueError("raw model response digest mismatch")
    if row["independent_replay"] is not True:
        raise ValueError("unreplayed model outcome is not reliable")
    if row["outcome"] not in OUTCOMES or type(row["outcome"]) is not str:
        raise ValueError("invalid model outcome")
    candidate = row["candidate_source_sha256"]
    reason = row["rejection_reason"]
    if type(reason) is not str or len(reason) > 140:
        raise ValueError("invalid failure reason")
    if row["outcome"] == "static_rejected":
        if candidate is not None or not reason:
            raise ValueError("static rejection must not carry accepted source")
    elif not _sha(candidate) or candidate == baseline or reason:
        raise ValueError("candidate source is unchanged or outcome is contradictory")
    return row["response_sha256"], row["outcome"] == "static_rejected" and (
        reason in NO_OP_REASONS)


def evaluate(history, task_sha256, model_sha256, baseline_source_sha256,
             max_attempts=3):
    """Return stop or permit a SINGLE additional attempt; no work is done.

    The verdict is valid only for the same immutable task/model/baseline trio.
    It intentionally stops repeated exact answers and distinct no-op answers.
    A successful candidate means *review*, not automatic source promotion.
    """
    if (not all(_sha(x) for x in (task_sha256, model_sha256,
                                 baseline_source_sha256))
            or type(max_attempts) is not int
            or not 1 <= max_attempts <= MAX_ATTEMPTS
            or type(history) is not list or len(history) > max_attempts):
        raise ValueError("invalid immutable model task or bounded retry history")
    if any(type(row) is not dict for row in history):
        raise ValueError("invalid model evidence record")
    seen = set()
    noop_count = 0
    last_passed = False
    duplicate = False
    for attempt, row in enumerate(history, 1):
        reply_sha, noop = _record(row, attempt, task_sha256, model_sha256,
                                  baseline_source_sha256)
        if last_passed:
            raise ValueError("additional model calls after a passing candidate")
        duplicate = duplicate or reply_sha in seen
        seen.add(reply_sha)
        noop_count += int(noop)
        last_passed = row["outcome"] == "candidate_passed"

    reason = None
    if last_passed:
        reason = "passing_candidate_requires_human_review"
    elif duplicate:
        reason = "duplicate_model_response"
    elif noop_count >= 2:
        reason = "repeated_unchanged_source"
    elif len(history) >= max_attempts:
        reason = "retry_budget_exhausted"
    if reason is not None:
        return {
            "decision": "stop", "reason": reason, "attempts": len(history),
            "model_call_performed": False, "merge_authorized": False,
            "requires_human_review": True,
            "external_ci_attested": False
        }
    return {
        "decision": "allow_one_model_call", "next_attempt": len(history) + 1,
        "attempts": len(history), "max_attempts": max_attempts,
        "model_call_performed": False, "merge_authorized": False,
        "requires_human_review": True, "external_ci_attested": False
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--task-sha256", required=True)
    parser.add_argument("--model-sha256", required=True)
    parser.add_argument("--baseline-source-sha256", required=True)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if (args.history.is_symlink() or not args.history.is_file()
                or args.history.stat().st_size > 65000):
            raise ValueError("missing, linked or oversized prior response evidence")
        history = json.loads(args.history.read_text(encoding="utf-8"))
        verdict = evaluate(history, args.task_sha256, args.model_sha256,
                           args.baseline_source_sha256, args.max_attempts)
    except (ValueError, TypeError, OSError, UnicodeError,
            json.JSONDecodeError) as exc:
        verdict = {"decision": "blocked", "reason": str(exc)[:180],
                   "model_call_performed": False, "merge_authorized": False,
                   "external_ci_attested": False}
    if args.output:
        if args.output.exists() or args.output.is_symlink():
            print("BLOCK: refusing to overwrite evidence", file=sys.stderr)
            return 2
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(verdict, sort_keys=True, indent=2)
                               + "\n", encoding="utf-8")
    print(json.dumps(verdict, sort_keys=True))
    return 0 if verdict["decision"] == "allow_one_model_call" else 2


if __name__ == "__main__":
    sys.exit(main())
