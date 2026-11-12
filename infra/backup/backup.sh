#!/usr/bin/env bash
# Nightly-style Postgres backup for Amakuru.
# Usage: ./infra/backup/backup.sh [output_dir]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT_DIR="${1:-$ROOT/.backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT_DIR"

# Load .env if present (do not print secrets)
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
FILE="$OUT_DIR/amakuru_${POSTGRES_DB}_${STAMP}.sql.gz"

echo "Backing up ${POSTGRES_DB} @ ${POSTGRES_HOST}:${POSTGRES_PORT} → ${FILE}"

if command -v docker >/dev/null 2>&1 && docker compose -f "$ROOT/docker-compose.yml" ps postgres 2>/dev/null | grep -q Up; then
  docker compose -f "$ROOT/docker-compose.yml" exec -T postgres \
    pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --format=plain \
    | gzip -c > "$FILE"
else
  export PGPASSWORD="${POSTGRES_PASSWORD:-change-me}"
  pg_dump -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    --no-owner --format=plain | gzip -c > "$FILE"
fi

# Keep last 14 backups
ls -1t "$OUT_DIR"/amakuru_*.sql.gz 2>/dev/null | tail -n +15 | xargs -r rm -f

sha256sum "$FILE" > "${FILE}.sha256"
echo "OK $(du -h "$FILE" | awk '{print $1}')"
echo "$FILE"
