# Sovereign mode

## Intent

Operate Amakuru without sending question or knowledge text to AI providers outside the approved residency boundary (typically Uganda / self-hosted).

## Configuration

```bash
ALLOW_EXTERNAL_AI_CALLS=false
EMBEDDING_PROVIDER=hash   # or local self-hosted BGE when models are on disk
TRANSLATION_PROVIDER=none # or in-country Fasiri / approved endpoint
LLM_PROVIDER=stub         # or self-hosted OpenAI-compatible base URL inside country
```

Effects:

- `build_llm_gateway` uses `StubLLMGateway` / in-country endpoint only.
- Sunbird remote calls are skipped when external AI is disallowed.
- Product remains correct: verbatim approved answers, keyword/dense retrieval, number firewall.

## Operator checklist

1. Confirm model weights and translation services reside in approved locations.
2. Disable optional Sentry/Langfuse if they export abroad.
3. Document the residency mode on the tenant (`residency_mode`).
4. Re-run `make eval` after switching modes - scores may change; do not weaken thresholds to pass.
