# Integrating ATLAS Repository Agent v0.1

Copy this bundle into the root of the SRIS repository, preserving paths.

## 1. Confirm dependencies

The current SRIS `pyproject.toml` already contains:

- `pydantic`
- `httpx`
- `pytest` in the test extra

No new runtime package is required.

## 2. Important import note

The repository currently configures:

```toml
pythonpath = ["backend"]
```

Therefore the preferred invocation is:

```bash
python -m app.atlas_agent.cli ...
```

The helper script is optional.

## 3. Run tests

```bash
pip install -e ".[test]"
pytest backend/tests/test_atlas_repository_agent.py
```

## 4. Preview safely

```bash
python -m app.atlas_agent.cli   --input docs/atlas/inbox/example-update.md   --repo .   --mode preview
```

## 5. Apply locally

```bash
git checkout feature/ske-core
python -m app.atlas_agent.cli   --input docs/atlas/inbox/example-update.md   --repo .   --mode local
git diff
```

## 6. Commit the agent itself

```bash
git add backend/app/atlas_agent backend/tests/test_atlas_repository_agent.py   scripts/run_atlas_repository_agent.py .github/workflows/atlas-repository-agent.yml   docs/atlas-agent docs/atlas/inbox
git commit -m "Add ATLAS Repository Agent v0.1"
git push origin feature/ske-core
```

## 7. Security

Do not put a personal GitHub token in the repository. For local GitHub mode, export it in the shell. In GitHub Actions, use the automatically provided `GITHUB_TOKEN`.
