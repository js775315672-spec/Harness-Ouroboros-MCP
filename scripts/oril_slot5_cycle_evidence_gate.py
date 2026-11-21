"""Read-only fail-closed evidence gate; never grants promotion approval."""
import json, re, sys
from pathlib import Path
SHA=re.compile(r'^[0-9a-f]{40}$')
HASH=re.compile(r'^[0-9a-f]{64}$')
RUN=re.compile(r'https://github\.com/[^/]+/[^/]+/actions/runs/[0-9]+')
REQUIRED=('baseline_sha','candidate_sha','model_run_url','model_output_sha256','grader_sha','grader_run_url','feedback_sha256','next_cycle_id')
def audit(r):
    if not isinstance(r,dict): return {'status':'BLOCKED','errors':['record_not_object']}
    e=[]
    for k in REQUIRED:
        if not isinstance(r.get(k),str) or not r[k].strip(): e.append('missing:'+k)
    for k in ('baseline_sha','candidate_sha','grader_sha'):
        if k in r and not SHA.fullmatch(str(r[k])): e.append('invalid_sha:'+k)
    for k in ('model_output_sha256','feedback_sha256'):
        if k in r and not HASH.fullmatch(str(r[k])): e.append('invalid_sha256:'+k)
    for k in ('model_run_url','grader_run_url'):
        if k in r and not RUN.fullmatch(str(r[k])): e.append('invalid_run_url:'+k)
    if r.get('model_run_url') and r.get('model_run_url')==r.get('grader_run_url'): e.append('grader_not_separate_run')
    if r.get('independent_grade')!='PASS': e.append('independent_grade_not_pass')
    if type(r.get('critical_regressions')) is not int or r['critical_regressions']!=0: e.append('regressions_not_zero')
    if r.get('heldout_evaluation')!='PASS': e.append('heldout_not_pass')
    if r.get('model_weights_improved') is True:
        for k in ('gpu_log_url','adapter_sha256','optimizer_steps'):
            if not r.get(k): e.append('missing_weight_evidence:'+k)
        if r.get('adapter_sha256') and not HASH.fullmatch(str(r['adapter_sha256'])): e.append('invalid_adapter_sha256')
        if type(r.get('optimizer_steps')) is not int or r['optimizer_steps']<=0: e.append('invalid_optimizer_steps')
    return {'status':'BLOCKED' if e else 'EVIDENCE_COMPLETE_NOT_APPROVED','errors':sorted(set(e))}
if __name__=='__main__':
    if len(sys.argv)!=2: sys.exit('usage: python oril_slot5_cycle_evidence_gate.py record.json')
    try: result=audit(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')))
    except (OSError,ValueError) as ex: result={'status':'BLOCKED','errors':[type(ex).__name__]}
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    sys.exit(0 if result['status']=='EVIDENCE_COMPLETE_NOT_APPROVED' else 2)
