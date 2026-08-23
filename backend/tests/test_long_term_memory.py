from __future__ import annotations

import hashlib
import os
from uuid import uuid4

from fastapi.testclient import TestClient

from app.atlas_platform.database import Base, engine
from app.main import app

os.environ.pop("OPENAI_API_KEY", None)
os.environ["SRIS_AI_ENABLED"] = "false"

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
client = TestClient(app)


def _owner() -> tuple[dict[str, str], str]:
    suffix = uuid4().hex[:8]
    email = f"memory-owner-{suffix}@example.com"
    password = "strong-password-123"
    assert client.post("/api/auth/register", json={
        "email": email, "full_name": "Memory Owner", "password": password
    }).status_code == 201
    login = client.post("/api/auth/login", json={"email": email, "password": password})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    org = client.post("/api/organizations", headers=headers, json={
        "name": f"Memory Lab {suffix}", "slug": f"memory-lab-{suffix}"
    })
    assert org.status_code == 201, org.text
    return headers, org.json()["id"]


def _mission(headers: dict[str, str], org: str) -> dict:
    response = client.post(
        f"/api/organizations/{org}/mission-intelligence/missions",
        headers=headers,
        json={
            "title": "Consumo operacional de água",
            "objective": "Reduzir desperdício preservando contexto e aprendizagem.",
            "context": "Hotel com ocupação variável e consumo de água medido por período.",
            "central_question": "Que regra de decisão deve ser preservada para missões futuras?",
            "mission_kind": "mission",
            "domain": "operational_efficiency",
            "priority": "strategic",
            "horizon": "2026",
            "stakeholders": ["operações", "direção"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_memory_sync_asset_ledger_search_and_supersession() -> None:
    headers, org = _owner()
    mission = _mission(headers, org)
    learning = client.post(
        f"/api/organizations/{org}/mission-intelligence/missions/{mission['id']}/learnings",
        headers=headers,
        json={
            "expected_revision": mission["revision"],
            "title": "Normalizar por atividade antes de classificar anomalia",
            "description": "O consumo deve ser normalizado pela unidade operacional relevante antes de concluir que existe uma anomalia.",
            "based_on_ids": [],
            "validity_conditions": ["Unidade operacional comparável"],
            "invalidation_triggers": ["Mudança material do processo"],
            "confidence": "moderate",
        },
    )
    assert learning.status_code == 201, learning.text

    base = f"/api/organizations/{org}/mission-intelligence/memory"
    sync = client.post(f"{base}/sync", headers=headers)
    assert sync.status_code == 200, sync.text
    assert sync.json()["created"] >= 1

    status = client.get(f"{base}/status", headers=headers)
    assert status.status_code == 200, status.text
    payload = status.json()
    assert payload["memory_is_model_independent"] is True
    assert payload["retention_policy"] == "append_supersede_archive_no_silent_delete"
    assert payload["items_by_type"]["learning"] >= 1

    search = client.get(f"{base}/items?q=normalizado", headers=headers)
    assert search.status_code == 200, search.text
    assert len(search.json()) >= 1
    item = search.json()[0]
    assert item["canonical_record_id"].startswith("LRN-")

    content = b"original evidence bytes"
    sha = hashlib.sha256(content).hexdigest()
    asset = client.post(
        f"{base}/assets",
        headers=headers,
        json={
            "mission_id": mission["id"],
            "storage_backend": "s3-compatible",
            "object_key": f"org/{org}/mission/{mission['id']}/evidence.pdf",
            "original_filename": "evidence.pdf",
            "media_type": "application/pdf",
            "byte_size": len(content),
            "sha256": sha,
            "provenance": {"origin": "operator_upload", "method": "pilot"},
            "metadata": {"classification": "evidence_candidate"},
        },
    )
    assert asset.status_code == 201, asset.text
    assert asset.json()["asset"]["sha256"] == sha

    duplicate = client.post(
        f"{base}/assets",
        headers=headers,
        json={
            "mission_id": mission["id"],
            "storage_backend": "s3-compatible",
            "object_key": "duplicate-key",
            "original_filename": "same.pdf",
            "sha256": sha,
        },
    )
    assert duplicate.status_code == 201, duplicate.text
    assert duplicate.json()["status"] == "already_registered"

    supersede = client.post(
        f"{base}/items/{item['id']}/supersede",
        headers=headers,
        json={
            "title": "Regra de normalização revista",
            "summary": "A regra continua útil, mas deve ser aplicada apenas quando a unidade operacional permanece materialmente comparável.",
            "reason": "O piloto mostrou que alterações de processo quebram a comparabilidade.",
            "state": "active",
            "confidence": "moderate",
        },
    )
    assert supersede.status_code == 201, supersede.text
    assert supersede.json()["item"]["supersedes_id"] == item["id"]

    graph = client.get(f"{base}/graph", headers=headers)
    assert graph.status_code == 200, graph.text
    assert any(edge["relation_type"] == "supersedes" for edge in graph.json()["edges"])


def test_memory_sync_is_idempotent() -> None:
    headers, org = _owner()
    mission = _mission(headers, org)
    created = client.post(
        f"/api/organizations/{org}/mission-intelligence/missions/{mission['id']}/learnings",
        headers=headers,
        json={
            "expected_revision": mission["revision"],
            "title": "Aprendizagem persistente",
            "description": "Uma aprendizagem canónica deve ser indexada uma única vez mesmo após várias sincronizações.",
            "based_on_ids": [],
            "validity_conditions": [],
            "invalidation_triggers": [],
            "confidence": "low",
        },
    )
    assert created.status_code == 201, created.text
    base = f"/api/organizations/{org}/mission-intelligence/memory"
    first = client.post(f"{base}/sync", headers=headers)
    second = client.post(f"{base}/sync", headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["created"] == 0
