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

# OCR candidate A: Paddle. Instantiation downloads model files into the build-time cache.
from paddleocr import PaddleOCR

try:
    PaddleOCR(lang="vi",use_doc_orientation_classify=False,use_doc_unwarping=False,use_textline_orientation=False)
except TypeError:
    PaddleOCR(lang="vi",use_angle_cls=False)

# PP-StructureV3 is only called after a cheap ruled-table signal, but its assets must still be available offline.
from paddleocr import PPStructureV3

PPStructureV3(use_doc_orientation_classify=False, use_doc_unwarping=False)

# Semantic resolver model already used by the platform.
from sentence_transformers import SentenceTransformer

model_name=os.environ.get("EMBEDDING_MODEL_NAME","sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
SentenceTransformer(model_name).save(str(root/"sentence-transformers"/"paraphrase-multilingual-MiniLM-L12-v2"))

# VietOCR is an optional benchmark candidate, not a hard dependency: it hard-pins
# pillow==10.2.0, which cannot co-exist with pdfplumber's Pillow>=12.2 requirement.
# When it is deliberately installed (pip install '.[vietocr]') bake its weights too;
# otherwise skip quietly so the default paddle/paddle image still builds.
try:
    import shutil

    from vietocr.tool.config import Cfg
    from vietocr.tool.predictor import Predictor
    from vietocr.tool.utils import download_weights
except ImportError:
    print("vietocr not installed; skipping optional OCR benchmark weights")
else:
    cfg=Cfg.load_config_from_name("vgg_transformer")
    cfg["cnn"]["pretrained"]=False
    cfg["device"]="cpu"
    cfg["predictor"]["beamsearch"]=False
    downloaded=Path(download_weights(cfg["weights"]))
    viet_dir=root/"vietocr"
    viet_dir.mkdir(parents=True,exist_ok=True)
    local_weight=viet_dir/"vgg_transformer.pth"
    shutil.copy2(downloaded,local_weight)
    cfg["weights"]=str(local_weight)
    Predictor(cfg)
