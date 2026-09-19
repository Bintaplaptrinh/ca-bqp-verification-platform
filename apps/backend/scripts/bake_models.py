"""Download runtime model assets during image build; runtime is configured offline.

Imports below are intentionally placed after the cache-directory environment
is set up: each library reads those variables at import time, so hoisting them
to the top would send the downloads to the wrong location.
"""
# ruff: noqa: E402
from __future__ import annotations

import os
from pathlib import Path

root=Path(os.environ.get("HF_HOME","/models")); root.mkdir(parents=True,exist_ok=True)
os.environ.setdefault("HOME",str(root))
os.environ.setdefault("PADDLE_PDX_CACHE_HOME",str(root/"paddlex"))

# OCR candidate used in production. Vietnamese recognition assets are downloaded
# during the image build; runtime explicitly disables downloads.
import easyocr

easy_dir=Path(os.environ.get("EASYOCR_MODEL_DIR",str(root/"easyocr")))
easy_dir.mkdir(parents=True,exist_ok=True)
easyocr.Reader(
    ["vi"],
    gpu=False,
    model_storage_directory=str(easy_dir),
    download_enabled=True,
    verbose=False,
)

# PP-StructureV3 is only called after a cheap ruled-table signal, but its assets must still be available offline.
from paddleocr import PPStructureV3

PPStructureV3(use_doc_orientation_classify=False, use_doc_unwarping=False)

# Semantic resolver model already used by the platform.
from sentence_transformers import SentenceTransformer

model_name=os.environ.get("EMBEDDING_MODEL_NAME","sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
SentenceTransformer(model_name).save(str(root/"sentence-transformers"/"paraphrase-multilingual-MiniLM-L12-v2"))

# VietOCR: the fallback recognizer run when EasyOCR's mean confidence falls below
# OCR_FALLBACK_CONFIDENCE_MIN. Both its YAML configs and its checkpoint must be on
# disk before runtime, which is offline (VIETOCR_DOWNLOAD_ENABLED=false).
# The application package is not installed yet at this point in the build, so the
# config/weight resolution is duplicated here deliberately rather than imported from
# cabqp.modules.document_intelligence.ocr.engines.
import vietocr
import yaml
from vietocr.tool.config import Cfg
from vietocr.tool.predictor import Predictor

config_dir=Path(os.environ.get("VIETOCR_CONFIG_DIR") or Path(vietocr.__file__).resolve().parent.parent/"config")
merged: dict={}
for name in ("base.yml","vgg-transformer.yml"):
    with (config_dir/name).open(encoding="utf-8") as handle:
        merged.update(yaml.safe_load(handle))
cfg=Cfg(merged)
cfg["cnn"]["pretrained"]=False
cfg["device"]="cpu"
cfg["predictor"]["beamsearch"]=False
viet_dir=root/"vietocr"; viet_dir.mkdir(parents=True,exist_ok=True)
local_weight=Path(os.environ.get("VIETOCR_WEIGHTS") or viet_dir/"vgg_transformer.pth")
local_weight.parent.mkdir(parents=True,exist_ok=True)
import requests

with requests.get(cfg["weights"],stream=True,timeout=300) as response:
    response.raise_for_status()
    with local_weight.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=1<<20):
            handle.write(chunk)
cfg["weights"]=str(local_weight)
Predictor(cfg)
