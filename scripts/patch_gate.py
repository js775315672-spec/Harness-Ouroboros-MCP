#!/usr/bin/env python3
"""Validate model-suggested git patches before any isolated workspace applies them.

This is a static safety boundary, not a complete patch parser or sandbox.
"""
import argparse,json,pathlib,re,sys
from model_adapter import validate_response

ALLOWED_PREFIXES=("scripts/","tests/","agents/","orchestration/","memory/","training/")
FORBIDDEN_SEGMENTS=(".git",".github","__pycache__")
MAX_PATCH_BYTES=100000

def _safe_path(value):
    if not isinstance(value,str) or not value or value.startswith("/") or "\\" in value:
        return False
    parts=value.split("/")
    if any(part in ("",".","..") for part in parts):return False
    if any(part in FORBIDDEN_SEGMENTS for part in parts):return False
    return value.startswith(ALLOWED_PREFIXES)

def inspect_patch(response):
    validated=validate_response(response)
    if validated["status"]!="proposal":raise ValueError("only proposed patches may be inspected")
    patch=response["patch"]
    if len(patch.encode("utf-8"))>MAX_PATCH_BYTES:raise ValueError("oversized patch")
    headers=re.findall(r"^diff --git a/(\S+) b/(\S+)$",patch,re.MULTILINE)
    if not headers or len(headers)>20:raise ValueError("invalid file count")
    for old,new in headers:
        if old!=new or not _safe_path(old) or not _safe_path(new):
            raise ValueError("unsafe patch target")
    if "\x00" in patch or "\r" in patch:raise ValueError("binary or CRLF patch denied")
    if re.search(r"^(?:GIT binary patch|Binary files |rename from |rename to |copy from |copy to |old mode |new mode |deleted file mode )",patch,re.MULTILINE):
        raise ValueError("binary, rename, deletion or permission change denied")
    if patch.count("diff --git ")!=len(headers):raise ValueError("malformed diff header")
    return {"provider":validated["provider"],"files":sorted(set(new for _,new in headers)),
            "patch_approved_for_application":False,"requires_isolated_application":True,
            "requires_harness_revalidation":True}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("response",type=pathlib.Path)
    args=p.parse_args()
    try:
        result=inspect_patch(json.loads(args.response.read_text(encoding="utf-8")))
    except (OSError,ValueError,UnicodeError) as exc:
        print("BLOCK:",str(exc),file=sys.stderr);return 2
    print(json.dumps(result,sort_keys=True));return 0
if __name__=="__main__":sys.exit(main())
