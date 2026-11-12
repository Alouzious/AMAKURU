# Runbook: API down / not ready

## Symptoms

- `/health` fails or times out
- `/ready` returns `503` with `not_ready`
- Admin / widget cannot reach the API

## Checks

```bash
docker compose ps
curl -sS http://127.0.0.1:8000/health
curl -sS http://127.0.0.1:8000/ready
docker compose logs api --tail=200
```

## Mitigations

1. Restart API: `docker compose restart api` (or local uvicorn process).
2. If `/ready` shows database/redis false, follow those runbooks first.
3. Confirm `.env` is present and `SECRET_KEY` / `DATABASE_URL` parse.
4. Free disk / memory if the host OOM-killed the process.

## Verify

`/health` → `ok`, `/ready` → `ready`, widget demo loads.
