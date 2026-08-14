# Security architecture

- Authentication: short-lived JWT access tokens, renewable session tokens and
  immediate session revocation through `auth_version`. The browser replaces
  both tokens after every renewal and keeps them scoped to the current tab.
- Authorization: organization membership plus role-based access control.
- Tenant isolation: mandatory `X-Organization-ID`, organization filters on every tenant query, and optional PostgreSQL RLS.
- Encryption in transit: terminate TLS at the platform/load balancer; HSTS is enabled in production.
- Encryption at rest: database/storage encryption by provider plus AES-256-GCM for selected sensitive application fields. Per-organization keys are derived from the master key.
- Secrets: never commit `.env`; use the deployment platform secret manager.
- Audit: create/update/reuse/ingest and membership changes are recorded with actor and request ID.
- API keys: only hashes are stored; raw key is shown once.
- Webhooks: HMAC-SHA256 signatures.
- Browser security: CSP, anti-framing, MIME sniffing prevention and restricted browser permissions.

## Production gates

1. Independent penetration test.
2. Dependency and container vulnerability scanning.
3. MFA or external OIDC/SAML SSO.
4. Data retention and deletion policies per client.
5. DPIA and processing agreements under RGPD.
6. Tested incident response and breach notification process.
7. Quarterly restore drills.
8. Central observability and alerting.
