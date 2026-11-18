#!/usr/bin/env python3
"""W08 safe next-task preview, blocked until verified W07 approval and activation."""
import argparse
import json
from pathlib import Path
from task_selector import select

def preview(w07_review,previous_task_id="ledger_validation",completed=0):
    if type(w07_review) is not dict or w07_review.get("schema")!="p3l-w07-review-only-v1":
        raise ValueError("invalid W07 handoff")
    if (w07_review.get("decision")!="await_verified_commit_ci_and_user_approval"
            or w07_review.get("promotion_performed") is not False
            or w07_review.get("candidate_active") is not False
            or w07_review.get("w08_handoff_authorized") is not False
            or w07_review.get("merge_authorized") is not False):
        raise ValueError("W07 approval state cannot be attested")
    if type(previous_task_id) is not str or previous_task_id!="ledger_validation":
        raise ValueError("unknown previous task identity")
    if type(completed) is not int or completed!=0:
        raise ValueError("cannot credit unverified development")
    choice=select(completed=completed)
    if choice["decision"]!="propose" or choice.get("coding_agent_connected") is not False:
        raise ValueError("unsupported next task proposal")
    # W07's candidate has not become the active executor. Never use it as base.
    return {
        "schema":"p3l-w08-successor-preview-v1",
        "decision":"blocked_until_w07_authorized_activation",
        "previous_task_id":previous_task_id,
        "proposed_task_phase":choice["phase"],
        "proposed_task_description":choice["task"],
        "proposed_task_area":choice["area"],
        "current_active_sha":w07_review["active_commit"],
        "unapproved_candidate_sha":w07_review["proposed_commit"],
        "successor_task_started":False,
        "model_calls":0,
        "new_source_patch_submitted":False,
        "verified_development_cycles":0,
        "merge_authorized":False,
        "promoted":False,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--w07-review",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    if a.w07_review.is_symlink() or not a.w07_review.is_file() or a.w07_review.stat().st_size>8000:
        raise SystemExit("BLOCK: unsafe W07 review")
    result=preview(json.loads(a.w07_review.read_text(encoding="utf-8")))
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("W08: next-task preview saved; no successor or promotion attempted")

if __name__=="__main__":
    main()
