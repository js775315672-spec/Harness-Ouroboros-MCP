"""Run one bounded public experiment; only aggregate public memory crosses cycles."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import oril_v2_slot2_pretrained_paired_diagnostic as paired
from oril_v2_slot1_30_public_qwen_pairs import public_tasks, summarize
from oril_v2_slot3_public30_pretrained_aa_null import audit_null
from oril_v2_pretrained_qwen_cpu_smoke import MODEL_ID, sha256_file

REV = "7ae557604adf67be50417f59c2c2f167def9a775"
WEIGHT = "fdf756fa7fcbe7404d5c60e26bff1a0c8b8aa1f72ced49e7dd0210fe288fb7fe"
TASKS = "da01e3d2e6d4d484f9dfa166e298e22d29979d5360bb93ce93510e8f18101cdd"
PROMPTS = {
    "remove_redundancy": paired.COMPACT,
    "integer_format": "Return the final integer only.",
    "check_sum": "Add the two integers carefully. Output just the sum.",
}
SEED = "99376656a4c4a7df737d54d9da36f9743b4ede02bc73d54461c379db69860a09"


def plan(memory):
    order = list(PROMPTS)
    if memory["candidate_errors"] > 0:
        order = ["integer_format", "check_sum", "remove_redundancy"]
    return next(name for name in order if name not in memory["tried"])


def write(path, data):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, sort_keys=True, ensure_ascii=False)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("number", type=int, choices=(1, 2, 3))
    args = parser.parse_args()
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from huggingface_hub import snapshot_download
    torch.set_num_threads(2)
    torch.manual_seed(42)
    n = args.number
    run = os.environ["GITHUB_RUN_ID"]
    folder = Path("candidate")
    folder.mkdir()
    parent = Path("input/memory.json")
    if n == 1:
        seed = Path("input/public_30_pairs.json")
        if sha256_file(seed) != SEED:
            raise ValueError("historical evidence mismatch")
        from oril_v2_slot2_public30_independent_audit import audit
        prior = audit(json.loads(seed.read_text(encoding="utf-8")))
        memory = {"tried": [], "candidate_errors": 0}
        source = SEED
        observed = prior["input_tokens"]
    else:
        memory = json.loads(parent.read_text(encoding="utf-8"))
        if memory["cycle_id"] != f"{run}-{n-1}" or len(set(memory["tried"])) != n-1:
            raise ValueError("unrelated predecessor")
        source = sha256_file(parent)
        observed = memory["candidate_errors"]
    strategy = plan(memory)
    paired.COMPACT = PROMPTS[strategy]
    tasks = public_tasks()
    if hashlib.sha256(json.dumps(tasks, sort_keys=True).encode()).hexdigest() != TASKS:
        raise ValueError("public suite changed")
    path = Path(snapshot_download(MODEL_ID, revision=REV, allow_patterns=["*.json","*.safetensors","*.txt"]))
    weight = path / "model.safetensors"
    if sha256_file(weight) != WEIGHT:
        raise ValueError("weight file mismatch")
    tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(path, local_files_only=True, torch_dtype=torch.float32).eval()
    common = dict(schema_version=1, model_id=MODEL_ID, resolved_revision=REV,
                  weight_files=[dict(name=weight.name, bytes=weight.stat().st_size, sha256=WEIGHT)],
                  public_tasks_sha256=TASKS, pretrained_checkpoint_loaded=True, weights_trained_this_run=False,
                  gpu_lora_training_proven=False, independent_heldout_accuracy_proven=False, quality_gain=None, speed_gain=None)
    ab, aa = [], []
    start = time.monotonic()
    for i, task in enumerate(tasks):
        order = ["verbose","compact"] if i % 2 == 0 else ["compact","verbose"]
        for kind in (("ab","aa") if i % 2 == 0 else ("aa","ab")):
            variants = order if kind == "ab" else ["compact","compact"]
            observations = [paired.measure(model, tokenizer, torch, task["question"], task["expected"], v) for v in variants]
            row = dict(task, observations=observations)
            if kind == "ab":
                ab.append(dict(row, execution_order=order))
            else:
                aa.append(row)
    write(folder / "ab.json", dict(common, rows=ab, summary=summarize(ab)))
    write(folder / "aa.json", dict(common, rows=aa, summary=audit_null(aa)))
    write(folder / "candidate.json", dict(cycle_id=f"{run}-{n}", parent_cycle_id=f"{run}-{n-1}" if n>1 else None,
          base_sha=os.environ["BASE_SHA"], implementation_sha=os.environ["SOURCE_SHA"],
          candidate_sha=hashlib.sha256(paired.COMPACT.encode()).hexdigest(), prompt=paired.COMPACT,
          run_id=run, parent_evidence_sha256=source, tried=memory["tried"]+[strategy],
          hypothesis_id=strategy, failure_category="PROMPT", observed_problem=observed,
          expected_effect="Reduce input tokens by at least 20 percent", guardrail="zero new public regressions",
          falsification="less than 20 percent saving or any new regression", elapsed_seconds=time.monotonic()-start,
          raw_sha256={name:sha256_file(folder/name) for name in ("ab.json","aa.json")}))


if __name__ == "__main__":
    main()
