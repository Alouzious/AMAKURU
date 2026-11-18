# User flows and diagrams

Mermaid diagrams for Amakuru. They render on GitHub and in most Markdown previews.

Related: [overview.md](overview.md) · [data-model.md](data-model.md)

---

## 1. System context

Who uses what, and what Amakuru talks to.

```mermaid
flowchart LR
  subgraph people [People]
    V[Visitor]
    S[Staff]
  end
  subgraph sites [Sites]
    HOST[Organization website]
    WA[WhatsApp]
    ADM[Admin dashboard]
  end
  subgraph amakuru [Amakuru]
    W[Chat widget]
    API[FastAPI]
    WRK[Worker]
    DB[(Postgres)]
    R[(Redis)]
  end
  subgraph external [Optional]
    LLM[LLM provider]
    SRC[Org DB or API or site]
  end
  V --> HOST
  HOST --> W
  W --> API
  V --> WA
  WA --> API
  S --> ADM
  ADM --> API
  API --> DB
  API --> R
  API -.-> LLM
  WRK --> DB
  WRK --> SRC
  SRC --> API
```

---

## 2. Visitor ask flow

End-to-end path when someone asks a question on the widget (or WhatsApp / API).

```mermaid
flowchart TD
  A[Visitor opens chat popup] --> B[Types question or taps topic]
  B --> C[API: scrub and detect language]
  C --> D{Cache hit?}
  D -->|yes| R[Return cached reply]
  D -->|no| E[Embed question]
  E --> F[Hybrid search: vector plus keyword]
  F --> G[Rerank candidates]
  G --> H{Decision}
  H -->|strong match| I[Return approved text verbatim]
  H -->|good match| J[Optional LLM rephrase from sources only]
  J --> K[Number firewall]
  K -->|pass| L[Reply to visitor]
  K -->|fail| I
  H -->|ambiguous| M[Ask clarifying question]
  H -->|weak or escalate| N[Hand off with office contacts]
  I --> O[Store search event and trace]
  L --> O
  M --> O
  N --> O
  R --> O
```

---

## 3. Sequence: widget ask

```mermaid
sequenceDiagram
  participant V as Visitor
  participant W as Widget
  participant API as FastAPI
  participant DB as Postgres
  participant LLM as LLM optional

  V->>W: Ask question
  W->>API: POST public chat stream
  API->>API: Scrub and language
  API->>DB: Hybrid retrieve published answers
  API->>API: Decide path
  alt verbatim
    API-->>W: Approved text
  else compose
    API->>LLM: Grounded rephrase
    LLM-->>API: Draft reply
    API->>API: Number firewall
    API-->>W: Safe reply
  else handoff
    API->>DB: Unanswered queue
    API-->>W: Contacts card
  end
  API->>DB: Search event plus trace
  W-->>V: Show reply
```

---

## 4. Staff governance flow

How answers become live. Editors do not approve their own versions.

```mermaid
flowchart TD
  A[Editor drafts answer] --> B[Submit for review]
  B --> C[Status: in_review]
  C --> D[Different approver reviews]
  D -->|reject| A
  D -->|approve| E[Status: approved]
  E --> F[Publish]
  F --> G[Status: published]
  G --> H[Indexed for retrieval]
  G --> I{Valid until date}
  I -->|still valid| J[Bot may serve it]
  I -->|expired| K[Auto unpublish]
  K --> L[Hand off until updated]
```

---

## 5. Knowledge intake flow

Connectors and live searches feed drafts. Humans still publish.

```mermaid
flowchart LR
  subgraph sources [Sources]
    SQL[Org SQL DB]
    REST[REST JSON API]
    WEB[Website crawl]
    CSV[CSV Excel]
    ASK[Live visitor questions]
  end
  subgraph amakuru [Amakuru]
    CON[Connectors sync]
    SE[Search events]
    DR[Drafts or needs-answer]
    RV[Review and publish]
    BK[Published answer bank]
  end
  SQL --> CON
  REST --> CON
  WEB --> CON
  CSV --> CON
  CON --> DR
  ASK --> SE
  SE -->|promote hot unanswered| DR
  DR --> RV
  RV --> BK
```

---

## 6. Embed on a customer site

You host Amakuru. Their site only loads the popup script.

```mermaid
flowchart LR
  subgraph you [Your hosting]
    API[Amakuru API]
    JS[amakuru-widget.js]
    DB[(Answer bank)]
  end
  subgraph customer [Customer website]
    PAGE[Any HTML page]
    POP[Chat popup]
  end
  PAGE -->|script tag plus widget key| JS
  JS --> POP
  POP -->|ask over HTTPS| API
  API --> DB
```

Embed snippet (replace host and key):

```html
<script>
  window.AmakuruConfig = {
    apiBase: "https://api.yourdomain.com",
    key: "ak_live_CUSTOMER_KEY",
    language: "en"
  };
</script>
<script src="https://api.yourdomain.com/widget/amakuru-widget.js" defer></script>
```

---

## 7. Organization onboarding flow

```mermaid
flowchart TD
  A[Create organization] --> B[Set branding and language]
  B --> C[Add offices or teams]
  C --> D[Invite staff roles]
  D --> E[Connect knowledge source]
  E --> F[Sync drafts]
  F --> G[Approve and publish]
  G --> H[Copy widget embed]
  H --> I[Allow site origin]
  I --> J[Go live on website]
  J --> K[Watch live searches and gaps]
```

---

## 8. Worker jobs

```mermaid
flowchart TD
  W[Worker loop] --> E[Expiry: unpublish and remind]
  W --> C[Sync active connectors]
  W --> S[Promote hot unanswered searches]
  E --> DB[(Postgres)]
  C --> DB
  S --> DB
```

---

## 9. Multi-organization isolation

```mermaid
flowchart TB
  subgraph orgA [Organization A]
    WA[Widget A]
    DA[Dashboard A]
    KA[Knowledge A]
  end
  subgraph orgB [Organization B]
    WB[Widget B]
    DB[Dashboard B]
    KB[Knowledge B]
  end
  API[Amakuru API]
  PG[(Postgres with RLS)]
  WA --> API
  DA --> API
  WB --> API
  DB --> API
  API --> PG
  KA --- PG
  KB --- PG
```

Row Level Security ensures A never reads B’s data (and the reverse).

---

## Where to look in code

| Flow | Main code |
|------|-----------|
| Ask pipeline | `backend/src/amakuru/modules/retrieval/service.py` |
| Widget chat | `backend/src/amakuru/modules/channels/` · `frontend/widget/` |
| Governance | `backend/src/amakuru/modules/knowledge/` |
| Connectors | `backend/src/amakuru/modules/knowledge/adapters/` · dashboard **Connectors** |
| Live searches | `backend/src/amakuru/modules/knowledge/search_intel.py` · dashboard **Live searches** |
| Worker | `backend/src/amakuru/worker.py` |
| Embed demo | http://localhost:8000/widget/demo |
