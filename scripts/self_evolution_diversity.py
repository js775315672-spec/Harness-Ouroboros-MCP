#!/usr/bin/env python3
"""P1c: read-only candidate diversity aggregation; no attestation/merge power.

Consumes model-lane and separate-runner replay reports. This is a conservative
descriptive tally, NOT cryptographic attestation or permission to spawn children.
The CI that produces the replay reports must separately bind exact source SHA,
frozen holdouts, original raw output, and Docker regression outcomes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

LANES = ("01", "02")
HASH64 = re.compile(r"[0-9a-f]{64}\Z")
HASH40 = re.compile(r"[0-9a-f]{40}\Z")
VARIANT = "p1b-v2-exact-fence-and-boolean-prompt"


def _hash(value):
    return isinstance(value, str) and bool(HASH64.fullmatch(value))


def _unique_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate JSON evidence keys")
        obj[key] = value
    return obj


def _read(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 40000:
        raise ValueError("unsafe or oversized evidence file")
    return json.loads(path.read_text(encoding="utf-8"),
                      object_pairs_hook=_unique_pairs)


def summarize(model_rows, replay_rows, reviewed_sha):
    """Report observed *unique code bytes*, never count duplicate code as diversity."""
    if not isinstance(reviewed_sha, str) or not HASH40.fullmatch(reviewed_sha):
        raise ValueError("invalid reviewed commit SHA")
    if (type(model_rows) is not list or type(replay_rows) is not list
            or len(model_rows) != 2 or len(replay_rows) != 2):
        raise ValueError("both original and replay reports required")
    if any(not isinstance(x, dict) for x in model_rows + replay_rows):
        raise ValueError("report must be an object")
    model_by_lane = {x.get("lane"): x for x in model_rows}
    replay_by_lane = {x.get("lane"): x for x in replay_rows}
    if (set(model_by_lane) != set(LANES)
            or set(replay_by_lane) != set(LANES)):
        raise ValueError("lane evidence missing or duplicated")
    hashes = {}
    architectures = set()
    prompt_hashes = set()
    passes = 0
    details = []
    for lane in LANES:
        model = model_by_lane[lane]
        proof = replay_by_lane[lane]
        if (model.get("source_sha") != reviewed_sha
                or model.get("study_variant") != VARIANT
                or type(model.get("model_calls")) is not int
                or model["model_calls"] != 1
                or type(model.get("ci_attested_patches")) is not int
                or model["ci_attested_patches"] != 0
                or model.get("checkout_modified") is not False
                or model.get("merge_authorized") is not False
                or proof.get("merge_authorized") is not False
                or not _hash(model.get("contract_sha256"))
                or not _hash(model.get("holdout_sha256"))
                or not _hash(model.get("prompt_sha256"))
                or not _hash(model.get("response_sha256"))):
            raise ValueError("untrusted model evidence metadata")
        if (not isinstance(model.get("architecture"), str)
                or len(model["architecture"]) > 64):
            raise ValueError("untrusted architecture identity")
        architectures.add(model["architecture"])
        prompt_hashes.add(model["prompt_sha256"])
        outcome = model.get("outcome")
        status = proof.get("status")
        if outcome == "static_gate_rejected":
            valid = (status == "static_rejection_replayed"
                     and proof.get("candidate_passed") is False
                     and model.get("candidate_sha256") is None
                     and model.get("evaluation") is None)
        elif outcome in ("model_candidate_passed", "model_candidate_failed"):
            code_hash = model.get("candidate_sha256")
            valid = (
                _hash(code_hash)
                and status == "candidate_replayed"
                and type(proof.get("candidate_passed")) is bool
                and proof.get("candidate_sha256") == code_hash
                and proof["candidate_passed"] == (
                    outcome == "model_candidate_passed")
                and isinstance(model.get("evaluation"), dict)
                and model["evaluation"].get("status") == outcome)
        else:
            valid = False
        if not valid:
            raise ValueError("replay mismatch or false success")
        passed = outcome == "model_candidate_passed"
        if passed:
            passes += 1
            hashes.setdefault(model["candidate_sha256"], []).append(lane)
        details.append({"lane": lane, "outcome": outcome,
                        "cross_runner_replayed": True,
                        "candidate_passed": passed,
                        "candidate_sha256": model.get("candidate_sha256")})
    if len(architectures) != 2 or len(prompt_hashes) != 2:
        raise ValueError("identical architecture or prompt contract")
    return {"schema": 1, "status": "diversity_observed_not_ci_attested",
            "reviewed_sha": reviewed_sha, "model_trials": 2,
            "cross_runner_replayed_passing_trials": passes,
            "unique_passing_source_candidates": len(hashes),
            "duplicate_source_groups": [
                {"source_sha256": h, "lanes": lanes}
                for h, lanes in sorted(hashes.items())
                if len(lanes) > 1],
            "lanes": details, "distinct_source_bytes_observed": len(hashes) == 2,
            "architecture_diversity_proven": False,
            "ci_attested_source_commits": 0, "recursive_parent_promotions": 0,
            "remote_push_authorized": False, "merge_authorized": False}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--reviewed-sha", required=True)
    p.add_argument("--models", nargs=2, type=Path, required=True)
    p.add_argument("--replays", nargs=2, type=Path, required=True)
    p.add_argument("--report", required=True, type=Path)
    args = p.parse_args()
    if args.report.exists() or args.report.is_symlink():
        raise SystemExit("never overwrite diversity evidence")
    report = summarize([_read(x) for x in args.models],
                       [_read(x) for x in args.replays],
                       args.reviewed_sha)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps({"status": report["status"],
                      "replayed_passes": report["cross_runner_replayed_passing_trials"],
                      "unique_code": report["unique_passing_source_candidates"],
                      "recursive_parent_promotions": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
