# REDCap Batch Looking Webapp

Canonical project root for the REDCap batch locking/unlocking web application.

**Architecture & delivery plan:** [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)

## Current status

The repository now includes:

- FastAPI backend scaffold in `backend/`
- SQLAlchemy models for the Phase 4 data model
- Alembic migration scaffolding and the first core schema revision
- Cookie-based authentication endpoints with DB-backed sessions
- A built-in web login UI served by FastAPI
- Docker Compose for API + PostgreSQL

## Backend development

Backend lives in `backend/` (FastAPI). Run:

```bash
docker compose up -d postgres

cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg://redcap_app:redcap_app@localhost:5432/redcap_batch_locking
./scripts/migrate.sh
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- App: **http://127.0.0.1:8000/** — redirects to the login UI
- Login: **http://127.0.0.1:8000/login**
- Authenticated home: **http://127.0.0.1:8000/app**
- Health: **http://127.0.0.1:8000/health**
- Docs: **http://127.0.0.1:8000/docs**

## Bootstrap the first admin user

After migrations have been applied, create the first user:

```bash
cd backend
python scripts/create_superuser.py --email admin@example.com --full-name "Initial Admin"
```

You will be prompted for a password unless `--password` is supplied.

## Authentication endpoints

Initial authentication endpoints are available at:

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`

The login endpoint sets an HTTP-only cookie named `redcap_session` by default. Session records are stored in the database.

## Authentication UI

There is now a simple built-in UI for authentication:

- `/login` renders the sign-in form
- `/app` renders a protected authenticated page
- `/` redirects to `/login` or `/app` depending on whether the session cookie is valid

## Docker (Phase 4 — API + Postgres)

From the **project root** (this directory):

```bash
docker compose build
docker compose up -d postgres
docker compose run --rm api ./scripts/migrate.sh
docker compose up api
```

Same URLs as above. After code changes:

```bash
docker compose up --build
```

## Database migrations

Alembic is the source of truth for database tables and schema changes.

Run locally:

```bash
cd backend
export DATABASE_URL=postgresql+psycopg://redcap_app:redcap_app@localhost:5432/redcap_batch_locking
./scripts/migrate.sh
```

## Production note

For production, the normal setup flow will be:

1. Provision the PostgreSQL database and credentials.
2. Set `DATABASE_URL` for the backend container or service.
3. Run `alembic upgrade head` or `./scripts/migrate.sh`.
4. Start the API service.

This means yes: there is now a repeatable migration command for setting up backend tables, and Alembic will handle future schema upgrades safely.
