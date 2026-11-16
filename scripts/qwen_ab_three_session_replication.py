#!/usr/bin/env python3
"""Three full Qwen 7B CPU A/B sessions on one GitHub runner.

Repeat the *unchanged* original A/B experiment three times, deliberately
restarting llama-server each session and launching four fresh CLI processes.
This measures within-run session variability, not independent GPU/CPU hosts,
general coding ability, or confidence bounds for a software-task population.
All attempted sessions (including failures) are included in the report.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

from qwen_server_cli_comparison import experiment

SESSIONS = 3
IDENT = "qwen7b-ab-three-restarts-v1"


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def session_summary(rows):
    if (not isinstance(rows, list) or len(rows) != SESSIONS or
            [r.get("session") for r in rows] != [1, 2, 3]):
        raise ValueError("three sequential sessions are mandatory")
    measured = [r for r in rows if r.get("status") == "comparison_measured"]
    metrics = []
    for r in measured:
        record = r["report"]
        s = record["summary"]
        if (record.get("comparison_kind") !=
                "identical_model_prompt_sampling_no_grammar_no_retry" or
                record.get("experimental_task_count") != 4 or
                s["equal_prompt_sequence"] is not True or
                s["cli"]["attempts"] != 4 or s["server"]["attempts"] != 4 or
                record["merge_authorized"] is not False or
                s["autonomous_coding_proven"] is not False):
            raise ValueError("attempt violates fixed A/B comparison scope")
        metrics.append({
            "session": r["session"],
            "cli_median_seconds": s["cli"]["per_call_median_seconds"],
            "server_median_seconds": s["server"]["per_call_median_seconds"],
            "startup_seconds": s["server_startup_seconds"],
            "cli_batch_seconds": s["cli_batch_wall_seconds"],
            "server_total_seconds": s["server_startup_plus_batch_wall_seconds"],
            "cli_ast": s["cli"]["ast_accepted"],
            "server_ast": s["server"]["ast_accepted"],
            "request_latency_ratio": s["median_request_latency_speedup_if_greater_than_one"],
        })
    ratios = [x["request_latency_ratio"] for x in metrics
              if type(x["request_latency_ratio"]) in (int, float)]
    return {
        "sessions_planned": SESSIONS,
        "sessions_attempted": len(rows),
        "sessions_measured": len(measured),
        "sessions_failed": SESSIONS - len(measured),
        "measured_session_values": metrics,
        "median_session_ratio": round(statistics.median(ratios), 3)
            if ratios else None,
        "all_three_sessions_measured": len(measured) == SESSIONS,
        "claims": "within-one-run comparison only; no multi-host independence",
        "sampling_temperature": 0, "sampling_seed": 42,
        "grammar_used": False, "repair_retry_used": False,
        "benchmark_code_changed": False,
        "source_checkout_modified": False, "merge_authorized": False,
        "autonomous_coding_proven": False,
    }


def run_batch(root, cli, server, gguf, provenance, directory):
    directory = Path(directory).absolute()
    if directory.exists() or directory.is_symlink():
        raise ValueError("refuse to overwrite A/B replication artifacts")
    directory.mkdir(parents=True, exist_ok=False)
    rows = []
    started = time.monotonic()
    for number in range(1, SESSIONS + 1):
        target = directory / ("session_%02d" % number) / "ab-report.json"
        stage_start = time.monotonic()
        record = None
        failure = None
        try:
            record = experiment(root, cli, server, gguf, provenance, target)
            if record.get("status") != "comparison_measured":
                failure = record.get("error_category", "comparison_not_measured")
        except (OSError, ValueError, TypeError, KeyError,
                json.JSONDecodeError) as err:
            failure = type(err).__name__ + ": " + str(err)[:120]
        rows.append({
            "session": number,
            "status": "comparison_measured" if record is not None and
                      record.get("status") == "comparison_measured"
                      else "infrastructure_failed",
            "report_sha256": sha(target.read_bytes()) if target.is_file() else None,
            "report": record, "failure": failure,
            "session_elapsed_seconds": round(time.monotonic() - stage_start, 3)
        })
        (directory / "interim.json").write_text(json.dumps(
            {"experiment": IDENT, "sessions": rows}, sort_keys=True,
            indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    result = {
        "experiment": IDENT, "protocol_version": 1,
        "sessions": rows, "summary": session_summary(rows),
        "total_elapsed_seconds": round(time.monotonic() - started, 3),
        "human_merge_required": True,
    }
    (directory / "replication-report.json").write_text(json.dumps(
        result, sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def verify_batch(directory):
    directory = Path(directory)
    path = directory / "replication-report.json"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 300_000:
        raise ValueError("missing bounded replication evidence")
    report = json.loads(path.read_text(encoding="utf-8"))
    if (report.get("experiment") != IDENT or report.get("protocol_version") != 1
            or report.get("human_merge_required") is not True
            or report.get("summary") != session_summary(report["sessions"])):
        raise ValueError("wrong or false trial summary")
    for row in report["sessions"]:
        item = directory / ("session_%02d" % row["session"]) / "ab-report.json"
        if row["report_sha256"] is None:
            if item.exists() or row["status"] == "comparison_measured":
                raise ValueError("success without evidence")
        elif not item.is_file() or sha(item.read_bytes()) != row["report_sha256"]:
            raise ValueError("altered per-session report evidence")
        elif json.loads(item.read_text(encoding="utf-8")) != row["report"]:
            raise ValueError("session results differ from original evidence")
    return report["summary"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=("run", "verify"))
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--cli", type=Path)
    p.add_argument("--server", type=Path)
    p.add_argument("--gguf", type=Path)
    p.add_argument("--provenance", type=Path)
    p.add_argument("--directory", type=Path, required=True)
    args = p.parse_args()
    try:
        if args.mode == "verify":
            result = verify_batch(args.directory)
        else:
            if any(x is None for x in (args.cli, args.server, args.gguf, args.provenance)):
                raise ValueError("no free-form model or execution parameters")
            result = run_batch(args.root, args.cli, args.server, args.gguf,
                               args.provenance, args.directory)["summary"]
        print(json.dumps(result, sort_keys=True))
        return 0 if result["all_three_sessions_measured"] else 2
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as err:
        print(json.dumps({"status": "blocked", "error_type": type(err).__name__,
                          "error_category": str(err)[:140],
                          "merge_authorized": False}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
