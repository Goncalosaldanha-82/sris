from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.atlas_platform.api import (
    _institutional_access_available,
    complete_institutional_access,
)
from app.atlas_platform.config import (
    DEFAULT_MANAGED_DATABASE_SCHEMA,
    Settings,
    resolve_database_schema,
    resolve_database_url,
    validate_security_settings,
)
from app.atlas_platform.database import Base
from app.atlas_platform.institutional_access import institutional_access_gate
from app.atlas_platform.models import Membership, PasswordRecoveryUse, Role, User
from app.atlas_platform.schemas import InstitutionalAccessCompletionRequest
from app.atlas_platform.security import verify_password


def test_railway_standard_database_url_is_canonical_and_isolated() -> None:
    environ = {
        "RAILWAY_SERVICE_ID": "service-test",
        "DATABASE_URL": "postgresql://user:password@postgres.internal/railway",
    }

    assert resolve_database_url(environ) == (
        "postgresql+psycopg://user:password@postgres.internal/railway"
    )
    assert resolve_database_schema(environ) == DEFAULT_MANAGED_DATABASE_SCHEMA


def test_explicit_atlas_database_url_wins_over_standard_url() -> None:
    environ = {
        "DATABASE_URL": "postgresql://standard:password@host/standard",
        "ATLAS_DATABASE_URL": "postgresql://atlas:password@host/atlas",
    }

    assert resolve_database_url(environ) == (
        "postgresql+psycopg://atlas:password@host/atlas"
    )


def test_managed_runtime_refuses_ephemeral_sqlite(monkeypatch) -> None:
    monkeypatch.setenv("RAILWAY_SERVICE_ID", "service-test")
    value = Settings(
        database_url="sqlite+pysqlite:///./ephemeral.db",
        database_schema=DEFAULT_MANAGED_DATABASE_SCHEMA,
        jwt_secret="managed-test-secret-with-more-than-32-bytes",
        environment="staging",
    )

    with pytest.raises(RuntimeError, match="persistent PostgreSQL"):
        validate_security_settings(value)


def test_recovery_gate_bootstraps_owner_once_and_survives_new_connection(
    monkeypatch,
    tmp_path: Path,
) -> None:
    email = "persistent-owner@example.com"
    recovery_token = "persistent-recovery-token-with-more-than-32-characters"
    password = "persistent-owner-password-123"
    database_path = tmp_path / "persistent-owner.db"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"

    monkeypatch.delenv("SRIS_ACCESS_ACTIVATION_EMAIL", raising=False)
    monkeypatch.delenv("SRIS_ACCESS_ACTIVATION_TOKEN", raising=False)
    monkeypatch.setenv("SRIS_PASSWORD_RECOVERY_EMAIL", email)
    monkeypatch.setenv("SRIS_PASSWORD_RECOVERY_TOKEN", recovery_token)

    gate = institutional_access_gate()
    assert gate is not None
    assert gate.source == "existing_recovery_gate"
    assert gate.ledger_hash == hashlib.sha256(
        f"{email}\0{recovery_token}".encode("utf-8")
    ).hexdigest()

    first_engine = create_engine(database_url)
    Base.metadata.create_all(first_engine)
    try:
        with Session(first_engine) as db:
            assert _institutional_access_available(db) is True
            activated = complete_institutional_access(
                InstitutionalAccessCompletionRequest(
                    email=email,
                    activation_code=gate.code,
                    new_password=password,
                    full_name="Persistent Owner",
                ),
                db,
            )
            assert activated.role == Role.OWNER.value
    finally:
        first_engine.dispose()

    # A new engine/session models the post-deployment process reading the same
    # durable database, rather than trusting the session returned at activation.
    second_engine = create_engine(database_url)
    try:
        with Session(second_engine) as db:
            user = db.query(User).filter(User.email == email).one()
            membership = (
                db.query(Membership)
                .filter(Membership.user_id == user.id)
                .one()
            )
            assert verify_password(password, user.password_hash)
            assert membership.role == Role.OWNER.value
            assert db.get(PasswordRecoveryUse, gate.ledger_hash) is not None
            assert _institutional_access_available(db) is False
    finally:
        second_engine.dispose()
