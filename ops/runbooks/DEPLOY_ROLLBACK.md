# Deploy / Rollback Runbook

## Pre-release gates

- Backend tests + 8 Golden Suites pass.
- Policy regression pass 100%.
- Registry validation pass.
- Migration upgrade/downgrade drill pass trên DB test.
- Dependency/container scan không có critical finding chưa chấp nhận.
- Backup gần nhất được kiểm tra checksum.

## Deploy

1. Build image bằng commit SHA/tag.
2. Chạy `alembic upgrade head` bằng migration job.
3. Khởi động backend/worker, chờ `/health/ready`.
4. Smoke test lookup, text case, file case, review queue, admin Registry.
5. Mới chuyển traffic.

## Rollback application

- Roll back image trước nếu lỗi application không đòi rollback schema.
- Không downgrade DB tùy tiện nếu migration có data transform không reversible.
- Nếu cần schema rollback, dùng revision cụ thể đã diễn tập.

## Registry rollback

Không sửa snapshot `PUBLISHED` cũ. Dùng API `POST /api/v1/admin/registry/versions/rollback` để clone snapshot lịch sử thành version mới rồi publish atomically.
