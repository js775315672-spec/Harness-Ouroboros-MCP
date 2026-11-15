#!/usr/bin/env python3
"""Compare a tightly scoped model-generated regression fixture in disposable Docker containers.

Source and candidate are data-only until AST shape identity is proven.
Git applies the prevalidated diff in a throwaway directory; neither the
checkout nor any pull request is mutated. Container execution requires Docker.
"""
import argparse
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

try:
    from .real_repo_task import TASK
    from .cloud_real_repo_proposal import assess, _target_line
    from .replacement_proposal import build_single_line_diff
except ImportError:
    from real_repo_task import TASK
    from cloud_real_repo_proposal import assess, _target_line
    from replacement_proposal import build_single_line_diff

TARGET = "tests/test_model_feedback_loop.py"
MODULE = "scripts/model_feedback_loop.py"
PROBE = "scripts/regression_mutation_probe.py"
DOCKER_IMAGE = "python:3.11-slim"

def _digest(data):
    return hashlib.sha256(data).hexdigest()

def _literal_assignment(tree):
    for node in tree.body:
        if isinstance(node,ast.ClassDef) and node.name=="FeedbackLoopTests":
            for method in node.body:
                if isinstance(method,ast.FunctionDef) and method.name=="test_reject_multiple_fences":
                    if not method.body or not isinstance(method.body[0],ast.Assign):
                        raise ValueError("target statement missing")
                    assignment=method.body[0]
                    if (len(assignment.targets)!=1 or
                        not isinstance(assignment.targets[0],ast.Name) or
                        assignment.targets[0].id!="answer" or
                        not isinstance(assignment.value,ast.Constant) or
                        not isinstance(assignment.value.value,str)):
                        raise ValueError("only a string-literal answer assignment is allowed")
                    return assignment
    raise ValueError("target test method missing")

def prove_data_only_change(original,updated):
    before=ast.parse(original)
    after=ast.parse(updated)
    old=_literal_assignment(before)
    new=_literal_assignment(after)
    if old.value.value==new.value.value:
        raise ValueError("fixture value unchanged")
    if old.value.value.count(chr(96)*3)!=4 or new.value.value.count(chr(96)*3)!=4:
        raise ValueError("fixture fence structure changed")
    if "\n" not in new.value.value or "\\n" in new.value.value:
        raise ValueError("candidate does not contain actual newline test data")
    old_sha=_digest(old.value.value.encode("utf-8"))
    new_sha=_digest(new.value.value.encode("utf-8"))
    old.value.value=new.value.value="__scoped_fixture_sentinel__"
    if ast.dump(before,include_attributes=False)!=ast.dump(after,include_attributes=False):
        raise ValueError("executable Python AST changed outside the allowed string value")
    return {"executable_ast_identical":True,
            "only_string_literal_data_changed":True,
            "old_literal_sha256":old_sha,
            "new_literal_sha256":new_sha}

def _safe_file(root,relative):
    root=root.resolve(strict=True)
    path=root/relative
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
        raise ValueError("unsafe repository file")
    return path

def prepare_candidate(source_root,patch,workspace):
    root=Path(source_root).resolve(strict=True)
    if not root.is_dir() or Path(source_root).is_symlink():
        raise ValueError("unsafe repository root")
    original=_safe_file(root,TARGET).read_bytes()
    module=_safe_file(root,MODULE).read_bytes()
    probe=_safe_file(root,PROBE).read_bytes()
    if len(original)>12000 or len(module)>12000 or len(probe)>12000:
        raise ValueError("source exceeds size budget")
    source=original.decode("utf-8")
    verdict=assess(patch,TASK,source)
    if verdict["status"]!="accepted_for_review":
        raise ValueError("static gate rejected proposal: "+str(verdict["reason"]))
    line,old=_target_line(source)
    parts=patch.splitlines()
    if len(parts)!=6 or parts[4]!="-"+old or not parts[5].startswith("+        answer="):
        raise ValueError("unrecognized diff body")
    new_source=source.splitlines(keepends=True)
    new_source[line-1]=parts[5][1:]+"\n"
    expected="".join(new_source)
    data_proof=prove_data_only_change(source,expected)
    workspace=Path(workspace)
    original_dir=workspace/"baseline"
    candidate_dir=workspace/"candidate"
    for dest in (original_dir,candidate_dir):
        for relative,payload in ((TARGET,original),(MODULE,module),(PROBE,probe)):
            target=dest/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(payload)
    check=subprocess.run(["git","apply","--check","--unidiff-zero","-"],
                         input=patch,text=True,cwd=candidate_dir,
                         capture_output=True,timeout=10)
    if check.returncode:
        raise ValueError("temporary git apply --check failed: "+check.stderr[-200:])
    apply=subprocess.run(["git","apply","--unidiff-zero","-"],
                         input=patch,text=True,cwd=candidate_dir,
                         capture_output=True,timeout=10)
    if apply.returncode:
        raise ValueError("temporary git apply failed: "+apply.stderr[-200:])
    actual=(candidate_dir/TARGET).read_text(encoding="utf-8")
    if actual!=expected:
        raise ValueError("staged diff differs from source-anchored expected text")
    if _safe_file(root,TARGET).read_bytes()!=original:
        raise ValueError("checkout unexpectedly modified")
    for dest in (original_dir,candidate_dir):
        os.chmod(dest,0o755)
        for sub in ("tests","scripts"):
            os.chmod(dest/sub,0o755)
        for rel in (TARGET,MODULE,PROBE):
            os.chmod(dest/rel,0o644)
    return {"baseline_dir":str(original_dir),"candidate_dir":str(candidate_dir),
            "original_sha256":_digest(original),"candidate_sha256":_digest(actual.encode()),
            "source_unchanged":True,"patch_applied_to_disposable_copy_only":True,
            "model_code_executed":False,"merge_authorized":False,
            "proof":data_proof}

def _docker_command(workspace,image,python_arguments):
    location=Path(workspace).resolve(strict=True)
    return ["docker","run","--rm","--pull=never","--network=none",
            "--read-only","--cap-drop=ALL","--security-opt=no-new-privileges",
            "--pids-limit=64","--memory=256m","--cpus=1",
            "--user=65534:65534","--tmpfs=/tmp:rw,nosuid,nodev,size=16m",
            "-e","PYTHONDONTWRITEBYTECODE=1",
            "--mount",f"type=bind,src={location},dst=/work,readonly",
            "-w","/work",image,"python","-B",*python_arguments]

def docker_regression(workspace,image=DOCKER_IMAGE):
    cmd=_docker_command(workspace,image,
                        ["-m","unittest","discover","-s","tests",
                         "-p","test_model_feedback_loop.py","-v"])
    result=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
    output=(result.stdout+"\n"+result.stderr)[-5000:]
    match=re.search(r"Ran (\d+) tests?",output)
    return {"exit_code":result.returncode,"tests_run":int(match.group(1)) if match else None,
            "tests_passed":result.returncode==0 and bool(match),
            "log_tail":output[-1600:],
            "network_disabled":True,"filesystem_read_only":True,
            "privileges_dropped":True}


def verify_inference_provenance(inference_path,candidate_path,source_root):
    """Bind the executable test candidate to one completed real Qwen inference."""
    inference_bytes=Path(inference_path).read_bytes()
    candidate_bytes=Path(candidate_path).read_bytes()
    if len(inference_bytes)>120000 or len(candidate_bytes)>120000:
        raise ValueError("oversized inference or candidate evidence")
    report=json.loads(inference_bytes.decode("utf-8"))
    candidate=json.loads(candidate_bytes.decode("utf-8"))
    if not isinstance(report,dict) or not isinstance(candidate,dict):
        raise ValueError("evidence must be JSON objects")
    if (report.get("status")!="accepted_for_review" or
        report.get("model")!="Qwen/Qwen2.5-0.5B-Instruct" or
        report.get("patch_origin")!="deterministic_single_line_builder" or
        report.get("model_output_format")!="single_python_assignment_line"):
        raise ValueError("inference evidence lacks accepted real-model provenance")
    calls=report.get("real_model_calls")
    if type(calls) is not int or not 1<=calls<=2:
        raise ValueError("model invocation count missing or invalid")
    if (report.get("patch_applied") is not False or
        report.get("merge_authorized") is not False or
        report.get("full_harness_passed") is not False):
        raise ValueError("unsafe inference evidence flags")
    if candidate.get("provider")!="qwen" or candidate.get("status")!="proposal":
        raise ValueError("candidate does not match expected model proposal")
    if report.get("candidate_sha256")!=_digest(candidate_bytes):
        raise ValueError("candidate payload digest differs from inference report")
    source_digest=_digest(_safe_file(Path(source_root),TARGET).read_bytes())
    if report.get("source_sha256")!=source_digest:
        raise ValueError("source file differs from model prompt provenance")
    attempts=report.get("attempts")
    if not isinstance(attempts,list) or len(attempts)!=calls or not attempts:
        raise ValueError("missing model attempt record")
    last=attempts[-1]
    if not isinstance(last,dict) or last.get("status")!="accepted_for_review":
        raise ValueError("last model attempt did not pass static inspection")
    patch=candidate.get("patch")
    if (not isinstance(patch,str) or
        last.get("synthesized_patch_sha256")!=_digest(patch.encode("utf-8"))):
        raise ValueError("candidate diff does not match model-derived patch hash")
    # Rebuild the exact candidate from the recorded model response; hashes alone
    # are not evidence that the model actually proposed this code.
    raw=last.get("response_preview")
    if (not isinstance(raw,str) or len(raw)>500 or
        last.get("response_chars")!=len(raw) or
        last.get("response_sha256")!=_digest(raw.encode("utf-8"))):
        raise ValueError("complete model output not retained for replay")
    source=_safe_file(Path(source_root),TARGET).read_text(encoding="utf-8")
    line,old=_target_line(source)
    rebuilt=build_single_line_diff(raw,old,line)
    if rebuilt!=patch:
        raise ValueError("candidate differs from replayed model response")
    return {"real_model_calls":calls,
            "inference_sha256":_digest(inference_bytes),
            "candidate_sha256":_digest(candidate_bytes),
            "source_sha256":source_digest,
            "patch_sha256":_digest(patch.encode("utf-8")),
            "provenance_verified":True,
            "model_response_replayed":True}

def docker_mutation_probe(workspace,image=DOCKER_IMAGE):
    """A deliberate false-acceptance mutant should be caught by improved test data."""
    cmd=_docker_command(workspace,image,
                        ["-m","scripts.regression_mutation_probe"])
    result=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
    if result.returncode:
        raise ValueError("trusted mutation probe failed inside Docker")
    try:
        payload=json.loads(result.stdout.strip())
    except (ValueError,TypeError) as exc:
        raise ValueError("invalid mutation probe evidence") from exc
    if (not isinstance(payload,dict)
            or type(payload.get("mutant_detected")) is not bool
            or payload.get("target_tests_run")!=1
            or payload.get("mutant_limited_to_trusted_probe") is not True
            or payload.get("model_generated_code_executed") is not False):
        raise ValueError("unexpected mutation probe result")
    return {"mutant_detected":payload["mutant_detected"],
            "target_tests_run":payload["target_tests_run"],
            "probe_in_isolated_container":True,
            "network_disabled":True,"filesystem_read_only":True}

def compare(source_root,patch,image=DOCKER_IMAGE):
    with tempfile.TemporaryDirectory(prefix="harness-regression-") as temp:
        staged=prepare_candidate(source_root,patch,temp)
        baseline=docker_regression(staged["baseline_dir"],image)
        candidate=docker_regression(staged["candidate_dir"],image)
        baseline_mutation=docker_mutation_probe(staged["baseline_dir"],image)
        candidate_mutation=docker_mutation_probe(staged["candidate_dir"],image)
        passed=(baseline["tests_passed"] and candidate["tests_passed"]
                and baseline["tests_run"]==candidate["tests_run"]
                and baseline_mutation["mutant_detected"] is False
                and candidate_mutation["mutant_detected"] is True)
        return {"status":"isolated_regression_passed" if passed else "regression_failed",
                "staging":{k:v for k,v in staged.items() if not k.endswith("_dir")},
                "baseline":baseline,"candidate":candidate,
                "baseline_negative_control":baseline_mutation,
                "candidate_negative_control":candidate_mutation,
                "candidate_detects_previously_missed_mutant":(
                    not baseline_mutation["mutant_detected"]
                    and candidate_mutation["mutant_detected"]),
                "executed_only_string_literal_change":True,
                "patch_applied_to_checkout":False,
                "merge_authorized":False,"full_harness_passed":False}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",type=Path,default=Path("."))
    parser.add_argument("--candidate",type=Path,required=True)
    parser.add_argument("--inference-report",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    report={"status":"error","patch_applied_to_checkout":False,
            "merge_authorized":False,"full_harness_passed":False}
    try:
        response=json.loads(args.candidate.read_text(encoding="utf-8"))
        if set(response)!={"provider","status","summary","patch"}:
            raise ValueError("invalid candidate artifact fields")
        provenance=verify_inference_provenance(args.inference_report,args.candidate,args.source)
        report=compare(args.source,response["patch"])
        report["provenance"]=provenance
    except (OSError,ValueError,TypeError,KeyError,UnicodeError,subprocess.SubprocessError) as exc:
        report["error_type"]=type(exc).__name__
        report["error_message"]=str(exc)[:300]
    finally:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(report,sort_keys=True))
    return 0 if report["status"]=="isolated_regression_passed" else 2

if __name__=="__main__":
    sys.exit(main())
