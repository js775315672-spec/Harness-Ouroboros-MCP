# Harness-Ouroboros-MCP

Hydra runs approved tasks through GitHub Actions. Its next-task workflow reads the last 12 completed standing runs on main and writes a `hydra-next-task.json` artifact. A newer successful job resolves an earlier failure with the same name. An unresolved admission failure takes priority over worker failures.

When the selector finds no unresolved failure in that window, it checks the [Cycle 01 dispatch preflight](docs/evolution/cycle-01-dispatch-preflight.json). A blocked, undispatched cycle adds a `next_review` field with the evidence needed to proceed. This field is advisory. The [ORIL ledger and evaluation contract](docs/evolution/README.md) describes how to assess a candidate before adopting it.

Run the offline selector tests from the repository root with `python -B -m unittest discover -s tests -v`.
### GPU LoRA experiment

The supervised experiment interprets short English Hydra job summaries as success or failure. It uses a frozen Google BERT Tiny masked-language model. The CPU computes its frozen features. The GPU trains a rank-two update to the two label-token rows of its vocabulary projection with full-batch SGD. At inference the score for those rows is `x Wᵀ + bias + x Aᵀ Bᵀ`. The receipt records the measured effect on the public synthetic evaluation split and the next review task.

Use Python 3.12 and an isolated environment. For Windows DirectML, install the tested runtime with `python -m pip install torch-directml==0.2.5.dev240914 transformers==4.46.3 safetensors==0.8.0 numpy==1.26.4`. The trainer also accepts CUDA-enabled PyTorch. Download `config.json`, `vocab.txt`, and `model.safetensors` into one directory from the [pinned BERT checkpoint](https://huggingface.co/google/bert_uncased_L-2_H-128_A-2/tree/30b0a37ccaaa32f332884b96992754e246e48c5f). The trainer verifies their byte digests.

From the repository root, substitute your model directory for MODEL.

```sh
python scripts/hydra_gpu_lora.py --model MODEL --out my-lora-run
python scripts/hydra_gpu_lora.py --model MODEL --out experiments/hydra-lora/run-01 --verify
python scripts/hydra_gpu_lora.py --model MODEL --out my-lora-run --predict "The worker timed out before writing a receipt."
```

Training requires a hardware GPU. Prediction and verification use the saved adapter on CPU. Keep independent production evaluation separate from these public development examples. The standing worker continues to use its existing approval and independent grading path.

The recorded Radeon run completed 100 SGD updates. On 12 public evaluation examples the baseline got 6 correct and the restored adapter got 8 correct. Five answers improved and three regressed. The next-task artifact exposes this candidate for independent evaluation when the production failure queue is clear. See the [run receipt](experiments/hydra-lora/run-01/receipt.json).

## ORIL v3 공개 자기개선 실험

통합 브랜치에서는 GitHub Actions가 Qwen 추론, 공개 검산, 가설 선택과 후속 실행을 세 번 연결한다. [한국어 개발 보고서](docs/oril/report.ko.md)에서 측정값과 [독립 평가용 후보](docs/oril/candidate-for-independent-evaluation.json)를 확인할 수 있다.
