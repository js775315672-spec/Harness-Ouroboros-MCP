#!/usr/bin/env python3
"""Eight conservative read-only governance gates. No dependencies or network."""
import argparse,json,pathlib,re,subprocess,sys
GATES=("boundaries","layers","secrets","security","structure","spec","deps","mutation")
def check(root,config):
    out={g:[] for g in GATES}
    names=subprocess.run(["git","-C",str(root),"ls-files","-z"],capture_output=True,check=True).stdout
    paths=sorted(p.decode("utf-8","surrogateescape") for p in names.split(b"\0") if p)
    for gate in GATES:
        if not isinstance(config.get(gate),dict): out[gate].append("missing gate configuration")
    for gate in ("boundaries","mutation"):
        for prefix in config.get(gate,{}).get("forbidden_paths",[]):
            if any(p==prefix or p.startswith(prefix.rstrip("/")+"/") for p in paths):
                out[gate].append("forbidden path: "+prefix)
    for gate in ("structure","spec"):
        for p in config.get(gate,{}).get("required_files",[]):
            if p not in paths: out[gate].append("missing required file: "+p)
    for p in config.get("deps",{}).get("forbidden_files",[]):
        if p in paths: out["deps"].append("forbidden tracked dependency/config: "+p)
    if config.get("secrets",{}).get("require_scanner") and "scripts/harness_check.py" not in paths:
        out["secrets"].append("scanner missing")
    for p in paths:
        if not p.endswith((".py",".js",".ts")) or p.startswith("tests/"): continue
        try: data=(root/p).read_text(encoding="utf-8")
        except (OSError,UnicodeError):
            out["security"].append("unreadable source: "+p);continue
        for expr in config.get("security",{}).get("forbidden_patterns",[]):
            try:
                if re.search(expr,data): out["security"].append("forbidden pattern: "+p)
            except re.error: out["security"].append("invalid regex")
        for rule in config.get("layers",{}).get("forbidden_imports",[]):
            if not isinstance(rule,dict) or not all(k in rule for k in ("from","import")):
                out["layers"].append("invalid layer rule");continue
            if p.startswith(rule["from"]) and re.search(r"(?m)^\s*(?:from|import)\s+"+re.escape(rule["import"])+r"\b",data):
                out["layers"].append("forbidden import: "+p)
    return out
def main():
    a=argparse.ArgumentParser()
    a.add_argument("--root",type=pathlib.Path,default=pathlib.Path(__file__).resolve().parents[1])
    a.add_argument("--config",default="harness-policy.json")
    args=a.parse_args();root=args.root.resolve()
    try:
        config=json.loads((root/args.config).read_text())
        if not isinstance(config,dict): raise ValueError("invalid policy")
        result=check(root,config)
    except (OSError,ValueError,subprocess.CalledProcessError) as e:
        print("BLOCK: policy evaluation failed:",type(e).__name__);return 2
    for gate,errors in result.items():
        print(("FAIL" if errors else "PASS")+": "+gate)
        for error in errors: print("  "+error)
    return int(any(result.values()))
if __name__=="__main__":sys.exit(main())
