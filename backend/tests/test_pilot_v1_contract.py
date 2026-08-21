from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_pilot_v1_frontend_and_openapi_contract() -> None:
    frontend = client.get("/")
    assert frontend.status_code == 200

    # Pilot V1 is intentionally a new experience. Do not require legacy UI-R2/MI-1
    # presentation markers here; verify the new product contract instead.
    expected_markers = (
        "SRIS — Pilot V1",
        "PILOT V1 · SEPT 2026",
        "Command",
        "Missão ativa",
        "Memória",
        "Aprendizagem",
        "Evidência",
        "Pilot Mode",
        "A organização não deve voltar a aprender a mesma coisa do zero.",
        "PRÓXIMA MELHOR AÇÃO",
        "MEMÓRIA ORGANIZACIONAL",
        "LEARNING INHERITANCE",
        "A missão seguinte começa melhor porque a anterior existiu.",
    )
    for marker in expected_markers:
        assert marker in frontend.text

    # Guard against accidental fallback to the legacy staging shell.
    assert "UI-R2 · MI-1" not in frontend.text

    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    document = spec.json()
    assert document["info"]["title"] == "SRIS Mission Intelligence API"
    assert document["info"]["version"] == "1.7.3"

    # The Pilot V1 changes the experience layer, not the governed MI API contract.
    required_paths = (
        "/api/mission-intelligence/demo/missions/{mission_code}/analyze",
        "/api/organizations/{organization_id}/mission-intelligence/ai-governance",
        "/api/organizations/{organization_id}/mission-intelligence/ai-governance/policy",
        "/api/organizations/{organization_id}/mission-intelligence/ai-governance/events",
        "/api/organizations/{organization_id}/mission-intelligence/demo/{mission_code}/interact",
        "/api/organizations/{organization_id}/mission-intelligence/dialogues/{session_id}",
    )
    for path in required_paths:
        assert path in document["paths"]
