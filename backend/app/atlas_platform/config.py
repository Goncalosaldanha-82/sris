from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse


DEFAULT_DATABASE_URL = "sqlite+pysqlite:///./.atlas/atlas_platform.db"
DEFAULT_JWT_SECRET = "change-me-before-production"


def configured_database_url() -> str:
    """Resolve the database URL used by both the API and Alembic.

    Railway commonly exposes its PostgreSQL reference as ``DATABASE_URL``.
    ``ATLAS_DATABASE_URL`` remains the explicit override for existing installs.
    Keeping the resolution in one place prevents migrations and the running API
    from silently connecting to different databases.
    """

    return (
        os.getenv("ATLAS_DATABASE_URL", "").strip()
        or os.getenv("DATABASE_URL", "").strip()
        or DEFAULT_DATABASE_URL
    )


def environment_flag(name: str, *, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


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
    database_url: str = field(
        default_factory=configured_database_url
    )
    jwt_secret: str = field(
        default_factory=lambda: os.getenv("ATLAS_JWT_SECRET", DEFAULT_JWT_SECRET)
    )
    environment: str = field(
        default_factory=lambda: os.getenv("ATLAS_ENV", "development")
    )
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = field(
        default_factory=lambda: int(os.getenv("ATLAS_ACCESS_TOKEN_MINUTES", "60"))
    )
    refresh_token_days: int = field(
        default_factory=lambda: int(os.getenv("ATLAS_REFRESH_TOKEN_DAYS", "14"))
    )


def validate_security_settings(value: Settings) -> None:
    managed_railway = any(
        os.getenv(name)
        for name in ("RAILWAY_ENVIRONMENT_ID", "RAILWAY_PROJECT_ID", "RAILWAY_SERVICE_ID")
    )
    production = value.environment.strip().lower() in {"production", "prod"}
    if (production or managed_railway) and (
        value.jwt_secret == DEFAULT_JWT_SECRET or len(value.jwt_secret.encode("utf-8")) < 32
    ):
        raise RuntimeError(
            "ATLAS_JWT_SECRET must contain at least 32 bytes and must not use the "
            "default value in production"
        )

    if (production or managed_railway) and value.database_url.startswith("sqlite"):
        raise RuntimeError(
            "ATLAS_DATABASE_URL or DATABASE_URL must reference the Pilot's "
            "dedicated PostgreSQL database; managed deployments cannot use SQLite"
        )


settings = Settings()
validate_security_settings(settings)
ensure_sqlite_parent(settings.database_url)
