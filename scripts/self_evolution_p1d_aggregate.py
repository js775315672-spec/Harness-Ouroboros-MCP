#!/usr/bin/env python3
"""P1d fail-closed read-only aggregation of eight independently replayed tasks.

No CI attestation of source commits, no recursion, no remote write, no merges.
"""
import argparse
import json
from pathlib import Path
from self_evolution_eight_distinct import TASKS, VARIANT, context, sha


def unique_keys(pairs):
    out={}
    for k,v in pairs:
        if k in out:
            raise ValueError("duplicate JSON evidence key")
        out[k]=v
    return out


def read(path):
    p=Path(path)
    if p.is_symlink() or not p.is_file() or p.stat().st_size>30000:
        raise ValueError("missing, linked or oversized report")
    return json.loads(p.read_text(encoding="utf-8"),object_pairs_hook=unique_keys)


def aggregate(root,config,reviewed_sha,models,replays):
    if (type(models) is not list or type(replays) is not list
            or len(models)!=8 or len(replays)!=8):
        raise ValueError("exactly eight paired reports required")
    if any(not isinstance(r,dict) for r in models+replays):
        raise ValueError("malformed report")
    names=list(TASKS)
    if ([r.get("lane") for r in models]!=names
            or [r.get("lane") for r in replays]!=names):
        raise ValueError("missing/duplicate/out-of-order lane")
    passing=[]
    outcomes=[]
    digests={}
    prompts=set()
    for lane,m,p in zip(names,models,replays):
        trusted,_,_=context(root,config,lane,reviewed_sha)
        if any(type(m.get(k)) is not type(v) or m[k]!=v for k,v in trusted.items()):
            raise ValueError("candidate was not bound to the reviewed task")
        if (type(m.get("model_calls")) is not int or m["model_calls"]!=1
                or p.get("merge_authorized") is not False):
            raise ValueError("missing model call or unsafe replay")
        raw=m.get("raw_response")
        if (not isinstance(raw,str)
                or m.get("response_sha256")!=sha(raw.encode("utf-8"))):
            raise ValueError("corrupt model provenance")
        label=m.get("outcome")
        if label=="ast_rejected":
            correct=(p.get("status")=="replayed_ast_rejection"
                     and p.get("passed") is False
                     and m.get("candidate_sha256") is None
                     and p.get("candidate_sha256") is None)
        elif label in ("candidate_passed","candidate_failed"):
            correct=(p.get("status")=="replayed_candidate"
                     and type(p.get("passed")) is bool
                     and p["passed"]==(label=="candidate_passed")
                     and m.get("candidate_sha256")==p.get("candidate_sha256")
                     and isinstance(m.get("grade"),dict)
                     and m["grade"].get("status")==label)
        else:
            correct=False
        if not correct:
            raise ValueError("fabricated or unreplayed passing report")
        prompts.add(m["prompt_sha256"])
        if label=="candidate_passed":
            passing.append(lane)
            digests.setdefault(m["candidate_sha256"],[]).append(lane)
        outcomes.append({"lane":lane,"outcome":label,
                         "independently_replayed":True,
                         "candidate_sha256":m.get("candidate_sha256")})
    if len(prompts)!=8:
        raise ValueError("task prompt diversity missing")
    return {"schema":1,"status":"eight_distinct_tasks_measured",
            "tasks":8,"fresh_model_calls":8,"independent_replays":8,
            "candidate_passes":len(passing),
            "unique_passing_source_sha256":len(digests),
            "duplicate_source_groups":[{"sha256":k,"lanes":v}
                                       for k,v in sorted(digests.items())
                                       if len(v)>1],
            "passes":passing,"lanes":outcomes,
            "architecture_diversity_proven":False,
            "ci_attested_source_commits":0,"recursive_parent_promotions":0,
            "auto_merge_authorized":False,"remote_push_authorized":False}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",required=True,type=Path)
    p.add_argument("--config",required=True,type=Path)
    p.add_argument("--head-sha",required=True)
    p.add_argument("--model-dir",required=True,type=Path)
    p.add_argument("--replay-dir",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args()
    if a.output.exists() or a.output.is_symlink():
        raise SystemExit("cannot overwrite report")
    model=[read(a.model_dir/f"p1d-lane-{k}"/"record.json") for k in TASKS]
    replay=[read(a.replay_dir/f"lane-{k}.json") for k in TASKS]
    r=aggregate(a.root,a.config,a.head_sha,model,replay)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(r,sort_keys=True,indent=2)+"\n")
    print(json.dumps({key:r.get(key) for key in (
        "status","fresh_model_calls","candidate_passes",
        "unique_passing_source_sha256","recursive_parent_promotions")},sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
