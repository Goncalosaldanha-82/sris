from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.atlas_platform.database import Base, SessionLocal, engine
from app.atlas_platform.models import Membership, Organization, Role, User
from app.atlas_platform.security import create_access_token, hash_password
from app.atlas_platform.workspace_scope import (
    reset_active_organization_id,
    set_active_organization_id,
)
from app.main import app
from app.mission_intelligence.models import CanonicalMission


client = TestClient(app)


def _headers(user: User, organization_id: str | None = None) -> dict[str, str]:
    headers = {
        "Authorization": "Bearer "
        + create_access_token(
            user_id=user.id,
            auth_version=user.auth_version,
        )
    }
    if organization_id:
        headers["X-SRIS-Organization"] = organization_id
    return headers


def _fixture() -> tuple[User, Organization, Organization]:
    Base.metadata.create_all(bind=engine)
    suffix = uuid4().hex[:10]
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        user = User(
            email=f"workspace-{suffix}@example.test",
            full_name="Workspace Continuity",
            password_hash=hash_password("workspace-continuity-password"),
            is_active=True,
            auth_version=1,
        )
        empty = Organization(
            name=f"Empty {suffix}",
            slug=f"empty-{suffix}",
        )
        persistent = Organization(
            name=f"Persistent {suffix}",
            slug=f"persistent-{suffix}",
        )
        db.add_all([user, empty, persistent])
        db.flush()
        db.add_all(
            [
                Membership(
                    user_id=user.id,
                    organization_id=empty.id,
                    role=Role.OWNER.value,
                    created_at=now - timedelta(days=2),
                ),
                Membership(
                    user_id=user.id,
                    organization_id=persistent.id,
                    role=Role.OWNER.value,
                    created_at=now - timedelta(days=1),
                ),
            ]
        )
        db.add(
            CanonicalMission(
                organization_id=persistent.id,
                code=f"MIS-{suffix}",
                title="Missão persistente",
                document_json="{}",
                content_hash="a" * 64,
                revision=1,
                lifecycle_state="active",
                created_by_user_id=user.id,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        db.refresh(user)
        db.refresh(empty)
        db.refresh(persistent)
        return user, empty, persistent


def test_profile_recovers_workspace_with_persistent_missions() -> None:
    user, empty, persistent = _fixture()

    response = client.get("/api/pilot/profile", headers=_headers(user))

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["organization"]["id"] == persistent.id
    assert payload["workspace_selection"]["selected_by"] == "mission_activity"
    assert payload["workspace_selection"]["multiple"] is True
    counts = {row["id"]: row["mission_count"] for row in payload["workspaces"]}
    assert counts[empty.id] == 0
    assert counts[persistent.id] == 1


def test_profile_respects_an_explicit_authorized_workspace() -> None:
    user, empty, persistent = _fixture()

    response = client.get(
        f"/api/pilot/profile?organization_id={empty.id}",
        headers=_headers(user),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["organization"]["id"] == empty.id
    assert payload["workspace_selection"]["selected_by"] == "requested"
    assert payload["workspace_selection"]["requested_is_valid"] is True
    assert any(row["id"] == persistent.id for row in payload["workspaces"])


def test_request_scope_prioritises_only_an_existing_membership() -> None:
    user, empty, persistent = _fixture()

    token = set_active_organization_id(persistent.id)
    try:
        with SessionLocal() as db:
            selected = (
                db.query(Membership)
                .filter(Membership.user_id == user.id)
                .order_by(Membership.created_at.asc())
                .first()
            )
            assert selected is not None
            assert selected.organization_id == persistent.id
    finally:
        reset_active_organization_id(token)

    token = set_active_organization_id(str(uuid4()))
    try:
        with SessionLocal() as db:
            selected = (
                db.query(Membership)
                .filter(Membership.user_id == user.id)
                .order_by(Membership.created_at.asc())
                .first()
            )
            assert selected is not None
            assert selected.organization_id == empty.id
    finally:
        reset_active_organization_id(token)
