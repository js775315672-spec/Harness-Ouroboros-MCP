#!/usr/bin/env python3
"""Operator-controlled *real* local Hugging Face causal LM adapter for ORIL.

Protocol compatible with oril_v2_student_real_inference_probe.py.
Model is loaded from an existing local directory only, with remote code disabled.
Does NOT perform LoRA training, verify GPU attestation, or independently attest
its own token counts/model identity. One model load per request: slow by design.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys


def unique(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate request key")
        obj[key] = value
    return obj


def parse_request(raw):
    if len(raw) > 65536:
        raise ValueError("request exceeds 64 KiB")
    data = json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
    if not isinstance(data, dict) or set(data) != {"question", "case_id", "seed"}:
        raise ValueError("invalid request schema")
    if (not isinstance(data["question"], str) or
            not 0 < len(data["question"]) <= 4000 or "\x00" in data["question"]):
        raise ValueError("invalid question")
    if (not isinstance(data["case_id"], str) or
            not 0 < len(data["case_id"]) <= 128):
        raise ValueError("invalid case_id")
    if type(data["seed"]) is not int or not 0 <= data["seed"] <= 2147483647:
        raise ValueError("invalid seed")
    return data


def ensure_local_model(model_dir):
    """Reject symlinked ancestors/config before local model loading.

    This is a best-effort static preflight, NOT an atomic filesystem trust
    boundary: concurrent path swaps and other model files remain untrusted.
    """
    path = Path(model_dir).absolute()
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError("model must have non-symlink directory ancestry")
    if not path.is_dir():
        raise ValueError("model must be an existing non-symlink local directory")
    config = path / "config.json"
    if config.is_symlink():
        raise ValueError("local config.json must not be a symlink")
    if not config.is_file():
        raise ValueError("local config.json missing")
    # A local config is still untrusted input. Reject malformed or oversized
    # metadata before importing torch/transformers or touching model weights.
    # This is NOT a full checkpoint integrity proof; other weight files can
    # change and must be externally pinned before any trusted evaluation.
    with config.open("rb") as stream:
        raw = stream.read(1048577)
    if len(raw) > 1048576:
        raise ValueError("local config.json exceeds 1 MiB")
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite config JSON")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid local config JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("local config JSON must be an object")
    return str(path.resolve())


def render_question(question, tokenizer):
    """No heldout expected_answer enters the model prompt."""
    messages = [{"role": "user", "content": question}]
    if getattr(tokenizer, "chat_template", None):
        return tokenizer.apply_chat_template(messages, tokenize=False,
                                             add_generation_prompt=True)
    return question


def run_inference(request, *, model_dir, device="cpu", max_new_tokens=64):
    if device not in ("cpu", "cuda") or type(max_new_tokens) is not int or not 1 <= max_new_tokens <= 512:
        raise ValueError("invalid device or generation budget")
    model_path = ensure_local_model(model_dir)
    # Explicitly prohibit Hub network requests and arbitrary model code.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable")
    torch.manual_seed(request["seed"])
    if device == "cuda":
        torch.cuda.manual_seed_all(request["seed"])
    tokenizer = AutoTokenizer.from_pretrained(
        model_path, local_files_only=True, trust_remote_code=False)
    model = AutoModelForCausalLM.from_pretrained(
        model_path, local_files_only=True, trust_remote_code=False)
    model.to(device)
    model.eval()
    prompt = render_question(request["question"], tokenizer)
    encoded = tokenizer(prompt, return_tensors="pt")
    ids = encoded["input_ids"].to(device)
    mask = encoded.get("attention_mask")
    if mask is not None:
        mask = mask.to(device)
    if ids.shape[-1] > 4096:
        raise ValueError("prompt exceeds 4096 input tokens")
    kwargs = {"input_ids": ids, "max_new_tokens": max_new_tokens,
              "do_sample": False}
    if mask is not None:
        kwargs["attention_mask"] = mask
    with torch.inference_mode():
        generated = model.generate(**kwargs)
    if generated.shape[0] != 1 or generated.shape[1] < ids.shape[-1]:
        raise ValueError("invalid generated tensor shape")
    output_ids = generated[0, ids.shape[-1]:]
    answer = tokenizer.decode(output_ids, skip_special_tokens=True)
    if len(answer) > 20000:
        raise ValueError("answer exceeds adapter protocol limit")
    return {"answer": answer, "input_tokens": int(ids.shape[-1]),
            "output_tokens": int(output_ids.shape[-1]),
            "model_id": "local:" + Path(model_path).name}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model-dir", required=True)
    p.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    p.add_argument("--max-new-tokens", type=int, default=64)
    a = p.parse_args()
    raw = sys.stdin.buffer.read(65537)
    request = parse_request(raw.decode("utf-8"))
    result = run_inference(request, model_dir=a.model_dir,
                           device=a.device, max_new_tokens=a.max_new_tokens)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
