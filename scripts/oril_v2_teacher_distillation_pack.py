#!/usr/bin/env python3
"""Offline, deterministic teacher-example curation for an ORIL student model.

Not LoRA training, not an independent evaluator, and not a provenance authority.
Only already-reviewed concise teacher outputs can be selected. No model/API calls.
Hidden/held-out cases are NEVER written to the student training output.
"""
import argparse
import hashlib
import json
import math
import os
from contextlib import ExitStack
from pathlib import Path
import re
import unicodedata

FIELDS = {"case_id", "group_id", "split", "task_type", "question",
          "teacher_answer", "checks", "quality", "review_accepted",
          "review_url", "candidate_sha"}
SPLITS = {"train", "validation", "heldout"}
HEX40 = re.compile(r"^[a-f0-9]{40}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
SOURCE = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/(?:actions/runs/[0-9]+|pull/[0-9]+)(?:/[A-Za-z0-9_.-]+)?$")
TEXT_LIMIT = 4000


def norm(value):
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def has_invisible_format(value):
    """Reject invisible Unicode format controls in evaluation question text."""
    return any(unicodedata.category(ch) == "Cf" for ch in value)


def digest(value):
    return hashlib.sha256(norm(value).encode("utf-8")).hexdigest()


def validate(items):
    """Fail closed on split leakage or malformed/ambiguous training records."""
    if not isinstance(items, list) or not items:
        raise ValueError("nonempty JSONL records required")
    seen_ids, groups, seen_question = set(), {}, {}
    for row in items:
        if not isinstance(row, dict) or set(row) != FIELDS:
            raise ValueError("exact record fields required")
        for field in ("case_id", "group_id", "task_type"):
            if not isinstance(row[field], str) or not SAFE_ID.fullmatch(row[field]):
                raise ValueError("invalid " + field)
        if row["case_id"] in seen_ids:
            raise ValueError("duplicate case_id")
        seen_ids.add(row["case_id"])
        if row["split"] not in SPLITS:
            raise ValueError("invalid split")
        group = row["group_id"].casefold()  # Prevent case-variant group leakage
        if group in groups and groups[group] != row["split"]:
            raise ValueError("group leakage across splits")
        groups[group] = row["split"]
        for field in ("question", "teacher_answer"):
            value = row[field]
            if (not isinstance(value, str) or not value.strip()
                    or len(value) > TEXT_LIMIT or "\x00" in value):
                raise ValueError("invalid " + field)
        if has_invisible_format(row["question"]):
            raise ValueError("invisible format character in question")
        q = digest(row["question"])
        if q in seen_question and seen_question[q] != row["split"]:
            raise ValueError("duplicate question leakage across splits")
        seen_question[q] = row["split"]
        if (not isinstance(row["checks"], list) or not row["checks"] or
                len(row["checks"]) > 8 or not all(isinstance(x, str) and
                0 < len(x.strip()) <= 160 for x in row["checks"])):
            raise ValueError("bounded review checks required")
        if (type(row["quality"]) not in (int, float) or
                not math.isfinite(row["quality"]) or
                not 0 <= row["quality"] <= 1):
            raise ValueError("quality must be finite 0..1")
        if type(row["review_accepted"]) is not bool:
            raise ValueError("review acceptance must be boolean")
        if (not isinstance(row["review_url"], str) or
                not SOURCE.fullmatch(row["review_url"])):
            raise ValueError("review source URL required")
        if (not isinstance(row["candidate_sha"], str) or
                not HEX40.fullmatch(row["candidate_sha"])):
            raise ValueError("exact candidate SHA required")
    return True


def compile_examples(items, *, max_cases=16, max_total_chars=6000,
                     max_answer_chars=650, min_quality=0.9):
    """Select compact train-only cases with deterministic task-type coverage.

    Numbers are **character budgets**, not tokenizer-exact counts. Review
    URLs/booleans are *assertions* from input and are not externally verified.
    """
    validate(items)
    if (type(max_cases) is not int or not 1 <= max_cases <= 10000 or
            type(max_total_chars) is not int or max_total_chars < 1 or
            type(max_answer_chars) is not int or max_answer_chars < 1 or
            type(min_quality) not in (float, int) or
            not math.isfinite(min_quality) or not 0 <= min_quality <= 1):
        raise ValueError("invalid selection budgets")
    candidate = [
        x for x in items if x["split"] == "train"
        and x["review_accepted"] and x["quality"] >= min_quality
        and len(x["teacher_answer"]) <= max_answer_chars
    ]
    by_type = {}
    for item in candidate:
        by_type.setdefault(item["task_type"], []).append(item)
    for group in by_type.values():
        group.sort(key=lambda x: (-x["quality"], x["case_id"]))
    chosen, used, total = [], set(), 0
    while len(chosen) < max_cases:
        progressed = False
        for typ in sorted(by_type):
            while by_type[typ]:
                item = by_type[typ].pop(0)
                q = digest(item["question"])
                if q in used:
                    continue
                cost = len(item["question"]) + len(item["teacher_answer"])
                if total + cost > max_total_chars:
                    continue
                chosen.append(item)
                used.add(q)
                total += cost
                progressed = True
                break
            if len(chosen) >= max_cases:
                break
        if not progressed:
            break
    output = []
    for item in chosen:
        output.append({
            "messages": [
                {"role": "user", "content": item["question"]},
                {"role": "assistant", "content": item["teacher_answer"]},
            ],
            "metadata": {
                "case_id": item["case_id"], "group_id": item["group_id"],
                "task_type": item["task_type"],
                "review_assertion_url": item["review_url"],
                "candidate_sha": item["candidate_sha"],
                "quality_assertion": item["quality"],
            },
        })
    in_train = [x for x in items if x["split"] == "train"]
    available_chars = sum(len(x["question"]) + len(x["teacher_answer"])
                          for x in in_train)
    stats = {
        "schema_version": 1,
        "input_rows": len(items),
        "train_rows": len(in_train),
        "validation_rows": sum(x["split"] == "validation" for x in items),
        "heldout_rows": sum(x["split"] == "heldout" for x in items),
        "selected_train_rows": len(chosen),
        "selected_task_types": sorted(set(x["task_type"] for x in chosen)),
        "selected_chars": total,
        "available_train_chars": available_chars,
        "char_budget_reduction_pct":
            round(100 * (1 - total / available_chars), 2) if available_chars else None,
        "student_weights_updated": False,
        "independent_review_verified": False,
        "heldout_evaluation_performed": False,
        "model_quality_gain": None,
        "token_count": None,
        "note": "char savings are not token or cost savings; no heldout answers are exported",
    }
    return output, stats


def load(path):
    rows = []
    with Path(path).open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                continue
            if len(line) > 24000:
                raise ValueError("record exceeds size limit line " + str(i))
            def unique(pairs):
                d = {}
                for key, value in pairs:
                    if key in d:
                        raise ValueError("duplicate JSON object key")
                    d[key] = value
                return d
            rows.append(json.loads(line, object_pairs_hook=unique,
                                   parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON"))))
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True)
    p.add_argument("--output-train", required=True)
    p.add_argument("--output-report", required=True)
    p.add_argument("--max-cases", type=int, default=16)
    p.add_argument("--max-total-chars", type=int, default=6000)
    p.add_argument("--max-answer-chars", type=int, default=650)
    p.add_argument("--min-quality", type=float, default=0.9)
    args = p.parse_args()
    training, report = compile_examples(load(args.input),
                                        max_cases=args.max_cases,
                                        max_total_chars=args.max_total_chars,
                                        max_answer_chars=args.max_answer_chars,
                                        min_quality=args.min_quality)
    if not training:
        raise ValueError("no eligible reviewed training examples")
    # Refuse to overwrite heldout: output paths must be different from input.
    paths = {Path(args.input).resolve(), Path(args.output_train).resolve(),
             Path(args.output_report).resolve()}
    if len(paths) != 3:
        raise ValueError("input and outputs must be distinct")
    # A dataset compiler must never overwrite an existing (possibly heldout)
    # file or follow a symlink output. O_EXCL rejects even dangling symlinks.
    # Restrict newly created files to owner access, regardless of process umask.
    # Open BOTH outputs before writing either, so a pre-existing second output
    # cannot cause a partial overwrite of the first output.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    with ExitStack() as stack:
        train_fd = os.open(args.output_train, flags, 0o600)
        train_file = stack.enter_context(os.fdopen(train_fd, "w", encoding="utf-8"))
        report_fd = os.open(args.output_report, flags, 0o600)
        report_file = stack.enter_context(os.fdopen(report_fd, "w", encoding="utf-8"))
        train_file.write(
            "".join(json.dumps(x, sort_keys=True, ensure_ascii=False) + "\n" for x in training))
        report_file.write(
            json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
