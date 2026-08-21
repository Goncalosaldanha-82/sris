from __future__ import annotations

import os
from uuid import uuid4

from fastapi.testclient import TestClient

from app.atlas_platform.database import Base, engine
from app.main import app


os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("SRIS_AI_PILOT_ORGANIZATION_ID", None)
os.environ["SRIS_AI_ENABLED"] = "false"

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
client = TestClient(app)


def _owner() -> tuple[dict[str, str], str]:
    suffix = uuid4().hex[:8]
    email = f"evolution-owner-{suffix}@example.com"
    password = "strong-password-123"
    register = client.post(
        "/api/auth/register",
        json={"email": email, "full_name": "Evolution Owner", "password": password},
    )
    assert register.status_code == 201, register.text
    login = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    organization = client.post(
        "/api/organizations",
        headers=headers,
        json={"name": f"Evolution Lab {suffix}", "slug": f"evolution-lab-{suffix}"},
    )
    assert organization.status_code == 201, organization.text
    return headers, organization.json()["id"]


def _mission(headers: dict[str, str], organization_id: str, title: str, context: str) -> dict:
    response = client.post(
        f"/api/organizations/{organization_id}/mission-intelligence/missions",
        headers=headers,
        json={
            "title": title,
            "objective": "Usar experiência anterior sem transportar conclusões para contextos materialmente diferentes.",
            "context": context,
            "central_question": "Que conhecimento anterior continua aplicável e o que deve ser revalidado?",
            "mission_kind": "mission",
            "domain": "hospitality_operations",
            "priority": "strategic",
            "horizon": "2026",
            "stakeholders": ["operações", "gestão", "manutenção"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _learning(
    headers: dict[str, str],
    organization_id: str,
    mission: dict,
    *,
    title: str,
    description: str,
    scoped: bool = True,
) -> dict:
    response = client.post(
        f"/api/organizations/{organization_id}/mission-intelligence/missions/{mission['id']}/learnings",
        headers=headers,
        json={
            "expected_revision": mission["revision"],
            "title": title,
            "description": description,
            "based_on_ids": [],
            "validity_conditions": ["O indicador operacional é comparável"] if scoped else [],
            "invalidation_triggers": ["Alteração material do processo"] if scoped else [],
            "confidence": "moderate",
        },
    )
    assert response.status_code == 201, response.text
    mission["revision"] = response.json()["revision"]
    return response.json()["learning"]


def test_preflight_uses_context_fingerprint_and_prior_learning() -> None:
    headers, organization_id = _owner()
    october = _mission(
        headers,
        organization_id,
        "Consumo de água — outubro",
        "Hotel com ocupação de 72%, lavandaria interna e consumo de água por quarto ocupado.",
    )
    learning = _learning(
        headers,
        organization_id,
        october,
        title="Normalizar consumo antes de classificar anomalias",
        description="Normalizar o consumo de água por unidade de atividade antes de classificar a variação como anomalia operacional.",
    )
    february = _mission(
        headers,
        organization_id,
        "Consumo de água — fevereiro",
        "Hotel com ocupação de 31%, nova lavandaria e nova variação do consumo de água por quarto ocupado.",
    )

    fingerprint = client.get(
        f"/api/organizations/{organization_id}/mission-intelligence/missions/{february['id']}/context-fingerprint",
        headers=headers,
    )
    assert fingerprint.status_code == 200, fingerprint.text
    assert fingerprint.json()["domain"] == "hospitality_operations"
    assert len(fingerprint.json()["fingerprint_hash"]) == 64

    preflight = client.get(
        f"/api/organizations/{organization_id}/mission-intelligence/missions/{february['id']}/preflight",
        headers=headers,
    )
    assert preflight.status_code == 200, preflight.text
    payload = preflight.json()
    assert payload["related_missions"]
    assert payload["related_missions"][0]["mission_code"] == october["code"]
    assert any(item["learning"]["canonical_id"] == learning["canonical_id"] for item in payload["learning_candidates"])
    assert any("Rever" in item["action"] for item in payload["recommended_preflight_actions"])


def test_invalidation_becomes_visible_as_knowledge_conflict() -> None:
    headers, organization_id = _owner()
    source = _mission(
        headers,
        organization_id,
        "Processo original",
        "Hotel com processo operacional A e indicador de consumo comparável por unidade de atividade.",
    )
    learning = _learning(
        headers,
        organization_id,
        source,
        title="Comparar por unidade operacional",
        description="Comparar o consumo por unidade operacional equivalente antes de interpretar alterações absolutas.",
    )
    target = _mission(
        headers,
        organization_id,
        "Processo alterado",
        "Hotel depois de alteração material do processo e mudança da unidade operacional de comparação.",
    )
    review = client.post(
        (
            f"/api/organizations/{organization_id}/mission-intelligence/missions/{target['id']}"
            f"/learning-inheritance/{source['id']}/{learning['canonical_id']}"
        ),
        headers=headers,
        json={
            "expected_revision": target["revision"],
            "disposition": "invalidated",
            "rationale": "A aprendizagem não é transportável sem nova base comparável.",
            "context_change": "A unidade operacional e o processo foram alterados materialmente.",
        },
    )
    assert review.status_code == 200, review.text

    preflight = client.get(
        f"/api/organizations/{organization_id}/mission-intelligence/missions/{target['id']}/preflight",
        headers=headers,
    )
    assert preflight.status_code == 200, preflight.text
    conflicts = preflight.json()["contradictions"]
    assert any(item["relation_type"] == "context_invalidated_learning" for item in conflicts)
    assert any(item["status"] == "resolved_by_invalidation" for item in conflicts)


def test_decision_debt_flags_learning_without_validity_scope() -> None:
    headers, organization_id = _owner()
    mission = _mission(
        headers,
        organization_id,
        "Aprendizagem sem âmbito",
        "Missão de teste para verificar se conhecimento sem condições de validade cria pendência estrutural.",
    )
    _learning(
        headers,
        organization_id,
        mission,
        title="Regra sem condições declaradas",
        description="Uma regra operacional foi aprendida mas ainda não tem condições explícitas de validade ou invalidação.",
        scoped=False,
    )
    debt = client.get(
        f"/api/organizations/{organization_id}/mission-intelligence/decision-debt",
        headers=headers,
    )
    assert debt.status_code == 200, debt.text
    selected = next(item for item in debt.json()["missions"] if item["mission_id"] == mission["id"])
    assert selected["score"] >= 8
    assert selected["components"]["learnings_without_validity_scope"]


def test_graph_patterns_and_dashboard_accumulate_cross_mission_experience() -> None:
    headers, organization_id = _owner()
    first = _mission(
        headers,
        organization_id,
        "Água — unidade A",
        "Hotel A analisa consumo de água por quarto ocupado e atividade operacional.",
    )
    second = _mission(
        headers,
        organization_id,
        "Água — unidade B",
        "Hotel B analisa consumo de água por quarto ocupado e atividade operacional.",
    )
    _learning(
        headers,
        organization_id,
        first,
        title="Normalizar consumo por atividade",
        description="Normalizar consumo de água por atividade operacional comparável antes de investigar anomalias de consumo.",
    )
    _learning(
        headers,
        organization_id,
        second,
        title="Normalizar consumo por atividade operacional",
        description="Normalizar consumo de água por atividade operacional comparável antes de classificar anomalias no consumo.",
    )

    patterns = client.get(
        f"/api/organizations/{organization_id}/mission-intelligence/emergent-patterns",
        headers=headers,
    )
    assert patterns.status_code == 200, patterns.text
    assert patterns.json()["count"] >= 1
    assert patterns.json()["patterns"][0]["status"] == "emergent_hypothesis"

    graph = client.get(
        f"/api/organizations/{organization_id}/mission-intelligence/learning-graph",
        headers=headers,
    )
    assert graph.status_code == 200, graph.text
    assert graph.json()["summary"]["mission_nodes"] == 2
    assert graph.json()["summary"]["knowledge_nodes"] >= 2

    dashboard = client.get(
        f"/api/organizations/{organization_id}/mission-intelligence/evolution-dashboard",
        headers=headers,
    )
    assert dashboard.status_code == 200, dashboard.text
    metrics = dashboard.json()["metrics"]
    assert metrics["active_missions"] == 2
    assert metrics["canonical_learnings"] >= 2
    assert metrics["emergent_pattern_hypotheses"] >= 1
