# Backend E2E implementation

Frontend (`apps/web`) is integrated as the single role-aware Internal Portal; backend remains the authority for security and business decisions.

Runtime critical path:

`Text/File -> Case -> Parser/OCR -> Extraction -> CURRENT_WORK_UNIT -> Registry Resolver -> BCA/BQP/OTHER/UNKNOWN -> Subject Group -> Policy Engine -> Human Review -> Evidence/Audit`.

## Invariants implemented
- NOT_FOUND is UNKNOWN, never silently OTHER.
- CURRENT_WORK_UNIT is separated from former-unit mentions.
- Only APPROVED active Registry records can auto-resolve.
- Reviewer corrections do not mutate production Registry; alias feedback becomes a pending RegistryCandidate.
- Policy does not infer subject group from organization name.
- Published Registry versions are explicit and auditable.

## Runtime profiles

`RUNTIME_PROFILE=local` — PostgreSQL only. Documents are stored on disk and the
API process runs the tasks itself against the `outbox_events` table.

`RUNTIME_PROFILE=docker` — PostgreSQL 16, Redis 7, MinIO, ClamAV, FastAPI backend,
Celery worker/beat, Nginx frontend and Prometheus.

## Start (local profile)
```sh
conda run -n bqp python ops/local.py start
```
Starts PostgreSQL on port 5433, migrates, seeds the registry and accounts, then
runs the API and web dev server.

## Start (docker profile)
1. `cp .env.example .env`
2. `docker compose up -d --build`
3. Compose runs one-shot `migrate` then `seed` jobs before backend/worker.
4. Open `http://localhost:3000` for the portal or `http://localhost:8000/docs` for OpenAPI.

## Accounts
Accounts live in this platform's own database. The seeder
(`apps/backend/scripts/seed_accounts.py`) creates the single administrator
(`admin`/`admin`) and the default tra cứu account (`user`/`user`); an
administrator issues every other account in the product. Change both passwords
before any shared deployment.
