# Backup / Restore Runbook

## Mục tiêu

Kiểm chứng backup/restore thay vì chỉ cấu hình. Không restore trực tiếp vào production để "thử".

## Backup

```bash
POSTGRES_HOST=localhost POSTGRES_DB=cabqp POSTGRES_USER=cabqp \
  ./ops/scripts/backup_postgres.sh
```

Script tạo PostgreSQL custom-format dump + SHA256.

## Restore drill

1. Tạo DB rỗng riêng, ví dụ `cabqp_restore_drill`.
2. Chạy:

```bash
POSTGRES_DB=cabqp_restore_drill ./ops/scripts/restore_postgres.sh backups/cabqp_<timestamp>.dump
```

3. Kiểm tra các bảng `alembic_version`, `registry_versions`, `units`, `cases`, `audit_logs`.
4. Chạy API smoke test trên DB restore, không dùng dữ liệu production thật ở môi trường public.
5. Ghi lại RTO/RPO thực tế và checksum backup vào biên bản vận hành.

## Failure rules

- Checksum sai: dừng restore.
- Migration version không khớp release manifest: dừng cutover.
- Restore drill fail: release gate fail.
