# Local validation

`ops/scripts/validate_release.py` chạy các kiểm tra không cần Docker:

- Python compile.
- Backend pytest.
- Xác nhận frontend đã migrate sang React/TypeScript và không còn legacy static runtime files.
- Khi `apps/web/node_modules` có sẵn: chạy `npm run typecheck` và `npm run build`.
- JSON/YAML parse.
- Calibration artifact reproducibility.

CI luôn cài npm dependencies rồi chạy TypeScript typecheck + Vite production build trước khi build frontend Docker image. Docker integration, migration PostgreSQL drill, vulnerability scan và release security gates được chạy trong CI/release workflows.
