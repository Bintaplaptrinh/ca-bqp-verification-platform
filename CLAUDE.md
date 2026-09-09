# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`ca-bqp-verification-platform` — a platform for unit-based verification and scope identification under Bộ Công an (BCA) / Bộ Quốc phòng (BQP). The repository is currently in **Sprint 0 (SCRUM-7: Project Bootstrap)**: only the directory skeleton exists. There is no backend code, Docker setup, or CI yet — those are separate subtasks not yet implemented. Do not build OCR, NER, PhoBERT, fuzzy/semantic matching, Master Unit Registry logic, decision rules, or eligibility logic; those are explicitly out of scope until later tickets.

The full bootstrap plan, including target repo structure, Docker/CI requirements, and the agent operating protocol below, lives in [SCRUM-7_Project_Bootstrap_Plan_AGENT_READY_v3.md](SCRUM-7_Project_Bootstrap_Plan_AGENT_READY_v3.md) — treat it as the source of truth for Sprint 0 work and re-read it before starting a new subtask.

## Repository structure

```
apps/backend/src/cabqp/     # Python backend package (FastAPI, to be bootstrapped in SCRUM-26)
    modules/                 # business module boundaries — cases, registry, document_intelligence,
                              # resolution, decisioning, review, audit (all empty; do not implement early)
    shared/                   # cross-module shared code
apps/backend/tests/          # backend tests (pytest)
apps/web/                    # frontend web app (not started)
workers/                     # background/async workers (not started)
pipelines/registry_ingestion/, synthetic_data/, ml/   # data/ML pipelines (not started)
contracts/api/, contracts/data/                        # API and data contracts
datasets/manifests/, datasets/samples/                 # dataset manifests and samples
docs/business/, docs/architecture/, docs/data/         # documentation
deploy/, infra/, ops/         # deployment, infrastructure, operations (not started)
.github/workflows/            # CI (not started)
```

Module directories under `apps/backend/src/cabqp/modules/` are intentional empty boundaries — do not scaffold implementation code into them ahead of the corresponding Jira ticket.

## Planned commands (not yet functional)

These are defined in the bootstrap plan for when SCRUM-26/27/28/29 land; do not assume they exist until the corresponding files (`Dockerfile`, `compose.yaml`, `pyproject.toml`, `Makefile`) are actually created:

```bash
docker compose up --build     # start backend + PostgreSQL + Redis
make up / down / logs / test  # Makefile wrappers around docker compose
pytest                        # run backend tests (inside apps/backend)
curl http://localhost:8000/health   # health check, expects {"status": "ok", "service": "ca-bqp-backend"}
```

## Git workflow (binding for Sprint 0)

- Branch model: `main` ← `develop` ← `feature/SCRUM-<id>-<name>` / `fix/SCRUM-<id>-<name>`.
- **All of SCRUM-7's subtasks (SCRUM-24 through SCRUM-31) share a single branch: `feature/SCRUM-7-project-bootstrap`.** Do not create per-subtask branches.
- One PR for the whole SCRUM-7 parent ticket, targeting `develop`, titled `[SCRUM-7] Bootstrap repository and local development environment`.
- Never push directly to `main` or `develop`.
- Commit convention: Conventional Commits (`feat(api): ...`, `chore(repo): ...`, `test(api): ...`, `docs(readme): ...`, `ci(github): ...`). Never use vague messages like `update`, `fix`, `final`.

## Agent operating protocol for this repo

This repo's plan document defines a strict process for how an agent must work across Jira + GitHub. Key rules to follow:

- **Stay in scope.** Never implement business logic (OCR, NER, registry resolution, decisioning, eligibility) under SCRUM-7. Never expand architecture beyond the plan, and never add a dependency without flagging it.
- **Track Jira status honestly.** Subtasks move `To Do → In Progress` when started, `In Progress → In Review` when implementation + validation + tests pass, and only to `Done` after the PR is reviewed, CI passes, and it's merged into `develop`. Never self-declare a subtask `Done`, never treat a PR as approved or CI as passing without confirmation, and never merge `main`/`develop` yourself.
- **Work subtasks in order, one at a time**, grouped into 5 work packages (see the plan doc §17): WP1=SCRUM-24, WP2=SCRUM-25+26, WP3=SCRUM-27+28, WP4=SCRUM-29+30, WP5=SCRUM-31. Do not move multiple subtasks to `In Progress` simultaneously.
- **Never commit secrets, `.env`, or production/real data.** Only `.env.example` is committed.
- **End every work session with a completion report** covering: what was completed, files changed, validation performed, required Jira updates, and the next Git/GitHub action — never end with just "done".
- **On a blocker**, stop at the blocked boundary and report: the issue, its impact, what's completed, what remains, the Jira comment to post, and whether status should change — don't push past it.
