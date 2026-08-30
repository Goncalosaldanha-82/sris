# SRIS Pilot V1 — Deployment Contract

Deployment branch: `demo-experience-2026-08-30`

## Isolation rule

Pilot V1 must be deployed as a **new Railway service**. Do not repoint the existing `sris` staging service and do not reuse the institutional-site service.

Recommended service name: `sris-pilot-v1`.

Pilot V1 should use its **own PostgreSQL database/service** for pilot data. Do not run the pilot against the current staging database once external pilot work begins.

The public route `/demonstracao` is stateless, read-only and contains only a
clearly labelled fictional municipal case. The authenticated route `/app`
remains isolated from the demonstration and is available only to invited
institutional accounts.

## Runtime

- Dockerfile: repository root `Dockerfile`
- Application: `app.main:app`
- Frontend root: `frontend/pilot-v1/`
- Healthcheck: `/health`
- Port: Railway-provided `PORT`
- Database migrations: `python -m alembic upgrade head` before application start

The Pilot V1 Docker runtime intentionally does **not** execute legacy staging presentation or test-data purge scripts.

## Required environment groups

Copy only the configuration actually required by the current backend from the existing staging service, then replace database-related values with references to the dedicated Pilot V1 PostgreSQL service.

Do not copy secrets into GitHub.

At minimum verify before first pilot use:

1. Database connection resolves to the Pilot V1 database.
2. Authentication/session secrets are present.
3. AI/provider configuration required by Mission Intelligence is present.
4. Any email/recovery configuration used by login flows is present.
5. Object-storage configuration is either deliberately configured or explicitly left disabled until the storage backend is selected.
6. `ATLAS_SELF_REGISTRATION_ENABLED=false`,
   `ATLAS_ORGANIZATION_CREATION_ENABLED=false` and
   `SRIS_PUBLIC_SIGNUP_ENABLED=false` are all set explicitly.

## Release gates

A Railway deployment is not sufficient for pilot readiness. The service must pass:

1. `/health` healthy.
2. Login and logout.
3. Create a new mission.
4. Mission Preflight retrieves relevant prior knowledge when available.
5. Learning inheritance can be marked valid, requiring revalidation, or invalidated with context.
6. Mission outcome can be recorded.
7. Organizational Memory persists and can be retrieved after a fresh session.
8. Pilot Mode records baseline and end-state metrics.
9. File ingestion is tested with representative PDF, DOCX, XLSX and image inputs before external users are admitted.
10. No raw exceptions, provider errors, stack traces or internal debugging text are exposed in the UI.

## Rollback

Because Pilot V1 is a separate Railway service, rollback is performed within that service only. Existing staging and institutional-site services remain untouched.
