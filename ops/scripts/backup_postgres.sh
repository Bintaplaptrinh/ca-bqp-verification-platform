#!/usr/bin/env sh
set -eu
: "${POSTGRES_HOST:=localhost}"
: "${POSTGRES_PORT:=5432}"
: "${POSTGRES_DB:=cabqp}"
: "${POSTGRES_USER:=cabqp}"
: "${BACKUP_DIR:=./backups}"
mkdir -p "$BACKUP_DIR"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT="$BACKUP_DIR/${POSTGRES_DB}_${STAMP}.dump"
pg_dump -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f "$OUT"
sha256sum "$OUT" > "$OUT.sha256"
echo "$OUT"
