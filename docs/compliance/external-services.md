# External services and data flows (template)

Describe every external service Amakuru may call and what it receives. Keep this aligned with `.env` / tenant settings.

| Service | When used | Data sent | Data stored externally | Notes |
|---------|-----------|-----------|------------------------|-------|
| LLM provider (e.g. Groq OpenAI-compatible) | `compose` path when external AI allowed | System prompt + scrubbed question + approved source snippets | Per provider retention policy | No tools; number firewall after |
| Embedding remote (optional) | If `EMBEDDING_PROVIDER=openai_compatible` | Question / answer text | Per provider | Default is local/hash |
| Sunbird AI | Translation / language id when token set | Text with locked number placeholders | Per Sunbird policy | Firewall re-run after unlock |
| Meta WhatsApp Cloud API | WhatsApp channel enabled | Outbound reply text; inbound webhook payloads | Meta | Signature verify + dedupe |
| Email provider (SMTP/Resend) | Optional hand-off / expiry reminders | Question + conversation ref | Provider logs | Not required for core chat |
| Object storage (S3-compatible) | Optional file sources | Uploaded docs | Bucket | SSRF protections on fetches |
| Sentry / OTEL / Langfuse | Optional observability | Errors, traces, prompts if enabled | Vendor | Disable in sovereign deployments if required |

**Sovereign mode:** set `ALLOW_EXTERNAL_AI_CALLS=false` and use self-hosted/in-country models only - see [sovereign-mode.md](sovereign-mode.md).
