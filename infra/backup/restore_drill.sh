#!/usr/bin/env bash
# Non-destructive restore drill: backup → restore into a temporary database → verify → drop.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TMP_DIR="$ROOT/.backups/drill_${STAMP}"
mkdir -p "$TMP_DIR"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

POSTGRES_USER="${POSTGRES_USER:-amakuru}"
POSTGRES_DB="${POSTGRES_DB:-amakuru}"
DRILL_DB="amakuru_restore_drill"

echo "== 1. Take backup =="
DUMP="$("$ROOT/infra/backup/backup.sh" "$TMP_DIR" | tail -n1)"
test -f "$DUMP"

echo "== 2. Create drill database =="
docker compose -f "$ROOT/docker-compose.yml" exec -T postgres \
  psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 \
  -c "DROP DATABASE IF EXISTS ${DRILL_DB};" \
  -c "CREATE DATABASE ${DRILL_DB} OWNER ${POSTGRES_USER};"

# Ensure vector extension exists in drill DB
docker compose -f "$ROOT/docker-compose.yml" exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$DRILL_DB" -v ON_ERROR_STOP=1 \
  -c "CREATE EXTENSION IF NOT EXISTS vector;"

echo "== 3. Restore dump into drill DB =="
gunzip -c "$DUMP" | docker compose -f "$ROOT/docker-compose.yml" exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$DRILL_DB" -v ON_ERROR_STOP=1 >/dev/null

echo "== 4. Verify tables =="
COUNT="$(docker compose -f "$ROOT/docker-compose.yml" exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$DRILL_DB" -Atc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")"
echo "public tables: $COUNT"
test "$COUNT" -gt 5

TENANTS="$(docker compose -f "$ROOT/docker-compose.yml" exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$DRILL_DB" -Atc \
  "SELECT count(*) FROM tenants;" 2>/dev/null || echo 0)"
echo "tenants rows: $TENANTS"

echo "== 5. Drop drill database =="
docker compose -f "$ROOT/docker-compose.yml" exec -T postgres \
  psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 \
  -c "DROP DATABASE IF EXISTS ${DRILL_DB};"

echo "RESTORE_DRILL_PASSED"
echo "dump=$DUMP"
