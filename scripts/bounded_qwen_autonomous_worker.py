#!/usr/bin/env python3
"""Two new preapproved Qwen coding tasks, sequential AST+Docker gates, checkpoint.
No model code runs outside disposable no-network Docker. No checkout writes,
commit, paid API, secret, merge, deployment, or unearned Ouroboros queue credit.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import tempfile
import time

from gguf_cpu_runtime import CPUInference, approved_model, sha256_file
from qwen_source_disposable_compare import FILES, _safe_file, _test

REPO = "js775315672-spec/Harness-Ouroboros-MCP"
SOURCE = "scripts/feedback_controller_verified.py"
ARCHIVE = "proposals/two_qwen_7b_patches_v1.json"
TASKS = (("log_carriage_return", 13), ("log_del_control", 127))
BASE_LINE = ('        if status not in ("pass","fail") or not isinstance(log,str) '
             'or len(log)>MAX_LOG_CHARS or (chr(0) in log or chr(27) in log):')
MAX_ATTEMPTS = 3
MAX_BUDGET_SECONDS = 1800
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")

TEST = '''import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from feedback_controller import feedback
from task_selector import select
NEW=__NEW__
PREVIOUS=__PREVIOUS__
def checks(log):
    return {n:{"status":"pass","log":log} for n in
            ("harness","ouroboros","regression","secrets")}
class WorkerControl(unittest.TestCase):
    def test_new_control_rejected(self):
        with self.assertRaises(ValueError):
            feedback(select(),checks("prefix"+chr(NEW)+"suffix"))
    def test_previous_controls_remain_rejected(self):
        for point in PREVIOUS:
            with self.subTest(point=point):
                with self.assertRaises(ValueError):
                    feedback(select(),checks("a"+chr(point)+"b"))
    def test_normal_unicode_and_newline(self):
        self.assertEqual(feedback(select(),checks("한국어\\nnormal"))["decision"],"review")
'''


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def seal(payload):
    doc = dict(payload)
    doc["integrity"] = sha(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                      ensure_ascii=False).encode())
    return doc


def original(root):
    root = Path(root).resolve(strict=True)
    raw = _safe_file(root, SOURCE).read_bytes()
    doc = json.loads(_safe_file(root, ARCHIVE).read_text(encoding="utf-8"))
    if (sha(raw) != doc.get("first_plus_second_source_sha256") or
            raw.decode().count(BASE_LINE + "\n") != 1):
        raise ValueError("trusted model source baseline changed")
    return raw.decode(), sha(raw)


def parse(raw, point):
    if not isinstance(raw, str) or not 1 <= len(raw.encode()) <= 400:
        raise ValueError("unbounded inference output")
    value = raw.strip()
    if value.startswith(chr(96)) or value.endswith(chr(96)):
        if (value.count(chr(96)) != 2 or not value.startswith(chr(96)) or
                not value.endswith(chr(96))):
            raise ValueError("unsafe inline markup")
        value = value[1:-1].strip()
    if (len(value) > 120 or any(c in value for c in ("\n", "\r", "\x00", "\x1b", chr(96)))):
        raise ValueError("unsafe expression formatting")
    try:
        expr = ast.parse(value, mode="eval").body
    except SyntaxError as exc:
        raise ValueError("invalid model expression") from exc
    if (not isinstance(expr, ast.Compare) or
            not isinstance(expr.left, ast.Call) or
            not isinstance(expr.left.func, ast.Name) or expr.left.func.id != "chr" or
            len(expr.left.args) != 1 or expr.left.keywords or
            not isinstance(expr.left.args[0], ast.Constant) or
            type(expr.left.args[0].value) is not int or
            expr.left.args[0].value != point or len(expr.ops) != 1 or
            not isinstance(expr.ops[0], ast.In) or len(expr.comparators) != 1 or
            not isinstance(expr.comparators[0], ast.Name) or
            expr.comparators[0].id != "log"):
        raise ValueError("outside fixed AST membership allowlist")
    return value


def apply(before, expr, index):
    value = parse(expr, TASKS[index][1])
    line = BASE_LINE
    for _, point in TASKS[:index]:
        line = line[:-1] + " or (chr(" + str(point) + ") in log):"
    if before.count(line + "\n") != 1:
        raise ValueError("missing exact ordered source anchor")
    after = before.replace(line + "\n", line[:-1] + " or (" + value + "):\n", 1)
    a, b = ast.parse(before), ast.parse(after)
    n = before.splitlines().index(line) + 1
    for tree in (a, b):
        matches = [x for x in ast.walk(tree) if isinstance(x, ast.If) and x.lineno == n]
        if len(matches) != 1:
            raise ValueError("unscoped AST change")
        matches[0].test = ast.Constant(value=True)
    if ast.dump(a, include_attributes=False) != ast.dump(b, include_attributes=False):
        raise ValueError("model modified code outside approved guard")
    return after


def checkpoint_base(root, commit):
    if not isinstance(commit, str) or not SHA40.fullmatch(commit):
        raise ValueError("unbound Git commit")
    _, original_sha = original(root)
    return seal({"schema": 1, "repo": REPO, "commit": commit,
                 "base_source_sha256": original_sha, "source_sha256": original_sha,
                 "steps": [], "attempts": [], "state": "pending",
                 "completed_tasks": 0, "merge_authorized": False,
                 "human_review_required": True})


def validate(root, document, commit):
    if not isinstance(document, dict) or not isinstance(document.get("integrity"), str):
        raise ValueError("missing checkpoint seal")
    raw = {k:v for k,v in document.items() if k != "integrity"}
    if document != seal(raw):
        raise ValueError("tampered checkpoint or unexpected schema")
    original_source, original_sha = original(root)
    if (set(raw) != {"schema","repo","commit","base_source_sha256","source_sha256",
                    "steps","attempts","state","completed_tasks","merge_authorized",
                    "human_review_required"} or
            raw["schema"] != 1 or raw["repo"] != REPO or raw["commit"] != commit or
            raw["base_source_sha256"] != original_sha or
            raw["state"] not in ("pending","blocked","complete") or
            raw["merge_authorized"] is not False or
            raw["human_review_required"] is not True or
            not isinstance(raw["steps"], list) or not isinstance(raw["attempts"], list) or
            len(raw["steps"]) > len(TASKS) or len(raw["attempts"]) > 6 or
            type(raw["completed_tasks"]) is not int or
            raw["completed_tasks"] != len(raw["steps"])):
        raise ValueError("untrusted checkpoint fields")
    current = original_source
    for i, step in enumerate(raw["steps"]):
        if (not isinstance(step, dict) or
                set(step) != {"task","expression","model_response_sha256","source_sha256",
                              "regression_tests","negative_tests"} or
                step["task"] != TASKS[i][0] or
                not isinstance(step["model_response_sha256"], str) or
                not SHA64.fullmatch(step["model_response_sha256"]) or
                step["regression_tests"] != 8 or step["negative_tests"] != 3):
            raise ValueError("unverified completed task evidence")
        current = apply(current, step["expression"], i)
        if step["source_sha256"] != sha(current.encode()):
            raise ValueError("stale generated source digest")
    if raw["source_sha256"] != sha(current.encode()):
        raise ValueError("source cannot be reconstructed")
    if (raw["state"] == "complete") != (len(raw["steps"]) == len(TASKS)):
        raise ValueError("false loop completion")
    for row in raw["attempts"]:
        if (not isinstance(row, dict) or
                set(row) != {"task", "number", "response_sha256", "status"} or
                row["task"] not in [task[0] for task in TASKS] or
                type(row["number"]) is not int or not 1 <= row["number"] <= 3 or
                not isinstance(row["response_sha256"], str) or
                not SHA64.fullmatch(row["response_sha256"]) or
                row["status"] not in ("ast_rejected","docker_rejected","accepted")):
            raise ValueError("invalid bounded attempt history")
    for i, (task, _) in enumerate(TASKS):
        rows = [x for x in raw["attempts"] if x["task"] == task]
        if (len(rows) > 3 or [x["number"] for x in rows] != list(range(1,len(rows)+1))
                or sum(x["status"] == "accepted" for x in rows) != int(i < len(raw["steps"]))
                or (i < len(raw["steps"]) and rows[-1]["status"] != "accepted")):
            raise ValueError("falsified model attempt history")
    return current


def store(path, record):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("checkpoint symlinks forbidden")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
    if len(payload.encode()) > 32768:
        raise ValueError("checkpoint budget exceeded")
    fd, temp = tempfile.mkstemp(prefix=".bounded-qwen-", dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as out:
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def load(root, path, commit):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32768:
        raise ValueError("missing or unsafe checkpoint")
    doc = json.loads(path.read_text(encoding="utf-8"))
    validate(root, doc, commit)
    return doc


def docker_compare(root, before, after, index):
    root = Path(root).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="qwen-worker-") as temp:
        os.chmod(temp, 0o755)
        suites = []
        for label, body in (("before",before),("after",after)):
            stage = Path(temp) / label
            for relative in FILES:
                destination = stage / relative
                destination.parent.mkdir(parents=True,exist_ok=True)
                destination.write_bytes(_safe_file(root, relative).read_bytes())
            (stage / "scripts/feedback_controller.py").write_text(body,encoding="utf-8")
            t = TEST.replace("__NEW__",str(TASKS[index][1])).replace(
                "__PREVIOUS__",repr((0,27)+tuple(point for _,point in TASKS[:index])))
            (stage / "tests/test_bounded_control.py").write_text(t,encoding="utf-8")
            for d in (stage,stage/"scripts",stage/"tests"):
                os.chmod(d,0o755)
            for rel in FILES + ("tests/test_bounded_control.py",):
                os.chmod(stage/rel,0o644)
            suites.append((_test(stage,"test_feedback_controller.py"),
                           _test(stage,"test_bounded_control.py")))
        (base_reg,base_neg),(new_reg,new_neg) = suites
    ok = (base_reg.get("passed") is True and base_reg.get("tests_run")==8
          and base_neg.get("passed") is False and base_neg.get("tests_run")==3
          and base_neg.get("exit_code")==1
          and new_reg.get("passed") is True and new_reg.get("tests_run")==8
          and new_neg.get("passed") is True and new_neg.get("tests_run")==3)
    for item in (base_reg,base_neg,new_reg,new_neg):
        ok = ok and all(item.get(k) is True for k in
                        ("network_disabled","filesystem_read_only","privileges_dropped"))
    return bool(ok)


def request_prompt(index, attempt):
    task, point = TASKS[index]
    prompt = ("Fix a Python log validator. Write only ONE Python boolean "
              "expression that is true when the string named log contains the "
              "control character with Unicode code point " + str(point) + ". "
              "Use Python's chr(n) built-in, membership operator 'in', and log. "
              "Do not write the actual control character, if, return, "
              "Markdown, explanation, or any other names.")
    if attempt > 1:
        prompt += (" Your prior candidate failed scoped AST/Docker checks. "
                   "Use precisely a single chr call with code point " + str(point) +
                   ", combined with membership in log.")
    return prompt


def run(root, commit, inference, path, budget_seconds=1800, resume=False,
        compare=docker_compare):
    if type(budget_seconds) is not int or not 30 <= budget_seconds <= MAX_BUDGET_SECONDS:
        raise ValueError("unbounded time budget")
    started = time.monotonic()
    path = Path(path)
    if resume:
        state = load(root,path,commit)
        if state["state"]=="complete":
            return state
    else:
        if path.exists() or path.is_symlink():
            raise ValueError("checkpoint exists; explicit resume required")
        state = checkpoint_base(root,commit)
        store(path,state)
    source_text = validate(root,state,commit)
    for index in range(len(state["steps"]),len(TASKS)):
        task = TASKS[index][0]
        count = sum(row["task"]==task for row in state["attempts"])
        for number in range(count+1,MAX_ATTEMPTS+1):
            if time.monotonic()-started >= budget_seconds:
                state["state"]="blocked"
                state=seal({k:v for k,v in state.items() if k!="integrity"})
                store(path,state)
                return state
            raw = inference.generate(request_prompt(index,number))
            if not isinstance(raw,str) or len(raw.encode())>6000:
                raise ValueError("untrusted GGUF adapter output")
            result="ast_rejected"
            try:
                expr = parse(raw,TASKS[index][1])
                candidate=apply(source_text,expr,index)
                result="accepted" if compare(root,source_text,candidate,index) else "docker_rejected"
            except (ValueError,SyntaxError):
                result="ast_rejected"
            state["attempts"].append({"task":task,"number":number,
                                      "response_sha256":sha(raw.encode()),"status":result})
            if result=="accepted":
                state["steps"].append({"task":task,"expression":expr,
                                       "model_response_sha256":sha(raw.encode()),
                                       "source_sha256":sha(candidate.encode()),
                                       "regression_tests":8,"negative_tests":3})
                state["completed_tasks"]=len(state["steps"])
                state["source_sha256"]=sha(candidate.encode())
                source_text=candidate
            state["state"]="complete" if len(state["steps"])==len(TASKS) else "pending"
            state=seal({k:v for k,v in state.items() if k!="integrity"})
            validate(root,state,commit)
            store(path,state)
            if result=="accepted":
                break
        if len(state["steps"])==index:
            state["state"]="blocked"
            state=seal({k:v for k,v in state.items() if k!="integrity"})
            store(path,state)
            return state
    return state


def verify(root,path,commit,compare=docker_compare):
    state=load(root,path,commit)
    if state["state"]!="complete" or len(state["steps"])!=len(TASKS):
        raise ValueError("not a successful two-task model loop")
    before,_=original(root)
    for index,step in enumerate(state["steps"]):
        after=apply(before,step["expression"],index)
        if not compare(root,before,after,index):
            raise ValueError("independent Docker replay failed")
        before=after
    return {"status":"fresh_two_model_patches_replayed","model_calls":len(state["attempts"]),
            "sandbox_patches":2,"queue_ci_attested":0,"checkout_modified":False,
            "merge_authorized":False,"general_autonomous_development_proven":False}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("mode",choices=("run","verify"))
    p.add_argument("--root",type=Path,default=Path("."))
    p.add_argument("--head-sha",required=True)
    p.add_argument("--checkpoint",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True)
    p.add_argument("--cli",type=Path)
    p.add_argument("--gguf",type=Path)
    p.add_argument("--download-metadata",type=Path)
    p.add_argument("--budget-seconds",type=int,default=1800)
    p.add_argument("--resume",action="store_true")
    args=p.parse_args()
    out={"status":"blocked","merge_authorized":False}
    try:
        if args.mode=="verify":
            out=verify(args.root,args.checkpoint,args.head_sha)
        else:
            if args.cli is None or args.gguf is None or args.download_metadata is None:
                raise ValueError("official offline model required")
            model=approved_model("7b")
            info=json.loads(args.download_metadata.read_text(encoding="utf-8"))
            if (info.get("model")!="7b" or info.get("repository")!=model["repo"]
                    or info.get("filename")!=model["filename"]
                    or info.get("license")!="apache-2.0"
                    or info.get("quantization")!="Q4_K_M"
                    or sha256_file(args.gguf)!=info.get("sha256")):
                raise ValueError("model provenance mismatch")
            infer=CPUInference("7b",args.cli,args.gguf,timeout_seconds=150)
            started=time.perf_counter()
            state=run(args.root,args.head_sha,infer,args.checkpoint,
                      args.budget_seconds,args.resume)
            out={"status":"model_loop_complete" if state["state"]=="complete"
                 else "model_loop_incomplete",
                 "sandbox_completed":state["completed_tasks"],
                 "model_calls":len(state["attempts"]),
                 "elapsed_seconds":round(time.perf_counter()-started,3),
                 "peak_child_rss_kib":resource.getrusage(
                     resource.RUSAGE_CHILDREN).ru_maxrss,
                 "model_inference":infer.calls,"queue_ci_attested":0,
                 "checkout_modified":False,"merge_authorized":False}
    except (OSError,ValueError,KeyError,TypeError,SyntaxError,json.JSONDecodeError) as error:
        out={"status":"blocked","error_type":type(error).__name__,
             "error_category":str(error)[:140],"merge_authorized":False}
    if args.report.exists() or args.report.is_symlink():
        raise SystemExit("report exists")
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n",
                           encoding="utf-8")
    print(json.dumps({k:out.get(k) for k in
          ("status","sandbox_completed","model_calls","queue_ci_attested",
           "merge_authorized")},sort_keys=True))
    return 0 if out["status"] in ("model_loop_complete","fresh_two_model_patches_replayed") else 2

if __name__=="__main__":
    raise SystemExit(main())
