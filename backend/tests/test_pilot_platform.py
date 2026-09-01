from __future__ import annotations

import os
from uuid import uuid4

os.environ.setdefault("SRIS_PILOT_MODE", "true")
os.environ.setdefault("SRIS_PUBLIC_SIGNUP_ENABLED", "true")

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _workspace() -> tuple[dict[str, str], str]:
    marker = uuid4().hex
    response = client.post(
        "/api/pilot/register",
        json={
            "email": f"pilot-platform-{marker}@example.com",
            "full_name": "Pilot Platform Tester",
            "password": "A-secure-password-1234",
            "organization_name": f"Pilot Platform {marker[:8]}",
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    return {"Authorization": f"Bearer {payload['access_token']}"}, payload["organization_id"]


def test_pilot_platform_exposes_five_moments_and_eight_canonical_records() -> None:
    response = client.get("/api/pilot/capabilities")
    assert response.status_code == 200
    payload = response.json()
    assert payload["architecture"] == "universal_core_configurable_profiles"
    assert payload["user_moments"] == [
        "context",
        "evidence",
        "decision",
        "measurement",
        "memory",
    ]
    assert payload["canonical_records"] == [
        "observation",
        "evidence",
        "hypothesis",
        "alternative",
        "decision",
        "action",
        "outcome",
        "learning",
    ]
    assert payload["pilot_portfolio"] is True
    assert payload["profile_count"] == 6
    assert "research_and_innovation" in payload["configurable_sector_profiles"]
    assert "tourism_advance" in payload["program_sources"]
    assert "hospitality_resource_efficiency" in payload["hospitality_templates"]


def test_hospitality_pilot_is_created_without_invented_results_and_generates_report() -> None:
    headers, organization_id = _workspace()
    base = f"/api/organizations/{organization_id}/pilots"

    catalog = client.get(f"{base}/templates", headers=headers)
    assert catalog.status_code == 200, catalog.text
    keys = {row["key"] for row in catalog.json()["templates"]}
    assert {
        "universal_decision_pilot",
        "hospitality_resource_efficiency",
        "hospitality_operational_intelligence",
        "public_service_improvement",
        "investment_validation",
        "research_and_innovation_validation",
    } <= keys

    created = client.post(
        base,
        headers=headers,
        json={
            "title": "Eficiência hídrica numa unidade hoteleira",
            "template_key": "hospitality_resource_efficiency",
            "sector_profile": "hospitality",
            "program_source": "tourism_advance",
            "partner_name": "Parceiro piloto",
            "context_name": "Unidade demonstrativa",
            "context_type": "unit",
            "problem_statement": "O consumo absoluto aumentou e ainda não está explicado pela atividade real.",
            "decision_question": "Que intervenção reversível deve ser testada primeiro sem degradar a experiência do hóspede?",
            "objective": "Construir uma baseline normalizada, testar uma intervenção e medir o resultado observado.",
            "scope": "Uma unidade, um recurso prioritário e um horizonte de noventa dias.",
            "pilot_owner": "Responsável do piloto",
        },
    )
    assert created.status_code == 201, created.text
    pilot = created.json()
    assert pilot["code"] == "PLT-001"
    assert pilot["sector_profile"] == "hospitality"
    assert len(pilot["metrics"]) == 4
    assert len(pilot["data_sources"]) == 4
    assert len(pilot["work_items"]) == 6
    assert all(metric["current_value"] is None for metric in pilot["metrics"])
    assert pilot["readiness"]["ready_for_execution"] is False
    assert pilot["methodological_contract"]["canonical_records"][0] == "observation"

    metric = pilot["metrics"][0]
    measured = client.patch(
        f"{base}/{pilot['id']}/metrics/{metric['id']}",
        headers=headers,
        json={
            "baseline_value": 510,
            "target_value": 450,
            "current_value": 462,
            "source": "Mapa de consumos e ocupação; janeiro a março.",
            "method": "Litros divididos por quarto-noite ocupado.",
            "limitations": "Atribuição ainda sujeita a sazonalidade e rega.",
            "confidence": "moderate",
            "status": "tracking",
            "baseline_period": "2026-01 a 2026-03",
            "result_period": "2026-05 a 2026-07",
        },
    )
    assert measured.status_code == 200, measured.text
    metric_payload = measured.json()
    assert metric_payload["change_pct"] == -9.41
    assert metric_payload["status"] == "attention"

    report = client.get(f"{base}/{pilot['id']}/report", headers=headers)
    assert report.status_code == 200, report.text
    report_payload = report.json()
    assert report_payload["schema"] == "sris.pilot-report.v1"
    assert report_payload["pilot_brief"]["program_source"] == "tourism_advance"
    assert report_payload["outcome_scorecard"][0]["baseline"] == 510.0
    assert "Nenhum benefício" in report_payload["value_and_scale"]["rule"]

    summary = client.get(f"{base}/summary", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["total"] == 1
    assert summary.json()["require_attention"] == 1


def test_pilot_revision_conflict_is_explicit() -> None:
    headers, organization_id = _workspace()
    base = f"/api/organizations/{organization_id}/pilots"
    created = client.post(
        base,
        headers=headers,
        json={
            "title": "Piloto transversal de decisão",
            "problem_statement": "Existe uma decisão material sem baseline nem comparação estruturada.",
            "decision_question": "Qual intervenção deve ser testada antes de comprometer recursos adicionais?",
            "objective": "Reduzir incerteza e medir uma alteração operacional reversível.",
            "scope": "Uma unidade operacional e uma decisão.",
            "pilot_owner": "Owner",
        },
    )
    assert created.status_code == 201, created.text
    pilot = created.json()

    first = client.patch(
        f"{base}/{pilot['id']}",
        headers=headers,
        json={
            "expected_revision": 1,
            "lifecycle_state": "discovery",
            "change_note": "Discovery iniciado com o parceiro.",
        },
    )
    assert first.status_code == 200, first.text
    assert first.json()["revision"] == 2

    conflict = client.patch(
        f"{base}/{pilot['id']}",
        headers=headers,
        json={
            "expected_revision": 1,
            "lifecycle_state": "active",
            "change_note": "Tentativa concorrente desatualizada.",
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "pilot_revision_conflict"
