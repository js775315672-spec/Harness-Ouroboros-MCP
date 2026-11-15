#!/usr/bin/env python3
"""Validate evidence for distinct development cycles; fail closed on missing proof."""
import argparse,json,pathlib,re,sys
SHA=re.compile(r"^[0-9a-f]{40}$")
STEPS=("harness","ouroboros","regression","secrets")
def validate(records):
    if not isinstance(records,list):raise ValueError("expected list")
    seen=set()
    for index,record in enumerate(records,1):
        if not isinstance(record,dict) or set(record)!={"cycle","commit","change","checks","fixes","ci_url"}:raise ValueError("invalid record schema")
        if type(record["cycle"]) is not int or record["cycle"]!=index:raise ValueError("nonsequential cycle")
        if not isinstance(record["commit"],str) or not SHA.fullmatch(record["commit"]) or record["commit"] in seen:raise ValueError("missing or repeated development commit")
        seen.add(record["commit"])
        if not isinstance(record["change"],str) or not record["change"].strip():raise ValueError("missing change description")
        if not isinstance(record["ci_url"],str) or not record["ci_url"].startswith("https://github.com/"):raise ValueError("missing CI evidence")
        if not isinstance(record["checks"],dict) or set(record["checks"])!=set(STEPS) or any(record["checks"][step]!="pass" for step in STEPS):raise ValueError("unverified cycle")
        if not isinstance(record["fixes"],list) or any(not isinstance(x,str) for x in record["fixes"]):raise ValueError("invalid fixes")
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
