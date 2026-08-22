# Pilot V1 — Operational Guardrails

This increment adds the first operational-control layer required before wider pilot testing.

## Included

- authenticated `/api/pilot/ops/status` endpoint for environment, organization, member, audit and AI readiness signals;
- workspace account administration for owner/admin roles;
- account activation/deactivation with access-token invalidation through `auth_version`;
- role administration with explicit protection of the owner role;
- append-only audit events for account-state and role changes;
- rate limiting for public registration, password reset and AI/intelligence mutation endpoints;
- configurable limits through environment variables.

## Environment variables

- `SRIS_RATE_LIMIT_SIGNUP_PER_15M` (default `8`)
- `SRIS_RATE_LIMIT_PASSWORD_RESET_PER_15M` (default `6`)
- `SRIS_RATE_LIMIT_AI_PER_MINUTE` (default `20`)

## Scale boundary

The rate limiter is deliberately process-local for the one-replica Pilot V1 deployment. Before horizontal scaling, its state must move to a shared Redis-compatible backend. The application reports this explicitly as `rate_limit_scope=process-local-pilot`; it is not presented as a multi-replica guarantee.
