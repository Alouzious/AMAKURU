# Runbook: Database unavailable

## Symptoms

- `/ready` → `database: false`
- API logs show asyncpg connection errors
- Migrations / seed fail

## Checks

```bash
docker compose ps postgres
docker compose exec postgres pg_isready -U amakuru
docker compose logs postgres --tail=100
```

## Mitigations

1. `docker compose up -d postgres` and wait for healthy.
2. If disk full, free space under `/var/lib/docker` or move volumes.
3. Restore from latest backup if data corruption is confirmed:
   - `make backup` (capture current state if possible)
   - `AMAKURU_RESTORE_CONFIRM=YES ./infra/backup/restore.sh .backups/<file>.sql.gz`
4. Re-run `make migrate` after restore.

## Verify

`pg_isready` succeeds; `/ready` database true; login works.
