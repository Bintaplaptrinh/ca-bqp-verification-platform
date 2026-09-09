# SCRUM-7 — Project Bootstrap Plan

## GitHub Repository

**Recommended repository name:** `ca-bqp-verification-platform`

**Description:**  
Production-oriented platform for unit-based verification and scope identification under Bộ Công an (BCA) / Bộ Quốc phòng (BQP).

---

# 1. Mục tiêu của SCRUM-7

Khởi tạo nền tảng kỹ thuật ban đầu cho toàn bộ dự án để các thành viên trong nhóm có thể clone repository, chạy môi trường local và bắt đầu phát triển các module độc lập mà không cần tự cấu hình lại từ đầu.

SCRUM-7 chỉ tập trung vào **project foundation**, chưa triển khai logic nghiệp vụ BCA/BQP, OCR, NER, Registry Resolution hay Decision Engine.

## Definition of Done

Sau khi hoàn thành ticket, một thành viên khác phải có thể chạy:

```bash
git clone <repository-url>
cd ca-bqp-verification-platform
cp .env.example .env
docker compose up --build
```

và nhận được:

- Backend chạy thành công.
- `GET /health` trả HTTP 200.
- PostgreSQL ở trạng thái healthy.
- Redis ở trạng thái healthy.
- Test backend pass.
- CI của Pull Request pass.
- Không có secret hoặc dữ liệu production bị commit.

---

# 2. Git workflow

## Branch chính

```text
main
└── develop
    ├── feature/SCRUM-7-project-bootstrap
    ├── feature/SCRUM-xx-registry
    ├── feature/SCRUM-xx-document-processing
    └── fix/SCRUM-xx-description
```

### Quy ước

- `main`: bản ổn định/release.
- `develop`: branch tích hợp của team.
- `feature/SCRUM-<id>-<name>`: phát triển feature theo Jira ticket.
- `fix/SCRUM-<id>-<name>`: sửa lỗi theo Jira ticket.

Không push trực tiếp vào `main`.

## Quy tắc branch khi dự án có nhiều Jira ticket

Dự án có nhiều `SCRUM-xx` không phải vấn đề. Chỉ Jira work item **có artifact/code cần commit** mới cần branch.

```text
Jira task có thay đổi repo?
├── Không → cập nhật Jira, không bắt buộc tạo branch
└── Có
    ↓
feature/SCRUM-<id>-<short-name>
    ↓
PR → develop
    ↓
Review + CI
    ↓
Merge
    ↓
Delete feature branch
```

Feature branch là **short-lived**. Sau khi merge phải xóa branch để repository luôn sạch.

Với SCRUM-7:

```text
feature/SCRUM-7-project-bootstrap
```

Các subtask SCRUM-24..31 **không tạo branch riêng**.


## Branch protection đề xuất

### `main`
- Require Pull Request.
- Require CI success.
- Require 1 approval.
- Disable force push.
- Disable direct deletion.

### `develop`
- Require Pull Request.
- Require CI success.

---


## Tên branch cho SCRUM-7

Branch chính thức của task này:

```text
feature/SCRUM-7-project-bootstrap
```

Quy ước đặt tên branch cho toàn team:

```text
feature/SCRUM-<id>-<short-name>
fix/SCRUM-<id>-<short-name>
hotfix/<short-name>
chore/<short-name>
```

Ví dụ:

```text
feature/SCRUM-1-data-source-list
feature/SCRUM-23-file-preprocessing-plan
feature/SCRUM-6-tech-stack-plan
feature/SCRUM-7-project-bootstrap
```

Khuyến nghị:
- Mỗi Jira ticket tương ứng một branch riêng.
- Tên branch viết thường, dùng dấu gạch ngang `-`.
- Không dùng tên cá nhân hoặc tên mơ hồ như `test`, `new`, `final`, `abc`.
- Với SCRUM-7, dùng cố định `feature/SCRUM-7-project-bootstrap`.


# 3. Cấu trúc repository Sprint 0

```text
ca-bqp-verification-platform/
│
├── README.md
├── CONTRIBUTING.md
├── .gitignore
├── .env.example
├── .editorconfig
├── Makefile
├── compose.yaml
│
├── apps/
│   ├── backend/
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   ├── src/
│   │   │   └── cabqp/
│   │   │       ├── __init__.py
│   │   │       ├── main.py
│   │   │       ├── api/
│   │   │       │   └── health.py
│   │   │       ├── modules/
│   │   │       │   ├── cases/
│   │   │       │   ├── registry/
│   │   │       │   ├── document_intelligence/
│   │   │       │   ├── resolution/
│   │   │       │   ├── decisioning/
│   │   │       │   ├── review/
│   │   │       │   └── audit/
│   │   │       └── shared/
│   │   └── tests/
│   │       └── test_health.py
│   │
│   └── web/
│       └── README.md
│
├── workers/
│   └── README.md
│
├── pipelines/
│   ├── registry_ingestion/
│   │   └── README.md
│   ├── synthetic_data/
│   │   └── README.md
│   └── ml/
│       └── README.md
│
├── contracts/
│   ├── api/
│   └── data/
│
├── datasets/
│   ├── manifests/
│   └── samples/
│
├── docs/
│   ├── business/
│   ├── architecture/
│   └── data/
│
├── deploy/
├── infra/
├── ops/
│
└── .github/
    ├── pull_request_template.md
    └── workflows/
        └── ci.yml
```

> Không tạo hàng trăm file rỗng trong Sprint 0. Module chưa triển khai chỉ cần giữ boundary rõ ràng và có README mô tả mục đích nếu cần.

---

# 4. Backend Skeleton

Backend Sprint 0 chỉ cần chạy được FastAPI và health check.

## Endpoint tối thiểu

```http
GET /health
```

Response:

```json
{
  "status": "ok",
  "service": "ca-bqp-backend"
}
```

## Test tối thiểu

```bash
pytest
```

Test phải kiểm tra:
- HTTP status = 200.
- `status = ok`.

## Không làm trong SCRUM-7

- OCR.
- NER.
- PhoBERT.
- Fuzzy/Semantic Matching.
- Master Unit Registry logic.
- Decision rules.
- Eligibility/An sinh.
- UI nghiệp vụ hoàn chỉnh.

---

# 5. Docker Development Skeleton

Các service tối thiểu:

```text
backend
postgres
redis
```

Kiến trúc local:

```text
Developer
   │
   ▼
FastAPI Backend
   │
   ├── PostgreSQL
   └── Redis
```

Worker/Object Storage/Web implementation chỉ bật khi đã có task triển khai tương ứng; repository vẫn chừa boundary theo kiến trúc tổng thể.

## Yêu cầu

- Backend có Dockerfile.
- PostgreSQL có healthcheck.
- Redis có healthcheck.
- Backend có healthcheck hoặc endpoint health.
- `docker compose up --build` chạy thành công.
- Không restart loop.
- Không hardcode production credential.

---

# 6. Environment Configuration

Commit:
```text
.env.example
```

Không commit:
```text
.env
API keys
password thật
token
production dataset
private files
```

Ví dụ `.env.example`:

```env
APP_ENV=development

BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000

POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=cabqp
POSTGRES_USER=cabqp
POSTGRES_PASSWORD=change_me

REDIS_HOST=redis
REDIS_PORT=6379
```

---

# 7. Makefile

Các command nên hỗ trợ:

```bash
make up
make down
make logs
make test
make config
```

Ví dụ:

```makefile
up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f

test:
	docker compose exec backend pytest

config:
	docker compose config
```

---

# 8. Commit Convention

Dùng Conventional Commits.

Ví dụ:

```text
chore(repo): initialize repository structure
chore(docker): add local development stack
feat(api): add health endpoint
test(api): add health endpoint test
docs(readme): add local development guide
ci(github): add basic CI workflow
```

Không dùng:

```text
update
done
fix
final
final2
abc
```

---

# 9. CI tối thiểu

Pipeline Pull Request:

```text
Checkout
   ↓
Install dependencies
   ↓
Lint
   ↓
Unit Test
   ↓
Docker Compose Config Check
   ↓
Docker Build
```

SCRUM-7 chưa cần:
- Kubernetes.
- Terraform production.
- Auto deployment production.
- ML training pipeline.

---

# 10. README bắt buộc

README nên có:

1. Project Overview.
2. Architecture summary.
3. Repository Structure.
4. Requirements.
5. Local Setup.
6. Services.
7. Testing.
8. Branch Convention.
9. Commit Convention.
10. Modules.
11. Contribution Workflow.

Local setup chuẩn:

```bash
git clone <repository-url>
cd ca-bqp-verification-platform
cp .env.example .env
docker compose up --build
```

---

# 11. CONTRIBUTING.md

Workflow chuẩn:

```text
1. Checkout develop.
2. Pull latest changes.
3. Create feature/SCRUM-X-name.
4. Implement task.
5. Run local test.
6. Push branch.
7. Create Pull Request.
8. Request teammate review.
9. Merge only after CI passes.
```

---

# 12. Pull Request cho SCRUM-7

## PR Title

```text
[SCRUM-7] Bootstrap repository and local development environment
```

## PR Description

```markdown
## Purpose

Initialize the technical foundation for CA/BQP Verification Platform.

## Included

- Repository structure
- Git conventions
- FastAPI backend skeleton
- Health endpoint
- PostgreSQL local container
- Redis local container
- Docker Compose
- Environment template
- Makefile
- Backend test
- Basic CI
- README
- Contribution guide

## Not Included

- Registry business logic
- Document processing
- OCR / NER
- Resolution engine
- Decision engine
- Eligibility logic
- Production deployment

## Validation

- [x] docker compose config succeeds
- [x] docker compose up --build succeeds
- [x] PostgreSQL healthy
- [x] Redis healthy
- [x] Backend healthy
- [x] GET /health returns 200
- [x] Backend test passes
- [x] No secrets committed

## Jira

SCRUM-7
```

---

# 13. Clean-clone Verification

Trước khi mở PR, tạo thư mục mới và kiểm thử như một teammate:

```bash
git clone <repository-url>
cd ca-bqp-verification-platform
cp .env.example .env
docker compose up --build
```

Kiểm tra:

```bash
curl http://localhost:8000/health
```

Kết quả:

```json
{
  "status": "ok",
  "service": "ca-bqp-backend"
}
```

Sau đó:

```bash
make test
```

phải pass.

---

# 14. Checklist SCRUM-7

## Repository & Git
- [ ] GitHub repository created.
- [ ] `main` created.
- [ ] `develop` created.
- [ ] `feature/SCRUM-7-project-bootstrap` created.
- [ ] Branch convention documented.
- [ ] Branch protection configured if permissions allow.

## Project Foundation
- [ ] Repository structure created.
- [ ] FastAPI backend skeleton created.
- [ ] `/health` endpoint created.
- [ ] Backend test created.

## Docker
- [ ] Backend Dockerfile.
- [ ] PostgreSQL.
- [ ] Redis.
- [ ] `compose.yaml`.
- [ ] Healthchecks.
- [ ] Stack starts without restart loop.

## Configuration
- [ ] `.env.example`.
- [ ] `.gitignore`.
- [ ] `.editorconfig`.
- [ ] `Makefile`.

## Documentation
- [ ] `README.md`.
- [ ] `CONTRIBUTING.md`.
- [ ] Pull Request template.

## Quality
- [ ] Basic CI.
- [ ] Backend test passes.
- [ ] Docker build passes.
- [ ] No secret committed.
- [ ] No production data committed.
- [ ] Clean-clone test passes.
- [ ] PR reviewed by teammate.

---

---

# 16. Agent Coding Protocol — Jira & GitHub Update Rules

> Mục này dành cho AI coding agent / coding assistant. Khi thực hiện SCRUM-7, agent phải vừa code vừa **nhắc người dùng cập nhật Jira và GitHub đúng thời điểm**. Agent không được chỉ tập trung viết code rồi bỏ qua quy trình quản lý công việc.

## 16.1. Nguyên tắc bắt buộc

Agent phải tuân thủ:

1. Không tự ý thay đổi phạm vi SCRUM-7.
2. Không tự triển khai OCR, NER, Registry logic, Resolution Engine, Decision Engine hoặc nghiệp vụ ngoài ticket.
3. Mỗi bước lớn phải gắn với một Jira subtask.
4. Khi bắt đầu một subtask, agent phải nhắc:
   - Jira: chuyển `To Do -> In Progress`.
   - GitHub: checkout đúng branch.
5. Khi hoàn thành một phần có ý nghĩa, agent phải đề xuất commit message.
6. Khi code/test đã hoàn tất, agent phải nhắc:
   - push branch;
   - mở Pull Request;
   - chuyển Jira sang `In Review`;
   - comment link PR trong Jira.
7. Chỉ khi PR đã review + CI pass + merge thì mới nhắc chuyển Jira sang `Done`.
8. Nếu gặp blocker, agent phải dừng ở phạm vi bị block và báo rõ:
   - blocker là gì;
   - ảnh hưởng đến subtask nào;
   - Jira nên comment gì;
   - có nên chuyển trạng thái hay không.
9. Agent không được nói "Done" nếu Definition of Done chưa đạt.
10. Agent phải giữ lại bằng chứng kỹ thuật: command, test result, commit, PR, CI.

---

# 17. Mapping SCRUM-7 Subtasks với Jira

Các Jira subtask hiện đã được tạo và **giữ nguyên ID để bảo toàn lịch sử Jira**. Không cần xóa/đổi ID chỉ để làm board gọn hơn. Nhóm triển khai chúng theo **5 work package** để tránh micro-management.

## 17.1. Jira subtasks hiện có

| Jira | Subtask | Work package |
|---|---|---|
| SCRUM-24 | Create GitHub repository and branch strategy | WP1 — Repository Governance |
| SCRUM-25 | Create project directory skeleton | WP2 — Project Foundation |
| SCRUM-26 | Bootstrap FastAPI backend | WP2 — Project Foundation |
| SCRUM-27 | Add PostgreSQL and Redis local stack | WP3 — Local Runtime |
| SCRUM-28 | Create Dockerfile and Docker Compose | WP3 — Local Runtime |
| SCRUM-29 | Add environment and project configuration | WP4 — Configuration & Quality |
| SCRUM-30 | Add basic CI and health test | WP4 — Configuration & Quality |
| SCRUM-31 | Write README and contribution guide | WP5 — Documentation & Verification |

## 17.2. Năm work package dùng để quản lý công việc

### WP1 — Repository Governance
**Jira:** SCRUM-24

- Tạo GitHub repository.
- Tạo `main`, `develop`.
- Tạo branch `feature/SCRUM-7-project-bootstrap`.
- Chốt branch naming convention.
- Branch protection nếu quyền repository cho phép.

### WP2 — Project Foundation
**Jira:** SCRUM-25 + SCRUM-26

- Tạo project directory skeleton.
- Khởi tạo FastAPI backend tối thiểu.
- Thêm `/health`.
- Thêm backend test cơ bản.

### WP3 — Local Runtime
**Jira:** SCRUM-27 + SCRUM-28

- PostgreSQL.
- Redis.
- Backend Dockerfile.
- `compose.yaml`.
- Health checks.
- Local stack chạy ổn định.

### WP4 — Configuration & Quality
**Jira:** SCRUM-29 + SCRUM-30

- `.env.example`.
- `.gitignore`.
- `.editorconfig`.
- Makefile.
- Basic CI.
- Health test / quality gate.

### WP5 — Documentation & Verification
**Jira:** SCRUM-31

- README.
- CONTRIBUTING.
- Pull Request template.
- Clean-clone verification.
- Xác nhận teammate có thể setup dự án từ đầu.

## 17.3. Rule Git quan trọng

```text
1 SCRUM parent task = 1 feature branch
Subtask = Jira checkpoint + commit(s)
Work package = nhóm logic để báo cáo tiến độ
```

SCRUM-7 chỉ dùng **một branch**:

```text
feature/SCRUM-7-project-bootstrap
```

Không tạo branch riêng cho SCRUM-24..31.

## 17.4. Vì sao giữ 8 Jira subtask nhưng nhóm thành 5 work package?

- Jira đã có ID và history, không nên xóa/đổi task đang dùng chỉ để làm đẹp board.
- 8 subtask vẫn đủ nhỏ để theo dõi tiến độ.
- 5 work package giúp báo cáo với giảng viên/leader gọn hơn.
- Git history không bị vỡ vụn vì tất cả vẫn nằm trên một parent feature branch.
- Sau khi merge, branch `feature/SCRUM-7-project-bootstrap` được xóa; lịch sử còn trong PR/commit/Jira.

> Agent phải bám Jira subtask hiện có, nhưng khi báo cáo tiến độ nên gom theo 5 work package ở trên.

---

# 18. Workflow Agent phải nhắc ở từng Subtask

## 18.1. Khi bắt đầu

Agent phải hiển thị một checkpoint ngắn:

```text
[JIRA CHECKPOINT]

Subtask: SCRUM-XX - <name>

Trước khi code:
1. Chuyển Jira: To Do -> In Progress
2. Comment:
   Started working on <subtask>.
   Plan:
   - ...
   - ...
3. Kiểm tra branch hiện tại.
```

Nếu đây là subtask đầu tiên của SCRUM-7:

```bash
git checkout develop
git pull origin develop
git checkout -b feature/SCRUM-7-project-bootstrap
```

Nếu branch đã tồn tại thì chỉ cần:

```bash
git checkout feature/SCRUM-7-project-bootstrap
git pull
```

Agent phải xác nhận branch trước khi thay đổi file.

**Lưu ý:** mọi subtask SCRUM-24..31 của parent SCRUM-7 dùng chung `feature/SCRUM-7-project-bootstrap`. Không tạo branch riêng cho từng subtask.

---

## 18.2. Trong quá trình làm

Sau mỗi nhóm thay đổi hoàn chỉnh, agent phải đề xuất commit.

Format:

```text
[GIT CHECKPOINT]

Changes completed:
- ...
- ...

Suggested commit:
<type>(<scope>): <message>
```

Ví dụ:

```text
chore(repo): initialize repository structure
feat(api): add health endpoint
chore(docker): add postgres and redis services
test(api): add health endpoint test
ci(github): add backend CI workflow
docs(readme): add local development setup
```

Không commit nếu:
- code đang lỗi;
- test đang fail;
- thay đổi chưa hoàn chỉnh;
- có secret/data nhạy cảm trong staged files.

Trước commit, agent nên yêu cầu/check:

```bash
git status
git diff
```

---

## 18.3. Cuối buổi hoặc khi người dùng dừng làm

Agent phải tạo một mẫu Jira Daily Update để người dùng copy:

```text
[JIRA DAILY UPDATE]

Done:
- ...

Result:
- ...

Blocker:
- None
```

hoặc:

```text
Blocker:
- <mô tả vấn đề>
```

và:

```text
Next:
- ...
```

Ví dụ:

```text
Done:
- Created repository structure
- Added FastAPI skeleton

Result:
- Backend starts successfully
- GET /health returns HTTP 200

Blocker:
- None

Next:
- Configure PostgreSQL and Redis local stack
```

---

# 19. Quy trình khi Subtask hoàn thành

Một subtask chỉ được xem là hoàn thành kỹ thuật khi:

```text
Implementation complete
        +
Local validation pass
        +
Relevant test pass
        +
No secret committed
```

Sau đó agent phải nhắc:

```text
[JIRA/GITHUB CHECKPOINT]

Subtask implementation completed.

1. Review:
   git status
   git diff

2. Commit/push:
   git push -u origin feature/SCRUM-7-project-bootstrap

3. Jira:
   In Progress -> In Review

4. Jira comment:
   Implementation completed.

   Result:
   - ...

   Validation:
   - ...

   Branch:
   feature/SCRUM-7-project-bootstrap

   Commit:
   <commit hash/message>

   PR:
   <add after PR is created>
```

SCRUM-7 dùng **một Pull Request chính** cho parent ticket. Không mở PR riêng cho từng subtask trừ khi team có lý do kỹ thuật rõ ràng.

Trong quá trình làm:
- mỗi subtask vẫn cập nhật Jira riêng;
- mỗi thay đổi có commit rõ nghĩa;
- có thể mở Draft PR sớm nếu team muốn review liên tục.

---

# 20. Quy trình mở Pull Request

Khi tất cả subtask SCRUM-7 đã hoàn tất và local verification pass, agent phải nhắc mở PR.

## PR Title

```text
[SCRUM-7] Bootstrap repository and local development environment
```

## Trước khi PR

Agent phải kiểm tra hoặc yêu cầu chạy:

```bash
git status
docker compose config
docker compose up --build
pytest
```

Nếu có lint:

```bash
ruff check .
```

Nếu tất cả pass:

```bash
git push -u origin feature/SCRUM-7-project-bootstrap
```

Sau đó agent phải báo:

```text
Ready for PR.

Jira action:
- SCRUM-7: In Progress -> In Review
- Các subtask đã xong: chuyển In Review nếu team review cùng PR.

GitHub action:
- Open Pull Request:
  feature/SCRUM-7-project-bootstrap -> develop
```

---

# 21. Jira Comment Template khi mở PR

```text
Implementation completed and ready for review.

Completed:
- Repository structure
- Git conventions
- FastAPI skeleton
- PostgreSQL/Redis local stack
- Docker Compose
- Environment configuration
- Basic CI
- README/CONTRIBUTING

Validation:
- docker compose config: PASS
- docker compose up --build: PASS
- GET /health: HTTP 200
- backend tests: PASS
- secret check: PASS

Branch:
feature/SCRUM-7-project-bootstrap

Pull Request:
<PR URL>

Status:
Waiting for review.
```

---

# 22. Code Review Protocol

Agent phải nhắc người dùng:

```text
Người code != người approve PR
```

Reviewer cần kiểm tra:

- project tree có đúng plan không;
- có over-engineering không;
- có secret không;
- Docker có chạy không;
- healthcheck có pass không;
- test/CI có pass không;
- README có đủ setup không;
- có code ngoài phạm vi SCRUM-7 không.

Nếu reviewer yêu cầu sửa:

```text
Jira: giữ In Review
GitHub: sửa trên cùng branch
Commit: fix(...) / chore(...)
Push lại branch
```

Không tạo branch/PR mới chỉ để sửa review comment.

---

# 23. Khi PR được Merge

Chỉ sau khi:

```text
CI PASS
+
REVIEW APPROVED
+
PR MERGED INTO develop
```

agent mới được nhắc chuyển:

```text
SCRUM-7 -> Done
```

và subtask tương ứng -> `Done`.

Jira comment cuối:

```text
Completed and merged.

Result:
- Project foundation is ready for team development.
- Backend health check passes.
- PostgreSQL and Redis local services are healthy.
- Docker Compose local environment works.
- CI passes.
- Documentation is available.

Branch:
feature/SCRUM-7-project-bootstrap

PR:
<PR URL>

Merged into:
develop

Blocker:
None.
```

---

# 24. Agent Completion Report

Khi agent kết thúc một phiên code, response cuối phải có 5 mục:

```text
1. Completed
2. Files changed
3. Validation
4. Jira update required
5. Git/GitHub next action
```

Ví dụ:

```text
Completed
- Added FastAPI application skeleton.
- Added /health endpoint.

Files changed
- apps/backend/src/cabqp/main.py
- apps/backend/src/cabqp/api/health.py
- apps/backend/tests/test_health.py

Validation
- pytest: PASS
- GET /health: HTTP 200

Jira update required
- SCRUM-26: In Progress -> In Review
- Add completion comment with test result.

Git/GitHub next action
- Commit:
  feat(api): bootstrap FastAPI backend
- Push:
  feature/SCRUM-7-project-bootstrap
```

Agent không được kết thúc chỉ bằng câu "đã code xong".

---

# 25. Blocker Protocol

Nếu gặp blocker, ví dụ:

- Docker Desktop chưa chạy;
- port bị chiếm;
- GitHub permission thiếu;
- branch protection không cấu hình được;
- dependency conflict;
- CI không chạy do quyền repo;

agent phải báo:

```text
[BLOCKED]

Subtask:
SCRUM-XX

Issue:
...

Impact:
...

What has been completed:
...

What remains:
...

Jira update:
Keep status: In Progress
Comment:
Blocked by <reason>. Waiting for <action>.

Next action:
...
```

Nếu blocker hoàn toàn ngăn tiếp tục thì có thể dùng trạng thái `Blocked` nếu Jira workflow của nhóm có trạng thái này.

---

# 26. Agent không được làm các việc sau

```text
DO NOT:
- tự chuyển Jira sang Done;
- tự coi PR đã approved;
- tự coi CI đã pass nếu chưa chạy;
- tự merge main/develop;
- bỏ qua review;
- commit secret;
- commit .env;
- commit production dataset;
- force push main/develop;
- code sang task của teammate;
- mở rộng architecture ngoài plan;
- thêm dependency không cần thiết mà không báo.
```

---

# 27. Prompt vận hành cho Coding Agent

Khi bắt đầu coding SCRUM-7, có thể đưa cho agent prompt sau:

```text
Bạn đang triển khai Jira SCRUM-7 của dự án ca-bqp-verification-platform.

Hãy tuân thủ file SCRUM-7_Project_Bootstrap_Plan.md làm source of truth.

Yêu cầu:
1. Làm theo từng Jira subtask SCRUM-24 -> SCRUM-31 nhưng quản lý theo 5 work package:
   - WP1: SCRUM-24
   - WP2: SCRUM-25 + SCRUM-26
   - WP3: SCRUM-27 + SCRUM-28
   - WP4: SCRUM-29 + SCRUM-30
   - WP5: SCRUM-31
   Tất cả dùng chung branch `feature/SCRUM-7-project-bootstrap`.
2. Không code ngoài scope SCRUM-7.
3. Trước mỗi subtask, báo tôi cần chuyển Jira sang trạng thái nào.
4. Trong quá trình code, đề xuất commit message theo Conventional Commits.
5. Cuối mỗi bước, báo rõ:
   - đã làm gì;
   - file nào thay đổi;
   - test/validation;
   - tôi cần update Jira gì;
   - tôi cần commit/push/PR gì.
6. Không được tự nói Done nếu chưa đạt Definition of Done.
7. Nếu có blocker, dừng và tạo Jira blocker update cho tôi.
8. Trước khi mở PR phải chạy/kiểm tra:
   - git status;
   - docker compose config;
   - docker compose up --build;
   - pytest;
   - health endpoint.
9. PR cuối của ticket:
   [SCRUM-7] Bootstrap repository and local development environment
10. Target branch của PR: develop.
```

---

# 28. Báo cáo tiến độ dùng cho giảng viên

Toàn bộ workflow phải tạo được chuỗi bằng chứng:

```text
Master Plan
    ↓
Jira Task
    ↓
Jira Subtask
    ↓
Status History
    ↓
Branch
    ↓
Commit History
    ↓
Pull Request
    ↓
Review + CI
    ↓
Merge
    ↓
Jira Done
```

Khi báo cáo, nhóm chỉ cần trình bày:

```text
Kế hoạch
→ Task được giao
→ Quá trình thực hiện trên Jira
→ Commit/PR trên GitHub
→ Test/CI
→ Kết quả
→ Việc tiếp theo
```

Không cần viết lại nhật ký thủ công nếu Jira và GitHub đã được cập nhật đúng quy trình.

---

# 15. Kết quả cuối cùng

SCRUM-7 hoàn thành khi repository trở thành **development foundation dùng chung cho cả team**.

Một thành viên mới chỉ cần:

```bash
git clone ...
cp .env.example .env
docker compose up --build
```

và có thể bắt đầu phát triển module của Jira ticket riêng mà không cần thay đổi lại cấu trúc repository hoặc môi trường local.

---

# 29. Current Jira State

Trạng thái hiện tại:

| Jira | Status |
|---|---|
| SCRUM-24 | **In Progress** |
| SCRUM-25 | To Do |
| SCRUM-26 | To Do |
| SCRUM-27 | To Do |
| SCRUM-28 | To Do |
| SCRUM-29 | To Do |
| SCRUM-30 | To Do |
| SCRUM-31 | To Do |

Agent phải tập trung vào **WP1 / SCRUM-24** trước.

Khi SCRUM-24 hoàn tất implementation:

```text
SCRUM-24: In Progress → In Review
```

Sau khi review/accept:

```text
SCRUM-24: In Review → Done
SCRUM-25: To Do → In Progress
```

Không chuyển toàn bộ SCRUM-25..31 sang `In Progress` cùng lúc.
