# ADR 0004 - Widget key auth and WhatsApp webhook

## Status

Accepted - Phase 4

## Context

Public channels must never use staff session cookies. Each university needs its own embed key and WhatsApp number, with origin restrictions and Meta signature verification.

## Decision

- Widget clients authenticate with `X-Amakuru-Key`; only the SHA-256 hash is stored (`channel_configs`).
- Allowed origins are checked when an `Origin`/`Referer` header is present.
- WhatsApp webhooks verify `X-Hub-Signature-256` with `META_APP_SECRET`, dedupe message IDs in Redis for 24h, and answer via the Cloud API using the tenant’s encrypted access token.
- The Preact widget ships as a single IIFE under Shadow DOM so host page CSS cannot clash.

## Consequences

- Universities rotate keys by minting a new hash row (admin UI in Phase 5).
- Local demos work without Meta; production WhatsApp needs secrets in env + per-tenant token.
