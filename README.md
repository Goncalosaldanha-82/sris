# ATLAS Core v1.0

Consolidated operational foundation of SRIS Enterprise.

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
