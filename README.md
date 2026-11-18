# Amakuru

Verified FAQ assistant for **organizations**: universities, companies, NGOs, clinics, government offices, and any website that needs trustworthy answers.

Teams write and approve answers. The bot answers from that bank only (widget and optional WhatsApp). If it is not sure, it hands the person to the right team with contact details.

Configure one organization at a time (branding, teams/offices, knowledge). You can later connect another organization’s data the same way.

---

## What it includes

| Part | Purpose |
|------|---------|
| **Web widget** | Embed on your site; mobile-friendly chat |
| **WhatsApp** | Optional Cloud API channel |
| **Admin dashboard** | Answer bank, review, connectors, live searches, conversations, evaluation, team |
| **REST API** | FastAPI backend (`/api/v1`) with OpenAPI at `/docs` |

How answers work:

- Only approved, published answers are used
- Numbers, dates, phones, emails and links must match the approved text
- Staff can see why an answer was given (trace)
- Connectors pull from your existing DB, API, or website into drafts

---

## Stack

| Layer | Choice |
|-------|--------|
| API | Python 3.12, FastAPI, SQLAlchemy 2, Alembic |
| DB | PostgreSQL 16 with pgvector |
| Cache / jobs | Redis 7, ARQ |
| Admin | Vite + React (JSX), Tailwind, React Router |
| Widget | Preact (JSX), Shadow DOM |
| Deploy | Docker Compose |

**Folders:** `backend/` · `frontend/` · `frontend/widget/` · `docs/` · `infra/` · `eval/`

Architecture notes and ERDs: [docs/architecture/](docs/architecture/).

---

## Quick start

**Prerequisites:** Docker Compose, Node 20+, Python 3.12+.

```bash
# Database
docker compose up -d postgres redis

# API
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
alembic upgrade head
# optional: python -m amakuru.scripts.seed
uvicorn amakuru.main:app --host 0.0.0.0 --port 8000 --reload
```

```bash
# Dashboard
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

```bash
# Widget bundle (served by the API from frontend/widget/dist)
cd frontend/widget
npm install
npm run build
```

Copy `.env.example` to `.env` and fill secrets before first run. Do not commit `.env`.

Default seed admin (if you run seed):

- Email: `admin@example.com`
- Password: `ChangeMeNow123!`

Demo content is labelled demonstration only. Do not invent real fees, dates or contacts for a real organization.

API docs: http://localhost:8000/docs  
Chat demo: http://localhost:8000/widget/demo  

### Useful commands (if using the Makefile)

| Command | Purpose |
|---------|---------|
| `make doctor` | Check settings, DB, Redis |
| `make test` | Backend tests |
| `make migrate` / `make seed` | Schema + demo data |
| `make widget` | Build the embed script |

---

## Configuration

`.env.example` lists every setting. Channel secrets (for example WhatsApp tokens) are stored encrypted in the database after you enter them in the dashboard.

---

## Licence

Project work for **Beta-Tech Labs Co. Limited**.
