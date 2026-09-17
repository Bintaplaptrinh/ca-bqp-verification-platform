.PHONY: local local-stop local-status up down logs migrate seed test golden lint type security api web e2e migration-drill release-check

# Local profile: PostgreSQL only, no Docker. See ops/local.py.
local:
	conda run -n bqp python ops/local.py start

local-stop:
	conda run -n bqp python ops/local.py stop

local-status:
	conda run -n bqp python ops/local.py status

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f backend worker web

migrate:
	cd apps/backend && alembic upgrade head

seed:
	PYTHONPATH=apps/backend/src python apps/backend/scripts/seed.py
	PYTHONPATH=apps/backend/src python apps/backend/scripts/seed_accounts.py

test:
	cd apps/backend && pytest -q

golden:
	cd apps/backend && pytest -q tests/test_golden_suites.py

lint:
	cd apps/backend && ruff check src tests scripts

type:
	cd apps/backend && mypy src

security:
	cd apps/backend && bandit -q -r src && pip-audit --strict

migration-drill:
	./ops/scripts/migration_rollback_drill.sh

release-check:
	python ops/scripts/validate_release.py

api:
	cd apps/backend && uvicorn cabqp.main:app --reload

web:
	cd apps/web && npm install --no-audit --no-fund && npm run dev

e2e:
	cd apps/web && npx playwright test
