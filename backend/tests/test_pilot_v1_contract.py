from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_production_public_demo_and_openapi_contract() -> None:
    frontend = client.get("/")
    assert frontend.status_code == 200
    assert frontend.headers["x-sris-production-build"] == "20260827-public-demo-v1"

    for marker in (
        'meta name="sris-production-build" content="20260827-public-demo-v1"',
        "SRIS — Preservar o raciocínio das decisões",
        "Acesso institucional",
        "Entrar no SRIS",
        "Abrir demonstração",
        "Demonstração pública",
        "Sem sessão institucional",
        'id="demoButton"',
        'sessionStorage.setItem("sris_demo","true")',
        'openApp({mode:"demo"})',
        'config.missions["M-001"]',
        "/api/mission-intelligence/demo/missions",
        "A análise por IA não é executada no modo de demonstração",
        "UI-R2 · MI-1",
    ):
        assert marker in frontend.text

    for forbidden in (
        "PILOTO V1 · VALIDAÇÃO OPERACIONAL",
        "Criar conta e entrar",
        'meta name="sris-pilot-build"',
        "/emergency-stability-v1.css",
    ):
        assert forbidden not in frontend.text

    app_entry = client.get("/app")
    assert app_entry.status_code == 200
    assert "Abrir demonstração" in app_entry.text
    assert app_entry.headers["x-sris-production-build"] == "20260827-public-demo-v1"

    for public_page in (
        "/account.html",
        "/users.html",
        "/learning-inheritance.html",
        "/organizational-learning.html",
        "/organizational-memory.html",
    ):
        response = client.get(public_page)
        assert response.status_code == 200, public_page

    catalog = client.get("/api/mission-intelligence/demo/missions")
    assert catalog.status_code == 200
    mission_codes = catalog.json()["missions"]
    assert "M-001" in mission_codes
    assert "M-002" in mission_codes
    assert "CA-AWARD-APPLICATION" in mission_codes

    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    document = spec.json()
    assert document["info"]["title"] == "SRIS Mission Intelligence API"
    assert document["info"]["version"] == "1.7.3"
    required_paths = (
        "/api/mission-intelligence/demo/missions/{mission_code}/analyze",
        "/api/organizations/{organization_id}/mission-intelligence/missions",
        "/api/organizations/{organization_id}/mission-intelligence/missions/{mission_id}",
        "/api/organizations/{organization_id}/mission-intelligence/missions/{mission_code}/attachments",
        "/api/organizations/{organization_id}/mission-intelligence/dialogues",
        "/api/organizations/{organization_id}/mission-intelligence/dialogues/{session_id}",
        "/api/organizations/{organization_id}/mission-intelligence/ai-governance",
        "/api/organizations/{organization_id}/mission-intelligence/ai-governance/policy",
        "/api/organizations/{organization_id}/mission-intelligence/ai-governance/events",
    )
    for path in required_paths:
        assert path in document["paths"]

    serialized = json.dumps(document, ensure_ascii=False)
    for canonical_kind in (
        "observation",
        "evidence",
        "assumption",
        "constraint",
        "gap",
        "hypothesis",
        "alternative",
        "decision",
        "action",
        "outcome",
        "learning",
    ):
        assert canonical_kind in serialized
