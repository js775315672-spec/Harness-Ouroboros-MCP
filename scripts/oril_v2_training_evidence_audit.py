#!/usr/bin/env python3
"""ORIL v2 offline model-training evidence audit (experimental, not an approval).

A candidate can fabricate all of these files. This audit checks consistency and
artifact existence, NOT GPU attestation, independent evaluation or intelligence gains.
"""
import argparse
import hashlib
import json
import math
import pathlib
import re
import sys

HEX = re.compile(r"[0-9a-f]{64}\Z")
FIELDS = {"schema_version", "run_id", "model_id", "base_model_sha256",
          "dataset_sha256", "gpu", "adapter", "evaluation"}
GPU = {"device_name", "cuda_available", "training_steps", "duration_seconds", "log_sha256"}
ADAPTER = {"path", "sha256", "size_bytes"}
EVAL = {"dataset_sha256", "split", "metric", "direction", "baseline",
        "candidate", "sample_count", "evaluator_sha256"}


def strict_load(path):
    def pairs(items):
        d = {}
        for key, val in items:
            if key in d:
                raise ValueError("duplicate JSON key")
            d[key] = val
        return d
    def constant(_):
        raise ValueError("nonfinite JSON")
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"),
                      object_pairs_hook=pairs, parse_constant=constant)


def check(root, evidence_path):
    out = {"evidence_consistent": False, "artifact_verified": False,
           "gpu_execution_attested": False, "independent_evaluation_verified": False,
           "intelligence_improved": False, "training_approved": False,
           "promotion_approved": False}
    try:
        root = pathlib.Path(root).resolve(strict=True)
        d = strict_load(evidence_path)
        if type(d) is not dict or set(d) != FIELDS:
            raise ValueError("evidence schema")
        if type(d["schema_version"]) is not int or d["schema_version"] != 1:
            raise ValueError("schema version")
        for field in ("run_id", "model_id"):
            if type(d[field]) is not str or not d[field].strip():
                raise ValueError(field)
        for field in ("base_model_sha256", "dataset_sha256"):
            if type(d[field]) is not str or not HEX.fullmatch(d[field]):
                raise ValueError(field)
        gpu, adapter, ev = d["gpu"], d["adapter"], d["evaluation"]
        if any(type(obj) is not dict or set(obj) != fields for obj, fields in
               ((gpu, GPU), (adapter, ADAPTER), (ev, EVAL))):
            raise ValueError("nested evidence schema")
        if (type(gpu["device_name"]) is not str or not gpu["device_name"].strip()
            or gpu["cuda_available"] is not True
            or type(gpu["training_steps"]) is not int or gpu["training_steps"] < 1
            or type(gpu["duration_seconds"]) not in (int, float)
            or not math.isfinite(gpu["duration_seconds"]) or gpu["duration_seconds"] <= 0
            or type(gpu["log_sha256"]) is not str or not HEX.fullmatch(gpu["log_sha256"])):
            raise ValueError("gpu evidence fields")
        if (type(adapter["path"]) is not str or not adapter["path"]
            or type(adapter["size_bytes"]) is not int or adapter["size_bytes"] < 1
            or type(adapter["sha256"]) is not str or not HEX.fullmatch(adapter["sha256"])):
            raise ValueError("adapter evidence fields")
        relative = pathlib.PurePosixPath(adapter["path"])
        if relative.is_absolute() or any(x in (".", "..") for x in relative.parts) or "\\" in adapter["path"]:
            raise ValueError("unsafe adapter path")
        file = root / relative
        if not file.is_file() or file.is_symlink() or not file.resolve().is_relative_to(root):
            raise ValueError("adapter file missing, symlink or outside root")
        raw = file.read_bytes()
        if len(raw) != adapter["size_bytes"] or hashlib.sha256(raw).hexdigest() != adapter["sha256"]:
            raise ValueError("adapter artifact mismatch")
        out["artifact_verified"] = True
        if (ev["dataset_sha256"] != d["dataset_sha256"] or ev["split"] != "heldout"
            or type(ev["metric"]) is not str or not ev["metric"].strip()
            or ev["direction"] not in ("higher", "lower")
            or type(ev["sample_count"]) is not int or ev["sample_count"] < 30
            or type(ev["evaluator_sha256"]) is not str or not HEX.fullmatch(ev["evaluator_sha256"])):
            raise ValueError("evaluation provenance fields")
        for field in ("baseline", "candidate"):
            if type(ev[field]) not in (int, float) or not math.isfinite(ev[field]):
                raise ValueError("evaluation metric")
        # A claimed gain is only arithmetic on candidate-supplied evidence.
        gain = ev["candidate"] - ev["baseline"]
        if ev["direction"] == "lower":
            gain = -gain
        out["claimed_metric_gain"] = gain
        out["evidence_consistent"] = True
        out["reason"] = "candidate evidence internally consistent; no external GPU/evaluator attestation"
    except (OSError, ValueError, TypeError, UnicodeError, OverflowError) as exc:
        out["reason"] = str(exc)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", required=True)
    p.add_argument("--evidence", required=True)
    a = p.parse_args()
    result = check(a.root, a.evidence)
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0 if result["evidence_consistent"] else 1


if __name__ == "__main__":
    sys.exit(main())
