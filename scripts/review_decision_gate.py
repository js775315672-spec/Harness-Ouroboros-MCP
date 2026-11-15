#!/usr/bin/env python3
"""Fail-closed read-only decision gate for Qwen disposable validation evidence.

This is not independent attestation of GitHub Actions or model provenance:
the upstream workflow verifies that. The gate never applies or merges patches.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

def _pairs(items):
    result={}
    for k,v in items:
        if k in result:
            raise ValueError("duplicate evidence field")
        result[k]=v
    return result

def _load(path):
    data=Path(path).read_bytes()
    if not data or len(data)>120000:
        raise ValueError("evidence size out of bounds")
    value=json.loads(data.decode("utf-8"),object_pairs_hook=_pairs)
    if not isinstance(value,dict):
        raise ValueError("evidence must be an object")
    return value,hashlib.sha256(data).hexdigest()

def decision(inference,regression):
    """Require positive evidence across inference, provenance, tests, and mutation."""
    if inference.get("status")!="accepted_for_review":
        raise ValueError("model proposal not accepted")
    if inference.get("real_model_calls") not in (1,2) or type(inference.get("real_model_calls")) is not int:
        raise ValueError("invalid model call count")
    if (inference.get("patch_applied") is not False or
            inference.get("merge_authorized") is not False or
            inference.get("full_harness_passed") is not False):
        raise ValueError("model evidence claims unauthorized actions")
    if regression.get("status")!="isolated_regression_passed":
        raise ValueError("isolated regression did not pass")
    if (regression.get("patch_applied_to_checkout") is not False or
            regression.get("merge_authorized") is not False or
            regression.get("full_harness_passed") is not False):
        raise ValueError("regression evidence claims unauthorized actions")
    proof=regression.get("provenance")
    if not isinstance(proof,dict) or proof.get("provenance_verified") is not True or proof.get("model_response_replayed") is not True:
        raise ValueError("model-to-patch provenance not verified")
    if proof.get("real_model_calls")!=inference["real_model_calls"]:
        raise ValueError("model call counts disagree")
    if proof.get("source_sha256")!=inference.get("source_sha256"):
        raise ValueError("source provenance mismatch")
    if (regression.get("candidate_detects_previously_missed_mutant") is not True or
            regression.get("executed_only_string_literal_change") is not True):
        raise ValueError("candidate improvement or data-only proof missing")
    for name in ("baseline","candidate"):
        item=regression.get(name)
        if not isinstance(item,dict) or item.get("tests_passed") is not True or type(item.get("tests_run")) is not int or item["tests_run"]<1:
            raise ValueError("missing passing regression suite: "+name)
        if item.get("network_disabled") is not True or item.get("filesystem_read_only") is not True:
            raise ValueError("missing isolated container proof: "+name)
    if regression["baseline"]["tests_run"]!=regression["candidate"]["tests_run"]:
        raise ValueError("test counts differ")
    for name,expected in (("baseline_negative_control",False),("candidate_negative_control",True)):
        item=regression.get(name)
        if not isinstance(item,dict) or item.get("mutant_detected") is not expected or item.get("probe_in_isolated_container") is not True:
            raise ValueError("negative control missing: "+name)
    return {"decision":"ready_for_human_review",
            "model_patch_applied":False,"merge_authorized":False,
            "independent_github_ci_attested":False,
            "next_action":"human_review_only",
            "evidence_checks":["model_proposal","source_provenance","replayed_model_output",
                               "baseline_regression","candidate_regression",
                               "baseline_negative_control","candidate_negative_control"]}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--inference",type=Path,required=True)
    parser.add_argument("--regression",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    report={"decision":"blocked","merge_authorized":False,"model_patch_applied":False}
    try:
        inference,ih=_load(args.inference)
        regression,rh=_load(args.regression)
        report=decision(inference,regression)
        report["inference_evidence_sha256"]=ih
        report["regression_evidence_sha256"]=rh
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as exc:
        report["reason"]=str(exc)[:250]
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(report,sort_keys=True))
    return 0 if report["decision"]=="ready_for_human_review" else 2

if __name__=="__main__":
    sys.exit(main())
