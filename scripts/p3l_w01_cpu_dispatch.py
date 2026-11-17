#!/usr/bin/env python3
"""Produce a fail-closed CPU model handoff from an immutable W01 request.

This is coordinator-authored integration infrastructure, NOT a model call,
model-produced W01 documentation or authorization to run a model. W06 must
verify independent upstream gates and add the actual inference executor.
"""
import argparse
import json
from pathlib import Path
import re
import sys

from p3l_w01_request import build_request, canonical, digest, save_request, verified_head

REQUEST = Path("artifacts/p3l-w01/request.json")
OUTPUT = Path("artifacts/p3l-w01/dispatch.json")
SUPPORTED = frozenset(("0.5b", "1.5b", "7b", "14b"))
REQUIRES = ("W01_CONTRACT_REVIEW", "W02_PROMPT_REVIEW",
            "W04_DUPLICATE_AND_BUDGET_GATE", "W05_INDEPENDENT_REPLAY",
            "W06_EXPLICIT_SINGLE_INFERENCE_APPROVAL")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")


def load_request(root, filename, reviewed_commit):
    root = Path(root).resolve(strict=True)
    filename = Path(filename)
    if filename.is_absolute() or ".." in filename.parts or filename.parts[:2] != ("artifacts", "p3l-w01"):
        raise ValueError("W01 request must stay under artifacts/p3l-w01")
    path = root / filename
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
        raise ValueError("unsafe W01 request artifact")
    if path.stat().st_size > 24_000 or path.stat().st_size == 0:
        raise ValueError("unbounded W01 request artifact")
    saved = json.loads(path.read_text(encoding="utf-8"))
    regenerated = build_request(root, reviewed_commit)
    if saved != regenerated:
        raise ValueError("W01 request is stale, forged, or mismatched with reviewed sources")
    return regenerated


def dispatch(root, filename, reviewed_commit, model_id="0.5b", model_catalog=None):
    root = Path(root).resolve(strict=True)
    verified_head(root, reviewed_commit)
    request = load_request(root, filename, reviewed_commit)
    if model_id not in SUPPORTED:
        raise ValueError("CPU model is not an approved adapter target")
    if model_catalog is None:
        from gguf_cpu_runtime import approved_model
        model_catalog = approved_model
    spec = model_catalog(model_id)
    if not isinstance(spec, dict) or spec.get("license") != "apache-2.0":
        raise ValueError("unapproved model license or metadata")
    name, repository = spec.get("filename"), spec.get("repo")
    if (not isinstance(name, str) or not name.endswith(".gguf") or "/" in name
            or not isinstance(repository, str) or not repository.startswith("Qwen/")):
        raise ValueError("unexpected model repository or file")
    revision, weights_sha = spec.get("revision"), spec.get("sha256")
    pinned = isinstance(revision, str) and HEX40.fullmatch(revision) is not None and (
        isinstance(weights_sha, str) and HEX64.fullmatch(weights_sha) is not None)
    item = {
        "schema": "p3l-w01-cpu-dispatch-v1", "worker": "W01",
        "review_commit": reviewed_commit,
        "request_sha256": request["request_sha256"],
        "prompt_sha256": request["prompt_sha256"],
        "source_sha256": request["source_sha256"],
        "spec_sha256": request["spec_sha256"],
        "allowed_output": request["allowed_output"],
        "adapter": "gguf_cpu_runtime.CPUInference",
        "model_id": model_id, "model_repository": repository,
        "model_filename": name, "model_revision": revision,
        "model_sha256": weights_sha,
        "model_pinned": bool(pinned),
        "max_model_calls_after_approval": 1,
        "actual_model_calls": 0,
        "execution_enabled": False, "executor_connected": False,
        "real_model_response_observed": False,
        "independent_replay_verified": False,
        "candidate_verified": False, "merge_authorized": False,
        "required_approval_gates": list(REQUIRES),
        "status": "BLOCKED_PENDING_W01_W02_W04_W05_W06_REVIEW",
        "generated_by": "GPT-6 coordinator dispatch scaffold, not model output",
    }
    item["dispatch_sha256"] = digest(canonical(item))
    return item


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--request", type=Path, default=REQUEST)
    parser.add_argument("--model", choices=sorted(SUPPORTED), default="0.5b")
    parser.add_argument("--out", type=Path, default=OUTPUT)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        if args.execute:
            raise ValueError("model execution forbidden before independent W06 approval")
        planned = dispatch(args.root, args.request, args.head_sha, args.model)
        save_request(args.root, args.out, planned)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"BLOCK: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({key: planned[key] for key in
                      ("worker", "status", "dispatch_sha256", "actual_model_calls",
                       "execution_enabled", "model_pinned")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
