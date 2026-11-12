# Backup and restore

## Nightly backup

```bash
make backup
# writes .backups/amakuru_<db>_<timestamp>.sql.gz (+ .sha256)
```

Schedule via cron on the VPS, e.g. `15 2 * * * cd /opt/amakuru && make backup`.

## Restore (destructive)

```bash
AMAKURU_RESTORE_CONFIRM=YES make restore DUMP=.backups/amakuru_amakuru_YYYYMMDD….sql.gz
make migrate   # if dump predates latest migrations, apply forward only with care
```

## Restore drill (non-destructive)

```bash
make restore-drill
# Creates amakuru_restore_drill DB, restores into it, verifies table counts, drops it.
```

Exit criterion for Phase 6: `RESTORE_DRILL_PASSED` printed.
