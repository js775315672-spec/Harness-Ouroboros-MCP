#!/usr/bin/env python3
"""Thirty sequential, fail-fast Harness/Ouroboros verification cycles.

These are 30 verification repetitions, not 30 independent feature implementations.
No network, secrets, trading, merge or repository mutation.
"""
import argparse,json,os,pathlib,subprocess,sys,tempfile,time
ROOT=pathlib.Path(__file__).resolve().parents[1]
STEPS=(
    ("harness",["scripts/governance.py"]),
    ("ouroboros",["scripts/evaluation.py"]),
    ("regression",["-m","unittest","discover","-s","tests","-q"]),
    ("secrets",["scripts/harness_check.py"]),
)
def run_provenance(env=None):
    env=os.environ if env is None else env
    repo=env.get('GITHUB_REPOSITORY','')
    run_id=env.get('GITHUB_RUN_ID','')
    sha=env.get('GITHUB_SHA','')
    if not (repo and run_id and sha):return {'source':'local','verified_externally':False}
    if not (len(repo.split('/'))==2 and all(repo.split('/')) and run_id.isascii() and run_id.isdecimal() and len(sha)==40 and all(c in '0123456789abcdef' for c in sha)):
        raise ValueError('invalid GitHub run provenance')
    return {'source':'github_actions','repository':repo,'run_id':run_id,'workflow_sha':sha,'run_url':f'https://github.com/{repo}/actions/runs/{run_id}','verified_externally':False}
def write_report(path,report):
    if path is None:return
    path=pathlib.Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.verification-',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            json.dump(report,stream,sort_keys=True,indent=2)
            stream.write('\n')
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)
def run(rounds=30,root=ROOT,runner=None,report_path=None):
    if not 1<=rounds<=30:raise ValueError("rounds must be 1..30")
    runner=runner or subprocess.run
    provenance=run_provenance()
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
                report["cycles"]=completed
                report["provenance"]=provenance
                write_report(report_path,report)
                print(json.dumps(report,sort_keys=True),flush=True)
                return 1
        completed.append({"round":i,"steps":step_results,"duration_seconds":round(time.monotonic()-round_started,3)})
        print(json.dumps({"round":i,"status":"pass","duration_seconds":completed[-1]["duration_seconds"],"total_elapsed_seconds":round(time.monotonic()-started,3)}),flush=True)
    report={"requested_rounds":rounds,"completed_rounds":len(completed),"outcome":"pass","elapsed_seconds":round(time.monotonic()-started,3),"cycles":completed,"provenance":provenance,"note":"verification cycles only; no code changes performed"}
    write_report(report_path,report)
    print(json.dumps({key:value for key,value in report.items() if key!="cycles"},sort_keys=True),flush=True)
    return 0
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--rounds",type=int,default=30)
    parser.add_argument("--report",type=pathlib.Path)
    args=parser.parse_args()
    try:return run(args.rounds,report_path=args.report)
    except ValueError as exc:
        print("BLOCK:",str(exc),file=sys.stderr);return 2
if __name__=="__main__":sys.exit(main())
