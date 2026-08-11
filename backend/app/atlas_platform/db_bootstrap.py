from __future__ import annotations

import subprocess
import sys

from sqlalchemy import create_engine, text

from .config import settings


def ensure_database_namespace() -> None:
    """Create only the isolated canonical schema; preserve legacy public data."""

    if not settings.database_schema:
        return

    # The schema name has already passed the strict identifier validation in
    # atlas_platform.config.  Connect without search_path so it can be created
    # before Alembic opens the canonical namespace.
    bootstrap_engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with bootstrap_engine.begin() as connection:
            connection.execute(
                text(f'CREATE SCHEMA IF NOT EXISTS "{settings.database_schema}"')
            )
    finally:
        bootstrap_engine.dispose()


def run_migrations() -> None:
    ensure_database_namespace()
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    run_migrations()
