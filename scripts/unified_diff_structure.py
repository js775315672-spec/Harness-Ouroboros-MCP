#!/usr/bin/env python3
"""Conservative structure validation for unified Git diffs; no patch application."""
import re

DIFF=re.compile(r"diff --git a/(\S+) b/(\S+)")
HUNK=re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?:.*)?")
MAX_HUNKS=30

def validate_diff_structure(patch):
    if not isinstance(patch,str) or not patch.endswith("\n"):
        raise ValueError("diff must be newline-terminated text")
    lines=patch.splitlines()
    i=0
    files=[]
    hunks=0
    while i<len(lines):
        m=DIFF.fullmatch(lines[i])
        if not m:
            raise ValueError("expected git diff header")
        if m.group(1)!=m.group(2) or m.group(1) in files:
            raise ValueError("mismatched or repeated file")
        path=m.group(1)
        files.append(path)
        i+=1
        if i+1>=len(lines) or lines[i]!=f"--- a/{path}" or lines[i+1]!=f"+++ b/{path}":
            raise ValueError("missing or mismatched file markers")
        i+=2
        file_hunks=0
        while i<len(lines) and not lines[i].startswith("diff --git "):
            h=HUNK.fullmatch(lines[i])
            if not h:
                raise ValueError("expected unified hunk header")
            old_expected=int(h.group(2)) if h.group(2) is not None else 1
            new_expected=int(h.group(4)) if h.group(4) is not None else 1
            if old_expected+new_expected>10000:
                raise ValueError("hunk too large")
            old_seen=new_seen=0
            i+=1
            while i<len(lines) and not lines[i].startswith("@@ ") and not lines[i].startswith("diff --git "):
                line=lines[i]
                if not line or line[0] not in (" ","+","-"):
                    raise ValueError("unsupported or malformed diff line")
                if line[0] in (" ","-"):
                    old_seen+=1
                if line[0] in (" ","+"):
                    new_seen+=1
                if old_seen>old_expected or new_seen>new_expected:
                    raise ValueError("hunk line count exceeded")
                i+=1
            if (old_seen,new_seen)!=(old_expected,new_expected):
                raise ValueError("hunk line count mismatch")
            file_hunks+=1
            hunks+=1
            if hunks>MAX_HUNKS:
                raise ValueError("too many hunks")
        if file_hunks==0:
            raise ValueError("file has no hunks")
    if not files:
        raise ValueError("empty diff")
    return {"files":files,"hunks":hunks,"structure_valid":True,
            "patch_approved_for_application":False}
