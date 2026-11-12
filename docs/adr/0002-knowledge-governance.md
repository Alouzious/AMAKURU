# ADR 0002: Knowledge governance as immutable versions

## Status

Accepted - 12 November 2026

## Context

Universities must trust that answers are approved, dated, and traceable. Competitors in this market lack strong governance.

## Decision

Model answers as stable `answer_entries` with immutable `answer_versions`. Workflow is draft → in_review → approved → published (then expired/archived). The editor of a version cannot approve it. Approvers require TOTP when configured. Imports and connectors only create drafts. Expiry is enforced by a worker.

## Consequences

- Trust and auditability are first-class
- Retrieval (Phase 2) indexes only published, unexpired versions
- Dashboard (Phase 5) surfaces the same lifecycle the API already enforces
