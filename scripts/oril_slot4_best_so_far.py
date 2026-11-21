"""Advisory public best-so-far selection; never approves promotion."""
import json
import math
import sys

REQUIRED = {"cycle_id","candidate_sha","evidence_sha256","public_correct","public_total","new_regressions","token_saving_pct","review_state"}

def select(rows):
    if not isinstance(rows,list) or not rows:
        raise ValueError("nonempty records required")
    seen=set()
    eligible=[]
    for row in rows:
        if not isinstance(row,dict) or set(row)!=REQUIRED:
            raise ValueError("invalid record schema")
        cycle=row["cycle_id"]
        if not isinstance(cycle,str) or not cycle or cycle in seen:
            raise ValueError("duplicate/invalid cycle")
        seen.add(cycle)
        for k in ("candidate_sha","evidence_sha256"):
            s=row[k]
            if not isinstance(s,str) or len(s)!=64 or any(c not in "0123456789abcdef" for c in s):
                raise ValueError("invalid SHA256")
        for k in ("public_correct","public_total","new_regressions"):
            if type(row[k]) is not int or row[k]<0:
                raise ValueError("invalid count")
        if not 0<row["public_total"] or row["public_correct"]>row["public_total"] or row["new_regressions"]>row["public_total"]:
            raise ValueError("inconsistent counts")
        s=row["token_saving_pct"]
        if type(s) not in (int,float) or not math.isfinite(s) or not -100<=s<=100:
            raise ValueError("invalid savings")
        if row["review_state"] not in ("tested","rejected"):
            raise ValueError("not publicly reviewed")
        if row["review_state"]=="tested" and row["new_regressions"]==0:
            eligible.append(row)
    best=max(enumerate(eligible),key=lambda x:(x[1]["public_correct"]/x[1]["public_total"],x[1]["token_saving_pct"],-x[0]))[1] if eligible else None
    return {"public_best_cycle_id":best["cycle_id"] if best else None,
            "public_best_candidate_sha":best["candidate_sha"] if best else None,
            "eligible_count":len(eligible),"protected_grade":"pending","promotion_allowed":False}

if __name__=="__main__":
    with open(sys.argv[1],encoding="utf-8") as f:
        print(json.dumps(select(json.load(f)),sort_keys=True))
