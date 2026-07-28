#!/usr/bin/env sh
set -eu
: "${DATABASE_URL:?DATABASE_URL is required}"
: "${1:?Usage: restore.sh backup.dump}"
sha256sum -c "$1.sha256"
pg_restore --clean --if-exists --no-owner --dbname="$DATABASE_URL" "$1"
