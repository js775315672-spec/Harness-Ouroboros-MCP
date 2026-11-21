"""Offline consistency audit for the public Hydra LoRA receipt (not a GPU attestation)."""
import argparse
import csv
import hashlib
import json
import math
import struct
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(root):
    root = Path(root)
    receipt_path = root / "run-01" / "receipt.json"
    adapter = root / "run-01" / "adapter.safetensors"
    report = json.loads(receipt_path.read_text(encoding="utf-8"))
    if sha(adapter) != report["adapter_sha256"]:
        raise ValueError("adapter sha256 mismatch")
    with adapter.open("rb") as stream:
        header_length = struct.unpack("<Q", stream.read(8))[0]
        if not 0 < header_length < 1_000_000:
            raise ValueError("invalid safetensors header length")
        header = json.loads(stream.read(header_length))
        if not {"A", "B"} <= set(header):
            raise ValueError("missing LoRA tensors")
        if header.get("__metadata__", {}).get("revision") != report["revision"]:
            raise ValueError("adapter revision mismatch")
        a, b = header["A"]["shape"], header["B"]["shape"]
        if len(a) != 2 or len(b) != 2 or a[0] != b[1] or a[0] != report["rank"]:
            raise ValueError("invalid LoRA rank/shape")
    for name in ("train.csv", "eval.csv"):
        if sha(root / name) != report["split_sha256"][name]:
            raise ValueError("split digest mismatch: " + name)
    with (root / "eval.csv").open(newline="", encoding="utf-8") as stream:
        labels = [r["label"] for r in csv.DictReader(stream)]
    if not labels or set(labels) - {"failure", "success"}:
        raise ValueError("unsupported labels")
    expected = [int(label == "success") for label in labels]
    before = report["baseline_predictions"]
    after = report["candidate_predictions"]
    if len(before) != len(after) or len(after) != len(expected) or any(type(x) is not int or x not in (0, 1) for x in before + after):
        raise ValueError("prediction length/type mismatch")
    counts = {
        "eval_examples": len(expected),
        "baseline_correct": sum(x == y for x, y in zip(before, expected)),
        "candidate_correct": sum(x == y for x, y in zip(after, expected)),
        "recovered": sum(x != y and z == y for x, z, y in zip(before, after, expected)),
        "regressed": sum(x == y and z != y for x, z, y in zip(before, after, expected)),
    }
    for key, value in counts.items():
        if type(report.get(key)) is not int or report[key] != value:
            raise ValueError("inconsistent receipt field: " + key)
    if report["candidate_correct"] - report["baseline_correct"] != report["recovered"] - report["regressed"]:
        raise ValueError("impossible net improvement")
    if type(report.get("optimizer_steps")) is not int or report["optimizer_steps"] <= 0:
        raise ValueError("optimizer step evidence absent")
    if any(not math.isfinite(float(report[k])) for k in ("initial_loss", "last_pre_step_loss", "delta_norm")):
        raise ValueError("nonfinite training receipt")
    return {
        "adapter_sha256": sha(adapter),
        "optimizer_steps_reported": report["optimizer_steps"],
        "public_baseline_correct": counts["baseline_correct"],
        "public_candidate_correct": counts["candidate_correct"],
        "public_regressed": counts["regressed"],
        "receipt_consistent": True,
        "gpu_execution_independently_attested": False,
        "independent_hidden_eval_passed": False,
        "promotion_allowed": False,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    args = p.parse_args()
    print(json.dumps(audit(args.root), sort_keys=True))
