# CA/BQP Verification Platform - E2E Full-stack 2026

Hệ thống nội bộ **evidence-driven, registry-first, abstention-capable** để tiếp nhận text/file, trích xuất đối tượng + `CURRENT_WORK_UNIT`, resolve Master Unit Registry, xác định `BCA/BQP/OTHER/UNKNOWN`, xác định `subject_group`, chạy Policy/Eligibility Engine versioned và chuyển Human Review khi không đủ căn cứ.

## Business invariants

- `NOT_FOUND != OTHER`.
- Không suy ra một người là CAND/quân nhân chỉ vì đơn vị thuộc BCA/BQP.
- Nhiều ORG trong hồ sơ phải xác định `CURRENT_WORK_UNIT`; không lấy ORG đầu tiên.
- Fuzzy/semantic chỉ auto-accept khi đạt threshold + margin + calibration và không conflict.
- Policy thiếu required fields phải `INSUFFICIENT_DATA`.
- Review correction không auto-learn thành production alias.
- Crawler không ghi trực tiếp vào Registry đang `PUBLISHED`.
- Mọi kết quả lưu evidence + `registry/taxonomy/parser/model/threshold/policy version`.

## Business analysis - Input Intake / Review / Batch

Phân tích nghiệp vụ chi tiết, state machine, invariant, semantics Human Review, batch validation và traceability nằm tại:

- `docs/business/INPUT_INTAKE_BUSINESS_ANALYSIS_2026.md`

Bản review 2026-09 cũng khóa `as_of_date` theo Case để policy/registry replay deterministic, buộc policy thiếu required fields đi `NEED_REVIEW`, và bảo đảm mọi Case `NEED_REVIEW` có `ReviewCase` tương ứng.

## Chạy nhanh trên máy này (POC)

```sh
cd /mnt/new-volume/Project/bqp/ca-bqp-verification-platform
conda run -n bqp python ops/local.py start
```

- Giao diện: <http://127.0.0.1:3000>
- API/OpenAPI: <http://127.0.0.1:8000/docs>
- Đăng nhập: `admin`/`admin` (quản trị), `user`/`user` (tra cứu)

Lệnh này tự khởi động cụm PostgreSQL riêng (cổng 5433), chạy migration, seed
Master Unit Registry + hai tài khoản mặc định, rồi bật API và web. Các lệnh khác:
`stop`, `status`, `migrate`, `seed`, `backup`, `restore-drill`.

## Runtime architecture

Hệ thống có hai profile, cùng một mã nguồn:

```text
RUNTIME_PROFILE=local                     RUNTIME_PROFILE=docker
-----------------------                   ------------------------
Web SPA (Vite)                            Web SPA (Nginx)
      |                                          |
      v                                          v
FastAPI /api/v1  -- phien dang nhap noi bo --  FastAPI /api/v1
      |                                          |
      v                                          v
PostgreSQL                                PostgreSQL + Redis + MinIO
      |                                          |
      v                                          v
Outbox dispatcher in-process              Celery Worker / Outbox / DLQ
```

Từ đó trở xuống hai profile dùng chung một critical path:

```text
Parser/OCR -> Extraction -> Resolver
           |
           v
Subject Group -> Policy Engine
           |
           v
Result / Evidence / Human Review / Audit
```

Profile `local` chỉ cần PostgreSQL: tài liệu gốc lưu trên đĩa (`STORAGE_ROOT`) và
tiến trình API cũng chính là task runner, quét bảng `outbox_events` để không mất
việc khi tiến trình khởi động lại. Profile `docker` giữ nguyên MinIO/Redis/Celery
trong `compose.yaml`.

## Tài khoản và phân quyền

Tài khoản nằm trong chính cơ sở dữ liệu của hệ thống - không có identity provider
ngoài.

- **Quản trị viên**: duy nhất một tài khoản `admin`, do seeder tạo. Không có API
  nào tạo thêm tài khoản quản trị.
- **Tài khoản nghiệp vụ**: quản trị viên nhập thông tin hành chính (mã số cán bộ,
  họ tên, năm sinh, cấp bậc, chức vụ, phòng/ban, đơn vị); hệ thống sinh tên đăng
  nhập từ mã số (hoặc từ họ tên nếu không có mã) và một mật khẩu ngẫu nhiên, hiển
  thị **một lần** cho quản trị viên.
- **Tài khoản mặc định**: `user`/`user` giữ bộ quyền tra cứu cơ bản.

Không có vai trò "cán bộ thẩm định" riêng: đó là **bộ quyền** quản trị viên bật
cho từng tài khoản trong màn hình *Quản trị tài khoản*.

| Quyền | Ý nghĩa |
|---|---|
| `CASE_CREATE` / `CASE_BULK` / `LOOKUP_UNIT` / `CASE_EXPORT` | Bộ quyền tra cứu cơ bản |
| `CASE_VIEW_ALL` | Xem mọi hồ sơ, không giới hạn hồ sơ tự tạo |
| `REVIEW_QUEUE` / `REVIEW_DECIDE` | Hàng đợi và quyết định thẩm định |
| `REGISTRY_ADMIN` / `PERSON_REGISTRY_ADMIN` | QA và publish danh mục |
| `AUDIT_VIEW` | Nhật ký kiểm toán |
| `USER_ADMIN` | Quản trị tài khoản |

Bộ quyền "cán bộ thẩm định" = bộ tra cứu cơ bản + `CASE_VIEW_ALL` + `REVIEW_QUEUE`
+ `REVIEW_DECIDE`. `coverage_groups` chỉ **thu hẹp** phạm vi, không bao giờ cấp
thêm quyền.

### Phân quyền được enforce ở máy chủ, không ở giao diện

Token phiên là một chuỗi ngẫu nhiên **không mang thông tin quyền**; máy chủ chỉ
lưu SHA-256 của nó và đọc lại quyền từ bảng `app_users` ở **mọi** request. Vì vậy:

- Giao diện ẩn/hiện menu chỉ để dễ dùng. Sửa state trong devtools, gọi thẳng API,
  hay dựng lại bundle đều không mở thêm được gì - endpoint tự kiểm tra và trả 403.
- Quản trị viên thu hồi một quyền thì quyền đó mất hiệu lực ngay ở request kế
  tiếp của phiên đang mở, không cần chờ token hết hạn.
- Khóa tài khoản làm phiên đang mở ngừng hoạt động ngay.

Các tính chất này được khóa bằng test HTTP thật trong
`apps/backend/tests/test_local_auth.py`.

## Registry governance

```text
Official/provided source
-> crawler/import candidate
-> normalize/dedupe
-> PENDING_QA
-> Admin QA
-> DRAFT snapshot
-> VALIDATED
-> APPROVED
-> PUBLISHED (immutable)
```

Rollback không sửa snapshot lịch sử; hệ thống clone snapshot cũ thành version mới và publish atomically.

## Resolution cascade

```text
trusted code
-> canonical exact
-> approved alias
-> fuzzy + BM25
-> multilingual embedding fallback
-> calibrated confidence + top1/top2 margin
-> MATCHED hoặc ABSTAIN/Human Review
```

Artifact calibration: `apps/backend/artifacts/resolver_calibration.json`. Artifact hiện tại được fit từ deterministic synthetic mention-noise của Registry trong repo; phù hợp project/demo gate và phải refit trên labeled production validation data trước real deployment.

## Document intake

Hỗ trợ: PDF, DOCX, XLSX/XLS, PNG/JPG/JPEG, TXT/CSV.

- Structured/text parser trước.
- OCR pluggable (Paddle detector/recognizer, VietOCR candidate, Tesseract baseline); engine mặc định phải được chốt bằng benchmark, không hardcode theo giả định.
- Magic-byte + MIME validation.
- Office ZIP path/expanded-size guard.
- ClamAV scan; production fail-closed.
- File lưu MinIO, DB chỉ lưu metadata/checksum.
- OCR/parse confidence thấp -> `NEED_REVIEW`, không âm thầm đi thẳng tới kết luận.
- Upload file và text đều hỗ trợ `as_of_date`; batch hỗ trợ map cột ngày nghiệp vụ và chặn ngày sai ngay phase-1.
- Batch WARNING như `AMBIGUOUS_UNIT` vẫn tạo Case nhưng bắt buộc đi Human Review.

## Reliability / security

- Tài khoản nội bộ: PBKDF2-HMAC-SHA256 (salt riêng từng mật khẩu), phiên opaque
  lưu server-side, khóa tạm sau nhiều lần đăng nhập sai.
- Phân quyền theo permission + reviewer coverage scope, kiểm tra tại máy chủ.
- Idempotency key cho create text/file Case.
- Durable Outbox cho document job.
- Celery retry + terminal `FAILED` + DLQ.
- Circuit breaker/retry cho external dependencies.
- Redis rate limiting.
- Structured JSON technical logs + PII redaction.
- Append-only business audit.
- Non-root backend container + liveness/readiness.
- Alembic explicit migration; rollback drill trong CI.
- Prometheus metrics.
- CI: pytest/golden, Ruff, MyPy, Bandit, pip-audit, Docker build, Trivy, migration drill.
- Release: SBOM + SHA256 + GitHub build provenance attestation.

## Golden regression suites

`apps/backend/tests/test_golden_suites.py` khóa đủ 8 suite:

1. `GOLDEN-CLEAN`
2. `GOLDEN-NOISY`
3. `GOLDEN-OCR`
4. `GOLDEN-CONTEXT`
5. `GOLDEN-CONFLICT`
6. `GOLDEN-UNKNOWN`
7. `GOLDEN-POLICY`
8. `GOLDEN-E2E`

## Data trong repo

Seed ưu tiên registry đã QA trong `artifacts/registry/published/master_units_registry.csv`
(2.077 đơn vị `APPROVED` trên tổng 2.541 bản ghi), và chỉ rơi về
`datasets/curated/master_units_baseline43.csv` khi artifact không có mặt. Crawler/pipeline data tiếp tục đi qua candidate QA trước khi có thể xuất hiện trong snapshot production.

## Chạy local bằng Docker

```bash
cp .env.example .env
# Đổi toàn bộ password/secret mặc định trước môi trường thật.
docker compose up --build
```

Endpoints:

- Web: `http://localhost:3000`
- Backend OpenAPI: `http://localhost:8000/docs`
- Backend readiness: `http://localhost:8000/health/ready`
- MinIO Console: `http://localhost:9001`
- Prometheus: `http://localhost:9090`

## Dev test

```bash
cd apps/backend
pip install -e '.[dev]'
pytest -q
ruff check src tests scripts
mypy src
bandit -q -r src
pip-audit --strict
```

Frontend React + TypeScript:

```bash
cd apps/web
npm install --no-audit --no-fund
npm run typecheck
npm run build
```

Trong Docker, frontend gọi backend qua same-origin `/api/v1/*`; Nginx reverse-proxy sang service `backend:8000`. Ở profile `local`, Vite dev server proxy `/api` và `/health` sang `http://localhost:8000`.

E2E trên trình duyệt (`cd apps/web && npx playwright test`) chạy với ứng dụng thật đang bật; các spec đăng nhập qua form thật bằng tài khoản đã seed, không còn đường tắt dev-login.

## Migration / backup / rollback

Runbooks:

- `ops/runbooks/BACKUP_RESTORE.md`
- `ops/runbooks/DEPLOY_ROLLBACK.md`
- `ops/runbooks/REGISTRY_POLICY_UPDATE.md`
- `ops/runbooks/INCIDENT_RESPONSE.md`

Migration drill:

```bash
./ops/scripts/migration_rollback_drill.sh
```

## Kiểm chứng

`docs/quality/POC_VALIDATION_2026-09-17.md` ghi lại đúng những gì đã chạy thật
trong phiên bàn giao POC (275/279 backend test, 13 E2E trình duyệt, lint sạch,
luồng nghiệp vụ thật qua HTTP) và nêu rõ những phần **chưa** được kiểm chứng -
đáng chú ý: profile Docker chưa chạy được trên máy này vì Docker chưa cài.

## Production boundary

Repository cung cấp production-oriented controls nhưng **không tự biến demo data thành dữ liệu nghiệp vụ thật**. Source/provenance và `source_kind` phải được giữ đúng; kết quả synthetic phải mang `SYNTHETIC_DEMO`. Secret manager/WAF/TLS termination nên được cung cấp bởi hạ tầng triển khai (Kubernetes/Ingress/Cloud secret service hoặc tương đương), không hard-code vào repo.
