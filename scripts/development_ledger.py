#!/usr/bin/env python3
"""Validate evidence for distinct development cycles; fail closed on missing proof."""
import argparse,json,pathlib,re,sys
SHA=re.compile(r"^[0-9a-f]{40}$")
CI=re.compile(r"^https://github\.com/[^/\s]+/[^/\s]+/actions/runs/[1-9][0-9]*$")
STEPS=("harness","ouroboros","regression","secrets")

def _safe_text(value, max_utf8_bytes, allow_whitespace_only=False):
    """Keep untrusted ledger text short and free of control characters."""
    if not isinstance(value,str) or not value:
        return False
    if not allow_whitespace_only and not value.strip():
        return False
    if any(ord(char)<32 or 127<=ord(char)<=159 for char in value):
        return False
    try:
        return len(value.encode("utf-8"))<=max_utf8_bytes
    except UnicodeEncodeError:
        return False

def validate(records):
    if not isinstance(records,list):raise ValueError("expected list")
    seen=set()
    for index,record in enumerate(records,1):
        if not isinstance(record,dict) or set(record)!={"cycle","commit","change","checks","fixes","ci_url"}:raise ValueError("invalid record schema")
        if type(record["cycle"]) is not int or record["cycle"]!=index:raise ValueError("nonsequential cycle")
        if not isinstance(record["commit"],str) or not SHA.fullmatch(record["commit"]) or record["commit"] in seen:raise ValueError("missing or repeated development commit")
        seen.add(record["commit"])
        if not _safe_text(record["change"],256):raise ValueError("invalid change description or UTF-8 length")
        if not isinstance(record["ci_url"],str) or not CI.fullmatch(record["ci_url"]):raise ValueError("invalid CI evidence URL")
        if not isinstance(record["checks"],dict) or set(record["checks"])!=set(STEPS) or any(record["checks"][step]!="pass" for step in STEPS):raise ValueError("unverified cycle")
        if not isinstance(record["fixes"],list) or len(record["fixes"])>12 or any(not _safe_text(x,128,allow_whitespace_only=True) for x in record["fixes"]):raise ValueError("invalid fixes, control characters, or UTF-8 length")
    return len(records)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("ledger",type=pathlib.Path)
    p.add_argument("--min-cycles",type=int,default=30)
    args=p.parse_args()
    try:
        if args.min_cycles<1:raise ValueError("minimum must be positive")
        count=validate(json.loads(args.ledger.read_text(encoding="utf-8")))
        if count<args.min_cycles:raise ValueError("only %d verified development cycles"%count)
    except (OSError,ValueError,UnicodeError) as exc:
        print("BLOCK:",str(exc),file=sys.stderr);return 1
    print("PASS: %d distinct development cycles"%count);return 0
if __name__=="__main__":sys.exit(main())
