# ATLAS Platform Architecture v1.0

## Root cause fixed

The GitHub Action failed because setuptools used automatic discovery in a flat repository and found several top-level directories:

```text
backend
frontend
migrations
```

The project now explicitly installs only packages under:

```text
backend/app
```

## Definitive packaging configuration

```toml
[tool.setuptools]
package-dir = {"" = "backend"}

[tool.setuptools.packages.find]
where = ["backend"]
include = ["app*"]
```

## Supported installation

```bash
python -m pip install -e ".[test]"
```

## Repository structure

```text
sris/
├── backend/
│   ├── app/
│   └── tests/
├── frontend/
├── migrations/
├── docs/
├── scripts/
├── .github/
├── alembic.ini
├── pyproject.toml
└── MANIFEST.in
```

Do not add `__init__.py` to `frontend`, `migrations`, `docs` or `scripts`.
