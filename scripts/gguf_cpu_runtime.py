#!/usr/bin/env python3
"""Fail-closed local GGUF CPU completion adapter for the existing Harness loop.

Only official Qwen2.5-Coder 0.5B/1.5B Apache-2.0 models are allowed.
The restricted 3B research model is deliberately not executable here.
No shell, credentials, patch writes, model-provided commands or network downloads.
"""
import hashlib
import os
from pathlib import Path
import resource
import stat
import subprocess
import time

MODELS = {
    "0.5b": {
        "repo": "Qwen/Qwen2.5-Coder-0.5B-Instruct-GGUF",
        "filename": "qwen2.5-coder-0.5b-instruct-q4_k_m.gguf",
        "license": "apache-2.0",
        "minimum_bytes": 250_000_000,
        "maximum_bytes": 750_000_000,
    },
    "1.5b": {
        "repo": "Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF",
        "filename": "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf",
        "license": "apache-2.0",
        "minimum_bytes": 800_000_000,
        "maximum_bytes": 1_500_000_000,
    },
}
RESTRICTED = {"3b": "qwen-research: non-commercial evaluation only; not authorized here"}
MAX_PROMPT_BYTES = 5000
MAX_OUTPUT_BYTES = 6000


def approved_model(model):
    if not isinstance(model, str):
        raise ValueError("invalid model identifier")
    if model in RESTRICTED:
        raise ValueError("restricted model requires separate explicit license review")
    if model not in MODELS:
        raise ValueError("model not on the GGUF CPU allowlist")
    return MODELS[model].copy()


def _regular_file(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("non-regular or symlink path")
    if not stat.S_ISREG(os.stat(path, follow_symlinks=False).st_mode):
        raise ValueError("non-regular file")
    return path.resolve(strict=True)


def verify_paths(model, cli, gguf):
    spec = approved_model(model)
    executable = _regular_file(cli)
    if executable.name != "llama-completion":
        raise ValueError("only the pinned llama-completion binary is allowed")
    weights = _regular_file(gguf)
    if not os.access(executable, os.X_OK):
        raise ValueError("llama.cpp CLI is not executable")
    if weights.name != spec["filename"]:
        raise ValueError("GGUF basename is not the official allowlisted file")
    size = weights.stat().st_size
    if not spec["minimum_bytes"] <= size <= spec["maximum_bytes"]:
        raise ValueError("GGUF size outside allowlisted boundaries")
    with weights.open("rb") as src:
        if src.read(4) != b"GGUF":
            raise ValueError("invalid GGUF signature")
    return spec, executable, weights


def sha256_file(path):
    digest = hashlib.sha256()
    with _regular_file(path).open("rb") as src:
        for chunk in iter(lambda: src.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class CPUInference:
    def __init__(self, model, cli, gguf, timeout_seconds=150):
        self.spec, self.cli, self.gguf = verify_paths(model, cli, gguf)
        if type(timeout_seconds) is not int or not 10 <= timeout_seconds <= 240:
            raise ValueError("invalid bounded inference timeout")
        self.timeout_seconds = timeout_seconds
        self.calls = []

    def generate(self, prompt):
        if not isinstance(prompt, str) or not 1 <= len(prompt.encode("utf-8")) <= MAX_PROMPT_BYTES:
            raise ValueError("invalid prompt budget")
        # No optional command strings or arbitrary user-controlled CLI arguments.
        command = [
            str(self.cli), "--model", str(self.gguf),
            "--prompt", prompt, "--n-predict", "140",
            "--ctx-size", "2048", "--threads", "4",
            "--temp", "0", "--no-display-prompt",
            "--simple-io", "--single-turn", "--jinja",
            "--offline", "--log-verbosity", "1", "--color", "off",
        ]
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": "/tmp",
            "LANG": "C.UTF-8",
            "OMP_NUM_THREADS": "4",
        }
        before = time.perf_counter()
        try:
            output = subprocess.run(
                command, shell=False, capture_output=True, text=True,
                timeout=self.timeout_seconds, env=env, check=False,
                errors="replace")
        except subprocess.TimeoutExpired as exc:
            raise ValueError("bounded GGUF inference timeout") from exc
        elapsed = round(time.perf_counter() - before, 3)
        if output.returncode != 0:
            raise ValueError("llama-cli returned nonzero status")
        if len(output.stdout.encode("utf-8")) > MAX_OUTPUT_BYTES:
            raise ValueError("model output exceeded capped response budget")
        raw = output.stdout.strip()
        self.calls.append({
            "elapsed_seconds": elapsed,
            "response_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            "response_chars": len(raw),
            "peak_child_rss_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
            "return_code": output.returncode,
        })
        return raw
