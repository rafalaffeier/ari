#!/bin/sh
set -eu

: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${BACKUP_FILE:?BACKUP_FILE must point to a .dump file inside /backups}"

export PGPASSWORD="${POSTGRES_PASSWORD}"

pg_restore \
  --host="${POSTGRES_HOST:-db}" \
  --port="${POSTGRES_PORT:-5432}" \
  --username="${POSTGRES_USER}" \
  --dbname="${POSTGRES_DB}" \
  --clean \
  --if-exists \
  --no-owner \
  "${BACKUP_FILE}"

echo "RESTORE_OK ${BACKUP_FILE}"
