# vendor/

Third-party source vendored into this repository because it cannot be installed
from PyPI as published.

## vietocr

Upstream: https://github.com/pbcquoc/vietocr — commit `fe8c3a7fc714aec57ab81cec844eb3adf0c1636c`
(version 0.3.13), MIT licensed (`vietocr/LICENSE`). Only `.git/`, the README image
samples and the getting-started notebook were dropped; the package and its `config/`
YAMLs are unmodified.

It is the OCR **fallback recognizer**: `document_intelligence/ocr/engines.py` runs it
over EasyOCR's detected line boxes when EasyOCR's own mean recognition confidence
falls below `OCR_FALLBACK_CONFIDENCE_MIN`.

The PyPI release hard-pins `pillow==10.2.0`, which is unsatisfiable alongside
pdfplumber's `Pillow>=12.2`, so it is installed from this checkout without its
declared dependencies (they are declared in `apps/backend/pyproject.toml` instead):

```bash
pip install --no-deps -e apps/backend/vendor/vietocr   # from the repo root
```

The Docker image (build context `apps/backend`) copies this directory to `/opt/vietocr`, installs it the same way and
sets `VIETOCR_CONFIG_DIR=/opt/vietocr/config`.

Upstream's `Cfg.load_config_from_name()` downloads both YAML configs from vocr.vn at
construction time; the engine reads `config/base.yml` + the architecture file from this
checkout instead so a worker never depends on that host mid-request. The recognizer
checkpoint is resolved the same way — `VIETOCR_WEIGHTS` if set (baked into the image),
otherwise downloaded once into `~/.cache/cabqp/vietocr/`.
