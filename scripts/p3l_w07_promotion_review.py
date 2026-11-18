#!/usr/bin/env python3
"""W07 read-only promotion eligibility and rollback plan, never activates code."""
import argparse
import json
import re
from pathlib import Path

SHA=re.compile(r"^[a-f0-9]{40}$")
DIGEST=re.compile(r"^[a-f0-9]{64}$")
FROZEN={"test_development_ledger.py":8,"test_ci_attestation.py":7,
        "heldout_p3f_development_ledger.py":10}

def review(w05_receipt,active_commit,candidate_commit):
    if not (type(active_commit) is str and SHA.fullmatch(active_commit)
            and type(candidate_commit) is str and SHA.fullmatch(candidate_commit)
            and active_commit!=candidate_commit):
        raise ValueError("invalid distinct active/candidate source commits")
    if type(w05_receipt) is not dict:
        raise ValueError("missing independent replay receipt")
    expected={"schema","run_id","runner_role","task_sha256","source_sha256",
              "raw_response_sha256","candidate_source_sha256","diff_sha256",
              "test_count","suites","candidate_passed","independent_replay_completed",
              "merge_authorized","promoted"}
    if set(w05_receipt)!=expected:
        raise ValueError("malformed W05 receipt")
    if (w05_receipt["schema"]!="p3l-w05-independent-replay-v1"
            or w05_receipt["runner_role"]!="independent_replay"
            or type(w05_receipt["run_id"]) is not int or w05_receipt["run_id"]<1
            or w05_receipt["merge_authorized"] is not False
            or w05_receipt["promoted"] is not False
            or w05_receipt["candidate_passed"] is not True
            or w05_receipt["independent_replay_completed"] is not True
            or type(w05_receipt["test_count"]) is not int or w05_receipt["test_count"]!=25):
        raise ValueError("W05 replay is not complete and passing")
    if any(type(w05_receipt[k]) is not str or not DIGEST.fullmatch(w05_receipt[k])
           for k in ("task_sha256","source_sha256","raw_response_sha256",
                     "candidate_source_sha256","diff_sha256")):
        raise ValueError("missing W05 exact source hashes")
    suites=w05_receipt["suites"]
    if type(suites) is not dict or set(suites)!=set(FROZEN):
        raise ValueError("frozen suite result missing")
    for name,count in FROZEN.items():
        result=suites[name]
        if (type(result) is not dict or set(result)!={"tests_run","passed"}
                or type(result["tests_run"]) is not int
                or result["tests_run"]!=count or result["passed"] is not True):
            raise ValueError("frozen independent suite did not pass")
    # Content checks are only advisory until GitHub's workflow, PR SHA, and
    # user authorization are verified OUTSIDE this self-reported JSON.
    return {
        "schema":"p3l-w07-review-only-v1",
        "active_commit":active_commit,"proposed_commit":candidate_commit,
        "rollback_target_commit":active_commit,
        "candidate_source_sha256":w05_receipt["candidate_source_sha256"],
        "w05_run_id":w05_receipt["run_id"],
        "w05_claimed_test_count":25,
        "decision":"await_verified_commit_ci_and_user_approval",
        "candidate_active":False,"promotion_performed":False,
        "rollback_performed":False,"merge_authorized":False,
        "w08_handoff_authorized":False,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--w05-receipt",type=Path,required=True)
    p.add_argument("--active-commit",required=True)
    p.add_argument("--candidate-commit",required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    if a.w05_receipt.is_symlink() or not a.w05_receipt.is_file() or a.w05_receipt.stat().st_size>16000:
        raise SystemExit("BLOCK: unsafe W05 receipt")
    result=review(json.loads(a.w05_receipt.read_text(encoding="utf-8")),a.active_commit,a.candidate_commit)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print("W07: candidate remains in human review; no promotion or rollback performed")

if __name__=="__main__":
    main()
