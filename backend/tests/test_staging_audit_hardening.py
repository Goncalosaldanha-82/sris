from __future__ import annotations

import os
import subprocess
import sys
from uuid import uuid4

os.environ.setdefault("SRIS_PILOT_MODE", "true")
os.environ.setdefault("SRIS_PUBLIC_SIGNUP_ENABLED", "true")
os.environ.setdefault("ATLAS_SELF_REGISTRATION_ENABLED", "true")

from fastapi.testclient import TestClient

from app.atlas_platform import identity
from app.main import app
from app.mission_intelligence.attachments import AttachmentError
from app.mission_intelligence.fictional_demo import fictional_demo_catalog
from app.mission_intelligence import dialogue_service
from app.pilot_capabilities import PILOT_BUILD


client = TestClient(app)


def test_attachment_context_error_is_bound_to_the_controlled_api_exception() -> None:
    assert dialogue_service.AttachmentError is AttachmentError


def test_public_build_is_minimal_and_release_state_requires_authentication() -> None:
    public = client.get("/api/pilot/build")
    assert public.status_code == 200
    assert public.json() == {
        "build": PILOT_BUILD,
        "product": "SRIS Pilot & Mission Intelligence",
    }
    assert client.get("/api/pilot/release-state").status_code == 401

    marker = uuid4().hex
    registered = client.post(
        "/api/pilot/register",
        json={
            "email": f"release-state-{marker}@example.com",
            "full_name": "Release State Tester",
            "password": "A-secure-password-1234",
            "organization_name": f"Release State {marker[:8]}",
        },
    )
    assert registered.status_code == 201, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    protected = client.get("/api/pilot/release-state", headers=headers)
    assert protected.status_code == 200, protected.text
    assert protected.json()["migration_heads"]


def test_account_page_receives_the_active_build_token() -> None:
    response = client.get("/account.html")
    assert response.status_code == 200
    assert f'name="sris-pilot-build" content="{PILOT_BUILD}"' in response.text
    assert f"/pilot.css?v={PILOT_BUILD}" in response.text
    assert "20260828-brand-system-v30" not in response.text


def test_managed_runtime_hides_openapi_by_default() -> None:
    code = """
from app.atlas_platform.api import app
assert app.openapi_url is None
assert app.docs_url is None
assert app.redoc_url is None
"""
    environment = os.environ.copy()
    environment.update(
        {
            "RAILWAY_ENVIRONMENT_ID": "managed-test",
            "ATLAS_DATABASE_URL": "postgresql+psycopg://user:pass@localhost:5432/test",
            "ATLAS_JWT_SECRET": "managed-test-secret-with-more-than-thirty-two-bytes",
            "SRIS_PUBLIC_API_DOCS_ENABLED": "false",
        }
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        env=environment,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_public_demo_uses_the_fixed_chain_and_six_criterion_matrix() -> None:
    mission = fictional_demo_catalog()["missions"]["DEMO-TA-001"]
    assert [row["label"] for row in mission["situation"]["chain"]] == [
        "Observação",
        "Evidência",
        "Hipótese",
        "Alternativa",
        "Decisão",
        "Ação",
        "Resultado",
        "Aprendizagem",
    ]
    matrix = mission["analysis"]["decision_matrix"]
    assert [criterion["id"] for criterion in matrix["criteria"]] == [
        "effectiveness",
        "cost",
        "risk",
        "reversibility",
        "experience",
        "robustness",
    ]
    for row in matrix["rows"]:
        assert len(row["scores"]) == 6
        assert row["total"] == sum(row["scores"])


def test_legacy_pilot_reset_urls_delegate_to_the_canonical_token_store(monkeypatch) -> None:
    captured: list[str] = []
    monkeypatch.setattr(identity, "auth_email_delivery_ready", lambda: True)
    monkeypatch.setattr(
        identity,
        "_send_password_reset_email",
        lambda _reset_id, raw_token: captured.append(raw_token),
    )
    marker = uuid4().hex
    email = f"reset-alias-{marker}@example.com"
    password = "Original-password-1234"
    registered = client.post(
        "/api/auth/register",
        json={"email": email, "full_name": "Reset Alias", "password": password},
    )
    assert registered.status_code == 201, registered.text

    requested = client.post(
        "/api/pilot/password-reset/request",
        json={"email": email},
    )
    assert requested.status_code == 202, requested.text
    assert captured

    replacement = "Replacement-password-5678"
    confirmed = client.post(
        "/api/pilot/password-reset/confirm",
        json={"token": captured[-1], "new_password": replacement},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert client.post(
        "/api/auth/login",
        json={"email": email, "password": replacement},
    ).status_code == 200
