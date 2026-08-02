# Integration

Copy all files into the root of the `sris` repository and replace existing files.

Required replacements:

```text
backend/app/atlas_platform/config.py
backend/app/atlas_platform/database.py
backend/app/atlas_platform/__init__.py
backend/tests/conftest.py
.github/workflows/atlas-core-ci.yml
.github/workflows/atlas-database-migrations.yml
```

Run locally:

```text
scripts/VERIFY_ATLAS_CORE_v1_1.cmd
```

Commit summary:

```text
Fix ATLAS Core CI database isolation and test infrastructure
```
