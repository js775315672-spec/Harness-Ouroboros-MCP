#!/usr/bin/env bash
set -euo pipefail

python3 -m pip install --disable-pip-version-check --index-url https://download.pytorch.org/whl/cpu 'torch==2.5.1+cpu'
python3 -m pip install --disable-pip-version-check 'transformers==4.46.3' 'huggingface_hub==0.26.5' 'safetensors==0.4.5'
python3 -c 'import torch; assert torch.version.cuda is None, torch.__version__'
