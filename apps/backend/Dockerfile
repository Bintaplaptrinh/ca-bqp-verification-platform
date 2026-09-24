FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    HF_HOME=/models \
    HOME=/models \
    PADDLE_PDX_CACHE_HOME=/models/paddlex \
    EASYOCR_MODEL_DIR=/models/easyocr \
    USE_TF=0 \
    USE_TORCH=1 \
    RESOLVER_CALIBRATION_PATH=/app/artifacts/resolver_calibration.json

WORKDIR /app

# git is a build requirement, not an afterthought: `passwordgen` is pinned to a
# git+https source in pyproject.toml (the PyPI name is an unrelated project), and
# pip resolves a VCS requirement by shelling out to `git clone`. python:3.11-slim
# ships without it, so the dependency install below fails outright when it is missing.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git libmagic1 libgl1 libglib2.0-0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system cabqp \
    && useradd --system --gid cabqp --home-dir /app --shell /usr/sbin/nologin cabqp

# Dependency install and the model bake only need the dependency list and bake_models.py,
# not the application source (`pip install .` needs `src/` present because packages are
# discovered there, so the *package itself* is installed in the second RUN below, after
# COPY src). Copying just these first means an edit anywhere else (src/, other scripts,
# migrations, config) reuses this layer's cache instead of re-running pip install and
# re-downloading every OCR/embedding model.
COPY pyproject.toml ./
COPY scripts/bake_models.py ./scripts/bake_models.py
# The VietOCR fallback recognizer is vendored rather than installed from PyPI: the
# published sdist hard-pins pillow==10.2.0, which pdfplumber's Pillow>=12.2 rules out.
# Installing the checkout with --no-deps takes the code without the pin; its actual
# runtime requirements are declared in pyproject.toml.
COPY vendor/vietocr /opt/vietocr

# Build is the only networked model-fetch phase. A failed model bake fails the image build.
# torch arrives only via sentence-transformers and this service runs inference on CPU
# (see ocr/engines.py and bake_models.py). Installing it from the CPU index first keeps
# pip from pulling ~3.5GB of unused CUDA wheels into the image.
ENV PIP_DEFAULT_TIMEOUT=180 \
    PIP_RETRIES=10
# The pip cache is mounted from the BuildKit cache store, not baked into a layer, so it
# survives across builds without adding bytes to the final image. That matters here
# because the dependency set (torch, paddlepaddle, paddleocr, ...) runs several GB and a
# `docker builder prune` or a fresh Docker Desktop install otherwise means re-downloading
# all of it from scratch every time.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --index-url https://download.pytorch.org/whl/cpu torch \
    && python -c "import tomllib,subprocess,sys; deps=tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']; subprocess.check_call([sys.executable,'-m','pip','install',*deps])" \
    && pip install --no-deps /opt/vietocr \
    && mkdir -p /models \
    && python scripts/bake_models.py

# Everything below changes far more often than dependencies do; putting it in its own
# layer keeps a source-only edit from invalidating the (slow) install above. All
# dependencies are already installed, so this is a metadata-only install (no wheels
# downloaded, no version resolution).
COPY src ./src
COPY config ./config
COPY alembic.ini ./
COPY migrations ./migrations
COPY scripts ./scripts
COPY artifacts ./artifacts
COPY bootstrap ./bootstrap
RUN pip install --no-cache-dir --no-deps . \
    && chown -R cabqp:cabqp /app /models

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
    EASYOCR_DOWNLOAD_ENABLED=false \
    EMBEDDING_LOCAL_FILES_ONLY=true \
    EMBEDDING_MODEL_NAME=/models/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 \
    VIETOCR_WEIGHTS=/models/vietocr/vgg_transformer.pth \
    VIETOCR_CONFIG_DIR=/opt/vietocr/config \
    VIETOCR_DOWNLOAD_ENABLED=false
# The fallback recognizer's checkpoint and YAML configs are baked into the image, so
# a worker never reaches vocr.vn mid-request.

USER cabqp
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3).read()" || exit 1
CMD ["uvicorn","cabqp.main:app","--host","0.0.0.0","--port","8000"]
