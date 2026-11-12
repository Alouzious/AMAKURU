# Runbook: LLM provider errors / rate limits

## Symptoms

- Composed answers fall back to verbatim approved text
- Traces show `compose_fallback_verbatim` or circuit-open providers
- HTTP 429 from Groq / fallback vendor

## Checks

```bash
# Confirm settings (do not paste secrets into chat)
grep -E '^(LLM_|ALLOW_EXTERNAL)' .env
curl -sS http://127.0.0.1:8000/metrics | head
```

Inspect recent `query_traces.steps` for compose / firewall paths in the admin Conversations screen.

## Mitigations

1. Prefer verbatim / cache paths - product remains correct.
2. If 429: wait for Retry-After; circuit breaker opens automatically.
3. Switch `LLM_PROVIDER` / fallback base URL, or set `ALLOW_EXTERNAL_AI_CALLS=false` for sovereign stub mode.
4. Re-index is not required for LLM outages.

## Verify

Ask a `compose`-band question; either composed reply returns or safe verbatim fallback with firewall OK.
