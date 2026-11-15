#!/usr/bin/env python3
"""Local checkpoint recording and validated read-only recovery; never executes tasks."""
import argparse,datetime,json,os,pathlib,subprocess,sys,tempfile
STAGES=("interview","seed","trd","decompose","run","evaluate","evolve")
OUTCOMES=("pass","fail","blocked")
def validate(record):
    if not isinstance(record,dict) or set(record)!={"schema_version","stage","outcome","note","commit","timestamp","next_stage","requires_human_merge_approval"}:raise ValueError("invalid checkpoint schema")
    if type(record["schema_version"]) is not int or record["schema_version"]!=1:raise ValueError("unsupported schema")
    stage,outcome=record["stage"],record["outcome"]
    if stage not in STAGES or outcome not in OUTCOMES:raise ValueError("invalid stage/outcome")
    expected=STAGES[(STAGES.index(stage)+1)%len(STAGES)] if outcome=="pass" else stage
    if record["next_stage"]!=expected:raise ValueError("invalid transition")
    if record["requires_human_merge_approval"] is not True:raise ValueError("approval required")
    if not isinstance(record["commit"],str) or len(record["commit"]) not in (40,64) or any(c not in "0123456789abcdef" for c in record["commit"]):raise ValueError("invalid commit")
    if not isinstance(record["note"],str) or len(record["note"])>1000:raise ValueError("invalid note")
    if not isinstance(record["timestamp"],str):raise ValueError("invalid timestamp")
    dt=datetime.datetime.fromisoformat(record["timestamp"])
    if dt.tzinfo is None:raise ValueError("timestamp must have timezone")
    return record
def evaluate(root,stage,outcome,note):
    if stage not in STAGES or outcome not in OUTCOMES:raise ValueError("invalid stage or outcome")
    if not isinstance(note,str):raise ValueError("invalid note")
    head=subprocess.run(["git","-C",str(root),"rev-parse","HEAD"],check=True,capture_output=True,text=True).stdout.strip()
    return validate({"schema_version":1,"stage":stage,"outcome":outcome,"note":note[:1000],"commit":head,
      "timestamp":datetime.datetime.now(datetime.timezone.utc).isoformat(),
      "next_stage":STAGES[(STAGES.index(stage)+1)%len(STAGES)] if outcome=="pass" else stage,
      "requires_human_merge_approval":True})
def checkpoint(path,record):
    validate(record)
    path=path.resolve()
    if path.is_symlink():raise ValueError("symlink checkpoint forbidden")
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=".checkpoint-",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump(record,f,ensure_ascii=False,indent=2);f.write("\n");f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
def recover(path,root=None):
    path=path.absolute()
    if path.is_symlink() or path.stat().st_size>65536:raise ValueError("unsafe checkpoint")
    record=validate(json.loads(path.read_text(encoding="utf-8")))
    if root is not None:
        head=subprocess.run(["git","-C",str(root),"rev-parse","HEAD"],check=True,capture_output=True,text=True).stdout.strip()
        if head!=record["commit"]:raise ValueError("checkpoint commit differs from HEAD")
    return record
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=pathlib.Path,default=pathlib.Path(__file__).resolve().parents[1])
    p.add_argument("--stage",choices=STAGES)
    p.add_argument("--outcome",choices=OUTCOMES)
    p.add_argument("--note",default="")
    p.add_argument("--recover",action="store_true")
    p.add_argument("--output",type=pathlib.Path,default=pathlib.Path("artifacts/ouroboros-checkpoint.json"))
    a=p.parse_args()
    try:
        if a.recover:
            if a.stage or a.outcome:raise ValueError("recovery does not accept stage/outcome")
            record=recover(a.output,a.root)
        else:
            if not a.stage or not a.outcome:raise ValueError("stage and outcome required")
            record=evaluate(a.root,a.stage,a.outcome,a.note);checkpoint(a.output,record)
    except (OSError,ValueError,UnicodeError,json.JSONDecodeError,subprocess.CalledProcessError) as e:
        print("checkpoint error:",type(e).__name__,file=sys.stderr);return 2
    print(json.dumps(record,ensure_ascii=False));return 0
if __name__=="__main__":sys.exit(main())
