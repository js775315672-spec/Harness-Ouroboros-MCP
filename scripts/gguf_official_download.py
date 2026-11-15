#!/usr/bin/env python3
"""Download only officially-published, license-checked Qwen GGUF weights.

No unrestricted model URI, implicit token, third-party quantizer or 3B access.
Download commit and SHA256 are saved for experimental provenance.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

try:
    from .gguf_cpu_runtime import approved_model, sha256_file
except ImportError:
    from gguf_cpu_runtime import approved_model, sha256_file


def resolve_license(card):
    if isinstance(card, dict):
        return card.get("license")
    return getattr(card, "license", None)


def download(model, destination, get_info, get_file):
    spec = approved_model(model)
    info = get_info(spec["repo"])
    sha = getattr(info, "sha", None)
    license_id = resolve_license(getattr(info, "card_data", None))
    if not isinstance(sha, str) or re.fullmatch("[0-9a-f]{40}", sha) is None:
        raise ValueError("unverified official model commit")
    if license_id != "apache-2.0":
        raise ValueError("official model license is not an approved Apache-2.0 license")
    root = Path(destination)
    if root.is_symlink():
        raise ValueError("destination cannot be a symlink")
    root.mkdir(parents=True, exist_ok=True)
    filename = spec["filename"]
    target = root / filename
    if target.exists() or target.is_symlink():
        raise ValueError("refusing to overwrite a previously downloaded model")
    cache_path = Path(get_file(spec["repo"], filename, sha))
    if cache_path.is_symlink():
        # huggingface_hub cache snapshots can be symlinked to blob storage;
        # only resolved cache paths are read, never used as executable source.
        cache_path = cache_path.resolve(strict=True)
    if not cache_path.is_file():
        raise ValueError("missing downloaded GGUF weights")
    size = cache_path.stat().st_size
    if not spec["minimum_bytes"] <= size <= spec["maximum_bytes"]:
        raise ValueError("downloaded model size outside the allowlist")
    with cache_path.open("rb") as stream:
        if stream.read(4) != b"GGUF":
            raise ValueError("download did not have GGUF file signature")
    # A 7B GGUF is several gigabytes. On the same ephemeral CI volume, a
    # hardlink avoids retaining an unnecessary second full model copy.
    # Fail closed if a safe hardlink cannot be created; no download fallback
    # from untrusted hosts, partial model or unrestricted path is permitted.
    if model == "7b":
        os.link(cache_path, target)
    else:
        shutil.copyfile(cache_path, target)
    return {
        "model": model, "repository": spec["repo"], "revision": sha,
        "filename": filename, "license": license_id, "quantization": "Q4_K_M",
        "size_bytes": target.stat().st_size,
        "sha256": sha256_file(target),
        "secret_or_paid_api_used": False, "approved_for_3b": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, choices=["0.5b", "1.5b", "7b"])
    parser.add_argument("--destination", type=Path, default=Path("models"))
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    from huggingface_hub import hf_hub_download, model_info
    def get_info(repo):
        return model_info(repo, token=False)
    def get_file(repo, filename, sha):
        return hf_hub_download(
            repo_id=repo, filename=filename, revision=sha, token=False)
    result = download(args.model, args.destination, get_info, get_file)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
