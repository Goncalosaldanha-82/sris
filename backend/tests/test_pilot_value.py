from __future__ import annotations

import os
from uuid import uuid4

os.environ.setdefault("SRIS_PILOT_MODE", "true")
os.environ.setdefault("SRIS_PUBLIC_SIGNUP_ENABLED", "true")

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _pilot() -> tuple[dict[str, str], str, dict]:
    marker = uuid4().hex
    registration = client.post(
        "/api/pilot/register",
        json={
            "email": f"pilot-value-{marker}@example.com",
            "full_name": "Pilot Value Tester",
            "password": "A-secure-password-1234",
            "organization_name": f"Pilot Value {marker[:8]}",
        },
    )
    assert registration.status_code == 201, registration.text
    payload = registration.json()
    headers = {"Authorization": f"Bearer {payload['access_token']}"}
    organization_id = payload["organization_id"]
    created = client.post(
        f"/api/organizations/{organization_id}/pilots",
        headers=headers,
        json={
            "title": "Piloto de valor verificável",
            "problem_statement": "Existe valor esperado, mas ainda não foi demonstrado num contexto real.",
            "decision_question": "Que intervenção produz valor suficiente para justificar escala?",
            "objective": "Medir resultado e valor sem promover estimativas a benefícios realizados.",
            "scope": "Uma unidade, um processo e um período de observação definido.",
            "pilot_owner": "Pilot Owner",
        },
    )
    assert created.status_code == 201, created.text
    return headers, organization_id, created.json()


def test_realized_value_requires_period_baseline_source_calculation_and_attribution() -> None:
    headers, organization_id, pilot = _pilot()
    endpoint = (
        f"/api/organizations/{organization_id}/pilots/"
        f"{pilot['id']}/value-case/items"
    )

    invalid = client.post(
        endpoint,
        headers=headers,
        json={
            "dimension": "economic",
            "label": "Poupança anual",
            "value_status": "realized",
            "numeric_value": 12000,
            "unit": "EUR",
        },
    )
    assert invalid.status_code == 422

    expected = client.post(
        endpoint,
        headers=headers,
        json={
            "dimension": "economic",
            "label": "Poupança anual esperada",
            "value_status": "expected",
            "numeric_value": 15000,
            "unit": "EUR",
            "limitations": "Estimativa anterior à intervenção.",
        },
    )
    assert expected.status_code == 201, expected.text

    realized = client.post(
        endpoint,
        headers=headers,
        json={
            "dimension": "economic",
            "label": "Poupança observada e atribuída",
            "value_status": "realized",
            "numeric_value": 9000,
            "unit": "EUR",
            "period": "2026-04 a 2026-08",
            "baseline_reference": "Baseline normalizada de 2026-01 a 2026-03",
            "source": "Faturas, ocupação e registos operacionais",
            "calculation": "Diferença normalizada multiplicada pela atividade observada",
            "attribution": "Intervenção comparada com sazonalidade e alterações de ocupação",
            "limitations": "Sem grupo de controlo independente",
            "confidence": "moderate",
        },
    )
    assert realized.status_code == 201, realized.text

    value_case = client.get(
        f"/api/organizations/{organization_id}/pilots/{pilot['id']}/value-case",
        headers=headers,
    )
    assert value_case.status_code == 200, value_case.text
    payload = value_case.json()
    assert payload["monetary_eur"]["expected"] == 15000.0
    assert payload["monetary_eur"]["realized"] == 9000.0
    assert payload["evidence_completeness_pct"] == 100
    assert payload["dimensions"]["economic"]["count"] == 2


def test_pilot_team_and_report_suite_are_scoped_to_the_pilot() -> None:
    headers, organization_id, pilot = _pilot()
    base = f"/api/organizations/{organization_id}/pilots/{pilot['id']}"

    collaborator = client.post(
        f"{base}/collaborators",
        headers=headers,
        json={
            "role_key": "program_mentor",
            "display_name": "Mentor do programa",
            "email": "mentor@example.com",
            "organization_name": "Programa de inovação",
            "can_edit": False,
            "can_review": True,
            "notes": "Acompanha o piloto sem autoridade sobre a decisão formal.",
        },
    )
    assert collaborator.status_code == 201, collaborator.text
    collaborator_payload = collaborator.json()
    assert collaborator_payload["role_key"] == "program_mentor"
    assert collaborator_payload["can_review"] is True

    team = client.get(f"{base}/collaborators", headers=headers)
    assert team.status_code == 200, team.text
    assert len(team.json()["collaborators"]) == 1
    assert "pilot_owner" in team.json()["roles"]

    reports = client.get(f"{base}/reports", headers=headers)
    assert reports.status_code == 200, reports.text
    report_types = {row["type"] for row in reports.json()["reports"]}
    assert {
        "pilot_brief",
        "data_readiness",
        "decision_dossier",
        "progress",
        "outcome",
        "scale_recommendation",
        "full",
    } == report_types

    full = client.get(f"{base}/reports/full", headers=headers)
    assert full.status_code == 200, full.text
    full_payload = full.json()
    assert full_payload["schema"] == "sris.full.v1"
    assert full_payload["pilot"]["id"] == pilot["id"]
    assert full_payload["governance"]["collaborators"][0]["role_key"] == "program_mentor"
    assert "outcome" in full_payload["sections"]
    assert "scale_recommendation" in full_payload["sections"]
