import os
from pathlib import Path
from tempfile import TemporaryDirectory

_temp_dir = TemporaryDirectory()
_db_path = Path(_temp_dir.name) / "atlas-test.db"

os.environ["ATLAS_DATABASE_URL"] = f"sqlite+pysqlite:///{_db_path}"
os.environ["ATLAS_JWT_SECRET"] = "test-secret"

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
