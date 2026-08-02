# ATLAS Core v1.0 — Integration

1. Back up `C:\Users\barba\Documents\GitHub\sris`.
2. Copy all package contents into the repository root.
3. Replace structural files: `pyproject.toml`, `MANIFEST.in`, `Dockerfile`, `docker-compose.yml`, `.env.example`, and both ATLAS CI workflows.
4. Merge existing subsystem folders under `backend/app`.
5. Run `scripts/VERIFY_ATLAS_CORE.cmd`.
6. Commit only after verification passes.

Commit summary:

```text
Consolidate ATLAS Core v1.0 architecture and packaging
```
