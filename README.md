# REDCap Batch Looking Webapp

Canonical project root for the REDCap batch locking/unlocking web application.

**Architecture & delivery plan:** [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)

## Current status

The repository now includes:

- FastAPI backend with cookie-based authentication and DB-backed sessions
- Built-in FastAPI-served legacy UI for login, jobs, mappings, reports, and user management
- Separate Next.js frontend in `frontend/` with shared global CSS and typed API consumption
- SQLAlchemy models plus Alembic migrations for jobs, mappings, sessions, audit events, reports, and REDCap host configuration
- Authenticated jobs import flow with:
  - template export
  - request CSV validation
  - REDCap API URL / API key intake
  - optional existing queries CSV import
  - REDCap preflight validation and metadata fetch
- Mapping review flow for lock-status fields, lock-date fields, and per-instrument confirmation
- Background job execution for lock/unlock processing with inline progress updates on the Jobs page
- Real REDCap mapping refresh flow, saved-mapping reuse decisions, and improved checkbox choice inference/prefill in mapping review
- Project-scoped REDCap API rate limiting with visible wait/resume messaging
- CSV report generation and export for completed, partial-error, and failed jobs
- Session-scoped encrypted REDCap API key cache so repeat processing in the same session does not always prompt again
- Docker Compose for Next.js frontend + API + PostgreSQL + Redis + Celery worker-backed background processing

## Implemented snapshot

As of 19 May 2026, the app supports the following end-to-end workflow:

1. User signs in and opens the Jobs page.
2. User exports the request template or imports a request package.
3. Import preflight validates the request CSV, checks REDCap connectivity, fetches metadata, inspects optional unresolved queries CSV content, and creates a draft job.
4. If the REDCap project already has saved mappings, the user can either refresh mappings from live REDCap metadata or continue with the saved mapping set.
5. If field detection is ambiguous or missing, the user confirms mappings on the Mappings page.
6. Small jobs can run live in the browser session, while larger jobs run in the background through Celery workers.
7. The UI shows processing progress, processed row counts, row outcome summaries, and REDCap rate-limit wait/resume state.
8. A CSV execution report can be exported from Jobs or Reports once processing finishes.

## Current gaps / next major work

- Background execution now runs through Celery + Redis instead of in-process threads.
- Active cancellation now exists for queued/running jobs, but there is still no resume/restart-in-place flow for interrupted work.
- Admin 2FA is still not implemented.
- The legacy FastAPI/Jinja UI still exists for complex workflows that have not been fully migrated yet.
- Automated test coverage is still limited.

## Backend development

Backend lives in `backend/` (FastAPI). Run:

```bash
docker compose up -d postgres redis

cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg://redcap_app:redcap_app@localhost:5432/redcap_batch_locking
export REDIS_URL=redis://localhost:6379/0
export CELERY_BROKER_URL=$REDIS_URL
export CELERY_RESULT_BACKEND=$REDIS_URL
export REDCAP_API_KEY_CACHE_SECRET=local-dev-redcap-api-key-cache-secret
./scripts/migrate.sh
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Run the Celery worker in a second terminal when working outside Docker:

```bash
cd backend
source .venv/bin/activate
celery -A app.workers.celery_app.celery_app worker --loglevel=info --queues=redcap_jobs
```

Use the same `REDCAP_API_KEY_CACHE_SECRET` value for both the API process and the worker. The worker does not receive the raw REDCap API key on the queue; it reloads the encrypted session-scoped cache instead.

- App: **http://127.0.0.1:8000/** — redirects to the login UI
- Login: **http://127.0.0.1:8000/login**
- Authenticated home: **http://127.0.0.1:8000/app**
- Health: **http://127.0.0.1:8000/health**
- Docs: **http://127.0.0.1:8000/docs**

## Frontend development

Frontend lives in `frontend/` (Next.js app router). Run:

```bash
cd frontend
npm install
export BACKEND_ORIGIN=http://localhost:8000
export NEXT_PUBLIC_BACKEND_ORIGIN=http://localhost:8000
npm run dev
```

- New frontend: **http://localhost:3000/**
- Login: **http://localhost:3000/login**
- Overview: **http://localhost:3000/app**
- Jobs: **http://localhost:3000/jobs**
- Mappings: **http://localhost:3000/mappings**
- Reports: **http://localhost:3000/reports**
- Users: **http://localhost:3000/users**

The Next.js frontend uses a shared global stylesheet in `frontend/src/app/globals.css` and consumes backend JSON endpoints under `/api/v1/...`.

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

## Docker

From the **project root** (this directory):

```bash
docker compose build
docker compose up -d postgres
docker compose run --rm api ./scripts/migrate.sh
docker compose up api frontend
```

This brings up:

- Next.js frontend: **http://localhost:3000**
- FastAPI backend + legacy UI: **http://localhost:8000**

After code changes:

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

For multi-process or Docker deployments, also set a shared `REDCAP_API_KEY_CACHE_SECRET` for both the API and worker services so background jobs can safely decrypt the short-lived cached REDCap API key.
