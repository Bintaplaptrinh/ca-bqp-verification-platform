# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`ca-bqp-verification-platform` — a platform for unit-based verification and scope identification under Bộ Công an (BCA) / Bộ Quốc phòng (BQP). The repository is early-stage: a FastAPI backend skeleton with a single health endpoint, plus a local Docker Compose stack (Postgres, Redis, backend). Everything else (web frontend, workers, pipelines, CI) is an empty directory boundary, not yet implemented. Do not build OCR, NER, PhoBERT, fuzzy/semantic matching, Master Unit Registry logic, decision rules, or eligibility logic into this skeleton — those are separate, later pieces of work and are out of scope for foundational/bootstrap changes.

## Commands

### Docker (full local stack)

```bash
cp .env.example .env
docker compose up --build          # starts postgres, redis, backend
docker compose config -q           # validate compose.yaml without starting anything
curl http://127.0.0.1:8000/health  # expect {"status": "ok", "service": "ca-bqp-backend"}
docker compose down                # stop and remove containers/network
```

`backend` only starts once `postgres` and `redis` report healthy (`condition: service_healthy` in `compose.yaml`). The same lifecycle is wrapped in the `Makefile` at the repo root: `make up`, `make down`, `make logs`, `make config`, `make test` (runs `pytest` inside the running `backend` container, so the stack must already be up).

### Backend, without Docker

All commands run from `apps/backend/`, using a local virtualenv:

```bash
# from apps/backend/
python -m venv .venv
./.venv/Scripts/pip install -e ".[dev]"      # or: pip install fastapi "uvicorn[standard]" pytest httpx ruff
./.venv/Scripts/python -m pytest             # run all tests (pythonpath=src is set in pyproject.toml)
./.venv/Scripts/python -m pytest -v tests/test_health.py::test_health_returns_ok   # run a single test
./.venv/Scripts/python -m ruff check .       # lint (same check CI runs)
./.venv/Scripts/python -m uvicorn --app-dir src cabqp.main:app --reload --port 8000  # run the dev server
```

### CI

`.github/workflows/ci.yml` runs on PRs/pushes to `main`/`develop` with two jobs: `backend` (install `.[dev]`, `ruff check .`, `pytest`, all from `apps/backend/`) and `docker` (`docker compose config -q`, `docker compose build`). Match these locally before pushing.

## Architecture

The backend is a `src/`-layout Python package (`cabqp`) installed under `apps/backend/`:

- `apps/backend/src/cabqp/main.py` — FastAPI app instance; wires routers in via `app.include_router(...)`.
- `apps/backend/src/cabqp/api/` — HTTP route modules (currently just `health.py`), each exposing an `APIRouter` that `main.py` includes.
- `apps/backend/src/cabqp/modules/` — business module boundaries: `cases`, `registry`, `document_intelligence`, `resolution`, `decisioning`, `review`, `audit`. These are intentionally empty placeholders reserved for future domain logic — do not scaffold implementation into them ahead of the work that actually needs them.
- `apps/backend/src/cabqp/shared/` — cross-module shared code (also currently empty).
- `apps/backend/tests/` — pytest tests; `pythonpath = ["src"]` in `pyproject.toml` lets tests `import cabqp` without an editable install.
- `apps/backend/Dockerfile` — builds the image via `pip install .` against `pyproject.toml` (not editable install; see Windows/path note).

`compose.yaml` at the repo root wires `postgres` (16-alpine), `redis` (7-alpine), and `backend` together for local development; `.env.example` documents the environment variables each service reads (`APP_ENV`, `BACKEND_HOST`, `BACKEND_PORT`, `POSTGRES_*`, `REDIS_*`). Copy it to `.env` before running Docker Compose — `.env` is gitignored and must never be committed.

Outside the backend, these top-level directories exist as reserved boundaries with no code yet: `apps/web/` (frontend), `workers/` (background/async workers), `pipelines/registry_ingestion/`, `pipelines/synthetic_data/`, `pipelines/ml/` (data/ML pipelines), `contracts/api/`, `contracts/data/` (API/data contracts), `datasets/manifests/`, `datasets/samples/`, `docs/business/`, `docs/architecture/`, `docs/data/`, and `deploy/`, `infra/`, `ops/`. Each has only a README or `.gitkeep` — treat them as placeholders to fill in when the corresponding feature work begins, not as an invitation to design their contents speculatively now.

## Windows/path note

The repository path contains non-ASCII characters (`Chuyên-đề`). `pip install -e .` (editable install) fails on Windows with a `UnicodeEncodeError` from setuptools' `.pth` file writer under this path. Install dependencies directly instead (`pip install fastapi uvicorn pytest httpx`) rather than an editable install of the local `cabqp` package when working outside Docker; `pythonpath = ["src"]` in `pyproject.toml` makes the package importable for tests without it. This does not affect the Docker build, since the build context inside the container has no such path.
