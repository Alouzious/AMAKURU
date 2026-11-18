# Architecture overview

Amakuru is a verified FAQ assistant for organizations (universities, companies, sites, and other teams): one FastAPI API, one worker, one Vite React (JSX) admin app, and one Preact (JSX) widget bundle. Configure one organization at a time.

**User flows and more diagrams:** [flows.md](flows.md)

## System context

Who talks to what in production (or on a single VPS with Docker Compose).

```mermaid
flowchart LR
  subgraph users [Users]
    S[Student or parent]
    O[Organization staff]
    P[Platform admin]
  end
  subgraph edges [Clients]
    W[Web widget]
    WA[WhatsApp Cloud API]
    ADM[Admin dashboard]
  end
  subgraph core [Amakuru]
    API[FastAPI API and worker]
    R[(Redis)]
    DB[(PostgreSQL with pgvector)]
  end
  subgraph external [Optional external]
    LLM[LLM provider]
    TR[Translation provider]
  end
  S --> W
  W --> API
  S --> WA
  WA --> API
  O --> ADM
  ADM --> API
  P --> ADM
  API --> R
  API --> DB
  API -.-> LLM
  API -.-> TR
```

| Piece | Path | Role |
|-------|------|------|
| API | `backend/` | Auth, knowledge, retrieval, generation, channels, billing, analytics |
| Admin | `frontend/` | Office workflows and why-this-answer traces (Vite React, JSX) |
| Widget | `frontend/widget/` | Shadow DOM embed (small gzip bundle, Preact JSX) |
| Data | PostgreSQL 16 with pgvector | Relational data, vectors, FTS, RLS |
| Cache | Redis 7 | Reply cache, rate limits, background jobs |

**Repo layout:** `backend/`, `frontend/`, `frontend/widget/`, `packages/api-client`, `eval/`, `docs/`, `infra/`.

## Module boundaries

Modules talk through typed services. They never query another module's tables directly.

```mermaid
flowchart TB
  identity --> tenancy
  knowledge --> identity
  retrieval --> knowledge
  generation --> retrieval
  channels --> generation
  channels --> knowledge
  billing --> tenancy
  analytics --> channels
  evaluation --> retrieval
  platform --> identity
```

| Module | Scope |
|--------|--------|
| `identity` | Users, sessions, memberships, CSRF, TOTP |
| `tenancy` | Organizations (tenants), branding |
| `knowledge` | Offices, answer entries/versions, import, connectors, expiry |
| `retrieval` | Embeddings, hybrid search, rerank, decision policy, traces |
| `generation` | LLM gateway, compose, number firewall, scrubber, translation |
| `channels` | Widget chat, WhatsApp webhook, hand-off, unanswered queue |
| `billing` | Plans, entitlements, metering, API keys, onboarding |
| `analytics` | Dashboard aggregates |
| `evaluation` | Golden sets, eval runs |
| `platform` | Health, metrics, audit log |

## Query pipeline

```mermaid
flowchart TD
  A[Normalise and size limit] --> B[Scrub PII]
  B --> C[Detect language]
  C --> D{Follow-up}
  D -->|yes| E[Rewrite with cheap model]
  D -->|no| F[Cache lookup]
  E --> F
  F -->|hit| Z[Reply]
  F -->|miss| G[Hybrid retrieve]
  G --> H[Rerank candidates]
  H --> I{Decision policy}
  I -->|greeting| Z
  I -->|verbatim| Z
  I -->|compose| J[LLM grounded reply]
  J --> K[Number firewall]
  K -->|ok| L[Optional translate]
  K -->|fail| V[Fall back to approved text]
  L --> Z
  V --> Z
  I -->|clarify| Z
  I -->|handoff| M[Office contact and unanswered queue]
  M --> Z
  Z --> N[Store query trace and usage]
```

| Path | Meaning |
|------|---------|
| **verbatim** | Return approved text as written (no LLM cost) |
| **compose** | Short grounded rewrite; firewall discards invented numbers or contacts |
| **clarify** | Ask one question when candidates differ only by applicability |
| **hand-off** | Honest uncertainty plus office contacts |

## Tenant isolation

```mermaid
sequenceDiagram
  participant Client
  participant API
  participant DB as Postgres RLS

  Client->>API: Request with auth or widget key
  API->>DB: BEGIN
  API->>DB: SET LOCAL app.tenant_id
  API->>DB: Query tenant tables
  Note over DB: Policies allow matching tenant only
  API->>DB: COMMIT
```

The `amakuru_app` role has `NOBYPASSRLS`. Isolation tests under `backend/tests/isolation/` must stay green.

## Knowledge lifecycle

```mermaid
stateDiagram-v2
  [*] --> draft
  draft --> in_review: editor submits
  in_review --> approved: other office approver
  in_review --> draft: reject
  approved --> published: publish
  published --> expired: past valid_until
  published --> archived: replaced
  expired --> archived
```

Editor of a version cannot approve it. Expiry reminders fire at 30 / 14 / 3 days.

## Data model (ERDs)

Entity-relationship diagrams for each domain (tenancy, knowledge, retrieval, channels, billing), with explanations:

→ **[data-model.md](data-model.md)**

## Related docs

- [ADRs](../adr/) - significant design choices  
- [Runbooks](../runbooks/) - common incidents  
- [Compliance templates](../compliance/) - Uganda DPPA-oriented drafts (not legal advice)  
- [OpenAPI](../api/openapi.json) - generated API contract  
