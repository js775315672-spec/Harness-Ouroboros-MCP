#!/usr/bin/env python3
"""Read-only audit of whether a real Qwen/LoRA evaluation can be attempted.

This tool never executes a model, downloads weights, changes approvals, or claims
that GPU detection proves training. No private absolute paths are written.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def sha_file(path, limit=4 * 1024 * 1024):
    if path.stat().st_size > limit:
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_checkpoint(path):
    if not path:
        return {"present": False, "config_sha256": None, "weights_present": False}
    root = Path(path)
    if root.is_symlink() or not root.is_dir():
        return {"present": False, "config_sha256": None, "weights_present": False}
    config = root / "config.json"
    if config.is_symlink() or not config.is_file():
        return {"present": True, "config_sha256": None, "weights_present": False}
    try:
        conf_hash = sha_file(config)
        weight_files = [p for p in root.iterdir() if p.is_file() and not p.is_symlink()
                        and (p.suffix == ".safetensors" or p.name == "pytorch_model.bin")
                        and p.stat().st_size > 0]
        return {"present": True, "config_sha256": conf_hash,
                "weights_present": bool(weight_files)}
    except OSError:
        return {"present": True, "config_sha256": None, "weights_present": False}


def probe_gpu():
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {"nvidia_smi_available": False, "gpu_count": None, "gpu_names": []}
    try:
        result = subprocess.run(
            [executable, "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5, check=False)
        if result.returncode != 0:
            return {"nvidia_smi_available": True, "gpu_count": None, "gpu_names": []}
        names = [line.strip()[:100] for line in result.stdout.splitlines() if line.strip()]
        return {"nvidia_smi_available": True, "gpu_count": len(names),
                "gpu_names": names[:8]}
    except (OSError, subprocess.TimeoutExpired):
        return {"nvidia_smi_available": True, "gpu_count": None, "gpu_names": []}


def audit(checkpoint=None, heldout=None, adapter=None, gpu_probe=None):
    gpu = gpu_probe if gpu_probe is not None else probe_gpu()
    ckpt = check_checkpoint(checkpoint)
    eval_path = Path(heldout) if heldout else None
    eval_ready = bool(eval_path and eval_path.is_file() and not eval_path.is_symlink()
                      and eval_path.stat().st_size > 0)
    adapter_path = Path(adapter) if adapter else None
    adapter_present = bool(adapter_path and adapter_path.is_dir()
                           and not adapter_path.is_symlink()
                           and (adapter_path / "adapter_config.json").is_file()
                           and any(x.is_file() and x.stat().st_size > 0
                                   for x in (adapter_path / "adapter_model.safetensors",
                                             adapter_path / "adapter_model.bin")))
    ready = bool(ckpt["present"] and ckpt["config_sha256"] and
                 ckpt["weights_present"] and eval_ready)
    missing = []
    if not ckpt["config_sha256"] or not ckpt["weights_present"]:
        missing.append("local_model_checkpoint")
    if not eval_ready:
        missing.append("heldout_dataset")
    if gpu["gpu_count"] is None or gpu["gpu_count"] == 0:
        missing.append("verified_gpu_execution")
    if not adapter_present:
        missing.append("real_lora_adapter")
    return {
        "schema_version": 1,
        "checkpoint": ckpt,
        "heldout_input_present": eval_ready,
        "adapter_files_present": adapter_present,
        "gpu": gpu,
        "ready_for_local_inference_attempt": ready,
        "ready_for_proven_lora_training": False,
        "missing_evidence": missing,
        "training_steps_observed": None,
        "adapter_sha256_verified": False,
        "independent_heldout_score": None,
        "model_intelligence_improved": None,
        "disclaimer": "GPU device discovery and files are not training or evaluation evidence."
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--checkpoint")
    p.add_argument("--heldout")
    p.add_argument("--adapter")
    p.add_argument("--output", required=True)
    args = p.parse_args()
    report = audit(args.checkpoint, args.heldout, args.adapter)
    output = Path(args.output)
    if output.is_symlink() or output.exists():
        raise ValueError("output must be new regular path (no overwrite)")
    with output.open("x", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    print(json.dumps({"ready_for_local_inference_attempt":
                      report["ready_for_local_inference_attempt"],
                      "missing_evidence": report["missing_evidence"]}))


if __name__ == "__main__":
    main()
