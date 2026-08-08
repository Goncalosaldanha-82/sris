from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.atlas_platform.database import Base, engine
from app.atlas_platform.config import Settings, validate_security_settings
from app.main import app
from app.mission_intelligence import service
from app.mission_intelligence.ai import AIUnavailableError
from app.mission_intelligence.contracts import AIOption


os.environ.pop("OPENAI_API_KEY", None)
os.environ["SRIS_AI_ENABLED"] = "false"

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
client = TestClient(app)


def _owner() -> tuple[dict[str, str], str]:
    register = client.post(
        "/api/auth/register",
        json={
            "email": "mi-owner@example.com",
            "full_name": "Mission Owner",
            "password": "strong-password-123",
        },
    )
    assert register.status_code == 201, register.text
    login = client.post(
        "/api/auth/login",
        json={"email": "mi-owner@example.com", "password": "strong-password-123"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    organization = client.post(
        "/api/organizations",
        headers=headers,
        json={"name": "Mission Intelligence Lab", "slug": "mission-intelligence-lab"},
    )
    assert organization.status_code == 201, organization.text
    return headers, organization.json()["id"]


def _analysis_payload(**patch):
    payload = {
        "title": "M-001 — decisão de gestão florestal",
        "context": "Parcela florestal com decisão de gestão por tomar.",
        "central_question": "Qual é a próxima decisão defensável?",
        "available_evidence": "OBS-0001, OBS-0002 e OBS-0003.",
        "unknowns": "ASS-0001, ASS-0002, RST-0001 e RST-0002.",
        "use_ai": False,
    }
    payload.update(patch)
    return payload


def test_public_demo_runs_real_deterministic_mission_intelligence() -> None:
    status = client.get("/api/mission-intelligence/status")
    assert status.status_code == 200
    assert status.json()["foundation_version"] == "1.3"
    assert status.json()["human_review_required"] is True

    response = client.post(
        "/api/mission-intelligence/demo/missions/M-001/analyze",
        json=_analysis_payload(),
    )
    assert response.status_code == 200, response.text
    data = response.json()
    report = data["deterministic"]
    assert data["execution_mode"] == "deterministic"
    assert data["snapshot_hash"]
    assert report["mission_status"] == "requires_attention"
    assert report["mission_trend"] == "not_evaluable"
    assert report["decision_confidence"] == "moderate"
    gap_codes = {gap["code"] for gap in report["gaps"]}
    assert {"MI-ASSUMPTIONS-OPEN", "MI-CONSTRAINTS-OPEN", "MI-NO-BASELINE"}.issubset(gap_codes)
    assert any("Não se infere resultado" in item for item in report["non_inferences"])


def test_public_demo_never_spends_ai_without_authentication() -> None:
    response = client.post(
        "/api/mission-intelligence/demo/missions/M-001/analyze",
        json=_analysis_payload(use_ai=True),
    )
    assert response.status_code == 200
    assert response.json()["ai"] is None
    assert response.json()["ai_status"] == "authentication_required"


def test_free_text_claim_cannot_become_canonical_baseline() -> None:
    response = client.post(
        "/api/mission-intelligence/demo/missions/M-001/analyze",
        json=_analysis_payload(
            available_evidence="Declaro que existe uma linha de base medida."
        ),
    )
    assert response.status_code == 200
    gap_codes = {gap["code"] for gap in response.json()["deterministic"]["gaps"]}
    assert "MI-NO-BASELINE" in gap_codes


def test_authenticated_run_is_persisted_versioned_and_human_reviewed() -> None:
    headers, organization_id = _owner()
    endpoint = f"/api/organizations/{organization_id}/mission-intelligence/demo/M-001/analyze"
    first = client.post(endpoint, headers=headers, json=_analysis_payload(use_ai=True))
    assert first.status_code == 200, first.text
    first_data = first.json()
    assert first_data["ai_status"] == "not_configured"
    assert first_data["mission_revision"] == 1
    assert first_data["review_status"] == "required"

    same = client.post(endpoint, headers=headers, json=_analysis_payload())
    assert same.status_code == 200
    assert same.json()["mission_revision"] == 1

    changed = client.post(
        endpoint,
        headers=headers,
        json=_analysis_payload(context="Contexto revisto e aceite como nova revisão."),
    )
    assert changed.status_code == 200
    assert changed.json()["mission_revision"] == 2

    mission_list = client.get(
        f"/api/organizations/{organization_id}/mission-intelligence/missions",
        headers=headers,
    )
    assert mission_list.status_code == 200
    assert mission_list.json()[0]["revision"] == 2

    review = client.post(
        f"/api/organizations/{organization_id}/mission-intelligence/runs/{first_data['run_id']}/review",
        headers=headers,
        json={
            "decision": "approved",
            "comment": "Relatório revisto; aprovação não equivale a aceitar qualquer alternativa.",
        },
    )
    assert review.status_code == 200, review.text
    assert review.json()["review_status"] == "approved"


def test_health_checks_database_and_security_headers_are_present() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-request-id"]


def test_ai_failure_never_removes_the_deterministic_report(monkeypatch) -> None:
    monkeypatch.setattr(service, "is_ai_configured", lambda: True)

    def fail_provider(*_args, **_kwargs):
        raise AIUnavailableError("AI provider request failed")

    monkeypatch.setattr(service, "analyze_with_openai", fail_provider)
    result = service.analyze_demo(
        "M-001",
        service.AnalysisInput(**_analysis_payload(use_ai=True)),
        allow_ai=True,
    )
    assert result["ai_status"] == "failed"
    assert result["execution_mode"] == "deterministic"
    assert result["deterministic"]["mission_status"] == "requires_attention"
    assert result["ai"] is None


def test_every_ai_option_requires_a_canonical_basis() -> None:
    with pytest.raises(ValidationError):
        AIOption(
            title="Opção sem base",
            rationale="Não deve atravessar o contrato.",
            risks=[],
            prerequisites=[],
            based_on_ids=[],
        )


def test_frontend_and_openapi_expose_the_new_capability() -> None:
    frontend = client.get("/")
    assert frontend.status_code == 200
    assert "UI-R2 · MI-1" in frontend.text
    assert "Executar Mission Intelligence" in frontend.text

    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    assert spec.json()["info"]["title"] == "SRIS Mission Intelligence API"
    assert spec.json()["info"]["version"] == "1.3.0"
    assert "/api/mission-intelligence/demo/missions/{mission_code}/analyze" in spec.json()["paths"]


def test_production_rejects_a_weak_jwt_secret() -> None:
    with pytest.raises(RuntimeError, match="at least 32 bytes"):
        validate_security_settings(
            Settings(
                database_url="sqlite+pysqlite:///:memory:",
                jwt_secret="too-short",
                environment="production",
            )
        )
