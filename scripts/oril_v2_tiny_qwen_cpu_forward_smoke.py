#!/usr/bin/env python3
"""Actual CPU forward-pass smoke for ORIL local Qwen adapter.

Creates a TINY RANDOM-WEIGHT Qwen2 checkpoint. This is a real torch model
forward/generation run, NOT pretrained Qwen, LoRA, quality or intelligence proof.
No external model weights, private data, GPU, or network downloads are used.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def build_tiny_checkpoint(path):
    import torch
    from tokenizers import Tokenizer
    from tokenizers.models import WordLevel
    from tokenizers.pre_tokenizers import Whitespace
    from transformers import (Qwen2Config, Qwen2ForCausalLM,
                              PreTrainedTokenizerFast)
    torch.manual_seed(12345)
    vocab = {"[UNK]": 0, "[PAD]": 1, "Question": 2, "answer": 3,
             "short": 4, "verbose": 5, "explanation": 6, "test": 7,
             "safe": 8, "compact": 9, "reason": 10, "and": 11,
             "fix": 12, "a": 13, "bug": 14, "with": 15,
             "clear": 16, "steps": 17, ".": 18, ":": 19}
    tokenizer_backend = Tokenizer(WordLevel(vocab=vocab, unk_token="[UNK]"))
    tokenizer_backend.pre_tokenizer = Whitespace()
    tokenizer = PreTrainedTokenizerFast(tokenizer_object=tokenizer_backend,
                                        unk_token="[UNK]", pad_token="[PAD]")
    tokenizer.save_pretrained(path)
    model = Qwen2ForCausalLM(Qwen2Config(
        vocab_size=len(vocab), hidden_size=48, intermediate_size=96,
        num_hidden_layers=1, num_attention_heads=4, num_key_value_heads=2,
        max_position_embeddings=128, tie_word_embeddings=False,
        bos_token_id=0, eos_token_id=19, pad_token_id=1))
    model.save_pretrained(path, safe_serialization=True)
    return hashlib.sha256((Path(path) / "config.json").read_bytes()).hexdigest()


def invoke(adapter, model_dir, question):
    request = {"question": question, "case_id": "synthetic-forward-only", "seed": 5}
    start = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, str(adapter), "--model-dir", str(model_dir),
         "--device", "cpu", "--max-new-tokens", "3"],
        input=json.dumps(request), text=True, capture_output=True,
        timeout=120, check=False, env={
            **os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
            "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
        })
    if proc.returncode:
        raise RuntimeError("local Qwen CPU adapter failed: " + proc.stderr[-1500:])
    response = json.loads(proc.stdout)
    if set(response) != {"answer", "input_tokens", "output_tokens", "model_id"}:
        raise ValueError("unexpected response schema")
    if not (type(response["input_tokens"]) is int and response["input_tokens"] > 0
            and type(response["output_tokens"]) is int and response["output_tokens"] > 0
            and response["model_id"] == "local:" + model_dir.name):
        raise ValueError("actual token counts or model identity missing")
    return {"input_tokens": response["input_tokens"],
            "output_tokens": response["output_tokens"],
            "elapsed_seconds": round(time.perf_counter() - start, 3)}


def smoke():
    with tempfile.TemporaryDirectory(prefix="oril-tiny-qwen-smoke-") as td:
        model_dir = Path(td) / "random-qwen2"
        model_dir.mkdir()
        config_sha = build_tiny_checkpoint(model_dir)
        adapter = Path(__file__).resolve().parent / "oril_v2_local_qwen_adapter.py"
        short = invoke(adapter, model_dir, "Question: fix a bug.")
        verbose = invoke(adapter, model_dir,
                         "verbose explanation and clear steps and reason "
                         "with safe test and fix a bug. Question: fix a bug.")
        if short["input_tokens"] >= verbose["input_tokens"]:
            raise AssertionError("short prompt did not reduce measured tokens")
        return {
            "schema_version": 1,
            "checkpoint_kind": "random_tiny_qwen2_cpu_smoke",
            "pretrained_weights": False,
            "config_sha256": config_sha,
            "model_forward_executed": True,
            "two_real_cpu_generations": True,
            "compact_prompt": short,
            "verbose_prompt": verbose,
            "actual_tokenizer_input_token_delta":
                verbose["input_tokens"] - short["input_tokens"],
            "gpu_used": False, "optimizer_steps": 0,
            "lora_adapter_created": False,
            "independent_heldout_evaluation": False,
            "model_intelligence_gain": None,
            "warning": "Random weights and synthetic prompts: this is NOT real Qwen quality, LoRA training, or hidden evaluation evidence.",
        }


if __name__ == "__main__":
    print(json.dumps(smoke(), ensure_ascii=False, sort_keys=True))
