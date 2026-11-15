#!/usr/bin/env python3
"""Apply a prevalidated model patch only inside a disposable local copy.

Not a security sandbox: subprocess tests must run only on trusted fixtures or in
an independently sandboxed runner. Never execute model-supplied code here.
"""
import argparse,json,pathlib,shutil,subprocess,sys,tempfile
from patch_gate import inspect_patch

def stage_patch(response,source):
    inspection=inspect_patch(response)
    root=pathlib.Path(source).resolve(strict=True)
    if not root.is_dir():raise ValueError("source must be a directory")
    if root.is_symlink():raise ValueError("symlink source denied")
    with tempfile.TemporaryDirectory(prefix="harness-patch-") as temp:
        target=pathlib.Path(temp)/"workspace"
        shutil.copytree(root,target,symlinks=True,ignore=shutil.ignore_patterns(".git",".venv","__pycache__","artifacts"))
        for rel in inspection["files"]:
            original=root/rel
            staged=target/rel
            if original.is_symlink() or staged.is_symlink():raise ValueError("symlink patch target denied")
            if original.exists() and not original.is_file():raise ValueError("nonfile patch target denied")
            if not staged.resolve().is_relative_to(target.resolve()):raise ValueError("path escapes workspace")
        result=subprocess.run(["git","apply","--check","--no-index","-"],input=response["patch"],
                              text=True,cwd=target,capture_output=True,timeout=10)
        if result.returncode:raise ValueError("patch does not apply cleanly")
        applied=subprocess.run(["git","apply","--no-index","-"],input=response["patch"],
                               text=True,cwd=target,capture_output=True,timeout=10)
        if applied.returncode:raise ValueError("patch application failed")
        return {"status":"staged_in_disposable_copy","files":inspection["files"],
                "source_modified":False,"model_code_executed":False,
                "independent_sandbox_required":True,"harness_passed":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--response",type=pathlib.Path,required=True)
    p.add_argument("--source",type=pathlib.Path,required=True)
    args=p.parse_args()
    try:
        response=json.loads(args.response.read_text(encoding="utf-8"))
        result=stage_patch(response,args.source)
    except (OSError,ValueError,UnicodeError,subprocess.TimeoutExpired) as exc:
        print("BLOCK:",str(exc),file=sys.stderr);return 2
    print(json.dumps(result,sort_keys=True));return 0
if __name__=="__main__":sys.exit(main())
