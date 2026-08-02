# ATLAS Core v1.1 — CI & Test Infrastructure

## Error corrected

```text
sqlite3.OperationalError: unable to open database file
```

The CI test database pointed to a directory that did not exist before SQLAlchemy
created the SQLite engine.

## Corrections

- test environment is configured before test collection;
- SQLite parent directories are created automatically;
- `atlas_platform` performs no eager database import;
- GitHub Actions creates CI directories explicitly;
- CI uses isolated SQLite files under `/tmp`;
- local Windows verification uses `.atlas/test`.

Production remains PostgreSQL-based. SQLite is used only for isolated tests.
