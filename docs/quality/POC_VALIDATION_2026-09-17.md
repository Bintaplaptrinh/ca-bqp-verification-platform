# POC Validation — 2026-09-17

Environment: Linux, conda env `bqp`, PostgreSQL 18 on port 5433 (`ops/local.py`'s
dedicated cluster). `RUNTIME_PROFILE=local`. Docker is **not installed on this
machine**.

This session replaced the external identity provider with in-product accounts,
added a permission model an administrator edits per account, and added a local
runtime profile that needs PostgreSQL and nothing else. It supersedes nothing in
`VALIDATION_REPORT.md` (2026-09-16), which records a different session.

## Executed for real in this session

| Check | Command | Result |
|---|---|---|
| Backend suite, SQLite | `pytest -q` from `apps/backend` | **275 passed, 4 skipped** |
| Backend suite, real PostgreSQL | same with `DATABASE_URL` at `cabqp_pytest` | **279 passed, 0 skipped** |
| Lint | `ruff check src tests scripts` | **All checks passed** |
| Frontend typecheck + build | `npm run build` | clean |
| Browser E2E | `npx playwright test` | **13 passed** |
| Readiness | `GET /health/ready` | `ready` — database ok, object_storage ok, identity ok, task_queue inline |

The 4 SQLite skips are exactly the Postgres-only audit append-only trigger tests;
they pass under PostgreSQL, which is what the second row shows.

## Verified end-to-end against the running system

Recorded from live HTTP calls, not from source reading:

- **Login and enforcement.** `admin`/`admin` and `user`/`user` both sign in. The
  `user` account receives **403** from `/admin/users`, `/admin/registry/units`,
  `/admin/audit` and `/reviews`. A wrong password and a fabricated bearer token
  both return **401**.
- **Account issuing.** `POST /admin/users` with `{display_name: "Nguyễn Thị Thẩm",
  personal_code: "BQP-2026-1180", birth_year: 1990, rank: "Thiếu tá", …}` issued
  `bqp20261180` with a 12-character random password and
  `must_change_password: true`. That account then signed in with exactly that
  password.
- **Permissions are live, not baked into the token.** The new account got 403
  from `/reviews`; after the administrator applied the reviewer preset it got
  **200 on the same open session, with no re-login**; after the preset was
  revoked it went back to 403; after deactivation `/auth/me` returned **401**.
- **Text verification.** "Bệnh viện 19-8" → `organization_type: BCA`,
  `resolution_status: MATCHED`, `match_method: CANONICAL_EXACT`,
  `registry_version: 2026.09-curated-registry`.
- **Abstention holds.** A fabricated unit name → `UNKNOWN` / `NOT_FOUND` /
  `NEED_REVIEW`. It was not forced to `OTHER`.
- **File upload through the local profile.** `ho_so_text.pdf` → 202
  `DISPATCH_REQUESTED`, parsed at 0.98 confidence by the in-process runner, split
  into two subject Cases, one resolving to `Cục Cảnh sát giao thông` (BCA). The
  original landed at
  `.local/documents/case_<id>/<sha256>_ho_so_text.pdf`.
- **OCR path.** `bca_sample_image.jpg` → parsed at 0.93, extracted
  `LÊ DUY TÂN`, and abstained to `AMBIGUOUS`/`NEED_REVIEW` rather than picking a
  candidate.
- **Case scoping.** The `user` account saw 22 of its own cases where `admin` saw
  all 29.

## Seed data

`ops/local.py init` loaded **2,077 `APPROVED` units** from
`artifacts/registry/published/master_units_registry.csv` (2,541 rows total; 464
skipped as not `APPROVED`, honouring the CSV's own `qa_status`), plus
official-scope policy metadata and the two delivered accounts.

## Not verified here — stated rather than implied

- **The Docker profile is unverified on this machine.** Docker is not installed.
  `compose.yaml` parses and the Keycloak service, its realm mount and the
  frontend's Keycloak build args were removed, but the stack has not been built
  or run since that change.
- **`admin`/`admin` and `user`/`user` are well-known development credentials.**
  The seeder prints a warning and refuses to run under `APP_ENV=production`
  without `SEED_ALLOW_PRODUCTION=true`, but they remain unsuitable for anything
  reachable by other people.
- **The browser E2E suite writes to the live local database.** It creates
  accounts, cases and reviews on every run. Expected for a POC; it does mean the
  database accumulates test rows, and that repeated runs leave several accounts
  named "Phạm Thị Kiểm Thử".
- **No calibration refit.** `resolver_calibration.json` is unchanged from the
  ported baseline and is still fit on synthetic mention-noise, not on labeled
  production validation data.
- **Session lifetime is fixed at 12 hours** (`SESSION_HOURS`) with no sliding
  renewal and no refresh token. Expired sessions require signing in again.
- **No TLS, no rate limiting in the local profile**, and `ANTIMALWARE_ENABLED` is
  off there. `Settings.production_guards` refuses to start a production
  deployment in that shape, but the local POC does run that way.
- Everything the prior report deferred (organisation-approved registry/policy
  publication, external observability, measured release gates) remains deferred.

## Security note on the permission model

The property the design rests on: **the session token carries no claims.** It is
32 random bytes; the server stores only its SHA-256 and re-reads the account's
permissions from `app_users` on every request.

That is what makes the frontend's menu-hiding purely cosmetic rather than
load-bearing. A caller who edits client state, rebuilds the bundle, or skips the
UI entirely gains nothing — `test_local_auth.py`'s
`test_default_user_cannot_reach_administration` drives the real HTTP surface to
pin that, and the revoke/deactivate behaviour above was confirmed live.
