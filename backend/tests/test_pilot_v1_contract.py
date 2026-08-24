from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_pilot_v1_frontend_and_openapi_contract() -> None:
    frontend = client.get("/")
    assert frontend.status_code == 200
    for marker in (
        "SRIS — Mission Intelligence",
        "PILOTO V1 · VALIDAÇÃO OPERACIONAL",
        "Bem-vindo",
        "Entrar",
        "Criar conta",
        "Recuperar palavra-passe",
        "Disciplina antes da assistência",
        "A assistência deve indicar incerteza, separar facto de inferência",
        "Ver melhor.",
        "Decidir melhor.",
        "Missões persistentes",
        "Evidência rastreável",
        "Memória organizacional",
        "/product-recovery-v1.css",
        "/product-core-v2.css",
        "/sunrise.svg",
        "/emergency-stability-v1.css",
    ):
        assert marker in frontend.text
    assert "PILOT V1 · SEPT 2026" not in frontend.text
    assert "gpt-5.6-terra" not in frontend.text
    assert "Crédito inicial incluído" not in frontend.text

    workspace = client.get("/app")
    assert workspace.status_code == 200
    assets = (
        "/mission-workspace-v2.js",
        "/learning-lineage.js",
        "/intelligence-v2.js",
        "/evidence-graph.js",
        "/admin-accounts.js",
        "/release-hardening-v2.js",
        "/decision-workbench-v1.js",
        "/decision-cycle-v1.js",
    )
    for marker in (
        "SRIS — Espaço de Missão",
        "Visão geral",
        "Comece pela decisão. Preserve a razão.",
        "Observação",
        "Evidência",
        "Hipótese",
        "Alternativa",
        "Decisão",
        "Ação",
        "Resultado",
        "Aprendizagem",
        "Pressupostos",
        "Restrições",
        "Lacunas",
        "Proveniência",
        "Confiança",
        "Comece por uma decisão real, não por uma conversa genérica.",
        "Eficiência de recursos",
        "Problema operacional",
        "Investimento ou alteração",
        "Critério de sucesso",
        "Portefólio persistente",
        "+ Sub-missão",
        "Inteligência documental",
        "Histórico persistente",
        "Grafo de evidência",
        "Análise assistida",
        "Memória organizacional",
        "/release-hardening-v2.css",
        "/emergency-stability-v1.css",
        *assets,
    ):
        assert marker in workspace.text
    for asset in assets:
        assert workspace.text.count(asset) == 1

    # The two overlapping observer layers remain available as source files for
    # audit, but must not execute in the authenticated browser shell.
    assert "/pilot-integration-v3.js" not in workspace.text
    assert "/mission-experience-v1.js" not in workspace.text

    for forbidden in (
        "/pilot-operational-v1.js",
        "Créditos e planos",
        "Serviço e utilização",
        "+ 10 €",
        "+ 25 €",
        "+ 50 €",
        "gpt-5.6-terra",
        "PILOT V1 · SEPT 2026",
    ):
        assert forbidden not in workspace.text

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
    assert "20260823-decision-first" in integration.text
    assert "installCapabilitySurface" not in integration.text
    assert "a interface carregou, mas o estado do workspace não foi obtido" not in integration.text
    assert "Optional Pilot capabilities unavailable" in integration.text
    assert "billing-balance" not in integration.text
    assert "model-name" not in integration.text

    hardening = client.get("/release-hardening-v2.js")
    assert hardening.status_code == 200
    for marker in (
        "Carregar documentos",
        "Relatório completo (.pdf)",
        "Relatório completo (.html)",
        "Secção atual (.md)",
        "Análise assistida disponível",
        "Análise assistida indisponível",
    ):
        assert marker in hardening.text

    app_script = client.get("/app.js")
    assert app_script.status_code == 200
    for marker in (
        "missionTemplates",
        "mission-assumptions",
        "mission-constraints",
        "mission-success",
        "node_type:nodeType",
        "source:'mission_onboarding'",
    ):
        assert marker in app_script.text
    assert "pilot_test_topup" not in app_script.text
    assert "billing-balance" not in app_script.text

    evidence_graph = client.get("/evidence-graph.js")
    assert evidence_graph.status_code == 200
    for marker in (
        "Pressuposto",
        "Restrição",
        "Lacuna de informação",
        "Alternativa",
        "Candidato assistido · revisão humana obrigatória",
        "recuperação documental apenas <strong>informa</strong>",
    ):
        assert marker in evidence_graph.text
    assert "provenance.model" not in evidence_graph.text

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
        "/api/pilot/capabilities",
        "/api/pilot/password-reset/request",
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
    for relation in ("constrained_by", "assumes", "requires", "addresses"):
        assert relation in serialized
