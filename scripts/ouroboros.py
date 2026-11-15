#!/usr/bin/env python3
"""Deterministic stage transition and atomic checkpoint; no execution or merging."""
import argparse,datetime,json,os,pathlib,subprocess,sys,tempfile
STAGES=("interview","seed","trd","decompose","run","evaluate","evolve")
def evaluate(root,stage,outcome,note):
    if stage not in STAGES or outcome not in ("pass","fail","blocked"):raise ValueError("invalid stage or outcome")
    head=subprocess.run(["git","-C",str(root),"rev-parse","HEAD"],check=True,capture_output=True,text=True).stdout.strip()
    return {"schema_version":1,"stage":stage,"outcome":outcome,"note":note[:1000],"commit":head,
      "timestamp":datetime.datetime.now(datetime.timezone.utc).isoformat(),
      "next_stage":STAGES[(STAGES.index(stage)+1)%len(STAGES)] if outcome=="pass" else stage,
      "requires_human_merge_approval":True}
def checkpoint(path,record):
    path=path.resolve();path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=".checkpoint-",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump(record,f,ensure_ascii=False,indent=2);f.write("\n");f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=pathlib.Path,default=pathlib.Path(__file__).resolve().parents[1])
    p.add_argument("--stage",required=True,choices=STAGES)
    p.add_argument("--outcome",required=True,choices=("pass","fail","blocked"))
    p.add_argument("--note",default="")
    p.add_argument("--output",type=pathlib.Path,default=pathlib.Path("artifacts/ouroboros-checkpoint.json"))
    a=p.parse_args()
    try:
        record=evaluate(a.root,a.stage,a.outcome,a.note);checkpoint(a.output,record)
    except (OSError,ValueError,subprocess.CalledProcessError) as e:
        print("checkpoint error:",type(e).__name__,file=sys.stderr);return 2
    print(json.dumps(record,ensure_ascii=False));return 0
if __name__=="__main__":sys.exit(main())
