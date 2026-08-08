# SRIS · Mission Intelligence 1.0

Operational SRIS foundation powered by ATLAS Core, with canonical mission
intelligence, deterministic analysis and an optional human-reviewed AI advisory.

Implementation and deployment controls:
[Mission Intelligence & AI v1](docs/MISSION-INTELLIGENCE-AI-V1.md).

Per-organization AI quotas, cost controls and pilot gate:
[AI Governance v1](docs/MISSION-INTELLIGENCE-AI-GOVERNANCE-V1.md).

Production assessment:
[application audit — 2026-08-08](docs/APP-AUDIT-2026-08-08.md).

## Install

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[test]"
```

Only `backend/app` is installed as Python packages.

## Verify

```text
scripts/VERIFY_ATLAS_CORE.cmd
```

## Run

```bash
docker compose up --build
```

API: `http://localhost:8000`  
OpenAPI: `http://localhost:8000/docs`

Database schema changes are controlled exclusively by Alembic.
