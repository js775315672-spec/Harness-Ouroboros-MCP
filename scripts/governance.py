#!/usr/bin/env python3
"""Conservative read-only governance gates, with validated policy configuration."""
import argparse,json,pathlib,re,subprocess,sys
GATES=("boundaries","layers","secrets","security","structure","spec","deps","mutation")
def validate(config):
    if not isinstance(config,dict) or set(config)!=set(GATES): raise ValueError("policy must define exactly eight gates")
    fields={"boundaries":{"forbidden_paths"},"layers":{"forbidden_imports"},"secrets":{"require_scanner"},"security":{"forbidden_patterns"},"structure":{"required_files"},"spec":{"required_files"},"deps":{"forbidden_files"},"mutation":{"forbidden_paths"}}
    for gate,keys in fields.items():
        entry=config[gate]
        if not isinstance(entry,dict) or set(entry)!=keys:raise ValueError("invalid gate configuration: "+gate)
        for key,value in entry.items():
            if gate=="secrets":
                if value is not True:raise ValueError("secret scanner must be enabled")
            elif gate=="layers":
                if not isinstance(value,list):raise ValueError("invalid import rules")
                for rule in value:
                    if not isinstance(rule,dict) or set(rule)!={"from","import"} or not all(isinstance(x,str) and x for x in rule.values()):raise ValueError("invalid import rule")
            else:
                if not isinstance(value,list) or not all(isinstance(x,str) and x for x in value):raise ValueError("invalid policy list: "+gate)
                if gate=="security":
                    for pattern in value:re.compile(pattern)
                elif any(x.startswith("/") or ".." in pathlib.PurePosixPath(x).parts for x in value):raise ValueError("unsafe policy path")
    return config
def check(root,config):
    validate(config)
    out={g:[] for g in GATES}
    names=subprocess.run(["git","-C",str(root),"ls-files","-z"],capture_output=True,check=True).stdout
    paths=sorted(p.decode("utf-8","surrogateescape") for p in names.split(b"\0") if p)
    for gate in ("boundaries","mutation"):
        for prefix in config[gate]["forbidden_paths"]:
            if any(p==prefix or p.startswith(prefix.rstrip("/")+"/") for p in paths):out[gate].append("forbidden path: "+prefix)
    for gate in ("structure","spec"):
        for p in config[gate]["required_files"]:
            if p not in paths or not (root/p).is_file():out[gate].append("missing required file: "+p)
    for p in config["deps"]["forbidden_files"]:
        if p in paths:out["deps"].append("forbidden tracked file: "+p)
    if "scripts/harness_check.py" not in paths or not (root/"scripts/harness_check.py").is_file():out["secrets"].append("scanner missing")
    for p in paths:
        if not p.endswith((".py",".js",".ts")) or p.startswith("tests/"):continue
        try:
            path=root/p
            if path.is_symlink():raise OSError("symlink")
            data=path.read_text(encoding="utf-8")
        except (OSError,UnicodeError):out["security"].append("unreadable source: "+p);continue
        for expr in config["security"]["forbidden_patterns"]:
            if re.search(expr,data):out["security"].append("forbidden pattern: "+p)
        for rule in config["layers"]["forbidden_imports"]:
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
        result=check(root,config)
    except (OSError,ValueError,re.error,subprocess.CalledProcessError) as e:
        print("BLOCK: policy evaluation failed:",type(e).__name__);return 2
    for gate,errors in result.items():
        print(("FAIL" if errors else "PASS")+": "+gate)
        for error in errors:print("  "+error)
    return int(any(result.values()))
if __name__=="__main__":sys.exit(main())
