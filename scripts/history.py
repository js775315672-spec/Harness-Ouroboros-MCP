#!/usr/bin/env python3
"""Append-only, hash-linked checkpoint journal. Read-only verification and recovery."""
import argparse,hashlib,json,os,pathlib,sys,tempfile
from ouroboros import validate
MAX_BYTES=8*1024*1024
def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")
def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()
def read_history(path):
    path=path.absolute()
    if path.is_symlink():raise ValueError("symlink history forbidden")
    if not path.exists():return []
    if path.stat().st_size>MAX_BYTES:raise ValueError("history too large")
    entries=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(entries,list):raise ValueError("history must be a list")
    previous=None
    for i,item in enumerate(entries):
        if not isinstance(item,dict) or set(item)!={"index","previous_hash","record","hash"}:raise ValueError("invalid journal entry")
        if type(item["index"]) is not int or item["index"]!=i:raise ValueError("invalid index")
        if item["previous_hash"]!=previous:raise ValueError("broken hash chain")
        validate(item["record"])
        expected=digest({"index":i,"previous_hash":previous,"record":item["record"]})
        if item["hash"]!=expected:raise ValueError("journal tampering detected")
        previous=item["hash"]
    return entries
def append(path,record):
    validate(record)
    path=path.absolute()
    if path.is_symlink():raise ValueError("symlink history forbidden")
    entries=read_history(path)
    if entries and entries[-1]["record"]["commit"]!=record["commit"]:
        raise ValueError("commit mismatch; start a new journal for this commit")
    if entries and entries[-1]["record"]["timestamp"]>record["timestamp"]:
        raise ValueError("non-monotonic timestamp")
    i=len(entries)
    prev=entries[-1]["hash"] if entries else None
    body={"index":i,"previous_hash":prev,"record":record}
    entries.append({**body,"hash":digest(body)})
    if len(canonical(entries))>MAX_BYTES:raise ValueError("journal size limit")
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix=".history-",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as file:
            json.dump(entries,file,ensure_ascii=False,indent=2)
            file.write("\n");file.flush();os.fsync(file.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    return entries[-1]
def recover_latest(path,expected_commit=None):
    entries=read_history(path)
    if not entries:raise ValueError("empty history")
    record=entries[-1]["record"]
    if expected_commit is not None and record["commit"]!=expected_commit:raise ValueError("commit mismatch")
    return record
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--history",type=pathlib.Path,required=True)
    p.add_argument("--verify",action="store_true")
    p.add_argument("--recover",action="store_true")
    p.add_argument("--expected-commit")
    a=p.parse_args()
    try:
        if a.verify:
            print(json.dumps({"verified_entries":len(read_history(a.history))}))
        elif a.recover:
            print(json.dumps(recover_latest(a.history,a.expected_commit),sort_keys=True))
        else:
            p.error("specify --verify or --recover")
    except (OSError,ValueError,UnicodeError,json.JSONDecodeError) as exc:
        print("BLOCK:",type(exc).__name__,file=sys.stderr);return 2
    return 0
if __name__=="__main__":sys.exit(main())
