# REDCap Batch Locking Web App - Product Requirements Document

## 1. Overview

This product is an internal authenticated web application for running CSV-driven REDCap lock and unlock jobs across one or more REDCap projects. Users upload a job file, optionally attach an unresolved queries export, confirm form-level mappings discovered from REDCap metadata, and run the job either with near-live progress or in the background. The system stores a full audit trail and produces downloadable execution reports.

The application is designed for self-hosted deployment on institutional infrastructure using Docker and Docker Compose. REDCap API tokens are supplied per job and are never stored at rest. The REDCap API/base URL may be stored for job history, host-level throttling, and auditability.

## 2. Goals

- Replace the existing desktop/manual workflow with a secure browser-based process.
- Support lock and unlock jobs against multiple REDCap projects over time.
- Prevent unsafe locking by validating form completeness and optionally blocking forms with unresolved queries.
- Give users clear feedback before, during, and after execution.
- Provide durable auditability for who ran what, when, and with what outcome.
- Support operationally safe background execution for large jobs.

## 3. Non-goals

- Public self-service registration.
- Long-term storage of REDCap API tokens.
- Direct editing of REDCap form design or metadata from this app.
- Full REDCap administration outside the lock/unlock use case.
- Managed cloud deployment dependencies.
- Advanced notifications, resumable jobs, and analytics in the initial MVP unless they are required for core safety.

## 4. Users and Roles

### SuperAdmin

- Configure system-wide settings and operational policies.
- Create and manage Admin accounts.
- View all jobs, reports, audit events, and system metrics.
- Manage security settings such as 2FA enforcement and retention.

### Admin

- Create and manage standard User accounts.
- View jobs and reports across operational scope.
- Monitor execution health and investigate failed jobs.
- Review audit trails and operational dashboards.

### User

- Create jobs using REDCap URL, token, CSV input, and options.
- Review validation results and confirm mappings.
- Start, monitor, cancel, and download reports for their own jobs.
- Access only their own job and report data unless elevated permissions are granted.

## 5. Core User Workflows

### 5.1 Authentication and session management

1. User signs in with username and password.
2. Admin and SuperAdmin users complete TOTP challenge when required.
3. App issues an HTTP-only session cookie.
4. Session is rotated and invalidated according to security policy.

### 5.2 Create a job

1. User opens the job creation wizard.
2. User selects action type: lock or unlock.
3. User enters REDCap API URL and token for the target project.
4. User uploads the request CSV and, if needed, an unresolved queries export CSV.
5. Backend validates file shape, required columns, and REDCap connectivity.
6. Backend fetches REDCap project info and metadata and associates the job with the returned project identifier.

### 5.3 Review validation and mapping

1. System normalizes requested rows and detects instruments involved.
2. System discovers likely complete field, CRF status field, and lock date field for each instrument.
3. System assigns a confidence result for each mapping candidate.
4. If confidence is low or missing, user must confirm or adjust mappings before execution can start.
5. User may reuse existing saved mappings for the same REDCap project and instrument where valid.

### 5.4 Execute and monitor job

1. User starts the job after validation and mapping confirmation.
2. Small jobs may appear live, but execution still runs via the worker path for consistency and safety.
3. Large jobs run in the background and publish progress through polling and/or SSE.
4. The job processes rows in chunks with cancellation checkpoints.
5. User sees counts for queued, processed, locked, unlocked, ignored, blocked, failed, and retried rows.

### 5.5 Handle unresolved queries before locking

1. If a queries export is provided, the system parses it with a real CSV parser that respects quoted commas and CRLF line endings.
2. In the `Field` column, the first token is treated as the REDCap variable name and the remaining text is treated as the label.
3. The system maps each query field to its REDCap form using metadata.
4. For a given record, event, and instance context, any query whose status is not `CLOSED` is treated as unresolved.
5. If any unresolved query belongs to the form being locked, locking is blocked for that row and reported clearly.

### 5.6 Download and review reports

1. User opens a completed or partially completed job.
2. User downloads a CSV report and later optionally XLSX reports.
3. Report includes row-level outcomes, messages, timing, and retry context.
4. Audit history for key actions is visible to authorized users.

### 5.7 Admin operations

1. Admin or SuperAdmin manages users and access.
2. Admin monitors job queues, failures, and system health.
3. SuperAdmin adjusts policies such as thresholds, retention, throttling defaults, and 2FA requirements.

## 6. Functional Requirements

### 6.1 Authentication and authorization

- The app must support authenticated browser access with server-side sessions and HTTP-only cookies.
- The app must support role-based access for SuperAdmin, Admin, and User.
- The app must enforce object-level access checks on jobs, reports, and audit views.
- The app must require 2FA for Admin and SuperAdmin users, with optional 2FA for standard users.
- The app must not allow self-service user registration.

### 6.2 Job intake and validation

- The app must accept a request CSV upload for each job.
- The app must optionally accept an unresolved queries export CSV.
- The app must validate content type, file size, and parseability before accepting a job.
- The app must parse CSV safely, including quoted commas and multi-line text values.
- The app must validate required input columns for lock and unlock workflows.
- The app must test REDCap connectivity with the provided URL and token before allowing execution.
- The app must persist the REDCap API/base URL used for the job.
- The app must derive and persist the REDCap project identifier from project metadata returned during preflight.
- The app does not need to persist the raw uploaded request CSV or unresolved queries CSV once parsing/import is complete.

### 6.3 Metadata and mapping

- The app must fetch REDCap metadata for the target project during preflight.
- The app must infer form-level mappings for complete fields, CRF status fields, and lock date fields.
- The app must store confirmed mappings scoped to REDCap project identifier and instrument.
- The app must surface confidence levels and require user confirmation when mappings are uncertain.
- The app must support later drift detection when metadata no longer matches stored mappings.

### 6.4 Lock workflow

- The app must determine the target record, event, arm, and instance context for each row.
- The app must skip rows already locked and report them as ignored.
- The app must verify form completeness before attempting a lock when configured to do so.
- The app must optionally check unresolved queries before locking.
- The app must treat any query status other than `CLOSED` as unresolved.
- The app must block locking if unresolved queries exist for the same record/event/instance and the same form.
- The app must write CRF status and lock date fields using metadata-aware formatting when configured.
- The app must call the REDCap lock endpoint only after safety checks pass.

### 6.5 Unlock workflow

- The app must detect rows that are already unlocked and report them as ignored.
- The app must call the REDCap unlock action only when the row is actually locked.
- The app must optionally clear or reset CRF status and lock date fields after successful unlock according to project policy.

### 6.6 Background execution and progress

- The app must execute jobs through a background worker for reliability and consistent behavior.
- The app must process rows in chunks and persist progress after each chunk.
- The app must support cancellation between chunk boundaries.
- The app must record retries for transient REDCap or network failures.
- The app must expose job progress to the UI using polling and/or SSE.

### 6.7 Throttling and REDCap safety

- The app must route REDCap calls through a shared client wrapper.
- The app must enforce configurable rate limits globally and per REDCap host.
- The app must apply retry and backoff behavior for transient failures and rate limits.
- The app must support a waiting state when a job is paused due to throttling.

### 6.8 Reports and audit

- The app must generate downloadable job reports with row-level outcomes.
- The app must store immutable audit events for login, job creation, mapping confirmation, execution start, cancellation, completion, download, and admin changes.
- The app must let authorized users query audit history.
- The app must retain only the minimum required file artifacts and must avoid storing raw REDCap payloads unless there is a justified operational need.
- The app must store generated reports for later export/download according to retention policy.

### 6.9 Administration and settings

- The app must allow SuperAdmin to manage system-wide operational settings.
- The app must allow Admin and SuperAdmin to manage users according to role policy.
- The app must make thresholds, retention, and throttling settings configurable.

## 7. Non-functional Requirements

### 7.1 Security

- REDCap tokens must never be stored at rest.
- Sensitive application secrets must be managed securely and encrypted at rest where applicable.
- Passwords must be hashed with a modern algorithm such as Argon2 or bcrypt.
- Sessions must be protected with secure cookie settings and CSRF protections where applicable.
- Audit logs must be append-only from the application perspective.

### 7.2 Performance and scale

- The system must support large jobs of at least 10,000 rows without blocking the web request lifecycle.
- Progress updates should feel near-real-time for interactive users.
- Chunk sizing and worker concurrency must be configurable to balance throughput and REDCap safety.

### 7.3 Availability and operations

- The system must be deployable with Docker and Docker Compose on institutional infrastructure.
- Service health checks and structured logs must be available for the API, worker, Redis, and Postgres services.
- The system should degrade gracefully when REDCap is slow or rate limited.

### 7.4 Observability

- The system must emit structured logs for API requests, job lifecycle events, worker actions, and REDCap calls.
- The system should expose job metrics suitable for dashboards and operational troubleshooting.

### 7.5 Data retention

- Generated reports and job records must follow configurable retention policies.
- Retention and purge behavior must preserve the integrity of the audit trail.

## 8. MVP Scope

The MVP includes:

- Authentication and RBAC
- Job upload and validation
- REDCap metadata preflight
- Mapping confirmation and reuse
- Background execution with progress
- CSV reporting
- Core audit trail

The MVP excludes unless needed for launch:

- XLSX reports
- Advanced dashboards and analytics
- Notifications
- Resumable jobs across worker restarts
- WebSockets

## 9. Acceptance Criteria

### 9.1 Authentication and RBAC

- A standard user can log in and access only their own jobs and reports.
- An Admin can manage standard users and view operational data according to policy.
- A SuperAdmin can manage admins and system settings.
- Admin and SuperAdmin login requires TOTP when 2FA enforcement is enabled.

### 9.2 Job creation and validation

- A user can upload a valid request CSV and receive structured validation feedback before execution.
- Invalid CSV shape or missing required columns prevent job start and display actionable errors.
- A failed REDCap connectivity test prevents execution and records a preflight failure event.

### 9.3 Mapping confirmation

- For a project with high-confidence mappings, the UI shows suggested mappings and lets the user confirm them.
- For missing or low-confidence mappings, execution cannot start until the user resolves them.
- Saved mappings are scoped to the REDCap project identifier and instrument and can be reused in later jobs.

### 9.4 Lock and unlock behavior

- A row that is already locked or already unlocked is reported as ignored rather than failed.
- A lock row is blocked when the target form is incomplete and the policy requires completeness.
- A lock row is blocked when a supplied queries export contains any non-`CLOSED` query for the same record/event/instance and form.
- An unlock row clears configured lock-related fields only when the project policy says to do so.

### 9.5 Query file handling

- The queries CSV parser correctly handles quoted commas in comment text.
- The parser extracts the REDCap variable name from the first token of the `Field` column.
- The parser maps query fields to forms via REDCap metadata, not label text matching alone.

### 9.6 Background execution and reporting

- A large job runs asynchronously without timing out the originating web request.
- Users can see progress updates while the job is running.
- Users can cancel a running job and the worker stops at the next chunk checkpoint.
- A completed job produces a downloadable CSV report with row-level outcomes and messages.

### 9.7 Audit and compliance

- Job creation, start, cancel, completion, report download, and admin changes produce audit events.
- REDCap tokens do not appear in persisted database records, audit logs, or generated reports.
- REDCap API/base URLs are persisted, but raw uploaded source files are not retained after import.

## 10. Open implementation notes

- The query export sample indicates that record and instance context may be encoded in a combined record cell such as `1 (#6)`, so the parser layer must normalize this reliably.
- Longitudinal projects may require event-aware matching when query exports populate the `Event` column.
- Additional parser adapters may be added later if other REDCap query exports or XLSX-based institutional exports need to be supported.
