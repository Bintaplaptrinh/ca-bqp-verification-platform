# Frontend Implementation — React + TypeScript

## Product boundary

Đây là **một Internal Portal React** cho ba role, không phải ba web độc lập. Backend luôn là authority cho RBAC, Registry Resolution, Policy Engine, workflow và audit. Frontend chỉ điều phối UX và gọi API thật.

- USER: tra cứu, tạo Case text/file/batch, xem result/evidence.
- REVIEWER: Review Queue theo coverage scope và optimistic-lock `expected_version`.
- ADMIN: Master Registry, Candidate QA, Registry Versions, Audit Log.

## Technology

- React 19 + TypeScript + Vite.
- Source nằm trong `apps/web/src/**/*.tsx|ts`; không còn `app.js`, `pages.js`, `config.js` runtime kiểu web tĩnh cũ.
- Nginx chỉ serve **bundle build** và reverse proxy `/api/*` sang FastAPI.
- Vite dev server proxy `/api` sang `localhost:8000`.
- CSS hiện giữ design system cũ để migration không làm thay đổi workflow/UI ngoài ý muốn.

> React SPA vẫn được Nginx phân phối dưới dạng static assets sau build, nhưng **dữ liệu và nghiệp vụ không tĩnh**: mọi Case/Review/Registry/Batch đều lấy từ backend API.

## FE ↔ BE runtime

```text
Browser
  ├─ React/TypeScript bundle ← Nginx :3000 (Docker) hoặc Vite :3000 (local)
  ├─ POST /api/v1/auth/login ─→ FastAPI, trả về session token opaque
  └─ /api/v1/* ──────────────→ FastAPI backend:8000 (Bearer = session token)

FastAPI
  └─ mỗi request: tra session → đọc lại quyền từ bảng app_users
```

Không có identity provider ngoài. Token phiên là 32 byte ngẫu nhiên, máy chủ chỉ lưu SHA-256 của nó và **không nhúng bất kỳ claim nào** vào token.

## Security

- Tài khoản nội bộ; mật khẩu PBKDF2-HMAC-SHA256 với salt riêng từng bản ghi.
- Token phiên lưu `sessionStorage`, không localStorage; thêm cookie `HttpOnly` cho same-origin.
- Mỗi API request gắn bearer token; 401/403 vẫn do backend quyết định.
- Route/menu guard **chỉ là UX**. Quyền được đọc lại từ cơ sở dữ liệu ở mọi request, nên sửa state phía client không mở thêm được gì — endpoint trả 403.
- Không hardcode case/review/registry data trong frontend.
- Same-origin `/api` giảm phụ thuộc CORS và tránh hardcode `http://localhost:8000`.

## Routes

| Route | Role | Backend chính |
|---|---|---|
| `#/dashboard` | USER+ | `/cases`, `/reviews`, registry stats |
| `#/lookup` | USER+ | `/lookup/unit` |
| `#/cases/new` | USER+ | `/cases/text`, `/cases/file`, `/bulk` |
| `#/cases` | USER+ | `/cases` |
| `#/cases/:id` | USER+ | `/cases/:id` |
| `#/reviews` | REVIEWER/ADMIN | `/reviews` |
| `#/admin/registry` | ADMIN | `/admin/registry/units` |
| `#/admin/candidates` | ADMIN | `/admin/registry/candidates` |
| `#/admin/versions` | ADMIN | `/admin/registry/versions` |
| `#/admin/audit` | ADMIN | `/admin/audit` |

## Build / quality gate

```bash
cd apps/web
npm install --no-audit --no-fund
npm run typecheck
npm run build
```

CI chạy cả typecheck và production build trước Docker image build.
