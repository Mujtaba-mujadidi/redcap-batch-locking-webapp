# REDCap Batch Looking Webapp

Canonical project root for the REDCap batch locking/unlocking web application.

**Architecture & delivery plan:** [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)

## Phase 0 — Hello World API

Backend lives in `backend/` (FastAPI). Run:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- App: **http://127.0.0.1:8000/** — JSON `{"message":"Hello World"}`
- Docs: **http://127.0.0.1:8000/docs**

## Docker (Phase A — API only)

From the **project root** (this directory):

```bash
docker compose build
docker compose up
```

Same URLs as above. After code changes:

```bash
docker compose up --build
```

Implementation scaffold (Celery, Postgres, Redis, frontend) will be added in later phases.
