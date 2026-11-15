#!/usr/bin/env python3
"""Pre-registered reliability measurement for the two constrained Qwen tasks.

Does not modify tasks, tests, AST gates, prompts, code checkout, or checkpoint
criteria. Every planned trial is counted, including model/infra failures and
budget-exhausted/not-started cases. This is NOT a coding capability benchmark.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import resource
import sys
import time

from bounded_qwen_autonomous_worker import run, verify, load, TASKS
from gguf_cpu_runtime import CPUInference, approved_model, sha256_file, FROZEN_CPU_SEED

BENCHMARK = "benchmarks/qwen7b_scoped_smoke_v1.lock.json"
TOTAL = 20
MAX_WALL_SECONDS = 1700
CONFIG_KEYS = {"schema_version", "benchmark_id", "classification", "status",
               "measurement_cut", "repeats_required", "repeats_preferred",
               "model", "runtime", "tasks", "gates", "metrics", "limitations",
               "human_merge_required", "no_paid_api"}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_config(root):
    path = Path(root).resolve(strict=True) / BENCHMARK
    if path.is_symlink() or path.stat().st_size > 14000:
        raise ValueError("untrusted benchmark lock file")
    raw = path.read_bytes()
    cfg = json.loads(raw)
    if (not isinstance(cfg, dict) or set(cfg) != CONFIG_KEYS
            or cfg["schema_version"] != 1
            or cfg["benchmark_id"] != "qwen7b-scoped-expression-smoke-v1"
            or cfg["repeats_required"] != TOTAL
            or cfg["runtime"]["seed"] != FROZEN_CPU_SEED
            or cfg["runtime"]["temperature"] != 0
            or cfg["gates"]["model_must_not_edit_tests"] is not True
            or cfg["gates"]["failures_count_in_denominator"] is not True
            or cfg["human_merge_required"] is not True
            or cfg["no_paid_api"] is not True
            or [t["id"] for t in cfg["tasks"]] != [x[0] for x in TASKS]):
        raise ValueError("benchmark has been modified outside preregistered scope")
    return cfg, sha256(raw)


def wilson(successes, sample, z=1.96):
    if not sample:
        return [None, None]
    p = successes / sample
    den = 1 + z*z/sample
    mid = (p + z*z/(2*sample)) / den
    span = z * math.sqrt((p*(1-p)+z*z/(4*sample))/sample) / den
    return [round(max(0, mid-span), 4), round(min(1, mid+span), 4)]


def summarize(rows, lock_sha, commit):
    if len(rows) != TOTAL or [r["trial"] for r in rows] != list(range(1, TOTAL+1)):
        raise ValueError("missing/duplicated measurement trial record")
    valid = {"passed_in_runner", "model_failed", "infra_failed", "not_started_budget"}
    if any(r["status"] not in valid for r in rows):
        raise ValueError("unapproved measurement outcome")
    n = len(rows)
    completed = sum(r["status"] == "passed_in_runner" for r in rows)
    first = sum(r["first_attempt_both"] is True for r in rows)
    infra = sum(r["status"] == "infra_failed" for r in rows)
    unstarted = sum(r["status"] == "not_started_budget" for r in rows)
    return {
        "benchmark": "qwen7b-scoped-expression-smoke-v1",
        "classification": "constrained_one_line_smoke_not_general_coding",
        "locked_config_sha256": lock_sha,
        "evaluation_commit": commit, "planned_trials": n,
        "started_trials": n-unstarted,
        "in_runner_two_task_passes": completed,
        "in_runner_pass_rate_all_planned": round(completed/n, 4),
        "in_runner_pass_rate_95pct_wilson": wilson(completed, n),
        "first_attempt_both_passes": first,
        "first_attempt_both_rate_all_planned": round(first/n, 4),
        "first_attempt_95pct_wilson": wilson(first, n),
        "infrastructure_failures": infra,
        "not_started_due_to_budget": unstarted,
        "full_two_job_recovery_passes": None,
        "general_autonomous_coding_proven": False,
        "ci_attested_source_tasks": 0, "merge_authorized": False,
        "measurement_complete": unstarted == 0,
        "frozen_assessment": "Only fixed two-line log-control tasks are evaluated",
    }


class CaptureModel:
    def __init__(self, inference):
        self.inference = inference
        self.raw_attempts = []

    def generate(self, prompt):
        start = time.monotonic()
        try:
            answer = self.inference.generate(prompt)
        except (OSError, ValueError) as exc:
            self.raw_attempts.append({
                "prompt": prompt,
                "prompt_sha256": sha256(prompt.encode("utf-8")),
                "response": None, "error_type": type(exc).__name__,
                "duration_seconds": round(time.monotonic()-start, 3)})
            raise
        if not isinstance(answer, str) or len(answer.encode("utf-8")) > 6000:
            raise ValueError("untrusted model output")
        self.raw_attempts.append({
            "prompt": prompt, "prompt_sha256": sha256(prompt.encode("utf-8")),
            "response": answer,
            "response_sha256": sha256(answer.encode("utf-8")),
            "duration_seconds": round(time.monotonic()-start, 3)})
        return answer


def prepare_model(cfg, cli, gguf, metadata_path):
    spec = approved_model("7b")
    meta = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    if (cfg["model"]["repository"] != spec["repo"]
            or cfg["model"]["file"] != spec["filename"]
            or cfg["model"]["sha256"] != sha256_file(gguf)
            or meta.get("sha256") != cfg["model"]["sha256"]
            or meta.get("revision") != cfg["model"]["revision"]
            or meta.get("license") != cfg["model"]["license"]
            or meta.get("quantization") != cfg["model"]["quantization"]
            or meta.get("model") != "7b"
            or cfg["runtime"]["seed"] != FROZEN_CPU_SEED):
        raise ValueError("model weights or inference parameters differ from lock")
    return CPUInference("7b", cli, gguf, timeout_seconds=150)


def run_batch(root, commit, directory, cli, gguf, metadata_path,
              budget_seconds=MAX_WALL_SECONDS):
    if type(budget_seconds) is not int or not 60 <= budget_seconds <= MAX_WALL_SECONDS:
        raise ValueError("unbounded benchmark duration")
    directory = Path(directory)
    if directory.exists() or directory.is_symlink():
        raise ValueError("refusing to overwrite measurements")
    directory.mkdir(parents=True, exist_ok=False)
    cfg, lock_sha = read_config(root)
    infer = prepare_model(cfg, cli, gguf, metadata_path)
    started = time.monotonic()
    rows = []
    for trial_id in range(1, TOTAL+1):
        remaining = budget_seconds - (time.monotonic()-started)
        if remaining < 30:
            rows.append({"trial":trial_id, "status":"not_started_budget",
                         "first_attempt_both":False, "model_calls":0,
                         "duration_seconds":0, "checkpoint_sha256":None,
                         "trace_sha256":None, "error_type":"budget_exhausted"})
            continue
        trial_dir = directory / f"trial_{trial_id:02d}"
        trial_dir.mkdir()
        checkpoint = trial_dir / "checkpoint.json"
        capture = CaptureModel(infer)
        began = time.monotonic()
        status = "infra_failed"
        error = None
        state = None
        try:
            state = run(root, commit, capture, checkpoint,
                        budget_seconds=max(30,min(1800,int(remaining))))
            if state["state"] == "complete":
                evidence = verify(root, checkpoint, commit)
                if evidence.get("status") != "fresh_two_model_patches_replayed":
                    raise ValueError("in-run independent Docker replay failed")
                status = "passed_in_runner"
            else:
                status = "model_failed"
        except (ValueError, OSError, TypeError, KeyError,
                json.JSONDecodeError) as exc:
            error = type(exc).__name__
            status = "infra_failed"
        trace = {"trial": trial_id, "model_outputs": capture.raw_attempts,
                 "model_inference": infer.calls[-len(capture.raw_attempts):]
                 if capture.raw_attempts else [],
                 "code_was_not_applied_to_checkout": True}
        trace_content = (json.dumps(trace, indent=2, sort_keys=True,
                                    ensure_ascii=False) + "\n").encode("utf-8")
        (trial_dir / "model_trace.json").write_bytes(trace_content)
        checkpoint_hash = sha256(checkpoint.read_bytes()) if checkpoint.is_file() else None
        attempts = (state or {}).get("attempts", [])
        first = (status == "passed_in_runner" and len(attempts) == 2
                 and all(a.get("number") == 1 and a.get("status") == "accepted"
                         for a in attempts))
        rows.append({
            "trial":trial_id, "status":status,
            "first_attempt_both":first, "model_calls":len(capture.raw_attempts),
            "duration_seconds":round(time.monotonic()-began, 3),
            "checkpoint_sha256":checkpoint_hash,
            "trace_sha256":sha256(trace_content),
            "error_type":error,
        })
        report = {"schema_version":1,"config":cfg,"lock_sha256":lock_sha,
                  "commit":commit,"trials":rows,"summary":None}
        (directory / "interim.json").write_text(json.dumps(report, indent=2,
                  ensure_ascii=False) + "\n", encoding="utf-8")
    result = {"schema_version":1, "config":cfg,"lock_sha256":lock_sha,
              "commit":commit, "trials":rows,
              "summary":summarize(rows, lock_sha, commit),
              "elapsed_seconds":round(time.monotonic()-started,3),
              "peak_child_rss_kib":resource.getrusage(
                  resource.RUSAGE_CHILDREN).ru_maxrss}
    (directory / "report.json").write_text(json.dumps(result, indent=2,
                        ensure_ascii=False, sort_keys=True) + "\n",encoding="utf-8")
    return result


def replay_batch(root, commit, directory):
    directory=Path(directory)
    cfg, sha=read_config(root)
    report_path=directory/"report.json"
    if not report_path.is_file() or report_path.stat().st_size > 256_000:
        raise ValueError("missing bounded batch report")
    report=json.loads(report_path.read_text(encoding="utf-8"))
    if (report["schema_version"] != 1 or report["config"] != cfg
            or report["lock_sha256"] != sha or report["commit"] != commit
            or report["summary"] != summarize(report["trials"], sha, commit)):
        raise ValueError("untrusted benchmark report")
    replays=0
    for row in report["trials"]:
        folder=directory/f"trial_{row['trial']:02d}"
        if row["status"] == "not_started_budget":
            if row["model_calls"] != 0 or folder.exists():
                raise ValueError("not-started trial has unexpected evidence")
            continue
        trace=folder/"model_trace.json"
        if not trace.is_file() or sha256(trace.read_bytes()) != row["trace_sha256"]:
            raise ValueError("missing or altered raw model-output evidence")
        content=json.loads(trace.read_text(encoding="utf-8"))
        if (content["trial"] != row["trial"]
                or len(content["model_outputs"]) != row["model_calls"]):
            raise ValueError("raw model-output count mismatch")
        cp=folder/"checkpoint.json"
        if cp.is_file():
            if sha256(cp.read_bytes()) != row["checkpoint_sha256"]:
                raise ValueError("altered saved checkpoint")
            _=load(root,cp,commit)
            if row["status"] == "passed_in_runner":
                proof=verify(root,cp,commit)
                if proof["status"] != "fresh_two_model_patches_replayed":
                    raise ValueError("independent Docker replay failed")
                replays+=1
        elif row["status"] == "passed_in_runner" or row["checkpoint_sha256"] is not None:
            raise ValueError("missing required completion checkpoint")
    return {
        "status":"independent_recovery_batch_verified",
        "benchmark":cfg["benchmark_id"],
        "planned":TOTAL,"replayed_passes":replays,
        "model_failure_trials":sum(x["status"]=="model_failed" for x in report["trials"]),
        "infrastructure_failure_trials":sum(x["status"]=="infra_failed" for x in report["trials"]),
        "budget_not_started":sum(x["status"]=="not_started_budget" for x in report["trials"]),
        "ci_attested_source_tasks":0,"merge_authorized":False,
        "general_autonomous_coding_proven":False,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("mode",choices=("run","replay"))
    p.add_argument("--root",type=Path,default=Path("."))
    p.add_argument("--commit",required=True)
    p.add_argument("--directory",type=Path,required=True)
    p.add_argument("--cli",type=Path)
    p.add_argument("--gguf",type=Path)
    p.add_argument("--metadata",type=Path)
    p.add_argument("--budget-seconds",type=int,default=MAX_WALL_SECONDS)
    p.add_argument("--summary",type=Path,required=True)
    a=p.parse_args()
    result={"status":"blocked","merge_authorized":False}
    try:
        if a.mode=="run":
            if any(x is None for x in (a.cli,a.gguf,a.metadata)):
                raise ValueError("missing locked CPU model assets")
            result=run_batch(a.root,a.commit,a.directory,
                             a.cli,a.gguf,a.metadata,a.budget_seconds)
        else:
            result=replay_batch(a.root,a.commit,a.directory)
    except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError) as err:
        result={"status":"blocked","error_type":type(err).__name__,
                "error_code":str(err)[:150],"merge_authorized":False}
    a.summary.parent.mkdir(parents=True,exist_ok=True)
    a.summary.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",
                         encoding="utf-8")
    print(json.dumps({"status":result.get("status",
          "pre_registered_20_trial_batch_complete" if result.get("trials") else None),
          "count":len(result.get("trials",[])),
          "replayed":result.get("replayed_passes"),
          "merge_authorized":result.get("merge_authorized",False)}))
    return 0 if result.get("status")=="independent_recovery_batch_verified" or (
        "trials" in result and len(result["trials"])==TOTAL) else 2


if __name__=="__main__":
    raise SystemExit(main())
