# REDCap Batch Looking Webapp

Canonical project root for the REDCap batch locking/unlocking web application.

**Architecture & delivery plan:** [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)

## Current status

The repository now includes:

- FastAPI backend with cookie-based authentication and DB-backed sessions
- Built-in FastAPI-served UI for login, jobs, mappings, reports, and user management
- SQLAlchemy models plus Alembic migrations for jobs, mappings, sessions, audit events, reports, and REDCap host configuration
- Authenticated jobs import flow with:
  - template export
  - request CSV validation
  - REDCap API URL / API key intake
  - optional existing queries CSV import
  - REDCap preflight validation and metadata fetch
- Mapping review flow for lock-status fields, lock-date fields, and per-instrument confirmation
- Background job execution for lock/unlock processing with inline progress updates on the Jobs page
- Project-scoped REDCap API rate limiting with visible wait/resume messaging
- CSV report generation and export for completed, partial-error, and failed jobs
- Session-scoped encrypted REDCap API key cache so repeat processing in the same session does not always prompt again
- Docker Compose for API + PostgreSQL

## Implemented snapshot

As of 15 April 2026, the app supports the following end-to-end workflow:

1. User signs in and opens the Jobs page.
2. User exports the request template or imports a request package.
3. Import preflight validates the request CSV, checks REDCap connectivity, fetches metadata, inspects optional unresolved queries CSV content, and creates a draft job.
4. If field detection is ambiguous or missing, the user confirms mappings on the Mappings page.
5. The job can then be processed in the background from the Jobs page.
6. The UI shows background progress, processed row counts, and REDCap rate-limit wait/resume state.
7. A CSV execution report can be exported from Jobs or Reports once processing finishes.

## Current gaps / next major work

- Background execution currently uses in-process worker threads, not Celery/Redis yet.
- There is no true distributed worker queue or resumable worker infrastructure yet.
- The UI is still FastAPI/Jinja based; the planned Next.js frontend is not built.
- Automated test coverage is still limited.

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
