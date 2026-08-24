from __future__ import annotations

import json
from uuid import uuid4

from fastapi.testclient import TestClient

from app.atlas_platform.config import Settings, configured_database_url, validate_security_settings
from app.main import app
from app.pilot_capabilities import PILOT_BUILD


client = TestClient(app)


def auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def test_railway_database_fallback_and_sqlite_guard(monkeypatch) -> None:
    monkeypatch.delenv("ATLAS_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://pilot.example/pilot")
    assert configured_database_url() == "postgresql+psycopg://pilot.example/pilot"

    monkeypatch.setenv("RAILWAY_SERVICE_ID", "sris-pilot-v1")
    guarded = Settings(
        database_url="sqlite+pysqlite:///./ephemeral.db",
        jwt_secret="a-dedicated-pilot-secret-with-more-than-32-bytes",
        environment="production",
    )
    try:
        validate_security_settings(guarded)
    except RuntimeError as error:
        assert "managed deployments cannot use SQLite" in str(error)
    else:
        raise AssertionError("Railway must never start the Pilot with SQLite")


def test_pilot_entry_is_one_versioned_mobile_safe_surface() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["x-sris-pilot-build"] == PILOT_BUILD
    assert response.headers["cache-control"].startswith("no-store")
    assert response.text.count('rel="stylesheet"') == 1
    for marker in (
        "SRIS — Mission Intelligence",
        "PILOTO V1 · VALIDAÇÃO OPERACIONAL",
        "Bem-vindo",
        "Entrar",
        "Criar conta",
        "Recuperar palavra-passe",
        "Disciplina antes da assistência",
        "Ver melhor.",
        "Decidir melhor.",
        "/pilot.css?v=20260824-mobile-workflow-v2",
        "/territory-sunrise.webp?v=20260824-mobile-workflow-v2",
        "/auth.js?v=20260824-mobile-workflow-v2",
        'id="login-submit"',
    ):
        assert marker in response.text
    for forbidden in (
        "/sunrise.svg",
        "/product-recovery-v1.css",
        "/emergency-stability-v1.css",
        "PILOT V1 · SEPT 2026",
        "gpt-5.6-terra",
        "Crédito inicial incluído",
    ):
        assert forbidden not in response.text

    photo = client.get("/territory-sunrise.webp")
    assert photo.status_code == 200
    assert photo.content.startswith(b"RIFF")
    assert photo.content[8:12] == b"WEBP"
    assert photo.headers["cache-control"].endswith("immutable")


def test_pilot_workspace_loads_only_the_canonical_runtime() -> None:
    response = client.get("/app")
    assert response.status_code == 200
    assert response.headers["x-sris-pilot-build"] == PILOT_BUILD
    assert response.text.count('rel="stylesheet"') == 1

    assets = (
        "/app.js",
        "/mission-workspace-v2.js",
        "/evidence-graph.js",
        "/learning-lineage.js",
        "/decision-cycle-v1.js",
        "/admin-accounts.js",
    )
    for asset in assets:
        assert response.text.count(asset) == 1

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
        "Portefólio persistente",
        "+ Sub-missão",
        "Inteligência documental",
        "Histórico persistente",
        "Análise assistida, não centro do produto.",
        "Imprimir / PDF",
        "Relatório .html",
        "Secção .md",
        'id="upload-drop-zone"',
        'id="mission-file" multiple',
    ):
        assert marker in response.text

    for forbidden in (
        "/pilot-integration-v3.js",
        "/mission-experience-v1.js",
        "/release-hardening-v2.js",
        "/decision-workbench-v1.js",
        "/intelligence-v2.js",
        "/pilot-operational-v1.js",
        "Créditos e planos",
        "+ 10 €",
        "gpt-5.6-terra",
    ):
        assert forbidden not in response.text


def test_pilot_runtime_contracts_are_stable_and_honest() -> None:
    capabilities = client.get("/api/pilot/capabilities")
    assert capabilities.status_code == 200
    payload = capabilities.json()
    assert payload["build"] == PILOT_BUILD
    assert payload["mission_intelligence"] is True
    assert payload["document_intelligence"] is True
    assert payload["persistent_dialogue"] is True
    assert payload["evidence_graph"] is True
    assert payload["organizational_memory"] is True
    assert payload["billing_mode"] == "disabled"

    app_script = client.get("/app.js")
    assert app_script.status_code == 200
    for marker in (
        "async function renewSession",
        "/api/auth/refresh",
        "async function uploadFiles",
        "data-download-attachment",
        "function completeReportHtml",
        "function exportReport",
        "sris:mission-opened",
        "missionTemplates",
        "source:'mission_onboarding'",
    ):
        assert marker in app_script.text
    assert "billing-balance" not in app_script.text

    learning = client.get("/learning-lineage.js")
    decision = client.get("/decision-cycle-v1.js")
    assert "window.fetch=" not in learning.text
    assert "MutationObserver" not in decision.text
    assert "sris:evidence-graph-updated" in decision.text


def test_pilot_openapi_exposes_the_operational_scope() -> None:
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    document = spec.json()
    assert document["info"]["title"] == "SRIS Mission Intelligence API"
    required_paths = (
        "/api/auth/login",
        "/api/auth/refresh",
        "/api/organizations/{organization_id}/mission-intelligence/missions",
        "/api/organizations/{organization_id}/mission-intelligence/missions/{mission_id}",
        "/api/organizations/{organization_id}/mission-intelligence/missions/{mission_code}/attachments",
        "/api/organizations/{organization_id}/mission-intelligence/missions/{mission_code}/attachments/{attachment_id}/download",
        "/api/organizations/{organization_id}/mission-intelligence/dialogues",
        "/api/pilot/register",
        "/api/pilot/profile",
        "/api/pilot/capabilities",
        "/api/pilot/password-reset/request",
        "/api/pilot/password-reset/confirm",
        "/api/pilot/intelligence/ask",
        "/api/pilot/decision-cycles",
        "/api/pilot/evidence-graph/missions/{mission_code}",
        "/api/pilot/learning/missions/{mission_code}/candidates",
        "/api/pilot/learning/missions/{mission_code}/active-context",
    )
    for path in required_paths:
        assert path in document["paths"]

    serialized = json.dumps(document, ensure_ascii=False)
    for kind in (
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
        assert kind in serialized


def test_account_to_persistent_mission_journey(monkeypatch) -> None:
    monkeypatch.setenv("SRIS_PUBLIC_SIGNUP_ENABLED", "true")
    monkeypatch.setenv("SRIS_PILOT_MODE", "true")
    monkeypatch.setenv("SRIS_PILOT_SHOW_RESET_LINK", "true")

    suffix = uuid4().hex[:10]
    email = f"pilot-journey-{suffix}@example.com"
    password = "pilot-password-123"
    new_password = "pilot-password-456"

    registered = client.post(
        "/api/pilot/register",
        json={
            "full_name": "Pilot Journey",
            "organization_name": f"Pilot Workspace {suffix}",
            "email": email,
            "password": password,
        },
    )
    assert registered.status_code == 201, registered.text
    tokens = registered.json()
    headers = auth_headers(tokens["access_token"])

    profile = client.get("/api/pilot/profile", headers=headers)
    assert profile.status_code == 200, profile.text
    organization_id = profile.json()["organization"]["id"]

    mission = client.post(
        f"/api/organizations/{organization_id}/mission-intelligence/missions",
        headers=headers,
        json={
            "title": "Validar persistência do piloto",
            "objective": "Confirmar que a missão permanece depois de voltar a entrar.",
            "central_question": "A missão persiste numa nova sessão autenticada?",
            "context": "Percurso funcional automatizado do Pilot V1.",
            "mission_kind": "mission",
            "domain": "pilot_validation",
            "priority": "strategic",
            "horizon": "1 dia",
            "stakeholders": [],
        },
    )
    assert mission.status_code == 201, mission.text
    mission_payload = mission.json()

    uploaded = client.post(
        f"/api/organizations/{organization_id}/mission-intelligence/missions/{mission_payload['code']}/attachments",
        headers=headers,
        files={"file": ("evidence.txt", b"Evidence preserved by the Pilot journey.", "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    attachment = uploaded.json()
    downloaded = client.get(
        f"/api/organizations/{organization_id}/mission-intelligence/missions/{mission_payload['code']}/attachments/{attachment['id']}/download",
        headers=headers,
    )
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.content == b"Evidence preserved by the Pilot journey."

    logged_in = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert logged_in.status_code == 200, logged_in.text
    relogin_headers = auth_headers(logged_in.json()["access_token"])
    missions = client.get(
        f"/api/organizations/{organization_id}/mission-intelligence/missions",
        headers=relogin_headers,
    )
    assert missions.status_code == 200, missions.text
    assert any(row["id"] == mission_payload["id"] for row in missions.json())

    renewed = client.post(
        "/api/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert renewed.status_code == 200, renewed.text

    reset = client.post(
        "/api/pilot/password-reset/request",
        json={"email": email},
    )
    assert reset.status_code == 200, reset.text
    assert reset.json().get("reset_token")
    confirmed = client.post(
        "/api/pilot/password-reset/confirm",
        json={
            "token": reset.json()["reset_token"],
            "new_password": new_password,
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    assert client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    ).status_code == 401
    assert client.post(
        "/api/auth/login",
        json={"email": email, "password": new_password},
    ).status_code == 200
