from __future__ import annotations

import os
from uuid import uuid4

os.environ.setdefault("SRIS_PILOT_MODE", "true")
os.environ.setdefault("SRIS_PUBLIC_SIGNUP_ENABLED", "true")

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _workspace(prefix: str) -> tuple[dict[str, str], str]:
    marker = uuid4().hex
    response = client.post(
        "/api/pilot/register",
        json={
            "email": f"{prefix.lower().replace(' ', '-')}-{marker}@example.com",
            "full_name": f"{prefix} Owner",
            "password": "A-secure-password-1234",
            "organization_name": f"{prefix} {marker[:8]}",
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    return {"Authorization": f"Bearer {payload['access_token']}"}, payload["organization_id"]


def test_pilot_value_team_and_reports_are_not_accessible_across_organizations() -> None:
    headers_a, organization_a = _workspace("Tenant A")
    headers_b, organization_b = _workspace("Tenant B")

    created = client.post(
        f"/api/organizations/{organization_a}/pilots",
        headers=headers_a,
        json={
            "title": "Piloto privado da organização A",
            "problem_statement": "A organização A está a testar uma decisão que não pertence ao tenant B.",
            "decision_question": "Que intervenção deve ser executada pela organização A?",
            "objective": "Preservar isolamento integral entre organizações.",
            "scope": "Dados e utilizadores da organização A.",
            "pilot_owner": "Owner A",
        },
    )
    assert created.status_code == 201, created.text
    pilot = created.json()

    own = client.get(
        f"/api/organizations/{organization_a}/pilots/{pilot['id']}",
        headers=headers_a,
    )
    assert own.status_code == 200

    # A token from tenant B cannot claim tenant A in the path.
    for suffix in (
        "",
        "/value-case",
        "/collaborators",
        "/reports",
        "/reports/full",
    ):
        response = client.get(
            f"/api/organizations/{organization_a}/pilots/{pilot['id']}{suffix}",
            headers=headers_b,
        )
        assert response.status_code in {403, 404}, (suffix, response.text)

    # Substituting tenant B in the path still cannot reveal a pilot owned by A.
    for suffix in ("", "/value-case", "/collaborators", "/reports/full"):
        response = client.get(
            f"/api/organizations/{organization_b}/pilots/{pilot['id']}{suffix}",
            headers=headers_b,
        )
        assert response.status_code == 404, (suffix, response.text)

    unauthorized_write = client.post(
        f"/api/organizations/{organization_a}/pilots/{pilot['id']}/value-case/items",
        headers=headers_b,
        json={
            "dimension": "economic",
            "label": "Tentativa de escrita cruzada",
            "value_status": "expected",
            "numeric_value": 1,
            "unit": "EUR",
        },
    )
    assert unauthorized_write.status_code in {403, 404}

    list_b = client.get(
        f"/api/organizations/{organization_b}/pilots",
        headers=headers_b,
    )
    assert list_b.status_code == 200
    assert list_b.json() == []
