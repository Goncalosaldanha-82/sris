from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_pilot_v1_frontend_and_openapi_contract() -> None:
    frontend = client.get("/")
    assert frontend.status_code == 200
    for marker in (
        "SRIS — Mission Intelligence",
        "PILOT V1 · SEPT 2026",
        "Bem-vindo",
        "Entrar",
        "Criar conta",
        "Recuperar palavra-passe",
        "Workspace de decisão incluído",
        "Ver melhor.",
        "Decidir melhor.",
        "Memória organizacional",
        "/product-recovery-v1.css",
    ):
        assert marker in frontend.text

    workspace = client.get("/app")
    assert workspace.status_code == 200
    assets = (
        "/mission-workspace-v2.js",
        "/learning-lineage.js",
        "/intelligence-v2.js",
        "/evidence-graph.js",
        "/admin-accounts.js",
        "/pilot-integration-v3.js",
        "/pilot-operational-v1.js",
        "/mission-experience-v1.js",
        "/decision-workbench-v1.js",
        "/decision-cycle-v1.js",
    )
    for marker in (
        "SRIS — Mission Workspace",
        "Visão geral",
        "Mission Workspace",
        "Da complexidade à decisão verificável.",
        "Observação",
        "Aprendizagem",
        "Comece pela decisão que precisa de ficar melhor fundamentada.",
        "Portfolio persistente",
        "+ Sub-missão",
        "Document Intelligence",
        "Histórico persistente",
        "Evidence Graph",
        "Análise assistida",
        "Serviço e utilização",
        "Memória organizacional",
        *assets,
    ):
        assert marker in workspace.text
    for asset in assets:
        assert workspace.text.count(asset) == 1

    decision_cycle = client.get("/decision-cycle-v1.js")
    assert decision_cycle.status_code == 200
    for marker in (
        "Decisão → Ação → Resultado → Aprendizagem",
        "Enviar aprendizagem para revisão",
        "Publicar na memória organizacional",
        "Governança da aprendizagem",
    ):
        assert marker in decision_cycle.text

    integration = client.get("/pilot-integration-v3.js")
    assert integration.status_code == 200
    assert "installCapabilitySurface" not in integration.text
    assert "a interface carregou, mas o estado do workspace não foi obtido" not in integration.text
    assert "Optional Pilot capabilities unavailable" in integration.text

    assert "UI-R2 · MI-1" not in frontend.text
    assert "UI-R2 · MI-1" not in workspace.text

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
        "/api/pilot/intelligence/ask",
        "/api/pilot/intelligence/history",
        "/api/pilot/decision-cycles",
        "/api/pilot/decision-cycles/missions/{mission_code}",
        "/api/pilot/decision-cycles/{cycle_id}",
        "/api/pilot/decision-cycles/{cycle_id}/materialize-learning",
        "/api/pilot/evidence-graph/missions/{mission_code}/sync",
        "/api/pilot/evidence-graph/missions/{mission_code}",
        "/api/pilot/evidence-graph/missions/{mission_code}/nodes",
        "/api/pilot/evidence-graph/missions/{mission_code}/nodes/{node_id}",
        "/api/pilot/evidence-graph/missions/{mission_code}/edges",
        "/api/pilot/learning/missions/{mission_code}/publish/{learning_node_id}",
        "/api/pilot/learning/missions/{mission_code}/candidates",
        "/api/pilot/learning/missions/{mission_code}/candidates/{packet_id}/review",
        "/api/pilot/learning/missions/{mission_code}/active-context",
    )
    for path in required_paths:
        assert path in document["paths"]
