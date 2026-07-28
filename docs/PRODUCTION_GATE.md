# Production gate

Do not onboard confidential client data until every item below has an owner, evidence and acceptance date.

## Identity and access
- MFA or enterprise SSO enabled.
- Role matrix reviewed with the first client.
- Joiner, mover and leaver process tested.
- Refresh-token revocation and emergency account lockout tested.

## Tenant isolation
- PostgreSQL RLS policies applied to every tenant table, including the epistemic core tables.
- Automated negative tests run against every endpoint.
- Database role used by the application cannot bypass RLS.

## Secrets and encryption
- Secrets stored in a managed secret manager, never in source control.
- Unique production encryption key and documented rotation procedure.
- TLS at the edge and between managed services where available.
- Backup encryption independently verified.

## Reliability
- Point-in-time recovery configured for PostgreSQL.
- Backup restore tested into an isolated environment.
- RPO and RTO agreed with the client.
- Application, database and queue monitoring active.

## Privacy and governance
- Data inventory and retention schedule approved.
- DPIA completed when required.
- Data-processing agreements executed.
- Export, rectification and deletion procedures tested.
- Audit retention and access rules approved.

## Application assurance
- Dependency and container scanning active.
- Independent penetration test completed.
- Abuse cases tested: IDOR, cross-tenant access, token replay, privilege escalation, mass assignment, webhook forgery and CSV injection.
- Rate limiting and request-size limits configured at the edge.

## SRIS methodological integrity
- No monetary value is presented as realised without baseline, period, sources, calculation and attribution assessment.
- Observation is not silently promoted to evidence.
- Hypotheses retain counter-evidence and missing-data declarations.
- Attribution assessment states limitations and algorithm version.
- Learning is not labelled reused without a recorded link to a later mission or decision.
