#!/usr/bin/env python3
"""P1b: two independent Qwen 7B function probes; no host execution of model code."""
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
from gguf_cpu_runtime import CPUInference, approved_model, sha256_file
from self_evolution_task_contract import load_config, build_manifests

ROOT = Path(__file__).resolve().parents[1]
HOLDOUT = "tests/heldout_self_evolution_action.py"
LANES = ("01", "02")
TEST_COUNT = 12
LIMIT = 6000
TASK = (
    "Write exactly ONE Python function with header def choose_action(state): "
    "If state is not a dict return 'BLOCK'. Require state.get('safety') is True "
    "or return 'BLOCK'. If stage is 'new' return 'GENERATE'. If 'coded' return "
    "'VERIFY'. If 'tested' return 'ATTEST' only if tests_ok is True, otherwise "
    "'BLOCK'. If 'attested' return 'REVIEW'. Every other input returns 'BLOCK'. "
    "Never return 'MERGE'. No imports, helpers, classes, side effects or packages. "
    "Output only one valid Python function, no markdown, explanations or tests. "
)
ALLOWED = (
    ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.If, ast.Return,
    ast.Name, ast.Load, ast.Store, ast.Constant, ast.Compare,
    ast.Eq, ast.NotEq, ast.Is, ast.IsNot, ast.In, ast.NotIn,
    ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.Call,
    ast.Attribute, ast.Dict, ast.Assign, ast.Subscript, ast.Tuple, ast.List,
)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def heldout(root):
    root = Path(root).resolve(strict=True)
    path = root / HOLDOUT
    if (path.is_symlink() or not path.is_file()
            or not path.resolve(strict=True).is_relative_to(root)
            or not 500 <= path.stat().st_size <= 16000):
        raise ValueError("missing or unsafe frozen tests")
    raw = path.read_bytes()
    return raw, sha(raw)

def _v2_unfence(raw):
    """Remove only one exact Python Markdown envelope, with no prose or edits."""
    if not isinstance(raw, str):
        raise ValueError("non-string response")
    if len(raw.encode("utf-8")) > LIMIT or any(x in raw for x in ("\x00", "\x1b", "\r")):
        raise ValueError("unsafe model response")
    stripped = raw.strip()
    marker = chr(96) * 3
    if marker not in stripped:
        return raw
    opener = marker + "python\n"
    closer = "\n" + marker
    if (not stripped.startswith(opener) or not stripped.endswith(closer)
            or stripped.count(marker) != 2):
        raise ValueError("untrusted Markdown envelope")
    return stripped[len(opener):-len(closer)] + "\n"

def inspect_function(raw, *, allow_fence=False):
    if allow_fence:
        raw = _v2_unfence(raw)
    if (not isinstance(raw, str) or not 30 <= len(raw.encode()) <= LIMIT
            or len(raw.splitlines()) > 65
            or any(x in raw for x in ("\x00", "\x1b", "\r", chr(96) * 3))):
        raise ValueError("invalid bounded model source")
    source = raw.strip() + "\n"
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError("model did not return valid source") from exc
    if len(tree.body) != 1 or type(tree.body[0]) is not ast.FunctionDef:
        raise ValueError("exactly one function required")
    f = tree.body[0]
    a = f.args
    if (f.name != "choose_action" or f.decorator_list or f.returns is not None
            or f.type_comment or getattr(f, "type_params", ())
            or a.posonlyargs or len(a.args) != 1 or a.args[0].arg != "state"
            or a.args[0].annotation is not None or a.kwonlyargs or a.vararg
            or a.kwarg or a.defaults or a.kw_defaults):
        raise ValueError("function signature modified")
    assigned = set()
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED):
            raise ValueError("unsafe AST node " + type(node).__name__)
        if isinstance(node, (ast.Name, ast.Attribute)):
            name = node.id if isinstance(node, ast.Name) else node.attr
            if "__" in name:
                raise ValueError("dunder access forbidden")
        if isinstance(node, ast.Assign):
            if (len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name)
                    or node.targets[0].id in ("state", "dict", "isinstance")):
                raise ValueError("unsafe assignment")
            assigned.add(node.targets[0].id)
        if isinstance(node, ast.Attribute):
            if (node.attr != "get" or not isinstance(node.value, ast.Name)
                    or node.value.id != "state"):
                raise ValueError("unsafe attribute access")
        if isinstance(node, ast.Call):
            fcall = node.func
            valid_get = (
                isinstance(fcall, ast.Attribute) and fcall.attr == "get"
                and isinstance(fcall.value, ast.Name) and fcall.value.id == "state"
                and len(node.args) in (1, 2) and not node.keywords
                and isinstance(node.args[0], ast.Constant)
                and type(node.args[0].value) is str
                and node.args[0].value in ("stage", "safety", "tests_ok"))
            valid_type = (
                isinstance(fcall, ast.Name) and fcall.id == "isinstance"
                and len(node.args) == 2 and not node.keywords
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id == "state"
                and isinstance(node.args[1], ast.Name)
                and node.args[1].id == "dict")
            if not (valid_get or valid_type):
                raise ValueError("unapproved function call")
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id not in (
                {"state", "dict", "isinstance"} | assigned):
            raise ValueError("unknown global name")
    return source

def prompt(config, lane, v2=False):
    if lane not in LANES:
        raise ValueError("pilot only authorizes lanes 01 and 02")
    row = next(r for r in config["lanes"] if r["id"] == lane)
    variant = (
        " REQUIRE literal boolean identity comparisons, exactly "
        "state.get('safety') is True and "
        "state.get('tests_ok') is True. Never use truthiness "
        "checks for either key. Do NOT use Markdown fences or "
        "ternary expressions. Use return statements within if blocks. "
        if v2 else ""
    )
    return TASK + variant + "Implementation hypothesis: " + row["hypothesis"] + "."

def docker_test(folder):
    cmd = _docker_command(folder, "python:3.11-slim", [
        "-m", "unittest", "discover", "-s", "tests",
        "-p", "heldout_self_evolution_action.py", "-v"])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        return {"passed": False, "tests_run": None, "error": "timeout"}
    output = (r.stdout + "\n" + r.stderr)[-4000:]
    match = re.search(r"Ran (\d+) tests?", output)
    n = int(match.group(1)) if match else None
    return {"passed": r.returncode == 0 and n == TEST_COUNT,
            "tests_run": n, "exit_code": r.returncode,
            "log_tail": output[-1300:], "network_disabled": "--network=none" in cmd,
            "read_only": "--read-only" in cmd,
            "unprivileged": "--user=65534:65534" in cmd}

def grade(tests, code):
    """Trusted baseline must fail and proposed source must pass in Docker."""
    with tempfile.TemporaryDirectory(prefix="ouroboros-p1b-") as td:
        os.chmod(td, 0o755)
        results = []
        for label, source in (
            ("baseline", "def choose_action(state):\n    raise NotImplementedError\n"),
            ("candidate", code)):
            folder = Path(td) / label
            (folder / "tests").mkdir(parents=True)
            (folder / "candidate.py").write_text(source, encoding="utf-8")
            (folder / "tests" / "heldout_self_evolution_action.py").write_bytes(tests)
            for p in (folder, folder / "tests"):
                os.chmod(p, 0o755)
            for p in (folder / "candidate.py",
                      folder / "tests" / "heldout_self_evolution_action.py"):
                os.chmod(p, 0o644)
            results.append(docker_test(folder))
    baseline, candidate = results
    if (baseline.get("passed") is not False or baseline.get("tests_run") != TEST_COUNT
            or candidate.get("tests_run") != TEST_COUNT
            or not all(r.get(k) is True for r in results for k in (
                "network_disabled", "read_only", "unprivileged"))):
        raise ValueError("invalid negative control or sandbox")
    return {"status": "model_candidate_passed" if candidate["passed"]
            else "model_candidate_failed", "baseline": baseline, "candidate": candidate,
            "merge_authorized": False}

def context(root, config_path, lane, commit, v2=False):
    c = load_config(config_path)
    m = next(x for x in build_manifests(c, commit) if x["lane_id"] == lane)
    tests, tests_hash = heldout(root)
    message = prompt(c, lane, v2=v2)
    fields = {"schema": 1, "repository": m["repository"],
              "source_sha": commit, "lane": lane,
              "architecture": m["architecture_key"],
              "contract_sha256": m["contract_sha256"],
              "holdout_sha256": tests_hash, "prompt_sha256": sha(message.encode()),
              "model": "Qwen2.5-Coder-7B-Instruct-Q4_K_M",
              "merge_authorized": False, "ci_attested_patches": 0,
              "checkout_modified": False}
    if v2:
        fields["study_variant"] = "p1b-v2-exact-fence-and-boolean-prompt"
    return fields, tests, message

def check_model(gguf, metadata):
    model = approved_model("7b")
    meta = json.loads(Path(metadata).read_text())
    if (meta.get("model") != "7b" or meta.get("repository") != model["repo"]
            or meta.get("filename") != model["filename"]
            or meta.get("license") != "apache-2.0"
            or meta.get("quantization") != "Q4_K_M"
            or sha256_file(gguf) != meta.get("sha256")):
        raise ValueError("model provenance changed")

def run(root, conf, lane, commit, cli, gguf, metadata, v2=False):
    fields, tests, message = context(root, conf, lane, commit, v2=v2)
    check_model(gguf, metadata)
    started = time.monotonic()
    raw = CPUInference("7b", cli, gguf, timeout_seconds=150).generate(message)
    record = {**fields, "model_calls": 1, "raw_response": raw,
              "response_sha256": sha(raw.encode()),
              "outcome": "static_gate_rejected", "candidate_sha256": None,
              "evaluation": None,
              "inference_seconds": round(time.monotonic() - started, 3)}
    try:
        code = inspect_function(raw, allow_fence=v2)
    except ValueError as exc:
        record["reason"] = str(exc)[:200]
    else:
        record["candidate_sha256"] = sha(code.encode())
        record["evaluation"] = grade(tests, code)
        record["outcome"] = record["evaluation"]["status"]
    return record

def verify(root, conf, commit, record, v2=False):
    if not isinstance(record, dict) or record.get("lane") not in LANES:
        raise ValueError("invalid lane report")
    fields, tests, _ = context(root, conf, record["lane"], commit, v2=v2)
    if (any(type(record.get(k)) is not type(v) or record[k] != v
            for k, v in fields.items())
            or type(record.get("model_calls")) is not int
            or record["model_calls"] != 1):
        raise ValueError("report does not match reviewed contract")
    raw = record.get("raw_response")
    if (not isinstance(raw, str) or len(raw.encode()) > LIMIT
            or sha(raw.encode()) != record.get("response_sha256")):
        raise ValueError("response evidence is corrupt")
    try:
        code = inspect_function(raw, allow_fence=v2)
    except ValueError:
        if (record.get("outcome") != "static_gate_rejected"
                or record.get("candidate_sha256") is not None
                or record.get("evaluation") is not None):
            raise ValueError("false accepted model claim")
        return {"status": "static_rejection_replayed", "lane": record["lane"],
                "candidate_passed": False, "merge_authorized": False}
    if record.get("candidate_sha256") != sha(code.encode()):
        raise ValueError("candidate hash mismatch")
    grade_result = grade(tests, code)
    if (record.get("outcome") != grade_result["status"]
            or not isinstance(record.get("evaluation"), dict)
            or record["evaluation"].get("status") != grade_result["status"]):
        raise ValueError("cross-run grading differs")
    return {"status": "candidate_replayed", "lane": record["lane"],
            "candidate_passed": grade_result["status"] == "model_candidate_passed",
            "candidate_sha256": sha(code.encode()), "merge_authorized": False}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("preflight", "run", "verify"))
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--config", type=Path, default=ROOT / "configs/self-evolution-8lanes.json")
    ap.add_argument("--head-sha", required=True)
    ap.add_argument("--lane", choices=LANES)
    ap.add_argument("--cli", type=Path)
    ap.add_argument("--gguf", type=Path)
    ap.add_argument("--metadata", type=Path)
    ap.add_argument("--input", type=Path)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--v2-exact-format", action="store_true")
    a = ap.parse_args()
    if a.report.exists() or a.report.is_symlink():
        raise SystemExit("cannot overwrite evidence")
    try:
        if a.mode == "preflight":
            manifests = build_manifests(load_config(a.config), a.head_sha)
            result = {"status": "eight_preflights_validated", "count": len(manifests),
                      "model_calls": 0, "merge_authorized": False}
        elif a.mode == "run":
            if not a.lane or not a.cli or not a.gguf or not a.metadata:
                raise ValueError("model inputs missing")
            result = run(a.root, a.config, a.lane, a.head_sha,
                         a.cli, a.gguf, a.metadata, v2=a.v2_exact_format)
        else:
            if (a.input is None or a.input.is_symlink() or not a.input.is_file()
                    or a.input.stat().st_size > 30000):
                raise ValueError("invalid immutable evidence")
            result = verify(a.root, a.config, a.head_sha,
                            json.loads(a.input.read_text(encoding="utf-8")),
                            v2=a.v2_exact_format)
    except (ValueError, OSError, TypeError, KeyError, json.JSONDecodeError,
            subprocess.SubprocessError) as exc:
        result = {"status": "blocked", "type": type(exc).__name__,
                  "reason": str(exc)[:180], "merge_authorized": False}
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: result.get(key) for key in (
        "status", "outcome", "model_calls", "lane", "candidate_sha256",
        "merge_authorized")}, sort_keys=True))
    if result.get("status") == "blocked":
        return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
