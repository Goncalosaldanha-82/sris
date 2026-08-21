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
    email = f"learning-owner-{suffix}@example.com"
    password = "strong-password-123"
    register = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "full_name": "Learning Owner",
            "password": password,
        },
    )
    assert register.status_code == 201, register.text
    login = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    organization = client.post(
        "/api/organizations",
        headers=headers,
        json={
            "name": f"Learning Lab {suffix}",
            "slug": f"learning-lab-{suffix}",
        },
    )
    assert organization.status_code == 201, organization.text
    return headers, organization.json()["id"]


def _create_mission(
    *,
    headers: dict[str, str],
    organization_id: str,
    title: str,
    context: str,
) -> dict:
    response = client.post(
        f"/api/organizations/{organization_id}/mission-intelligence/missions",
        headers=headers,
        json={
            "title": title,
            "objective": "Reduzir decisões repetidas sem perder contexto operacional relevante.",
            "context": context,
            "central_question": "Que aprendizagem anterior continua defensável neste contexto operacional?",
            "mission_kind": "mission",
            "domain": "operational_efficiency",
            "priority": "strategic",
            "horizon": "2026",
            "stakeholders": ["operações", "gestão"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_learning_changes_the_next_mission_and_can_be_revalidated() -> None:
    headers, organization_id = _owner()

    source = _create_mission(
        headers=headers,
        organization_id=organization_id,
        title="Consumo de água — outubro",
        context=(
            "Unidade de alojamento com ocupação de 72%, configuração de lavandaria A "
            "e consumo de água analisado por quarto ocupado."
        ),
    )

    learning_response = client.post(
        (
            f"/api/organizations/{organization_id}/mission-intelligence/missions/"
            f"{source['id']}/learnings"
        ),
        headers=headers,
        json={
            "expected_revision": source["revision"],
            "title": "Normalizar consumo por atividade antes de investigar anomalias",
            "description": (
                "Neste contexto, a variação de consumo deve ser normalizada por quarto "
                "ocupado antes de ser interpretada como anomalia operacional."
            ),
            "based_on_ids": [],
            "validity_conditions": [
                "Métrica de ocupação comparável",
                "Configuração operacional materialmente equivalente",
            ],
            "invalidation_triggers": [
                "Alteração da lavandaria",
                "Alteração material da ocupação ou da rega",
            ],
            "confidence": "moderate",
        },
    )
    assert learning_response.status_code == 201, learning_response.text
    learning = learning_response.json()["learning"]

    target = _create_mission(
        headers=headers,
        organization_id=organization_id,
        title="Consumo de água — fevereiro",
        context=(
            "A mesma organização analisa nova variação de consumo com ocupação de 31% "
            "e nova configuração de lavandaria."
        ),
    )

    inheritance_url = (
        f"/api/organizations/{organization_id}/mission-intelligence/missions/"
        f"{target['id']}/learning-inheritance"
    )
    inheritance = client.get(inheritance_url, headers=headers)
    assert inheritance.status_code == 200, inheritance.text
    payload = inheritance.json()
    assert payload["summary"]["candidate_count"] == 1
    candidate = payload["candidates"][0]
    assert candidate["source_mission"]["id"] == source["id"]
    assert candidate["learning"]["canonical_id"] == learning["canonical_id"]

    review_url = (
        f"{inheritance_url}/{source['id']}/{learning['canonical_id']}"
    )
    still_valid = client.post(
        review_url,
        headers=headers,
        json={
            "expected_revision": target["revision"],
            "disposition": "still_valid",
            "rationale": "A regra de normalização continua metodologicamente aplicável.",
            "context_change": "",
        },
    )
    assert still_valid.status_code == 200, still_valid.text
    assert still_valid.json()["effect"] == "canonical_learning"
    target_revision = still_valid.json()["revision"]

    target_view = client.get(
        (
            f"/api/organizations/{organization_id}/mission-intelligence/missions/"
            f"{target['id']}"
        ),
        headers=headers,
    )
    assert target_view.status_code == 200, target_view.text
    inherited_records = [
        item
        for item in target_view.json()["records"]
        if item["canonical_id"].startswith("INH-")
    ]
    assert len(inherited_records) == 1
    assert inherited_records[0]["kind"] == "learning"
    assert inherited_records[0]["state"] == "inherited_valid"

    requires_revalidation = client.post(
        review_url,
        headers=headers,
        json={
            "expected_revision": target_revision,
            "disposition": "requires_revalidation",
            "rationale": "O princípio pode continuar útil, mas não deve ser herdado como facto.",
            "context_change": "A ocupação baixou para 31% e a lavandaria foi alterada.",
        },
    )
    assert requires_revalidation.status_code == 200, requires_revalidation.text
    assert requires_revalidation.json()["effect"] == "open_hypothesis"
    target_revision = requires_revalidation.json()["revision"]

    target_view = client.get(
        (
            f"/api/organizations/{organization_id}/mission-intelligence/missions/"
            f"{target['id']}"
        ),
        headers=headers,
    )
    inherited_records = [
        item
        for item in target_view.json()["records"]
        if item["canonical_id"].startswith("INH-")
    ]
    assert len(inherited_records) == 1
    assert inherited_records[0]["kind"] == "hypothesis"
    assert inherited_records[0]["state"] == "requires_revalidation"

    invalidated = client.post(
        review_url,
        headers=headers,
        json={
            "expected_revision": target_revision,
            "disposition": "invalidated",
            "rationale": "A aprendizagem não pode ser aplicada ao novo processo sem nova base.",
            "context_change": "O processo operacional e a unidade de comparação mudaram materialmente.",
        },
    )
    assert invalidated.status_code == 200, invalidated.text
    assert invalidated.json()["effect"] == "not_carried_forward"

    target_view = client.get(
        (
            f"/api/organizations/{organization_id}/mission-intelligence/missions/"
            f"{target['id']}"
        ),
        headers=headers,
    )
    assert not [
        item
        for item in target_view.json()["records"]
        if item["canonical_id"].startswith("INH-")
    ]

    final_inheritance = client.get(inheritance_url, headers=headers)
    assert final_inheritance.status_code == 200, final_inheritance.text
    final_payload = final_inheritance.json()
    assert final_payload["summary"]["invalidated_count"] == 1
    assert final_payload["summary"]["still_valid_count"] == 0
    assert final_payload["summary"]["requires_revalidation_count"] == 0


def test_revalidation_or_invalidation_requires_context_change() -> None:
    headers, organization_id = _owner()
    source = _create_mission(
        headers=headers,
        organization_id=organization_id,
        title="Missão de origem",
        context="Contexto operacional original com informação suficiente para produzir aprendizagem.",
    )
    learning = client.post(
        (
            f"/api/organizations/{organization_id}/mission-intelligence/missions/"
            f"{source['id']}/learnings"
        ),
        headers=headers,
        json={
            "expected_revision": source["revision"],
            "title": "Aprendizagem de teste",
            "description": "Uma aprendizagem suficientemente longa para ser revista numa missão futura.",
            "based_on_ids": [],
            "validity_conditions": [],
            "invalidation_triggers": [],
            "confidence": "moderate",
        },
    ).json()["learning"]
    target = _create_mission(
        headers=headers,
        organization_id=organization_id,
        title="Missão seguinte",
        context="Contexto operacional posterior em que a aprendizagem anterior deve ser revista.",
    )
    response = client.post(
        (
            f"/api/organizations/{organization_id}/mission-intelligence/missions/"
            f"{target['id']}/learning-inheritance/{source['id']}/{learning['canonical_id']}"
        ),
        headers=headers,
        json={
            "expected_revision": target["revision"],
            "disposition": "requires_revalidation",
            "rationale": "O contexto pode ter mudado.",
            "context_change": "",
        },
    )
    assert response.status_code == 422
