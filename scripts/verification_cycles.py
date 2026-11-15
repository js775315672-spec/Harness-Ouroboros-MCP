#!/usr/bin/env python3
"""Thirty sequential, fail-fast Harness/Ouroboros verification cycles.

These are 30 verification repetitions, not 30 independent feature implementations.
No network, secrets, trading, merge or repository mutation.
"""
import argparse,json,pathlib,subprocess,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[1]
STEPS=(
    ("harness",["scripts/governance.py"]),
    ("ouroboros",["scripts/evaluation.py"]),
    ("regression",["-m","unittest","discover","-s","tests","-q"]),
    ("secrets",["scripts/harness_check.py"]),
)
def run(rounds=30,root=ROOT,runner=None):
    if not 1<=rounds<=30:raise ValueError("rounds must be 1..30")
    runner=runner or subprocess.run
    completed=[]
    started=time.monotonic()
    for i in range(1,rounds+1):
        round_started=time.monotonic()
        step_results=[]
        for name,args in STEPS:
            step_started=time.monotonic()
            try:
                p=runner([sys.executable,*args],cwd=root,capture_output=True,text=True,timeout=90)
                status="pass" if p.returncode==0 else "fail"
                step_results.append({"step":name,"status":status,"exit_code":p.returncode})
            except (OSError,subprocess.TimeoutExpired) as exc:
                status="fail"
                step_results.append({"step":name,"status":"fail","error":type(exc).__name__})
            step_results[-1]["duration_seconds"]=round(time.monotonic()-step_started,3)
            if status!="pass":
                report={"requested_rounds":rounds,"completed_rounds":len(completed),"failed_round":i,"steps":step_results,"outcome":"blocked","elapsed_seconds":round(time.monotonic()-started,3)}
                print(json.dumps(report,sort_keys=True),flush=True)
                return 1
        completed.append({"round":i,"steps":step_results,"duration_seconds":round(time.monotonic()-round_started,3)})
        print(json.dumps({"round":i,"status":"pass","duration_seconds":completed[-1]["duration_seconds"],"total_elapsed_seconds":round(time.monotonic()-started,3)}),flush=True)
    print(json.dumps({"requested_rounds":rounds,"completed_rounds":len(completed),"outcome":"pass","elapsed_seconds":round(time.monotonic()-started,3),"note":"verification cycles only; no code changes performed"},sort_keys=True),flush=True)
    return 0
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--rounds",type=int,default=30)
    args=parser.parse_args()
    try:return run(args.rounds)
    except ValueError as exc:
        print("BLOCK:",str(exc),file=sys.stderr);return 2
if __name__=="__main__":sys.exit(main())
