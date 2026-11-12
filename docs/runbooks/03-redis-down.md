# Runbook: Redis unavailable / cache storm

## Symptoms

- `/ready` → `redis: false`
- Reply cache misses always; WhatsApp dedupe may fail open to duplicates
- Worker / ARQ jobs stall (when enabled)

## Checks

```bash
docker compose ps redis
docker compose exec redis redis-cli ping
docker compose logs redis --tail=100
```

## Mitigations

1. `docker compose up -d redis`
2. If Redis memory is exhausted: `redis-cli INFO memory` then flush only non-critical keys or restart Redis (accept cache cold start).
3. API remains correct without cache - expect higher latency and LLM cost until warm.

## Verify

`PONG` from redis-cli; `/ready` redis true; second identical widget question shows `cache_hit` in traces when enabled.
