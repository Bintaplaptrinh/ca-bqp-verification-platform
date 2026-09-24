# CA/BQP Web - React + TypeScript

Frontend nghiệp vụ dùng React 19 + TypeScript + Vite. UI được build từ source TSX/JSX,
dữ liệu nghiệp vụ lấy trực tiếp từ FastAPI qua `/api/v1/*` - không có dữ liệu
case/review/registry hardcode trong frontend.

## Luồng runtime

- `App.tsx` là một auth-gate mỏng: kiểm tra phiên đăng nhập hiện có
  (`fetchCurrentUser()`), hiển thị form đăng nhập khi chưa đăng nhập, nhắc đổi
  mật khẩu khi tài khoản còn dùng mật khẩu do quản trị viên cấp, rồi render
  `VerificationModule` -> `CABQPVerification.jsx` (giao diện nghiệp vụ chính).
- Đăng nhập qua tài khoản nội bộ của hệ thống (không có identity provider
  ngoài): form thật gọi `POST /api/v1/auth/login`, server trả về một session
  token không mang thông tin quyền - quyền được đọc lại từ database ở mọi
  request.
- Trong Docker, Nginx reverse-proxy `/api/v1/*` sang service `backend:8000`
  (same-origin). Ở profile local, Vite dev server proxy `/api` và `/health`
  sang `http://localhost:8000`.

## Local development

```bash
npm install --no-audit --no-fund
npm run dev
```

## Quality checks

```bash
npm run typecheck
npm run build
```

## End-to-end tests

```bash
npx playwright install chromium   # một lần mỗi máy
npx playwright test
```

Các spec đăng nhập qua form thật (`e2e/helpers.ts`'s `signInAs()`) bằng tài
khoản đã seed (`admin`/`admin`, `user`/`user`); không còn đường tắt dev-login.
E2E cần backend thật đang chạy cùng `npm run dev`.
