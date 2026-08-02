import os
from pathlib import Path
from tempfile import TemporaryDirectory

_temp = TemporaryDirectory()
_db_path = Path(_temp.name) / "workflow-test.db"
_repo_path = Path(_temp.name) / "repo"
_repo_path.mkdir()

os.environ["ATLAS_DATABASE_URL"] = f"sqlite+pysqlite:///{_db_path}"
os.environ["ATLAS_JWT_SECRET"] = "test-secret-at-least-32-characters-long"
os.environ["ATLAS_REPOSITORY_ROOT"] = str(_repo_path)

from fastapi.testclient import TestClient

from app.atlas_platform.database import Base, engine
from app.atlas_platform import workflow_models  # noqa: F401
from app.atlas_platform.api import app
from app.atlas_platform.workflow_api import router as workflow_router


if not any(getattr(route, "path", "").endswith("/workflows") for route in app.routes):
    app.include_router(workflow_router)

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

client = TestClient(app)


def auth_headers() -> tuple[dict[str, str], str]:
    client.post(
        "/api/auth/register",
        json={
            "email": "owner@example.com",
            "full_name": "Owner",
            "password": "strong-password-123",
        },
    )
    login = client.post(
        "/api/auth/login",
        json={
            "email": "owner@example.com",
            "password": "strong-password-123",
        },
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    org = client.post(
        "/api/organizations",
        headers=headers,
        json={"name": "Project ATLAS", "slug": "project-atlas"},
    )
    return headers, org.json()["id"]


def test_integrated_workflow_review_materialization() -> None:
    headers, organization_id = auth_headers()

    created = client.post(
        f"/api/organizations/{organization_id}/workflows",
        headers=headers,
        json={
            "title": "Integrated workflow",
            "source_name": "conversation.md",
            "source_type": "chat",
            "content": "# Decision\n\nGitHub is the source of truth.\n\n# Risk\n\nChat-only knowledge may be lost.",
        },
    )
    assert created.status_code == 201, created.text
    workflow = created.json()
    assert workflow["state"] == "review_required"
    assert len(workflow["candidates"]) == 2

    approvals = {candidate["id"]: True for candidate in workflow["candidates"]}
    reviewed = client.post(
        f"/api/organizations/{organization_id}/workflows/{workflow['id']}/review",
        headers=headers,
        json={"approvals": approvals, "comment": "Approved"},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["state"] == "approved"

    materialized = client.post(
        f"/api/organizations/{organization_id}/workflows/{workflow['id']}/materialize",
        headers=headers,
    )
    assert materialized.status_code == 200, materialized.text
    assert materialized.json()["state"] == "commit_proposed"

    proposal = client.get(
        f"/api/organizations/{organization_id}/workflows/{workflow['id']}/repository-proposal",
        headers=headers,
    )
    assert proposal.status_code == 200, proposal.text
    assert len(proposal.json()["changed_paths"]) == 2
    assert proposal.json()["diff_text"]
