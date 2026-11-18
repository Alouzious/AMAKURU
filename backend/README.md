# Amakuru backend

FastAPI REST API for a verified FAQ assistant (widget, WhatsApp, and staff dashboard). Works for universities, companies, and other organizations.

Interactive docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## Layout

```
backend/
  requirements.txt          # pip dependencies
  pyproject.toml            # package metadata + installable amakuru
  alembic/                  # database migrations
  src/amakuru/
    main.py                 # FastAPI app
    api/v1.py               # all /api/v1 REST routes registered here
    core/                   # settings, db, security, errors
    modules/                # domain code (one folder per concern)
      identity/             # /api/v1/auth
      tenancy/              # /api/v1/tenants
      knowledge/            # answer bank
      retrieval/            # ask / search
      generation/           # LLM compose + firewall
      channels/             # widget + WhatsApp
      billing/              # plans, usage, API keys
      analytics/            # dashboard data
      evaluation/           # quality harness
      platform/             # health, metrics, audit
    scripts/                # seed, doctor, eval CLI
  tests/
```

## Run

```bash
cd backend
source .venv/bin/activate          # or create: python3 -m venv .venv
pip install -r requirements.txt
pip install -e .
alembic upgrade head
uvicorn amakuru.main:app --host 0.0.0.0 --port 8000 --reload
```

Postgres + Redis must already be up: from repo root, `docker compose up -d postgres redis`.

## Live knowledge (no endless CSV)

Connectors pull into **drafts** (staff still approve before answers go live):

| Adapter | Use |
|---------|-----|
| `sql_db` | Organization Postgres/MySQL/SQLite FAQ database |
| `rest_json` | Their JSON/REST FAQ API |
| `website` | Crawl public site pages → suggested Q&A |
| `spreadsheet` | One-off CSV/Excel |

Create: `POST /api/v1/tenants/{id}/connectors` then sync: `POST .../connectors/{id}/sync`.  
The worker also re-syncs active connectors on an interval.

Every chat question is stored in `search_events`. Hot unanswered questions can be promoted:  
`POST /api/v1/tenants/{id}/search-events/promote`.

Run the worker: `python -m amakuru.worker` (from `backend/` with venv active).
