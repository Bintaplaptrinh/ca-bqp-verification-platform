# Contributing

## Workflow

1. Checkout `develop`.
2. Pull latest changes.
3. Create a branch: `feature/SCRUM-<id>-<short-name>` or `fix/SCRUM-<id>-<short-name>`.
4. Implement the task.
5. Run local tests and lint.
6. Push the branch.
7. Open a Pull Request against `develop`.
8. Request a teammate review.
9. Merge only after CI passes and the PR is approved.

## Before opening a Pull Request

```bash
docker compose config
docker compose up --build
curl http://localhost:8000/health
make test
```

From `apps/backend/`, if working outside Docker:

```bash
./.venv/Scripts/python -m ruff check .
./.venv/Scripts/python -m pytest
```

## Conventions

- Branch naming: lowercase, hyphen-separated, tied to a Jira ticket (`feature/SCRUM-7-project-bootstrap`). Avoid vague names like `test`, `new`, `final`.
- Commit messages: [Conventional Commits](https://www.conventionalcommits.org/) (`feat(...)`, `fix(...)`, `chore(...)`, `docs(...)`, `test(...)`, `ci(...)`).
- Never push directly to `main` or `develop`.
- Never commit secrets, `.env`, or production/real data — only `.env.example` is committed.
