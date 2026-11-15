#!/usr/bin/env python3
"""Strict audit of autonomous coding activity, not repeated test invocations.

Read-only. Inputs are externally supplied evidence and are NOT authenticated
GitHub attestations. Never label a trial verified without external attestation.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

def _time(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    if dt.tzinfo is None:
        raise ValueError("timezone required")
    return dt.astimezone(timezone.utc)

def audit(events, window_start, window_end, max_gap_seconds=300):
    start, end = _time(window_start), _time(window_end)
    duration = (end-start).total_seconds()
    if duration < 3600 or duration > 7200:
        raise ValueError("trial must cover at least 60 minutes and at most 120")
    if type(max_gap_seconds) is not int or not 1 <= max_gap_seconds <= 600:
        raise ValueError("invalid continuity gap")
    if not isinstance(events, list) or len(events) > 1000:
        raise ValueError("invalid events")
    ordered = []
    commits = set()
    for event in events:
        if not isinstance(event, dict) or set(event) != {"at", "kind", "commit", "checks_passed", "user_prompted", "attested"}:
            raise ValueError("malformed event")
        at = _time(event["at"])
        if not start <= at <= end:
            raise ValueError("event outside trial window")
        if event["kind"] not in ("code_change", "verification", "repair", "next_task"):
            raise ValueError("unsupported event kind")
        if any(type(event[key]) is not bool for key in ("checks_passed", "user_prompted", "attested")):
            raise ValueError("invalid evidence flags")
        commit = event["commit"]
        if commit is not None and (not isinstance(commit, str) or len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit)):
            raise ValueError("invalid commit")
        if event["kind"] == "code_change" and commit is None:
            raise ValueError("code change requires commit")
        if event["kind"] == "code_change" and commit in commits:
            raise ValueError("duplicate code change commit")
        if event["kind"] == "code_change":
            commits.add(commit)
        ordered.append((at, event))
    ordered.sort(key=lambda pair: pair[0])
    actual = [pair for pair in ordered if pair[1]["kind"] in ("code_change", "repair", "next_task")]
    passing_changes = [pair for pair in actual if pair[1]["kind"] == "code_change" and pair[1]["checks_passed"]]
    gaps = [(b[0]-a[0]).total_seconds() for a,b in zip(actual, actual[1:])]
    boundary_gaps = ([ (actual[0][0]-start).total_seconds(), (end-actual[-1][0]).total_seconds()] if actual else [duration])
    max_gap = max(gaps + boundary_gaps)
    external_attestation_complete = bool(actual) and all(e["attested"] for _,e in actual)
    independent = bool(actual) and all(not e["user_prompted"] for _,e in actual)
    sustained = (len(passing_changes) >= 2 and
                 any(e["kind"] == "next_task" for _,e in actual) and
                 max_gap <= max_gap_seconds and independent and external_attestation_complete)
    return {"decision": "verified_60_min_autonomous_development" if sustained else "not_proven",
            "window_seconds": duration, "actual_code_change_count": len(commits),
            "passing_code_change_count": len(passing_changes),
            "verification_repetitions_excluded": sum(e["kind"] == "verification" for _,e in ordered),
            "max_activity_gap_seconds": max_gap,
            "user_independent": independent,
            "external_attestation_claims_present": external_attestation_complete,
            "external_attestation_independently_verified": False,
            "note": "A positive decision is conditional on external authentication of all evidence; this script cannot attest GitHub."}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    args = parser.parse_args()
    try:
        events = json.loads(args.events.read_text(encoding="utf-8"))
        result = audit(events, args.start, args.end)
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        print(json.dumps({"decision": "blocked", "reason": str(exc)[:200]}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
