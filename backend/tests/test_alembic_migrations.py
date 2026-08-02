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


def test_upgrade_and_downgrade_initial_schema() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    with TemporaryDirectory() as tmp:
        database_path = Path(tmp) / "fresh-atlas-migrations.db"
        if database_path.exists():
            database_path.unlink()

        database_url = f"sqlite+pysqlite:///{database_path}"

        run_alembic(repo_root, "upgrade", "head", database_url=database_url)

        engine = create_engine(database_url)
        tables = set(inspect(engine).get_table_names())

        expected = {
            "alembic_version",
            "users",
            "organizations",
            "memberships",
            "knowledge_objects",
            "audit_events",
            "workflows",
            "workflow_candidates",
            "workflow_history",
            "repository_changes",
        }
        assert expected.issubset(tables)

        run_alembic(repo_root, "downgrade", "base", database_url=database_url)
        remaining = set(inspect(engine).get_table_names())
        assert remaining == {"alembic_version"}
