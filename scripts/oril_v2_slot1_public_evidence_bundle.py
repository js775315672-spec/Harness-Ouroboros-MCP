#!/usr/bin/env python3
"""Fail-closed public Qwen evidence bundle; provenance remains unverified."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from oril_v2_slot5_public_ab_aa_reconciliation import read_unique, reconcile

MAX_BYTES = 4 * 1024 * 1024

def file_digest(path):
    p = Path(path)
    if not p.is_file() or p.is_symlink():
        raise ValueError("input must be regular non-symlink file")
    if p.stat().st_size > MAX_BYTES:
        raise ValueError("oversized report")
    return hashlib.sha256(p.read_bytes()).hexdigest()

def bundle(ab_path, aa_path, *, ab_run, aa_run, ab_sha, aa_sha):
    if Path(ab_path).resolve() == Path(aa_path).resolve():
        raise ValueError("A/B and A/A inputs must differ")
    if not all(isinstance(v, int) and v > 0 for v in (ab_run, aa_run)):
        raise ValueError("invalid Actions run id")
    if ab_run == aa_run:
        raise ValueError("A/B and A/A run IDs must differ")
    for s in (ab_sha, aa_sha):
        if len(s) != 40 or any(c not in "0123456789abcdef" for c in s):
            raise ValueError("invalid commit SHA")
    digests = (file_digest(ab_path), file_digest(aa_path))
    if digests[0] == digests[1]:
        raise ValueError("identical raw reports")
    result = reconcile(read_unique(ab_path), read_unique(aa_path))
    return {
        "schema_version": 1,
        "evidence_kind": "public_cpu_cross_run_unattested",
        "source": {
            "ab": {"actions_run_url": f"https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/{ab_run}",
                   "claimed_head_sha": ab_sha, "raw_sha256": digests[0]},
            "aa": {"actions_run_url": f"https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/{aa_run}",
                   "claimed_head_sha": aa_sha, "raw_sha256": digests[1]},
        },
        "cross_run_audit": result,
        "artifacts_retrieved_by_independent_verifier": False,
        "source_run_sha_verified_via_github_api": False,
        "independent_heldout_quality_proven": False,
        "gpu_lora_training_proven": False,
        "causal_speed_gain_proven": False,
        "decision": "판단불가",
        "next_action": "Independently fetch each Actions artifact and compare API head SHA, archive digest, and raw digest before trusted evaluation.",
    }

def main():
    p = argparse.ArgumentParser()
    for key in ("ab", "aa", "output", "ab_sha", "aa_sha"):
        p.add_argument("--" + key.replace("_", "-"), required=True)
    p.add_argument("--ab-run", required=True, type=int)
    p.add_argument("--aa-run", required=True, type=int)
    a = p.parse_args()
    dest = Path(a.output)
    if dest.exists() or dest.is_symlink() or dest.resolve() in (Path(a.ab).resolve(), Path(a.aa).resolve()):
        raise ValueError("output must be new and distinct from inputs")
    data = bundle(a.ab, a.aa, ab_run=a.ab_run, aa_run=a.aa_run, ab_sha=a.ab_sha, aa_sha=a.aa_sha)
    dest.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(dest), "decision": data["decision"]}, ensure_ascii=False))

if __name__ == "__main__":
    main()
