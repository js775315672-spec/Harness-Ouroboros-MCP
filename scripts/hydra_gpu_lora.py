"""Train and replay a GPU LoRA for the Hydra outcome-reading experiment."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import torch
from torch import nn
from safetensors.torch import load_file, save_file
from transformers import BertForMaskedLM, BertTokenizerFast

FILES = {
    "config.json": "508e1f01aae55d73355cbdd82609be2f43ba5a0d3428837adbe56cf8391f8b39",
    "vocab.txt": "07eced375cec144d27c900241f3e339478dec958f92fddbc551f295c992038a3",
    "model.safetensors": "7fb69ad9f6866d8983183c930e33828f326470bf6ad8bbb2ad4ed957a92e9414",
}
REVISION = "30b0a37ccaaa32f332884b96992754e246e48c5f"
DATA = Path(__file__).resolve().parents[1] / "experiments/hydra-lora"
LABELS = ["failure", "success"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_model(folder):
    for name, expected in FILES.items():
        if digest(folder / name) != expected:
            raise ValueError(f"base file digest mismatch: {name}")
    model, info = BertForMaskedLM.from_pretrained(folder, output_loading_info=True)
    if info["missing_keys"] or info["mismatched_keys"]:
        raise ValueError(f"incomplete pretrained weights: {info}")
    return model.eval().requires_grad_(False), BertTokenizerFast.from_pretrained(folder)


@torch.no_grad()
def features(model, tokenizer, texts):
    prompts = [f"{text} The outcome was a [MASK]." for text in texts]
    tokens = tokenizer(prompts, padding=True, return_tensors="pt")
    mask = tokens.input_ids == tokenizer.mask_token_id
    if not (mask.sum(dim=1) == 1).all():
        raise ValueError("each observation must have one prediction position")
    hidden = model.bert(**tokens).last_hidden_state[mask]
    return model.cls.predictions.transform(hidden)


def logits(x, head, a, b):
    w, bias = head
    return nn.functional.linear(x, w, bias) + (x @ a.T) @ b.T


def read_split(name):
    with (DATA / name).open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    return [row["text"] for row in rows], torch.tensor([LABELS.index(row["label"]) for row in rows])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--verify", action="store_true", help="replay the recorded evaluation on CPU")
    action.add_argument("--predict", help="classify one job summary with the verified adapter")
    args = parser.parse_args()
    torch.manual_seed(317)
    torch.set_num_threads(2)
    model, tokenizer = load_model(args.model)
    ids = tokenizer.convert_tokens_to_ids(LABELS)
    decoder = model.cls.predictions.decoder
    head = decoder.weight[ids], decoder.bias[ids]
    adapter = args.out / "adapter.safetensors"
    receipt = args.out / "receipt.json"
    if args.predict is not None or args.verify:
        report = json.loads(receipt.read_text())
        if report["adapter_sha256"] != digest(adapter) or report["base_files"] != FILES:
            raise ValueError("receipt does not match the adapter and base")
        weights = load_file(str(adapter))
        if args.verify:
            texts, targets = read_split("eval.csv")
            if report["split_sha256"]["eval.csv"] != digest(DATA / "eval.csv"):
                raise ValueError("evaluation split digest mismatch")
            x = features(model, tokenizer, texts)
            before = nn.functional.linear(x, *head).argmax(1)
            after = logits(x, head, weights["A"], weights["B"]).argmax(1)
            for key, actual in [("baseline_predictions", before.tolist()),
                                ("candidate_predictions", after.tolist()),
                                ("baseline_correct", int(before.eq(targets).sum())),
                                ("candidate_correct", int(after.eq(targets).sum()))]:
                if actual != report[key]:
                    raise ValueError(f"evaluation mismatch: {key}")
            print(f"Verified {len(texts)} paired predictions and adapter {digest(adapter)}")
            return
        scores = logits(features(model, tokenizer, [args.predict]), head, weights["A"], weights["B"])
        print(LABELS[scores.argmax().item()])
        return

    train_text, y = read_split("train.csv")
    eval_text, targets = read_split("eval.csv")
    if set(train_text) & set(eval_text):
        raise ValueError("overlapping train and evaluation observations")
    if args.out.exists():
        raise FileExistsError("choose a new output directory for each run")
    if torch.cuda.is_available():
        device, gpu = torch.device("cuda"), torch.cuda.get_device_name()
    else:
        import torch_directml
        device, gpu = torch_directml.device(), torch_directml.device_name(0)
        if "basic render" in gpu.lower() or "warp" in gpu.lower():
            raise RuntimeError("hardware GPU required")

    x = features(model, tokenizer, train_text).to(device)
    y = y.to(device)
    gpu_head = tuple(t.to(device) for t in head)
    a = nn.Parameter((torch.randn(2, x.shape[1]) * 0.02).to(device))
    b = nn.Parameter(torch.zeros(2, 2).to(device))
    optimizer = torch.optim.SGD([a, b], lr=0.04, foreach=False)
    losses = []
    for _ in range(100):
        optimizer.zero_grad()
        loss = nn.functional.cross_entropy(logits(x, gpu_head, a, b), y)
        loss.backward()
        optimizer.step()
        losses.append(loss.item())
    weights = {"A": a.detach().cpu(), "B": b.detach().cpu()}
    update = weights["B"] @ weights["A"]
    if not torch.isfinite(torch.tensor(losses)).all() or not torch.isfinite(update).all() or not update.any():
        raise RuntimeError("training did not produce a finite nonzero adapter")
    args.out.mkdir(parents=True)
    save_file(weights, str(adapter), metadata={"target": "cls.predictions.decoder.weight",
              "rows": json.dumps(ids), "scale": "1", "revision": REVISION})
    restored = load_file(str(adapter))
    test_x = features(model, tokenizer, eval_text)
    baseline = nn.functional.linear(test_x, *head).argmax(1)
    candidate = logits(test_x, head, restored["A"], restored["B"]).argmax(1)
    before, after = baseline.eq(targets), candidate.eq(targets)
    report = dict(model="google/bert_uncased_L-2_H-128_A-2", revision=REVISION,
                  base_files=FILES, adapter_sha256=digest(adapter), device=str(device), gpu=gpu,
                  torch_version=torch.__version__, optimizer="SGD", lr=0.04, seed=317, rank=2,
                  optimizer_steps=len(losses), initial_loss=losses[0], last_pre_step_loss=losses[-1],
                  delta_norm=update.norm().item(), train_examples=len(y), eval_examples=len(targets),
                  split_sha256={n: digest(DATA / n) for n in ["train.csv", "eval.csv"]},
                  baseline_correct=int(before.sum()), candidate_correct=int(after.sum()),
                  recovered=int((~before & after).sum()), regressed=int((before & ~after).sum()),
                  baseline_predictions=baseline.tolist(), candidate_predictions=candidate.tolist(),
                  verdict="public_fixture_gain" if after.sum() > before.sum() else "no_public_fixture_gain",
                  next_task="independent_evaluation" if after.sum() > before.sum() else "review_training_errors")
    receipt.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
