import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine, inspect


def run_alembic(repo_root: Path, *args: str, database_url: str) -> None:
    env = os.environ.copy()
    env["ATLAS_DATABASE_URL"] = database_url
    env["PYTHONPATH"] = str(repo_root / "backend")

    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + "\n" + result.stderr


def table_names(database_url: str) -> set[str]:
    engine = create_engine(database_url)

    try:
        with engine.connect() as connection:
            return set(inspect(connection).get_table_names())
    finally:
        # Essential on Windows: closes pooled SQLite handles before
        # TemporaryDirectory attempts to delete the database file.
        engine.dispose()


def test_upgrade_and_downgrade_initial_schema() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    with TemporaryDirectory(prefix="atlas-migrations-") as tmp:
        database_path = Path(tmp) / "fresh-atlas-migrations.db"
        database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"

        run_alembic(
            repo_root,
            "upgrade",
            "head",
            database_url=database_url,
        )

        tables = table_names(database_url)

        expected = {
            "alembic_version",
            "users",
            "organizations",
            "memberships",
            "knowledge_objects",
            "audit_events",
            "password_recovery_uses",
            "workflows",
            "workflow_candidates",
            "workflow_history",
            "repository_changes",
            "mi_missions",
            "mi_mission_revisions",
            "mi_intelligence_runs",
            "mi_ai_organization_policies",
            "mi_ai_usage_periods",
            "mi_ai_usage_events",
        }

        assert expected.issubset(tables)

        run_alembic(
            repo_root,
            "downgrade",
            "base",
            database_url=database_url,
        )

        remaining = table_names(database_url)
        assert remaining in (set(), {"alembic_version"})
