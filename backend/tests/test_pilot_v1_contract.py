from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_pilot_v1_frontend_and_openapi_contract() -> None:
    # Public entry point: authentication and account onboarding.
    frontend = client.get("/")
    assert frontend.status_code == 200
    public_markers = (
        "SRIS · Mission Intelligence",
        "PILOT V1 · SEPT 2026",
        "Bem-vindo",
        "Entrar",
        "Criar conta",
        "Recuperar palavra-passe",
        "Crédito inicial incluído",
        "Ver melhor.",
        "Decidir melhor.",
        "Organizational Memory",
    )
    for marker in public_markers:
        assert marker in frontend.text

    # Authenticated workspace: persistent Mission Intelligence experience.
    workspace = client.get("/app")
    assert workspace.status_code == 200
    workspace_markers = (
        "SRIS · Workspace",
        "Visão geral",
        "Mission Intelligence",
        "Mission Workspace",
        "Uma missão não é uma conversa descartável.",
        "Portfolio persistente",
        "+ Sub-missão",
        "Document Intelligence",
        "Documentos",
        "Histórico",
        "Créditos e planos",
        "Copiloto IA",
        "Memória de decisão",
    )
    for marker in workspace_markers:
        assert marker in workspace.text

    # Guard against accidental fallback to the legacy staging shell.
    assert "UI-R2 · MI-1" not in frontend.text
    assert "UI-R2 · MI-1" not in workspace.text

    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    document = spec.json()
    assert document["info"]["title"] == "SRIS Mission Intelligence API"
    assert document["info"]["version"] == "1.7.3"

    # Pilot V1 now exposes the governed MI backbone directly through the workspace.
    required_paths = (
        "/api/mission-intelligence/demo/missions/{mission_code}/analyze",
        "/api/organizations/{organization_id}/mission-intelligence/missions",
        "/api/organizations/{organization_id}/mission-intelligence/missions/{mission_ref}",
        "/api/organizations/{organization_id}/mission-intelligence/missions/{mission_code}/attachments",
        "/api/organizations/{organization_id}/mission-intelligence/dialogues",
        "/api/organizations/{organization_id}/mission-intelligence/dialogues/{session_id}",
        "/api/organizations/{organization_id}/mission-intelligence/ai-governance",
        "/api/organizations/{organization_id}/mission-intelligence/ai-governance/policy",
        "/api/organizations/{organization_id}/mission-intelligence/ai-governance/events",
    )
    for path in required_paths:
        assert path in document["paths"]
