from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse


DEFAULT_DATABASE_URL = "sqlite+pysqlite:///./.atlas/atlas_platform.db"
DEFAULT_JWT_SECRET = "change-me-before-production"
DEFAULT_MANAGED_DATABASE_SCHEMA = "sris_atlas"
_SCHEMA_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


def managed_runtime(environ: Mapping[str, str] | None = None) -> bool:
    values = os.environ if environ is None else environ
    return any(
        values.get(name)
        for name in (
            "RAILWAY_ENVIRONMENT_ID",
            "RAILWAY_PROJECT_ID",
            "RAILWAY_SERVICE_ID",
        )
    )


def normalize_database_url(value: str) -> str:
    """Use the installed psycopg v3 dialect for Railway PostgreSQL URLs."""

    normalized = value.strip()
    if normalized.startswith("postgres://"):
        return normalized.replace("postgres://", "postgresql+psycopg://", 1)
    if normalized.startswith("postgresql://"):
        return normalized.replace("postgresql://", "postgresql+psycopg://", 1)
    return normalized


def resolve_database_url(environ: Mapping[str, str] | None = None) -> str:
    """Resolve the canonical database without silently ignoring Railway.

    Railway exposes a referenced PostgreSQL connection as ``DATABASE_URL``.
    Earlier ATLAS builds read only ``ATLAS_DATABASE_URL`` and consequently
    fell back to a container-local SQLite file even while PostgreSQL appeared
    online in the project.  Prefer the explicit ATLAS name, but accept the
    standard Railway name as the canonical fallback.
    """

    values = os.environ if environ is None else environ
    raw = (
        values.get("ATLAS_DATABASE_URL", "").strip()
        or values.get("DATABASE_URL", "").strip()
        or DEFAULT_DATABASE_URL
    )
    return normalize_database_url(raw)


def resolve_database_schema(environ: Mapping[str, str] | None = None) -> str | None:
    """Keep the canonical platform isolated from the legacy public schema."""

    values = os.environ if environ is None else environ
    explicit = values.get("ATLAS_DATABASE_SCHEMA", "").strip()
    schema = explicit or (
        DEFAULT_MANAGED_DATABASE_SCHEMA if managed_runtime(values) else ""
    )
    if not schema:
        return None
    if not _SCHEMA_PATTERN.fullmatch(schema):
        raise RuntimeError(
            "ATLAS_DATABASE_SCHEMA must be a valid PostgreSQL identifier"
        )
    return schema


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
        default_factory=resolve_database_url
    )
    database_schema: str | None = field(
        default_factory=resolve_database_schema
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


def validate_security_settings(value: Settings) -> None:
    managed_railway = managed_runtime()
    production = value.environment.strip().lower() in {"production", "prod"}
    if managed_railway and not value.database_url.startswith(
        "postgresql+psycopg://"
    ):
        raise RuntimeError(
            "Managed SRIS deployments require persistent PostgreSQL through "
            "ATLAS_DATABASE_URL or DATABASE_URL; container-local SQLite is forbidden"
        )
    if managed_railway and not value.database_schema:
        raise RuntimeError(
            "Managed SRIS deployments require an isolated PostgreSQL schema"
        )
    if (production or managed_railway) and (
        value.jwt_secret == DEFAULT_JWT_SECRET or len(value.jwt_secret.encode("utf-8")) < 32
    ):
        raise RuntimeError(
            "ATLAS_JWT_SECRET must contain at least 32 bytes and must not use the "
            "default value in production"
        )


settings = Settings()
validate_security_settings(settings)
ensure_sqlite_parent(settings.database_url)
