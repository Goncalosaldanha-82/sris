from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse


DEFAULT_DATABASE_URL = "sqlite+pysqlite:///./.atlas/atlas_platform.db"


def ensure_sqlite_parent(database_url: str) -> None:
    """Create the parent directory for file-backed SQLite databases."""
    if not database_url.startswith(("sqlite:///", "sqlite+pysqlite:///")):
        return
    if database_url.endswith(":memory:"):
        return

    if database_url.startswith(("sqlite:///./", "sqlite+pysqlite:///./")):
        raw_path = database_url.split("///", 1)[1]
        db_path = Path(raw_path)
    else:
        parsed = urlparse(database_url.replace("sqlite+pysqlite", "sqlite", 1))
        db_path = Path(unquote(parsed.path))

    db_path.expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("ATLAS_DATABASE_URL", DEFAULT_DATABASE_URL)
    jwt_secret: str = os.getenv(
        "ATLAS_JWT_SECRET",
        "change-me-before-production",
    )
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = int(
        os.getenv("ATLAS_ACCESS_TOKEN_MINUTES", "60")
    )


settings = Settings()
ensure_sqlite_parent(settings.database_url)
