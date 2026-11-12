# ADR 0003 - LLM gateway and number firewall

## Status

Accepted - Phase 3

## Context

Composed replies must stay faithful to approved answer text. Fees, dates, contacts, and URLs are high-risk if invented. The product must also run without a single LLM vendor and support sovereign mode (`ALLOW_EXTERNAL_AI_CALLS=false`).

## Decision

- All model calls go through `LLMGateway` (OpenAI-compatible HTTP) with a circuit breaker and configured fallback, ending in an offline `StubLLMGateway` when external calls are disabled or keys are missing.
- Grounded composition wraps approved sources in `<source>` delimiters and treats user/source text as untrusted data.
- Every composed or translated reply passes the **number firewall**: protected tokens in the output must appear character-for-character in the approved sources; otherwise the approved verbatim text is returned.
- Translation locks protected tokens to placeholders before calling a translator and re-runs the firewall afterwards.

## Consequences

- Tests and local demos work without Groq/Sunbird credentials.
- Production quality of composition depends on the configured model; safety does not.
