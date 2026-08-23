import os
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

_temp_dir = TemporaryDirectory()
_db_path = Path(_temp_dir.name) / "atlas-test.db"

os.environ["ATLAS_DATABASE_URL"] = f"sqlite+pysqlite:///{_db_path}"
os.environ["ATLAS_JWT_SECRET"] = "test-secret-at-least-32-characters-long"

from fastapi.testclient import TestClient

from app.atlas_platform.api import app
from app.atlas_platform.database import Base, engine


Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
client = TestClient(app)


def test_register_login_org_and_knowledge() -> None:
    register = client.post(
        "/api/auth/register",
        json={
            "email": "owner@example.com",
            "full_name": "ATLAS Owner",
            "password": "strong-password-123",
        },
    )
    assert register.status_code == 201, register.text

    login = client.post(
        "/api/auth/login",
        json={
            "email": "owner@example.com",
            "password": "strong-password-123",
        },
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    org = client.post(
        "/api/organizations",
        headers=headers,
        json={"name": "Project ATLAS", "slug": "project-atlas"},
    )
    assert org.status_code == 201, org.text
    organization_id = org.json()["id"]

    created = client.post(
        f"/api/organizations/{organization_id}/knowledge",
        headers=headers,
        json={
            "object_type": "hypothesis",
            "title": "Institutional continuity",
            "summary": "A candidate hypothesis.",
        },
    )
    assert created.status_code == 201, created.text

    listed = client.get(
        f"/api/organizations/{organization_id}/knowledge",
        headers=headers,
    )
    assert listed.status_code == 200, listed.text
    assert len(listed.json()) == 1


def test_session_refresh_renews_tokens_and_enforces_token_types() -> None:
    suffix = uuid4().hex[:10]
    email = f"refresh-{suffix}@example.com"
    password = "strong-password-123"
    registered = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "full_name": "Refresh Test Owner",
            "password": password,
        },
    )
    assert registered.status_code == 201, registered.text

    login = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    tokens = login.json()
    assert tokens["access_token"]
    assert tokens["refresh_token"]
    assert tokens["access_token"] != tokens["refresh_token"]

    refresh_as_access = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
    )
    assert refresh_as_access.status_code == 401

    access_as_refresh = client.post(
        "/api/auth/refresh",
        json={"refresh_token": tokens["access_token"]},
    )
    assert access_as_refresh.status_code == 401

    renewed = client.post(
        "/api/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert renewed.status_code == 200, renewed.text
    renewed_tokens = renewed.json()
    assert renewed_tokens["access_token"] != tokens["access_token"]
    assert renewed_tokens["refresh_token"] != tokens["refresh_token"]

    me = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {renewed_tokens['access_token']}"},
    )
    assert me.status_code == 200, me.text
    assert me.json()["email"] == email
