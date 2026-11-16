#!/usr/bin/env python3
"""P1d: eight DIFFERENT small Python coding tasks on independent Qwen CPU runners.

One fresh Qwen7B inference per lane. Each answer is a single solve(data)
function, inspected as untrusted AST, then evaluated only in locked-down
read-only, no-network, non-root Docker with lane-specific held-out tests.
There is no model-controlled shell/checkout write, Git push, merge, scheduling,
recursive task spawn or CI-attested source commit here.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

from disposable_regression_compare import _docker_command
from gguf_cpu_runtime import approved_model, sha256_file, verify_paths
from gguf_output_boundary import extract_completion
from qwen_chatml_prompt import format_chatml
from self_evolution_task_contract import load_config, build_manifests

ROOT = Path(__file__).resolve().parents[1]
HOLDOUT = "tests/heldout_p1d.py"
VARIANT = "p1d-eight-distinct-fixed-tasks-v1"
MAX_BYTES = 12000
TASKS = {
    "01": "Implement def solve(data): for a dict with genuine int epoch and limit (bool is NOT int), 0<=epoch<=100000 and 1<=limit<=100000. Return epoch+1 only if epoch<limit, else None. Invalid input returns None.",
    "02": "Implement def solve(data): data is a list of at most 16 nonempty strings, each length at most 16. Return a NEW list of IDs deduplicated in first-appearance order. Invalid input or any invalid member returns []. Do not mutate input.",
    "03": "Implement def solve(data): data is dict with tasks (list of dicts with string id and list-of-string deps) and done (list of strings), maximum 16 tasks. Return a lexicographically sorted NEW list of IDs not in done for which all dependencies are in done. For invalid input/duplicate task IDs return []. Do not mutate input.",
    "04": "Implement def solve(data): a dict with parents list of 1..8 DISTINCT nonempty strings, and genuine int fanout from 1..8 (bool invalid). Return in original parent order the strings parent+'/0', parent+'/1' ... through fanout-1, capped at 64 total. Invalid input returns [].",
    "05": "Implement def solve(data): data dict has cpu, cpu_max, mem, mem_max. Require all four are genuine Python int values (bool invalid), both maxima >0, each used value >=0. Return True only if cpu<=cpu_max AND mem<=mem_max. Invalid input returns False.",
    "06": "Implement def solve(data): for a list of at most 16 strings return a NEW SORTED UNIQUE list of safe relative repository file paths. Every path must start exactly scripts/, tests/, or docs/ followed by a nonempty name; no path may contain backslash, colon, empty segment, '.' or '..' segment. Invalid input or any invalid element returns []. Do not mutate input.",
    "07": "Implement def solve(data): data is a list of up to 16 candidate dicts with unique nonempty string id, passed that is genuine bool and latency that is genuine int >=0. If input malformed return []. Return up to THREE IDs from only passed=True entries, sorted ascending by (latency,id). Do not mutate input.",
    "08": "Implement def solve(data): data dict has phase and event strings. Exact transitions: ('pending','start')->'running', ('running','pass')->'verified', ('running','fail')->'blocked', ('verified','review')->'review', ('blocked','reset')->'pending'. ALL other inputs/pairs return 'blocked'. NEVER return 'merge'.",
}
BANNED = (
    ast.Import, ast.ImportFrom, ast.ClassDef, ast.AsyncFunctionDef,
    ast.With, ast.AsyncWith, ast.Global, ast.Nonlocal, ast.Delete,
    ast.Lambda, ast.Yield, ast.YieldFrom, ast.Await, ast.Try, ast.Raise,
    ast.While, ast.Assert, ast.NamedExpr, ast.Match,
)
ALLOWED_CALLS = {
    "len", "isinstance", "type", "range", "enumerate", "sorted", "list",
    "dict", "tuple", "set", "all", "any", "min", "max", "str", "int",
}
ALLOWED_METHODS = {"get", "append", "add", "startswith", "endswith", "split",
                   "sort", "count"}
SOURCE_SHA = re.compile(r"[0-9a-f]{40}\Z")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def task_prompt(config, lane):
    if lane not in TASKS:
        raise ValueError("unregistered task lane")
    row = next(x for x in config["lanes"] if x["id"] == lane)
    return (
        "You are coding a small deterministic, fail-closed Python function. "
        "Output EXACTLY one complete function source named solve, with one "
        "positional argument data; no Markdown fences, comments, prose or tests. "
        "Do NOT import, access files or network, define helpers, use while, "
        "eval/exec or global variables. Use if/for/return and safe builtins. "
        "Be precise about type(x) is int rather than isinstance(x,int) when "
        "excluding bool. Entire program max 110 lines. TASK: " + TASKS[lane] +
        " Architecture exploration hint (not an extra task): " + row["hypothesis"]
    )


def heldout(root):
    root = Path(root).resolve(strict=True)
    p = root / HOLDOUT
    if (p.is_symlink() or not p.is_file() or not p.resolve().is_relative_to(root)
            or not 1000 <= p.stat().st_size <= 30000):
        raise ValueError("missing or invalid held-out test suite")
    data = p.read_bytes()
    return data, sha(data)


def strip_exact_fence(raw):
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_BYTES:
        raise ValueError("model response size/type")
    if any(c in raw for c in ("\x00", "\r", "\x1b")):
        raise ValueError("physical control bytes forbidden")
    clean = raw.strip()
    mark = chr(96)*3
    if mark not in clean:
        return clean + "\n"
    opening, closing = mark + "python\n", "\n" + mark
    if (not clean.startswith(opening) or not clean.endswith(closing)
            or clean.count(mark) != 2):
        raise ValueError("untrusted source envelope")
    return clean[len(opening):-len(closing)].strip() + "\n"


def inspect_source(raw):
    """Only static structural checks on host. Model code runs in Docker alone."""
    source = strip_exact_fence(raw)
    if not 25 <= len(source.encode("utf-8")) <= MAX_BYTES or len(source.splitlines()) > 110:
        raise ValueError("invalid bounded source length")
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        raise ValueError("invalid model Python syntax") from e
    if len(tree.body) != 1 or type(tree.body[0]) is not ast.FunctionDef:
        raise ValueError("expected one function")
    fn = tree.body[0]
    args = fn.args
    if (fn.name != "solve" or fn.decorator_list or fn.returns
            or getattr(fn, "type_params", ()) or fn.type_comment
            or args.posonlyargs or len(args.args) != 1 or args.args[0].arg != "data"
            or args.args[0].annotation or args.kwonlyargs or args.vararg
            or args.kwarg or args.defaults or args.kw_defaults):
        raise ValueError("unexpected function signature")
    local_names = set()
    for node in ast.walk(tree):
        if isinstance(node, BANNED):
            raise ValueError("forbidden AST syntax")
        if isinstance(node, (ast.Name, ast.Attribute)):
            label = node.id if isinstance(node, ast.Name) else node.attr
            if "__" in label:
                raise ValueError("dunder expression forbidden")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id not in ALLOWED_CALLS:
                    raise ValueError("unapproved callable")
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr not in ALLOWED_METHODS:
                    raise ValueError("unapproved method")
            else:
                raise ValueError("dynamic call forbidden")
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if not isinstance(t, (ast.Name, ast.Tuple, ast.List)):
                    raise ValueError("model assignment to attribute/subscript forbidden")
        if isinstance(node, ast.AugAssign) and not isinstance(node.target, ast.Name):
            raise ValueError("unsafe augmented target")
        if isinstance(node, ast.AnnAssign):
            raise ValueError("model annotation not allowed")
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            if node.id == "data" or node.id in ALLOWED_CALLS:
                raise ValueError("input or builtin rebound")
            local_names.add(node.id)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id not in (local_names | ALLOWED_CALLS | {"data"}):
                raise ValueError("untrusted external/global name")
    return source


def infer(cli, gguf, prompt):
    """Same pinned llama.cpp/official GGUF, with bounded 320-token function budget."""
    _, binary, weights = verify_paths("7b", cli, gguf)
    if len(prompt.encode("utf-8")) > 5000:
        raise ValueError("oversized task prompt")
    args = [str(binary), "--model", str(weights),
            "--prompt", format_chatml(prompt),
            "--n-predict", "320", "--ctx-size", "2048",
            "--threads", "4", "--temp", "0", "--seed", "42",
            "--no-display-prompt", "--simple-io", "--single-turn",
            "--jinja", "--offline", "--log-verbosity", "1",
            "--color", "off"]
    env = {"PATH":"/usr/local/bin:/usr/bin:/bin", "HOME":"/tmp",
           "LANG":"C.UTF-8", "OMP_NUM_THREADS":"4"}
    began = time.monotonic()
    process = subprocess.run(args, shell=False, env=env, text=True,
                             errors="replace", capture_output=True, timeout=240)
    if process.returncode != 0:
        raise ValueError("pinned CPU completion returned nonzero")
    response, _ = extract_completion(process.stdout, max_output_bytes=MAX_BYTES)
    return response, round(time.monotonic()-began,3)


def verify_model(gguf, provenance):
    spec = approved_model("7b")
    meta = json.loads(Path(provenance).read_text(encoding="utf-8"))
    if (meta.get("model") != "7b" or meta.get("repository") != spec["repo"]
            or meta.get("filename") != spec["filename"]
            or meta.get("license") != "apache-2.0"
            or meta.get("quantization") != "Q4_K_M"
            or sha256_file(gguf) != meta.get("sha256")):
        raise ValueError("model provenance inconsistent")


def docker_one(stage, lane):
    cmd = _docker_command(stage, "python:3.11-slim", [
        "-m", "unittest", "discover", "-s", "tests",
        "-p", "heldout_p1d.py", "-v"])
    idx = cmd.index("python:3.11-slim")
    cmd[idx:idx] = ["-e", "P1D_LANE=" + lane]
    try:
        result = subprocess.run(cmd, text=True, capture_output=True,
                                timeout=100, check=False)
    except subprocess.TimeoutExpired:
        raise ValueError("bounded Docker execution timed out")
    output = (result.stdout + "\n" + result.stderr)[-3600:]
    match = re.search(r"Ran (\d+) tests?", output)
    count = int(match.group(1)) if match else None
    if (not all(x in cmd for x in ("--network=none","--read-only",
                                    "--user=65534:65534", "--cap-drop=ALL"))):
        raise ValueError("lost Docker isolation flag")
    return {"passed": result.returncode == 0 and count == 9,
            "tests_run": count, "exit_code": result.returncode,
            "log_tail": output[-1200:]}


def grade(tests, source, lane):
    """Use exact same frozen nine holdouts on baseline and candidate."""
    with tempfile.TemporaryDirectory(prefix="p1d-diverse-") as tmp:
        os.chmod(tmp, 0o755)
        outcomes = []
        for name, code in (("baseline", "def solve(data):\n    return None\n"),
                           ("candidate", source)):
            target = Path(tmp) / name
            (target/"tests").mkdir(parents=True)
            (target/"candidate.py").write_text(code, encoding="utf-8")
            (target/"tests"/"heldout_p1d.py").write_bytes(tests)
            for p in (target, target/"tests"):
                os.chmod(p,0o755)
            for p in (target/"candidate.py",target/"tests"/"heldout_p1d.py"):
                os.chmod(p,0o644)
            outcomes.append(docker_one(target,lane))
    base, candidate = outcomes
    if base["passed"] or base["tests_run"] != 9 or candidate["tests_run"] != 9:
        raise ValueError("negative controls or complete test discovery invalid")
    return {"status": "candidate_passed" if candidate["passed"]
            else "candidate_failed", "baseline": base, "candidate": candidate}


def context(root, config_path, lane, commit):
    if lane not in TASKS or not SOURCE_SHA.fullmatch(commit):
        raise ValueError("unregistered task or unpinned commit")
    cfg = load_config(config_path)
    manifest = next(m for m in build_manifests(cfg,commit) if m["lane_id"]==lane)
    tests, tests_hash = heldout(root)
    prompt = task_prompt(cfg,lane)
    record = {
        "schema":1,"variant":VARIANT,"repo":manifest["repository"],
        "source_sha":commit,"lane":lane,"architecture":manifest["architecture_key"],
        "contract_sha256":manifest["contract_sha256"],"holdout_sha256":tests_hash,
        "prompt_sha256":sha(prompt.encode()),"task_sha256":sha(TASKS[lane].encode()),
        "merge_authorized":False,"ci_attested_source_commits":0,
        "checkout_modified":False,"recursive_parent_promotions":0,
    }
    return record, tests, prompt


def run(root, cfg, lane, commit, cli, gguf, provenance):
    meta, tests, prompt = context(root,cfg,lane,commit)
    verify_model(gguf,provenance)
    response, seconds = infer(cli,gguf,prompt)
    record = {**meta, "model_calls":1, "model_seconds":seconds,
              "raw_response":response,"response_sha256":sha(response.encode()),
              "candidate_sha256":None,"outcome":"ast_rejected","grade":None}
    try:
        source = inspect_source(response)
    except ValueError as exc:
        record["reject_reason"]=str(exc)[:150]
    else:
        record["candidate_sha256"]=sha(source.encode())
        record["grade"]=grade(tests,source,lane)
        record["outcome"]=record["grade"]["status"]
    return record


def replay(root, cfg, commit, record):
    if not isinstance(record,dict) or record.get("lane") not in TASKS:
        raise ValueError("invalid lane report")
    expected, tests, _ = context(root,cfg,record["lane"],commit)
    if any(type(record.get(k)) is not type(v) or record[k]!=v
           for k,v in expected.items()):
        raise ValueError("unreviewed or elevated contract")
    if type(record.get("model_calls")) is not int or record["model_calls"] != 1:
        raise ValueError("missing fresh model invocation")
    raw = record.get("raw_response")
    if (not isinstance(raw,str) or not 1 <= len(raw.encode()) <= MAX_BYTES
            or record.get("response_sha256") != sha(raw.encode())):
        raise ValueError("missing or changed source bytes")
    try:
        source=inspect_source(raw)
    except ValueError:
        if (record.get("outcome")!="ast_rejected"
                or record.get("candidate_sha256") is not None
                or record.get("grade") is not None):
            raise ValueError("invalid rejected candidate claim")
        return {"lane":record["lane"],"status":"replayed_ast_rejection",
                "passed":False,"candidate_sha256":None,
                "merge_authorized":False}
    if record.get("candidate_sha256")!=sha(source.encode()):
        raise ValueError("candidate source digest mismatch")
    verdict=grade(tests,source,record["lane"])
    if (record.get("outcome")!=verdict["status"]
            or not isinstance(record.get("grade"),dict)
            or record["grade"].get("status")!=verdict["status"]):
        raise ValueError("independent Docker outcome differs")
    return {"lane":record["lane"],"status":"replayed_candidate",
            "passed":verdict["status"]=="candidate_passed",
            "candidate_sha256":sha(source.encode()),
            "merge_authorized":False}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("mode", choices=("run","replay","preflight"))
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--config", type=Path,
                   default=ROOT/"configs"/"self-evolution-8lanes.json")
    p.add_argument("--lane", choices=tuple(TASKS))
    p.add_argument("--head-sha", required=True)
    p.add_argument("--cli", type=Path)
    p.add_argument("--gguf", type=Path)
    p.add_argument("--provenance", type=Path)
    p.add_argument("--input",type=Path)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise SystemExit("cannot overwrite evidence")
    try:
        if args.mode=="preflight":
            m=build_manifests(load_config(args.config),args.head_sha)
            if len(TASKS)!=8 or len(set(TASKS.values()))!=8 or len(m)!=8:
                raise ValueError("distinct tasks or lanes missing")
            result={"status":"eight_distinct_contracts_preflight_passed",
                    "model_calls":0,"unique_task_prompts":8,
                    "merge_authorized":False}
        elif args.mode=="run":
            if (args.lane not in TASKS or args.cli is None or
                    args.gguf is None or args.provenance is None):
                raise ValueError("missing pinned model inputs")
            result=run(args.root,args.config,args.lane,args.head_sha,args.cli,
                       args.gguf,args.provenance)
        else:
            if (args.input is None or args.input.is_symlink()
                    or not args.input.is_file()
                    or args.input.stat().st_size>30000):
                raise ValueError("missing immutable model output")
            report=json.loads(args.input.read_text(encoding="utf-8"))
            result=replay(args.root,args.config,args.head_sha,report)
    except (ValueError,OSError,TypeError,KeyError,
            json.JSONDecodeError,subprocess.SubprocessError) as exc:
        result={"status":"blocked","error_type":type(exc).__name__,
                "error":str(exc)[:180],"merge_authorized":False}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True,
                                     ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({key:result.get(key) for key in (
        "status","lane","outcome","passed","model_calls","candidate_sha256",
        "merge_authorized")},sort_keys=True))
    return 2 if result.get("status")=="blocked" else 0


if __name__=="__main__":
    raise SystemExit(main())
