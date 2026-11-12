#!/usr/bin/env bash
# Restore Amakuru Postgres from a gzipped SQL dump.
# Usage: ./infra/backup/restore.sh path/to/dump.sql.gz
# WARNING: replaces the target database contents.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DUMP="${1:-}"

if [[ -z "$DUMP" || ! -f "$DUMP" ]]; then
  echo "Usage: $0 path/to/amakuru_*.sql.gz" >&2
  exit 1
fi

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

POSTGRES_USER="${POSTGRES_USER:-amakuru}"
POSTGRES_DB="${POSTGRES_DB:-amakuru}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"

if [[ -f "${DUMP}.sha256" ]]; then
  echo "Verifying checksum…"
  (cd "$(dirname "$DUMP")" && sha256sum -c "$(basename "$DUMP").sha256")
fi

echo "Restoring $DUMP into ${POSTGRES_DB} @ ${POSTGRES_HOST}:${POSTGRES_PORT}"
echo "This will DROP and recreate the public schema objects from the dump."

confirm="${AMAKURU_RESTORE_CONFIRM:-}"
if [[ "$confirm" != "YES" ]]; then
  echo "Set AMAKURU_RESTORE_CONFIRM=YES to proceed." >&2
  exit 2
fi

if command -v docker >/dev/null 2>&1 && docker compose -f "$ROOT/docker-compose.yml" ps postgres 2>/dev/null | grep -q Up; then
  gunzip -c "$DUMP" | docker compose -f "$ROOT/docker-compose.yml" exec -T postgres \
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1
else
  export PGPASSWORD="${POSTGRES_PASSWORD:-change-me}"
  gunzip -c "$DUMP" | psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" -v ON_ERROR_STOP=1
fi

echo "Restore complete."
