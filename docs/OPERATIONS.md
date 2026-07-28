# Operations

## Backups

Schedule `scripts/backup.sh` daily. Use provider snapshots in addition to logical dumps. Keep at least one copy in a separate account/region. A backup is not valid until restoration is tested.

## Recommended production topology

- Managed PostgreSQL with point-in-time recovery
- Managed Redis
- Object storage with versioning and retention lock
- Two or more application replicas behind TLS termination
- Central logs and metrics
- Secret manager and key rotation

## Recovery objectives

Set contractual RPO/RTO per plan. A reasonable initial target is RPO 24 hours and RTO 4 hours, then improve after operational validation.
