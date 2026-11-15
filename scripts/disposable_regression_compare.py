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
except ImportError:
    from real_repo_task import TASK
    from cloud_real_repo_proposal import assess, _target_line

TARGET = "tests/test_model_feedback_loop.py"
MODULE = "scripts/model_feedback_loop.py"
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
    old.value.value=new.value.value="__scoped_fixture_sentinel__"
    if ast.dump(before,include_attributes=False)!=ast.dump(after,include_attributes=False):
        raise ValueError("executable Python AST changed outside the allowed string value")
    return {"executable_ast_identical":True,
            "only_string_literal_data_changed":True,
            "old_literal_sha256":_digest(old.value.value.encode()),
            "new_literal_sha256":_digest(new.value.value.encode())}

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
    if len(original)>12000 or len(module)>12000:
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
        for relative,payload in ((TARGET,original),(MODULE,module)):
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
        for rel in (TARGET,MODULE):
            os.chmod(dest/rel,0o644)
    return {"baseline_dir":str(original_dir),"candidate_dir":str(candidate_dir),
            "original_sha256":_digest(original),"candidate_sha256":_digest(actual.encode()),
            "source_unchanged":True,"patch_applied_to_disposable_copy_only":True,
            "model_code_executed":False,"merge_authorized":False,
            "proof":data_proof}

def docker_regression(workspace,image=DOCKER_IMAGE):
    location=Path(workspace).resolve(strict=True)
    cmd=["docker","run","--rm","--pull=never","--network=none",
         "--read-only","--cap-drop=ALL","--security-opt=no-new-privileges",
         "--pids-limit=64","--memory=256m","--cpus=1",
         "--user=65534:65534","--tmpfs=/tmp:rw,nosuid,nodev,size=16m",
         "-e","PYTHONDONTWRITEBYTECODE=1",
         "--mount",f"type=bind,src={location},dst=/work,readonly",
         "-w","/work",image,"python","-B","-m","unittest",
         "discover","-s","tests","-p","test_model_feedback_loop.py","-v"]
    result=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
    output=(result.stdout+"\n"+result.stderr)[-5000:]
    match=re.search(r"Ran (\d+) tests?",output)
    return {"exit_code":result.returncode,"tests_run":int(match.group(1)) if match else None,
            "tests_passed":result.returncode==0 and bool(match),
            "log_tail":output[-1600:],
            "network_disabled":True,"filesystem_read_only":True,
            "privileges_dropped":True}

def compare(source_root,patch,image=DOCKER_IMAGE):
    with tempfile.TemporaryDirectory(prefix="harness-regression-") as temp:
        staged=prepare_candidate(source_root,patch,temp)
        baseline=docker_regression(staged["baseline_dir"],image)
        candidate=docker_regression(staged["candidate_dir"],image)
        passed=(baseline["tests_passed"] and candidate["tests_passed"]
                and baseline["tests_run"]==candidate["tests_run"])
        return {"status":"isolated_regression_passed" if passed else "regression_failed",
                "staging":{k:v for k,v in staged.items() if not k.endswith("_dir")},
                "baseline":baseline,"candidate":candidate,
                "executed_only_string_literal_change":True,
                "patch_applied_to_checkout":False,
                "merge_authorized":False,"full_harness_passed":False}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",type=Path,default=Path("."))
    parser.add_argument("--candidate",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    report={"status":"error","patch_applied_to_checkout":False,
            "merge_authorized":False,"full_harness_passed":False}
    try:
        response=json.loads(args.candidate.read_text(encoding="utf-8"))
        if set(response)!={"provider","status","summary","patch"}:
            raise ValueError("invalid candidate artifact fields")
        report=compare(args.source,response["patch"])
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
