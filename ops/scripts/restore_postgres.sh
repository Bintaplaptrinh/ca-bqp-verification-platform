#!/usr/bin/env sh
set -eu
if [ "$#" -ne 1 ]; then
  echo "usage: $0 <backup.dump>" >&2
  exit 2
fi
BACKUP=$1
: "${POSTGRES_HOST:=localhost}"
: "${POSTGRES_PORT:=5432}"
: "${POSTGRES_DB:=cabqp_restore_drill}"
: "${POSTGRES_USER:=cabqp}"
if [ ! -f "$BACKUP" ]; then echo "backup not found: $BACKUP" >&2; exit 2; fi
if [ -f "$BACKUP.sha256" ]; then sha256sum -c "$BACKUP.sha256"; fi
pg_restore -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner "$BACKUP"
echo "restored into $POSTGRES_DB"
