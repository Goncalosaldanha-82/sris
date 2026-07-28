#!/usr/bin/env sh
set -eu
: "${DATABASE_URL:?DATABASE_URL is required}"
TS=$(date -u +%Y%m%dT%H%M%SZ)
OUT=${BACKUP_DIR:-/backups}/sris-${TS}.dump
mkdir -p "$(dirname "$OUT")"
pg_dump "$DATABASE_URL" --format=custom --no-owner --file="$OUT"
sha256sum "$OUT" > "$OUT.sha256"
python /app/scripts/upload_backup.py "$OUT" || true
find "$(dirname "$OUT")" -type f -name 'sris-*.dump' -mtime +${BACKUP_RETENTION_DAYS:-30} -delete
printf '%s\n' "$OUT"
