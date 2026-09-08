# Pilot V1 operations increment — 2026-08-22

This increment moves the Pilot from feature-only validation toward controlled operational use.

It adds authenticated operational status, visible workspace account administration for owners/admins, account activation and role control with audit events, session invalidation when access is removed, and pilot-grade rate limiting on signup, password reset and AI endpoints.

The limiter is explicitly scoped to the current single-replica Pilot. A shared Redis-compatible limiter remains a scale prerequisite before multi-replica deployment.
