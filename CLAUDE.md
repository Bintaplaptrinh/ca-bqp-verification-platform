# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project scope

`ca-bqp-verification-platform` is an end-to-end internal verification / decision-support platform for CA/BQP workflows. The production direction is defined by `Ke_hoach_E2E_CA_BQP_PRODUCTION_QUALITY_2026.md` and the implementation notes under `docs/architecture/`.

Core flow:

`Text/File -> Case -> Parser/OCR -> Entity + CURRENT_WORK_UNIT extraction -> Master Unit Registry resolution -> BCA/BQP/OTHER/UNKNOWN -> Subject Group -> Policy/Eligibility Engine -> Human Review when needed -> Evidence/Audit/Export`

Do not remove or bypass the following invariants:

- `NOT_FOUND != OTHER`.
- Unit membership does not by itself prove the subject belongs to a force/personnel group.
- If several organizations appear, resolve `CURRENT_WORK_UNIT`, not the first organization mention.
- A name that resolves to units in more than one organization is `AMBIGUOUS`, never a pick. Distinct places can also collide after diacritic folding (`Phú Hữu` / `Phú Hựu`), so same-organization collisions abstain too.
- Policy rules are deterministic, versioned, effective-dated and must return `INSUFFICIENT_DATA` when required facts are missing.
- Crawler/reviewer feedback never writes directly to the active production registry; it goes through candidate/QA/version publish flow.
- Results must preserve evidence and independent versions: registry, taxonomy, parser, model, policy, threshold.
- Synthetic outputs must be explicitly labeled `SYNTHETIC_DEMO`.
- Prefer abstention / `NEED_REVIEW` to a forced low-confidence decision.
- A failed quality gate must never be reported alongside a high confidence score. Downstream routing compares the score against a threshold, so the two have to agree.

## Commands

### Running the platform locally (the default on this machine)

```bash
conda run -n bqp python ops/local.py start   # postgres + migrate + seed + api + web
conda run -n bqp python ops/local.py status  # includes /health/ready checks
conda run -n bqp python ops/local.py stop    # stops app processes, leaves postgres up
```

`ops/local.py` owns the local profile end to end: it starts a dedicated
PostgreSQL 18 cluster on **port 5433** (data under `~/.local/share/cabqp/postgres`
— the system cluster on 5432 does not grant this user database-creation rights,
and the project volume does not satisfy PostgreSQL's directory-permission
check), writes the repo-root `.env` with a generated password on first run,
applies migrations, seeds the registry and the two delivered accounts, then
starts uvicorn and Vite. Logs land in `.local/backend.log` / `.local/web.log`.

It injects the root `.env` into every child's environment explicitly rather than
relying on pydantic's relative lookup: alembic and the seed scripts run with
`apps/backend` as their working directory, where a relative `.env` does not
resolve. Same reason `USE_TF=0 USE_TORCH=1` is set there — importing
`transformers` fails against the stale TensorFlow install otherwise. Because
those values become *real* environment variables, which outrank pydantic's own
`.env` reading and are never unquoted by it, `read_env_file()` strips one layer
of matching surrounding quotes itself — otherwise a quoted
`GMAIL_APP_PASSWORD="abcd efgh ijkl mnop"` reaches Gmail with its quotes
attached and every credential/OTP mail fails with `SMTPAuthenticationError`.

`Makefile` targets mirror what CI runs:

```bash
make local             # ops/local.py start
make up                # docker compose up -d --build
make down / make logs
make migrate           # alembic upgrade head
make seed              # load the registry snapshot + policy metadata
make test              # backend suite
make golden            # golden regression suites only
make lint type security
make migration-drill   # upgrade / seed / downgrade / re-upgrade
make api               # uvicorn with reload
make web               # npm install && vite dev
```

Backend work happens from `apps/backend`:

```bash
pip install -e '.[dev]'
python -m pytest -q
python -m pytest -q tests/test_golden_suites.py::test_golden_clean_exact_code_and_canonical_name   # single test
python -m ruff check src tests scripts
python -m mypy src
```

`tests/conftest.py` points `DATABASE_URL` at a **file-backed** SQLite database in a
per-run temp directory and disables auth, embeddings, antimalware and rate
limiting, so `pytest` needs no setup. It is file-backed rather than `:memory:`
because the API now reads accounts and sessions through the process-wide
`SessionLocal`, and an in-memory SQLite database is not shared across the
connections a TestClient request goes through. Most tests still build their own
isolated engine and never touch it; those that need the app schema depend on the
`app_database` fixture.

Point `DATABASE_URL` at PostgreSQL to also exercise the tests skipped without it
(the audit append-only triggers) — `pytest -q` reports **376 passed, 5 skipped**
under SQLite and **380 passed, 1 skipped** under real Postgres; 4 of those skips are
exactly the append-only trigger tests, and the fifth needs real row locking
(`test_bulk_job_finalisation.py`'s lost-update race), which SQLite does not provide
either.

Frontend (`apps/web`): `npm run typecheck`, `npm run build` (build runs typecheck first), `npm run dev`. E2E: `npx playwright test` (or `npm run e2e`) runs `apps/web/e2e/*.spec.ts` against a real running backend + `npm run dev`. There is **no dev-login bypass any more**: every spec signs in through the real form via `e2e/helpers.ts`'s `signInAs()`, using the seeded `user`/`admin` accounts. `signInAs(page, 'REVIEWER')` provisions an `e2e_reviewer` account through the real admin API first, because reviewing is a permission set an administrator grants rather than a role that ships switched on. These specs write to the live local database (accounts, cases, reviews), which is expected for a POC but means the database accumulates test rows. `playwright.config.ts` pins `workers: 1`: a `--reload` dev-mode uvicorn process cannot serve concurrent `POST /cases/text` calls fast enough for the default multi-worker parallelism, and specs will time out (not fail assertions) at higher concurrency. Playwright is a devDependency (`@playwright/test`); run `npx playwright install chromium` once per machine to fetch the browser binary.

### Host development without rebuilding the backend image

On this machine the local profile above already runs everything on the host, so
this section only matters when reproducing the Docker profile. The `bqp` conda
environment has the whole AI stack installed (paddlepaddle/paddleocr/torch/
sentence-transformers), so a source edit can be tested by restarting `uvicorn`
directly rather than paying for `docker compose build backend`, which reinstalls
the full dependency set and bakes OCR/embedding models. Keep Docker for infra
only: `docker compose up -d postgres redis minio` (add `clamav` only if the
change under test needs it), then run migrate/seed/uvicorn/celery against
`localhost` ports. Note that Docker is **not installed on this machine**, so the
Docker profile is unverified here — `compose.yaml` parses, but it has not been
built or run since the Keycloak removal. Both the
worker and uvicorn need `USE_TF=0 USE_TORCH=1` in their environment or importing
`transformers` raises `RuntimeError: Failed to import transformers.modeling_tf_utils`
from a stale TensorFlow install; Celery on Windows also needs `--pool=solo`
(the default prefork pool doesn't work there). `docker.io/minio/minio` now rejects
anonymous pulls entirely (not just a missing tag) — `compose.yaml` pulls
`quay.io/minio/minio` instead. The backend image's apt layer must keep `git`:
`passwordgen` is pinned to a `git+https://` source in `pyproject.toml` (the PyPI
name is an unrelated project), and pip resolves a VCS requirement by shelling out
to `git clone`, which `python:3.11-slim` cannot do on its own.

Editable-install the backend from the correct checkout before trusting any host-run
server: `pip show cabqp` can silently point at a *different* sibling clone of this
project on the same machine (its `Editable project location` line) if `pip install
--no-deps -e .` was last run from there. A server bound to the wrong checkout still
answers requests successfully, it just runs stale/different code — `pip install
--no-deps -e .` again from *this* `apps/backend` fixes it. `--reload` also does not
reliably pick up every change under Windows/WatchFiles; if a fix "isn't taking
effect" over HTTP, compare the running process's start time (`wmic process where
"ProcessId=<pid>" get CreationDate`) against the file's mtime and restart uvicorn/
Celery outright rather than trusting the auto-reload.

On Windows, `curl`'s mingw build (`/mingw64/bin/curl` in Git Bash) can mangle
non-ASCII characters passed via `-d '...'` on the command line even though the raw
bytes look correct through a pipe (`echo -n ... | xxd`); a Vietnamese `unit_name`
sent this way can silently resolve as if it were a different, ASCII-adjacent
string. Prefer a short Python script with `httpx`/`requests` (`json=` sends UTF-8
correctly) over `curl -d` for any manual API test that includes Vietnamese text.

## Repository architecture

- `apps/backend/src/cabqp/api/` — thin FastAPI routers under `/api/v1`; every route declares `require_perms(...)` (or `current_principal` for reads that then scope themselves). `GET /cases/{id}` returns `extracted` (the `ExtractedRecord` row: `subject_name`, `subject_code`, `position`, `current_unit_raw`, `former_units`) alongside `case` and `result` — use that field rather than parsing `result.evidence` for what the pipeline pulled out of the document. Routers: `auth.py` (login/logout/me/change-password), `admin_users.py` (account administration), `cases.py`, `bulk.py`, `reviews.py`, `admin_registry.py` (Unit Registry admin/QA/versions), `admin_person_registry.py` (Person Registry admin/QA/versions — mirrors `admin_registry.py`'s endpoint shape one-for-one), `lookup.py` (`POST /lookup/unit`, a thin wrapper over the unit `Resolver` used by the frontend's live-lookup UI), `audit.py`, `health.py` (`/health`, `/health/live`, `/health/ready` — readiness only checks what the active profile actually uses: Redis is checked under `QUEUE_BACKEND=celery` only, and "identity" is the presence of an administrator account, not an external discovery document).
- `apps/backend/src/cabqp/modules/` — domain services: `auth`, `cases`, `document_intelligence`, `registry` (Unit Registry), `resolution` (unit-name Resolver), `person_resolution` (identity resolver — see below), `subject_group`, `decisioning`, `review`, `bulk`, `audit`.
- `apps/backend/src/cabqp/modules/person_resolution/` — a second, parallel registry+resolver for **people**, structurally independent from the Unit Registry (`registry`/`resolution`). `service.py`'s `PersonResolver` resolves `full_name`/`personal_code` (optionally narrowed by `birth_year`/`unit_id`) to a `canonical_unit_id` — it is explicitly identity-only and never decides `organization_type` itself; `cases/service.py`'s `process_case` always re-resolves that `canonical_unit_id` through the unit `Resolver` so BCA/BQP classification has exactly one authority. `registry_service.py`'s `PersonRegistryService` mirrors the Unit Registry's DRAFT→VALIDATED→APPROVED→PUBLISHED version lifecycle, QA states, and advisory-lock publish — independently versioned from the unit registry.
- `apps/backend/src/cabqp/modules/document_intelligence/` — parsing, OCR, extraction, quality gating, and multi-subject splitting all live here (not at a top-level `cabqp/ocr/` — that path does not exist). Key files: `parsers.py`, `extraction.py`, `quality.py`, `router.py` (routing decisions), `subject_split.py` (see below), `table.py`, `file_validation.py`, `antimalware.py`, `storage.py`, `limits.py`, and the `ocr/` subpackage (`engines.py`, `preprocess.py`, `pipeline.py`, `base.py`).
- `apps/backend/src/cabqp/workers/` — Celery tasks. `celery_app.py` must keep `include=["cabqp.workers.tasks"]`; without it the worker registers no tasks and silently discards every message. Task routing also matters independently of that: `task_routes` sends `process_document`/`dispatch_outbox_event`/`process_bulk_job`/`process_bulk_row` to named queues (`documents`, `outbox`, `batch`), so a worker started without `-Q celery,outbox,documents,batch` accepts the default queue only and silently drops everything routed elsewhere — uploads then sit at `RECEIVED` forever with no error. A Celery Beat process is also required (`celery -A cabqp.workers.celery_app beat`) for `dispatch_pending_outbox`/`reconcile_bulk_jobs`, which is what durably retries dispatches that failed the first immediate attempt.
- `pipelines/registry_ingestion/` — offline crawl/extract/normalize/dedupe/coverage. It shares `cabqp.shared.normalization` so keys never drift between pipeline and runtime.
- `pipelines/synthetic_data/` — synthetic artifacts only; never silently promoted to authoritative data.
- `datasets/samples/` — fixture dossiers with a README describing the expected routing for each.
- `apps/web/src/App.tsx` is a thin auth-gate: it calls `fetchCurrentUser()` on boot, renders the username/password `LoginPage` when signed out, prompts `ChangePasswordPage` when the account still holds an administrator-issued password (a prompt, not a gate — nothing server-side depends on it), and otherwise renders `<VerificationModule user={user} onLogout={logout} />`. Keep it exactly this thin — a prior regression had it importing a `./pages/*` router tree (`Dashboard`/`Lookup`/`Cases`/`Reviews`/`Admin`/`PersonAdmin`) that does not exist anywhere in this repo or its git history, which broke `npm run build` outright; there is no legitimate reason for `App.tsx` to import anything under `./pages/`. `components/VerificationModule.jsx` renders `components/CABQPVerification.jsx` (~2.9k lines) — that is the real, actively-served UI, calling the backend directly with `axios` against relative `/api/v1/...` paths (routed by the Vite dev proxy or, in Docker, by Nginx) and pulling in the modal components (`OcrResultModal.jsx`, `DetailedComparisonModal.jsx`, `OriginalDossierModal.jsx`, `HistoryView.jsx`) and the admin screens under `components/admin/` (`ReviewsPage.jsx`, `RegistryAdminPage.jsx`, `PersonRegistryAdminPage.jsx`, `AuditPage.jsx`, `UsersAdminPage.jsx`, reachable from a permission-gated "Quản trị" dropdown in `components/layout/AppNavigation.jsx` — `CABQPVerification.jsx` builds the entry list, each entry is shown when `can(user, P.X)` holds, and the corresponding endpoints re-check the same permission server-side). The shell (header band, tab bar, footer, page title block) lives in `components/layout/`; UI look and copy rules are in `.claude/rules/ui-conventions.md`. `auth.ts`, `types.ts`, `config.ts`, `permissions.ts` are live and imported by this tree; `auth.ts` stores only an opaque session token and exposes `can(user, ...)` for rendering decisions — never treat it as an authorization check; there is no `api.ts`/`hooks.ts` in this repo — do not recreate a separate typed API client without checking whether the JSX tree already calls the endpoint directly via `axios`. `styles.css` only covers the admin pages' non-Tailwind bits and is wrapped in `@layer base` so Tailwind utilities win over it; everything else, including `App.tsx`'s login/boot screens, is styled with Tailwind utility classes directly (`index.css`'s `@import "tailwindcss"` + a `@theme` block pinning Inter/Be Vietnam Pro, Noto Serif and JetBrains Mono). `components/AppErrorBoundary.jsx` exists but is not imported anywhere in the tree — it is not wired to `main.tsx`/`App.tsx` today; do not assume render errors are actually caught by it.
- `CABQPVerification.jsx`'s `handleSearch` calls the real backend (`POST /cases/text` or `/cases/file`, then polls `GET /cases/{id}`) and, on any failure to obtain a usable `case_id`, must surface an error state (`setApiError`/`setAppState('initial')`) — never fabricate a result. A prior regression had a ~160-line client-side fallback that regex-guessed BCA/BQP/OTHER from department/position keywords and returned a plausible-looking but entirely fake verdict (hardcoded scores like `'98.8%'`) whenever the real call didn't return a `case_id`; that fallback violated the platform's abstain-over-guess and SYNTHETIC_DEMO-labeling invariants and has been removed. Do not reintroduce a client-side "offline simulation" branch in this handler.
- `GET /cases` returns `totals` (`all`/`verified`/`need_review`/`out_of_scope`/`no_conclusion`) counted over the caller's whole scoped queue, and `HistoryView.jsx` renders those. Do not go back to counting `items`: that request asks for `page_size=200`, so every summary figure froze at exactly 200 once the queue passed it, and the nav badge with it. They are built so `verified + need_review + out_of_scope + no_conclusion == all`, with `no_conclusion` as the remainder, which only stays non-negative because the other three predicates are mutually exclusive. `workflow_status == 'NEED_REVIEW'` is checked **first** and outranks the resolver's label: a Case a human still owns is never also counted as decided, and counting only `AMBIGUOUS`/`CONFLICT` (as an earlier version did) filed every other abstention — `NOT_FOUND`, a failed parse gate, a low-confidence extraction — under `no_conclusion`. `out_of_scope` is `MATCHED` + `OTHER`: a decided verdict with a resolved unit behind it, kept apart from `no_conclusion` because `NOT_FOUND != OTHER`. The web client derives a row's status through `CABQPVerification.jsx`'s `historyStatusCategory`, which `resolvedStateFromDetail` and `subjectRowStatus` share so a list row, a multi-subject row and the detail screen it opens can never disagree.
- No screen may turn a decided classification into an absent one either: `MATCHED` + `OTHER` is a conclusion with a resolved unit behind it and renders as "Ngoài phạm vi CA/BQP" (`appState: 'out-of-scope'`, `OutOfScopeView`), never as "Không tìm thấy" — that wording is `NOT_FOUND`'s, and `NOT_FOUND != OTHER` holds in the UI too. Equally, `verification_status` from `GET /cases/{id}` follows the decision, not workflow completion: a reviewer who decides `UNKNOWN` closes the Case `COMPLETED` while the result stays `NOT_FOUND`/`UNKNOWN`, which is "Chưa xác định được đơn vị", not "Đã xác định" (`api/cases.py`'s `_verification_status`). It arrives already worded for the operator — render it as given rather than looking it up in a code-keyed label map. `Document.parse_status` labels must key off the values the column actually holds; the DB `CHECK` allows exactly `PENDING`/`PARSED`/`FAILED`, and a map written against `COMPLETED`/`PROCESSING` silently showed every parsed document as unprocessed.

No screen may turn an absent classification into a decided one. `organization_type` defaults to `UNKNOWN`, never `OTHER` (`OTHER` is a verdict the pipeline has to reach, and `NOT_FOUND != OTHER`), an absent `resolution_status`/`workflow_status` stays absent rather than becoming `MATCHED`/`PROCESSED`, and a candidate row with no organization renders `Chưa xác định`. Nothing renders a ministry name from a two-way `isBqp ? 'Bộ Quốc phòng' : 'Bộ Công an'` test either: not-BQP is not automatically BCA. The verified banner used to fall back to guessing BCA/BQP from keywords the operator had typed into the form (`quân`, `bqp`, a `BQP-` prefix) — the same client-side guessing removed from `handleSearch`, and it is gone from there too.
- `OriginalDossierModal.jsx`/`DetailedComparisonModal.jsx` take a `caseDetail` prop that is the literal `GET /cases/{id}` response (fetched by `CABQPVerification.jsx`'s `openCaseModal`), not a synthetic object built from form values — render only fields that exist on that response (`subject`, `documents[].checksum/parse_status/parse_confidence`, `result.top_candidates`, `eligibility[]`). There is no scanned-image endpoint and no backend-side "approve" action for these modals; do not add a decision number, signer title, CCCD number, or match percentage that has no field in the real response, and do not add an approval button unless it calls the real `POST /reviews/{id}/decision`.
- `components/admin/ReviewsPage.jsx` receives `user` (not just `apiBaseUrl`) from `CABQPVerification.jsx` — self-assign/release read `user.username`, the admin-reassign form and unit picker are shown on `user.isAdmin` (and refused independently by `POST /reviews/{id}/assign`). It paginates `GET /reviews` (`page`/`page_size`, backend-sorted oldest-first) with real `Trước`/`Sau` controls; a card's `Case #<id>` fragment must strip the `case_` prefix before slicing (`String(item.case_id).replace(/^case_/i, '').slice(0, 8)`) — slicing the raw id first yields the literal string `CASE_XXX` for every row, a bug this fragment already caused once. `POST /lookup/unit` (used for the CONFIRM-decision unit picker) is a full `Resolver.resolve()` call, not a dedicated autocomplete endpoint — it can take several seconds on a cold cache (embedding model load) and ~2-3s warm; debounce accordingly and don't expect sub-second suggestions.

### Document intelligence

`route_input` decides the strategy before any parsing: PDFs are probed per page (`PDF_TEXT` / `PDF_SCAN` / `PDF_HYBRID`), spreadsheets are profiled into `TABULAR_LIST` (owned by bulk ingestion, one Case per row) or `KEY_VALUE_SHEET` (one dossier). Every upload passes `validate_upload` first — extension allow-list, magic-byte match, Office ZIP path/expansion guards — so the router's unknown-binary branch is only reachable internally. Magic-byte validation only reads the header, though, so a truncated or corrupt PDF still reaches `probe_pdf`; when PyMuPDF cannot open it, that is `DocumentLimitError("INVALID_PDF_DOCUMENT")`, **not** a fallback to `PDF_SCAN`. Every scan path rasterizes through the same library, so the old fallback could never read the file — it only moved the failure into OCR and reported it as an OCR problem. The upload route answers 422 and the worker turns it into an operator-visible `NEED_REVIEW`.

A free-text document (`PLAIN_TEXT`/`DOCX_TEXT`/`PDF_TEXT`) containing more than one `"Họ và tên"`-labeled block is not silently reduced to its first person. `document_intelligence/subject_split.py`'s `detect_subject_blocks` splits it into one block per person and `workers/tasks.py`'s `process_document` fans out into one independent Case per block — mirroring the bulk pipeline's one-Case-per-row pattern, each *sibling* keyed by a stable `f"{document.id}:{block_index}"` idempotency key so retries never duplicate Cases. Block #0 is the Case created synchronously at upload and **keeps the caller's own `Idempotency-Key`** on both fan-out paths; overwriting it with the group key (as the worker path once did) made a client retry carrying the original key match nothing and upload the dossier a second time. Block #0 is therefore recovered as a group member through `evidence.split_source.source_case_id`, which both paths stamp, not through the key prefix — see `api/cases.py`'s `_split_group_key`. OCR/hybrid documents (`OCR`/`PADDLE_OCR`/`PDF_HYBRID`) with multiple name labels are not geometrically split in v1 — bbox-based boundary detection on OCR line order is not trustworthy enough, so the whole document abstains to `NEED_REVIEW` (`MULTIPLE_SUBJECTS_OCR_UNSUPPORTED`) instead of guessing. A detected block with nothing extractable before the next name label likewise abstains (`MULTIPLE_SUBJECTS_AMBIGUOUS_BOUNDARY`) rather than merging into its neighbor. `extract()` itself is never called with more than one person's text and is never modified by this — the split happens before extraction, one call per block. A structured/tabular document (a table with a real personnel-list header) is a *different* path entirely and is rejected from the single-Case upload endpoint with `TABULAR_LIST_REQUIRES_BULK`, redirecting the client to `/api/v1/bulk` — a table that merely lacks visible gridlines (borderless PDF layout) still routes through bulk's table extraction if PP-StructureV3/native table parsing can reconstruct rows from it; a personnel list laid out as one field per line with no reconstructible row/column structure at all is not currently split by anything and stays a single (likely `NEED_REVIEW`) Case.

OCR defaults to EasyOCR's Vietnamese Latin recognizer with exactly one configured fallback (`PaddleOCR` by default). It selects one engine's complete output and never splices or votes on characters. When the two engines disagree on identity fields the gate fails (`parse_quality.critical_disagreement=true`) and confidence drops to zero — this is a deliberate fail-closed path, not a bug: a garbled scan that both engines mis-transcribe differently must abstain, not average the two guesses. EasyOCR/Paddle parameters are settings, not document-specific replacements, and Docker bakes all model assets so runtime remains offline.

PaddleOCR must be constructed with `enable_mkldnn=False` (`document_intelligence/ocr/engines.py`) — the oneDNN CPU backend's PIR runtime raises `NotImplementedError: ConvertPirAttribute2RuntimeAttribute` on this project's detection model on Windows; the plain CPU path has no such gap, and inference does run on a Windows host once that flag is set (`USE_TF=0 USE_TORCH=1` must also be set in the process environment, see Commands above).

`document_intelligence/ocr/preprocess.py`'s `deskew()` measures rotation from Hough line segments only. It used to also average in a `minAreaRect`-based angle over every dark pixel on the page; for a page of several separate text lines that rectangle is just the page's own axis-aligned bounding box, so it returns a meaningless angle (measured exactly 90° on an unrotated multi-line scan) that pulled the average toward a bogus rotation and clipped the start of every line by a growing amount line-by-line. Do not reintroduce a whole-page `minAreaRect` angle; if a skew detector needs to be added, validate it can't fire on a straight multi-line scan first. Likewise `perspective_correct()` only warps when the detected quadrilateral is actually skewed (checked against axis-aligned corners) — a screenshot or flatbed scan's own decorative border box is a straight rectangle that happens to satisfy the "biggest 4-point contour" search, and warping to it crops the true document margin.

Label matching in `extraction.py` (`label_values`, `spatial_key_values`, `_is_label`) scores a scanned label against the `LABELS` aliases with `rapidfuzz.fuzz.ratio` (threshold 75), not exact or substring matching. A real scan drops or garbles individual characters unpredictably — sometimes at the start of the line, sometimes a vowel mid-word ("chc v" for "chức vụ", "CCCO" for "CCCD") — so no fixed-position rule catches every case. `_inline_label_value` also tests short line prefixes when OCR drops the colon or merges label words (`Chucv Chuyenvien`); it preserves the model's raw remaining text and never replaces it with a dossier-specific value. `spatial_key_values` tries this inline form before searching neighboring OCR boxes, preventing the next label from being misattributed as the current value. Explicit `Nhóm đối tượng` values are preserved for the subject-group validator; broad labels such as `BQP` still abstain because they do not distinguish military from cipher personnel. `subject_split.py` reuses this same `LABELS`/`_label_score` machinery for its own boundary detection rather than duplicating the fuzzy-matching threshold — keep the two in sync if `_LABEL_FUZZY_THRESHOLD` changes.

A qualified historical label is its own `LABELS` field (`former_unit_name`: "Đơn vị công tác cũ", "Đơn vị công tác trước đây", "Nguyên đơn vị công tác", ...), never a variant of `unit_name`. At threshold 75 those spellings score ~91 against the `unit_name` aliases, so they used to be read as CURRENT_WORK_UNIT — and because the narrative `CURRENT_MARKERS` branch only runs when nothing was found, the document's real current unit was then dropped entirely. `former_unit_name` is listed *after* `unit_name` so an exact current-unit label still wins the equal-score tie. Narrative extraction cuts both directions at the next marker (`_cut_at_markers`): `_clean_unit` only splits on punctuation, so a scan that lost the sentence break produced a former unit spanning both clauses ("Cục A hiện đang công tác tại Cục B"). `_earliest_marker` picks the first marker mentioned rather than the first one listed, because `hiện đang công tác tại` contains `đang công tác tại` and list order could cut mid-marker.

### Resolution cascade

`TRUSTED_CODE (100) → CANONICAL_EXACT (100) → APPROVED_ALIAS (99) → ASCII_FOLDED (97) → ASCII_FOLDED_ALIAS (96) → fuzzy/BM25/semantic → ABSTAIN`

Folding is the last exact tier: accented spellings always win, and folding only rescues input that would otherwise reach fuzzy matching. `ascii_key` is stored next to `normalized_key` rather than replacing it. Migration `0003` derives its SQL fold map from `unicodedata` — never hand-type parallel translate() strings, they mis-pair silently.

This exact cascade is unit-name resolution (`modules/resolution/service.py`'s `Resolver`). `PersonResolver` (`modules/person_resolution/service.py`) runs a parallel but distinct cascade over person identity: trusted `personal_code` first (ambiguous/conflicting code matches abstain), then the same four exact-name tiers scored identically, then a `rapidfuzz.fuzz.WRatio`-only fuzzy fallback — it has no BM25 or semantic stage and no calibration model, unlike the unit Resolver's hybrid ranking. A `PersonResolution` match only ever yields a `canonical_unit_id`; the unit `Resolver` is re-invoked on that ID to get `organization_type` before any Case can be marked `MATCHED` for BCA/BQP scope.

## Authentication and authorization

Accounts live in this platform's own database. There is no external identity
provider; the Keycloak realm, JWT/JWKS validation and the frontend's dev-login
token minting were all removed.

- `modules/auth/permissions.py` — the catalog. It is the single authority on what
  exists; `normalize()` drops codes not in it, so a permission retired from the
  catalog cannot keep granting access through a stale stored row.
- `modules/auth/service.py` — PBKDF2-HMAC-SHA256 passwords (`pbkdf2_sha256$iter$salt$hash`,
  so the iteration count can be raised without invalidating rows), username
  derivation, and session lifecycle. `enforce_password_policy=False` exists only
  for the seeder installing the documented `admin`/`user` demo credentials —
  never route a person-chosen password through it.
- `modules/auth/dependencies.py` — `current_principal` resolves the caller's
  account **from the database on every request**; `require_perms(...)` checks the
  catalog. `Principal.roles` is a derived projection over `permissions`, kept so
  the audit log's `role` column and older `"ADMIN" in p.roles` reads stay
  meaningful — it is never a second source of authority, and nothing reads roles
  back from the client.

The security property to preserve: **the session token carries no claims.** It is
32 random bytes; only its SHA-256 is stored. Permissions are re-read per request,
so revoking one takes effect on the caller's next call and deactivating an
account ends its live sessions. This is why the frontend's menu-hiding is purely
cosmetic — do not add any check that the client can satisfy on its own, and do
not start encoding permissions into the token "to save a query".

An account's `email` and `personal_code` are unique across accounts, enforced in
two places: `auth/service.py`'s `ensure_identity_available` produces the message
an administrator reads (and the routes answer **409**, not 400), and the unique
indexes added in migration `0008` are the backstop a concurrent second insert
cannot pass. Both are stored normalized — addresses lower-cased, codes
upper-cased (`normalize_email` / `normalize_personal_code`) — which is what makes
the plain index case-insensitive without a database-specific collation; write
through those helpers rather than assigning the raw field. The address rule is a
security property, not tidiness: the issued password and every OTP are delivered
there, so two accounts on one mailbox hand its holder a way in as either. NULLs
stay distinct, so accounts with neither field set are unaffected.

Exactly one administrator account exists (`admin`, seeded). `admin_users.py`
cannot create another (`is_admin=False` is hard-coded on the create path) and
`_guard_admin_target` refuses edits to it. "Cán bộ thẩm định" is
`permissions.REVIEWER_PRESET`, not a role: it is a set of checkboxes an
administrator ticks. `coverage_groups` only ever narrows — an account holding
`CASE_VIEW_ALL` with no coverage group sees the whole queue, which is the
delivered preset's shape.

`SINGLE_ACTIVE_SESSION` (default on) means a successful sign-in revokes every
session that account already holds, so the same credentials cannot be live on two
devices at once. It works because sessions carry no claims and are re-read per
request: the other device stops working on its very next call, not at expiry.
This is *not* SSO. There is deliberately no external identity provider, no OAuth
2.0 and no OIDC in this build — the Keycloak realm and JWT/JWKS validation were
removed on purpose, and "one device at a time" was implemented inside the local
session layer instead. Re-introducing an IdP is an architecture decision, not a
hardening task; do not add one as a side effect of some other change.

## Transport and abuse resistance

`shared/middleware.py` holds three concerns, applied to every request:

- `SecurityHeadersMiddleware` is registered last so it is outermost, which is how
  a 429 from the rate limiter and a 500 from the exception handler carry the
  headers too. The API answers JSON and nothing else, so its policy is absolute:
  `Content-Security-Policy: default-src 'none'; ...; frame-ancestors 'none'`,
  `X-Frame-Options: DENY` (kept alongside CSP for browsers that only read it),
  `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`,
  `Cache-Control: no-store`, and HSTS only when production is actually serving
  HTTPS. `Settings.production_guards` refuses to start production with
  `SECURITY_HEADERS_ENABLED=false`. The SPA is served by Nginx, not by this
  process, and carries its own copy in `apps/web/nginx.conf`; that policy is
  looser by necessity (`style-src`/`font-src` allow Google Fonts, because
  `index.html` loads the Inter / Be Vietnam Pro / Material Symbols webfonts and
  dropping them breaks the icon ligatures the e2e label matching depends on).
  `vite.config.ts` sets the framing headers on the dev server for parity.
- The rate limiter enforces three budgets per client address, all of which must
  hold: per route shape (`RATE_LIMIT_PER_MINUTE`), across every route
  (`RATE_LIMIT_IP_PER_MINUTE` — without it a flood just sprays paths and stays
  under the per-route limit on each), and rejected credential attempts
  (`RATE_LIMIT_AUTH_PER_MINUTE`, checked before the call and charged only on a
  401/403, so an operator signing in normally never spends it). The account
  lockout in `modules/auth/service.py` is a different control: it protects one
  account, and does nothing against a sprayer walking a username list.
- `client_address()` decides who a request belongs to. `X-Forwarded-For` is
  honoured **only** when the socket peer matches `TRUSTED_PROXY_IPS` (addresses
  or CIDR ranges); otherwise the socket address is used. Trusting the header
  unconditionally, as an earlier version did, let any caller reset its own bucket
  on every request by sending a new value. The corollary: a deployment that puts
  Nginx, a load balancer or a WAF in front of the API **must** list that hop, or
  every user collapses into one shared bucket.

An external WAF (F5 BIG-IP ASM or equivalent) is where L7 signature filtering,
bot fingerprinting and volumetric defence belong; it is not in this repository
and cannot be installed from it. What the application guarantees is that it is
correct behind one: real client addresses survive the hop through
`TRUSTED_PROXY_IPS`, and the in-app limits stay in force if the appliance is
bypassed.

## Outgoing mail

`modules/notifications/email.py` has exactly one transport: **Gmail SMTP**
(`smtp.gmail.com:587`, STARTTLS) authenticated with a Google *app password* on
`GMAIL_USER` / `GMAIL_APP_PASSWORD`. The self-hosted `SMTP_HOST`/`SMTP_PORT`/
`SMTP_USERNAME`/`SMTP_PASSWORD`/`SMTP_USE_TLS` settings and the offline `.eml`
file writer (`MAIL_OUTBOX_DIR`, `mail_transport`, `mail_outbox_path`) were
removed — a configurable host let a deployment point issued passwords at an
unauthenticated relay, and the file transport left them in a local directory.
Do not reintroduce either; the host/port are constants on purpose.

Gmail rewrites a `From` it does not own, so the sender address is always derived
from `GMAIL_USER` and `MAIL_FROM_NAME` only sets the display name.
`Settings.mail_configured` is true once both halves of the credential are
present, and `production_guards` refuses to start production without them.
`_credential_response` in `api/admin_users.py` still withholds the password on a
successful send and returns it only when delivery failed.

Messages are MIME multipart: `multipart/related` wrapping a
`multipart/alternative` (plain text + HTML) plus the app's favicon as an inline
`image/png` the HTML references by `cid:`. The markup lives in
`modules/notifications/templates.py` and is deliberately table-based with inline
styles only: mail clients strip `<style>` blocks and Outlook renders through
Word, so flexbox/grid and external stylesheets do not survive. The logo ships
inside the package (`modules/notifications/assets/logo.png`, declared in
pyproject's `package-data`) rather than being read out of `apps/web` — the
backend image has no copy of the web tree. Keep the plain-text alternative
readable on its own; the tests read the credential and the OTP out of it.

Tests never open a socket: `tests/mail_stub.py` replaces `smtplib.SMTP` through
an autouse `conftest.py` fixture and records the `EmailMessage` that would have
gone out, which is what `test_local_auth.py`'s `_issued_password` and
`test_login_otp.py`'s `_sent_code` read.

## One-time sign-in codes

`POST /auth/otp/request` mails a six-digit code, `POST /auth/otp/verify`
redeems it and opens an ordinary session; `GET /auth/methods` tells the frontend
whether to render the tab. The service is `modules/auth/otp.py` and its module
docstring is the authority on why each control exists. The properties to keep,
each covered by a test in `tests/test_login_otp.py`:

- The code never appears in a response body, in the subject line, or in the
  inbox preheader. It travels by mail and nowhere else, and only its PBKDF2 hash
  is stored.
- `/auth/otp/request` answers **identically** for a real account, an unknown
  username, an account with no address, a locked account and an exhausted
  budget — and the SMTP conversation runs in a `BackgroundTask` *after* the
  response so the timing does not distinguish them either. Do not add a
  "không tìm thấy tài khoản" branch, a masked-email echo, or a delivery-failure
  message: each one turns this into an account-enumeration oracle.
- `/auth/otp/verify` gives one message for a wrong code and for an unknown
  username, and pays a decoy PBKDF2 round on the unknown branch so both cost the
  same. Deactivated/locked accounts keep their own message, matching what the
  password form already discloses.
- A wrong code charges the account's ordinary failed-attempt counter
  (`auth_service.record_failed_attempt`), so code guessing locks an account
  exactly as password guessing does. Without that this endpoint is a bypass of
  the lockout.
- A challenge is single-use, dies at `OTP_MAX_ATTEMPTS` wrong guesses even while
  still fresh, and issuing a new code consumes every outstanding one — several
  live codes would multiply a guesser's odds per attempt.
- Mail volume is bounded by durable counts over `login_otps` rows, not an
  in-process counter: a per-account cooldown, a per-account hourly cap and a
  per-address hourly cap. The address cap is the one that stops a sprayer
  walking a username list. Rows are therefore kept until `OTP_RETENTION_HOURS`
  (longer than the one-hour windows) — purging on expiry would hand the budget
  back. An unresolvable client address is charged to a shared `"unknown"`
  bucket rather than skipping the check.
- `/auth/otp/verify` is in `middleware._AUTH_PATHS`, so failures also spend the
  per-address credential budget. `/auth/otp/request` deliberately is not: it
  answers 200 to everyone, so there is no failure to count, and the per-route
  and per-address budgets plus the caps above are what bound it.
- The address the budgets are charged to comes from `middleware.client_address`,
  the same function the rate limiter uses, so `TRUSTED_PROXY_IPS` governs it too.
  Using `request.client.host` directly would collapse every caller behind a
  proxy into one bucket.

`Settings.otp_login_available` is `OTP_LOGIN_ENABLED and mail_configured`: a code
that cannot be delivered is never issued, and both endpoints answer 503 in that
state. `production_guards` refuses a cooldown shorter than the code's own TTL.
The frontend's tab (`App.tsx`'s `OtpForm`) and its countdown are display only —
the server holds the authoritative expiry and budget.

## Output encoding and response shape

There is no HTML rendered anywhere on the server: every route answers
`application/json` and the account emails are `text/plain`. Escaping therefore
belongs at the render site, and that is React, which escapes `<`, `>`, `&` and
quotes in text nodes on its own. Do **not** HTML-escape values on the way into
the database or into a JSON response: it corrupts the data (a name containing a
quote would be stored and later exported as `&quot;`) and would still not save a
sink that opts out of escaping. The guard is that no sink exists —
`tests/test_security_hardening.py` fails if `dangerouslySetInnerHTML`,
`innerHTML`, `document.write` or `eval(` appears anywhere under `apps/web/src`.

Every route returns an explicitly built projection, never a serialized ORM row.
`admin_users._serialize` is the pattern: it lists the fields that leave the
server, which is what keeps `password_hash` off the wire. Never add a field by
iterating a model's columns. All database access goes through SQLAlchemy ORM
constructs, which parameterize; the only `text()` in the codebase is the health
probe's `SELECT 1` and the two advisory-lock calls, and those bind their key
rather than formatting it into the statement.

## Deployment profiles

`RUNTIME_PROFILE` (`local` | `docker`) selects the storage and queue backends via
`Settings.effective_storage_backend` / `effective_queue_backend`; both can be
overridden directly with `STORAGE_BACKEND` / `QUEUE_BACKEND`.

- `document_intelligence/storage.py` — `ObjectStorage()` is a factory, not a
  class, returning `FilesystemStorage` (local) or `MinioStorage` (docker) behind
  one interface. Call sites are unchanged. `FilesystemStorage` writes
  `.partial` then renames, and rejects any key that would escape `STORAGE_ROOT`. The two backends mint different URIs (`file:///abs/path` and
`s3://bucket/key`), so a caller that has to turn a stored `storage_uri` back
into a key uses `storage.key_from_uri()` rather than string-slicing one scheme's
prefix — bulk confirm did the latter and answered 500 on every local-profile
spreadsheet.
- `workers/local_queue.py` — the in-process runner. It drives the same Celery
  task functions through `_InlineContext`, which supplies the
  `self.request.retries` / `self.max_retries` the task bodies read and turns
  `self.retry(...)` into a signal the runner acts on, so a task's own
  terminal-failure branch (mark the Case FAILED, dead-letter it) runs on the
  final attempt exactly as under a worker. Do not "simplify" this to a direct
  call: calling a bound Celery task directly makes `self.retry()` try to publish
  to a broker that does not exist in this profile.
- Durability still comes from `outbox_events`, not the broker. `main.py`'s
  lifespan starts a sweeper thread in the local profile that re-dispatches rows a
  crash left `PENDING`. What counts as a durable handoff differs per profile, and
  `tasks._dispatch_event` has to honour that: under Celery, `apply_async` publishing
  to the broker *is* durable, so the row is marked `SENT` there and then; inline,
  `LocalTaskQueue.submit` only hands the task to an in-process thread pool, so the
  dispatcher commits the attempt, runs `process_document` synchronously via
  `run_task_now`, and marks `SENT` only afterwards. Marking it at submit time — as an
  earlier version did — lost the work outright whenever the process died before the
  task ran, leaving a `SENT` row nothing would ever re-pick and a Case stuck at
  `RECEIVED`. A task that exhausts its *own* retry budget has already run its terminal
  branch (Case `FAILED` + dead letter), so that still counts as delivered and the row
  goes `SENT`; re-queueing it would loop the sweeper forever on a dead document.

## Bulk ingestion header mapping

`modules/bulk/service.py`'s `infer_mapping`/`_value_score` auto-detects which spreadsheet/table column maps to which canonical field (`subject_name`, `subject_code`, `unit_name`, ...) by combining a header-alias fuzzy score with a value-shape heuristic. The `subject_name` value heuristic requires whitespace-separated words *and* at least one lowercase letter (`looks_like_person_name` in `_value_score`) specifically so an all-caps constant column (e.g. a `source_kind`/`Nguồn dữ liệu` column holding `"SYNTHETIC_DEMO"` on every row) cannot be mistaken for a person's name — a naive word-count regex treats the underscore as a word boundary and would otherwise score it as a plausible 2-word name, colliding with the real name column and forcing the whole job to `AWAITING_MAPPING`. If a bulk job unexpectedly gets stuck in `AWAITING_MAPPING` with a real personnel-list file, inspect `BulkIngestJob.mapping_json` for a second header mapped onto the same target field before assuming the file itself is malformed.

## Registry data

The seed source resolves in this order: `REGISTRY_SEED_PATH` → `/app/registry/master_units_registry.csv` (mounted into the `seed` service) → `artifacts/registry/published/master_units_registry.csv` → `datasets/curated/master_units_baseline43.csv` → `/app/bootstrap/master_units_baseline43.csv`.

`artifacts/` is untracked — it holds the curated registry (~2.5k units) plus raw crawl evidence and is not in a fresh clone. Do not assume `datasets/curated/master_units_baseline43.csv` is the real registry; it is only the bootstrap fallback. Seeding honours the CSV's own `qa_status` and skips anything not `APPROVED`; never hard-code the column to `APPROVED`.

Production resolution may use only active, QA-approved units/names/codes. New manual units start `PENDING_QA`. Review corrections may create registry candidates but must not auto-create approved aliases. Keep historical unit validity instead of deleting historical facts.

The Person Registry has no equivalent seed script wired into `make seed` — `apps/backend/scripts/seed_persons.py` exists for bootstrapping a synthetic person roster (matches people to `canonical_unit_id`s that must already exist as `APPROVED` units) but is not invoked automatically; run it explicitly when a person-identity roster is needed for local testing.

## Backend conventions

- A supplied `unit_code` is CURRENT_WORK_UNIT evidence, not a missing relation. `process_case`'s `relationless_lookup` (`person_lookup or unit_code_lookup`) exempts both shapes from the `relation_confidence < 0.7` gate and from the four-field extraction-completeness score, because neither carries a narrative unit relation to score and neither claims to supply `current_unit`. Whether the code resolves stays a separate gate (`r.status != "MATCHED"`), so this never rescues an unknown code. The review-reason ladder reads the same predicate — reporting `CURRENT_WORK_UNIT_UNCERTAIN` for a Case that was not routed to review on that ground points the reviewer at the wrong fact.
- Route handlers stay thin; domain state transitions live in `modules/*/service.py`.
- `ExtractedRecord.document_id` is written by `_upsert_extracted_record` via `_source_document_id`, and only when the Case holds exactly one Document — Document→Extraction traceability the column declared and the API projected but nothing ever populated. With several Documents it stays `None` rather than guessing which produced a field.
- Case processing is safe to retry; result/extraction writes use upsert-by-case semantics. This is a per-Case guarantee, not a per-Document one: `Document.case_id` is not schema-unique, so `subject_split.py`'s fan-out can attach multiple Documents to the same originating upload without violating it — what must never happen is more than one `ExtractedRecord`/`VerificationResult` per Case (`VerificationResult.case_id` is DB-unique).
- Human review uses optimistic concurrency (`expected_version`) plus row locking, and a dismissed review fails the Case closed rather than leaving it `NEED_REVIEW` with no open item.
- One import creates at most `bulk_max_rows` Cases (default 50). This is a
  workload cap, not a parser guard — `document_max_spreadsheet_rows` already
  refuses a file big enough to exhaust memory. It is enforced in
  `profile_and_validate` before any row is written, so it also covers the
  re-profile a confirm performs, and its 422 carries `{code, rows, limit,
  message}` because the web client renders that message verbatim in a blocking
  dialog. Other `DocumentLimitError` codes keep their bare-code detail shape.
- Both web upload entry points — selecting a file and pressing the lookup
  button — must route a `TABULAR_LIST_REQUIRES_BULK` 422 to `/bulk` through
  `openBulkFromFile`. `handleSearch`'s branch lacked it and showed the operator
  the raw English server message on every personnel list.
- `bulk/service.py`'s `refresh_job_counts` locks the job row before recomputing
  its counters. Row tasks run concurrently and each recomputes the whole job, so
  an unsynchronised read-modify-write lets the last writer store a pre-peer
  snapshot and strand the job at `PROCESSING` forever — the local profile has no
  Beat running `reconcile_bulk_jobs` to finalise it afterwards. `GET /bulk/{id}`
  also returns each row's decided `organization_type`/`resolution_status`/
  `workflow_status` under the same names `GET /cases/{id}/subjects` uses, so the
  web client renders an import's results and a split document's with one list.
- Registry publish is serialized by an advisory lock; exactly one version stays `PUBLISHED`. The Person Registry has its own separate advisory lock and its own separate single-`PUBLISHED`-version invariant — publishing one registry has no effect on the other.
- Authorization is checked per request from the database, never from anything the client supplies. `AUTH_DISABLED` is development-only and `Settings.production_guards` refuses to start with it on in production.
- `audit_logs` is append-only, enforced by PostgreSQL triggers (migration `0004`). Only insert.
- Structured logs redact by key name (`_REDACT_KEYS` in `shared/logging.py`); never log raw PII, documents, bearer tokens or secrets.
- Effective dates go through `_validate_business_date` in `shared/schemas.py`. Batch ingestion reuses the same function so a spreadsheet column cannot bypass the guard.

## Policy rules

`PolicyRule.subject_groups=[]` is invalid as an implicit wildcard — a global rule must declare `['*']`. Runtime policy output is scope/applicability only unless an official, versioned formula and all required facts are available; do not invent salary amounts.

## Thresholds

Quality thresholds live in `apps/backend/config/document_quality.yaml` and are stamped onto every result as `threshold_version`. Changing a threshold changes recorded decisions, so bump the version in the same edit. IoC/entropy apply only to prose-shaped text; applying language-distribution statistics to short key/value forms produces false failures. OCR quality also includes source-image blur and contrast independently of recognizer confidence, because a recognizer can be confidently wrong on degraded scans.

## Testing / release

Golden suites cover CLEAN, NOISY, OCR, CONTEXT, CONFLICT, UNKNOWN, POLICY, E2E, and a multi-subject-splitting suite. A change touching a business invariant should add or update regression coverage; prefer a test that fails for the stated reason over one that merely pins current output. `tests/test_golden_suites.py` follows a direct-call convention — it calls `extract()`/`process_case()`/`detect_subject_blocks()` directly rather than through the FastAPI route or Celery task, seeding an in-memory SQLite session via the file's `db_session()`/`seed_unit()`/`seed_policy()` helpers. Follow that pattern for new golden tests rather than spinning up the API/worker.

Tests that need a real engine or server (OCR inference, the audit triggers) are skipped or stubbed rather than silently passing. The Docker image bakes EasyOCR, PaddleOCR and embedding models at build time and installs the Vietnamese Tesseract language pack, so a container never fetches models at runtime. On Windows, EasyOCR models live in the configured/user cache; Paddle additionally needs `enable_mkldnn=False` and `USE_TF=0 USE_TORCH=1` (see Document intelligence above).

`apps/backend/tests/test_local_auth.py` covers the account/session/permission layer, half at service level and half against the real HTTP surface with real sessions. When changing anything in `modules/auth/`, add the regression there rather than asserting on the Principal dataclass alone — the properties worth protecting (a revoked permission taking effect mid-session, a deactivated account's session dying, the administrator account being uneditable) only show up end to end.

Do not describe a build as production-ready while critical security, audit, migration, rollback, or golden-gate failures remain.
