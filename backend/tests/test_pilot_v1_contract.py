from __future__ import annotations

import json
from io import BytesIO
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image

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
        f"/pilot.css?v={PILOT_BUILD}",
        f"/territory-sunrise.webp?v={PILOT_BUILD}",
        f"/auth.js?v={PILOT_BUILD}",
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
        "/validation-protocol.js",
        "/learning-lineage.js",
        "/decision-cycle-v1.js",
        "/admin-accounts.js",
    )
    for asset in assets:
        assert response.text.count(asset) == 1

    for marker in (
        "SRIS — Espaço de Missão",
        "Visão geral",
        "O que precisa de atenção agora.",
        "Missões ativas",
        "Requerem atenção",
        "Resultados pendentes",
        "Aprendizagens publicadas",
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
        "Medição e impacto",
        "Protocolo de validação",
        "Tourism Advance · Eficiência de recursos",
        "Auditoria e histórico persistente",
        "Análise assistida, não centro do produto.",
        "Imprimir / PDF",
        "Relatório completo .html",
        "Arquivo verificável .json",
        "Relatório .md",
        "ESTADO OPERACIONAL",
        "PRÓXIMO PASSO",
        "Editar missão",
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
    assert payload["measurable_validation"] is True
    assert payload["tourism_advance_profile"] is True
    assert payload["baseline_and_result_comparison"] is True
    assert payload["billing_mode"] == "disabled"
    public_status = client.get("/api/mission-intelligence/status")
    assert public_status.status_code == 200
    assert "ai_model" not in public_status.json()

    app_script = client.get("/app.js")
    assert app_script.status_code == 200
    for marker in (
        "async function renewSession",
        "/api/auth/refresh",
        "async function uploadFiles",
        "data-download-attachment",
        "function completeReportHtml",
        "function exportReport",
        "async function reportSnapshot",
        "function stableJson",
        "async function loadWorkspaceSummary",
        "completion-readiness",
        "sris_active_mission:",
        "sris:mission-opened",
        "missionTemplates",
        "source:'mission_onboarding'",
    ):
        assert marker in app_script.text
    assert "billing-balance" not in app_script.text

    learning = client.get("/learning-lineage.js")
    validation = client.get("/validation-protocol.js")
    decision = client.get("/decision-cycle-v1.js")
    workspace = client.get("/mission-workspace-v2.js")
    assert "window.fetch=" not in learning.text
    assert validation.status_code == 200
    assert "CÁLCULO DETERMINÍSTICO · SEM IA" in validation.text
    assert "sris:validation-updated" in validation.text
    assert "window.fetch=" not in validation.text
    assert "MutationObserver" not in decision.text
    assert "sris:evidence-graph-updated" in decision.text
    assert "model_or_system" not in workspace.text
    assert "credit_eur" not in workspace.text


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
        "/api/organizations/{organization_id}/mission-intelligence/missions/{mission_code}/attachments/{attachment_id}/extraction",
        "/api/organizations/{organization_id}/mission-intelligence/dialogues",
        "/api/pilot/register",
        "/api/pilot/profile",
        "/api/pilot/capabilities",
        "/api/pilot/password-reset/request",
        "/api/pilot/password-reset/confirm",
        "/api/pilot/intelligence/ask",
        "/api/pilot/decision-cycles",
        "/api/pilot/evidence-graph/missions/{mission_code}",
        "/api/pilot/evidence-graph/missions/{mission_code}/document-evidence",
        "/api/pilot/validation/profiles",
        "/api/pilot/validation/missions/{mission_code}",
        "/api/pilot/validation/missions/{mission_code}/protocol",
        "/api/pilot/validation/missions/{mission_code}/measurements/{phase}",
        "/api/pilot/validation/missions/{mission_code}/review",
        "/api/pilot/learning/missions/{mission_code}/candidates",
        "/api/pilot/learning/missions/{mission_code}/active-context",
        "/api/pilot/workspace-summary",
        "/api/pilot/missions/{mission_code}/completion-readiness",
        "/api/pilot/admin/audit",
        "/api/organizations/{organization_id}/invitations",
        "/api/organizations/{organization_id}/mission-intelligence/missions/{mission_id}/revisions",
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


def test_pilot_account_activation_surface_uses_pilot_session_contract() -> None:
    response = client.get("/account.html")
    assert response.status_code == 200
    assert response.headers["cache-control"].startswith("no-store")
    for marker in (
        "Acesso ao workspace · SRIS Pilot",
        "/api/auth/invitations/inspect",
        "/api/auth/invitations/accept",
        "/api/auth/password-reset/confirm",
        "localStorage.setItem('sris_access_token'",
        "localStorage.setItem('sris_refresh_token'",
        "location.replace('/app')",
    ):
        assert marker in response.text


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

    extraction = client.get(
        f"/api/organizations/{organization_id}/mission-intelligence/missions/{mission_payload['code']}/attachments/{attachment['id']}/extraction",
        headers=headers,
    )
    assert extraction.status_code == 200, extraction.text
    assert extraction.json()["source_sha256"] == attachment["sha256"]
    assert extraction.json()["total_fragments"] == 1
    fragment = extraction.json()["fragments"][0]
    assert fragment["excerpt"] == "Evidence preserved by the Pilot journey."
    assert fragment["char_start"] == 0
    assert fragment["char_end"] == len(fragment["excerpt"])

    graph_base = f"/api/pilot/evidence-graph/missions/{mission_payload['code']}"
    evidence = client.post(
        f"{graph_base}/document-evidence",
        headers=headers,
        json={"chunk_id": fragment["id"], "label": "Fonte operacional preservada"},
    )
    assert evidence.status_code == 201, evidence.text
    assert evidence.json()["source_kind"] == "document_chunk"
    assert evidence.json()["attachment_id"] == attachment["id"]
    assert evidence.json()["char_start"] == fragment["char_start"]
    assert evidence.json()["char_end"] == fragment["char_end"]
    assert evidence.json()["source_sha256"] == attachment["sha256"]

    visual_buffer = BytesIO()
    Image.new("RGB", (2, 2), color=(28, 84, 66)).save(visual_buffer, format="PNG")
    visual_upload = client.post(
        f"/api/organizations/{organization_id}/mission-intelligence/missions/{mission_payload['code']}/attachments",
        headers=headers,
        files={"file": ("observation.png", visual_buffer.getvalue(), "image/png")},
    )
    assert visual_upload.status_code == 201, visual_upload.text
    assert visual_upload.json()["extraction_status"] == "visual_ready"
    visual_extraction = client.get(
        f"/api/organizations/{organization_id}/mission-intelligence/missions/{mission_payload['code']}/attachments/{visual_upload.json()['id']}/extraction",
        headers=headers,
    )
    assert visual_extraction.status_code == 200, visual_extraction.text
    assert visual_extraction.json()["fragments"] == []
    visual_evidence = client.post(
        f"{graph_base}/document-evidence",
        headers=headers,
        json={
            "attachment_id": visual_upload.json()["id"],
            "body": "Observação humana: a imagem recebida contém um quadrado verde uniforme.",
        },
    )
    assert visual_evidence.status_code == 201, visual_evidence.text
    assert visual_evidence.json()["source_kind"] == "visual_document"
    assert visual_evidence.json()["attachment_id"] == visual_upload.json()["id"]
    hypothesis = client.post(
        f"{graph_base}/nodes",
        headers=headers,
        json={
            "node_type": "hypothesis",
            "label": "Hipótese operacional",
            "body": "A persistência mantém o contexto entre sessões.",
            "status": "proposed",
        },
    )
    assert hypothesis.status_code == 201, hypothesis.text
    alternative = client.post(
        f"{graph_base}/nodes",
        headers=headers,
        json={
            "node_type": "alternative",
            "label": "Alternativa comparável",
            "body": "Manter o processo apenas em documentos dispersos.",
            "status": "proposed",
        },
    )
    assert alternative.status_code == 201, alternative.text
    second_alternative = client.post(
        f"{graph_base}/nodes",
        headers=headers,
        json={
            "node_type": "alternative",
            "label": "Alternativa persistente",
            "body": "Manter o contexto canónico, os documentos e a proveniência no Pilot V1.",
            "status": "proposed",
        },
    )
    assert second_alternative.status_code == 201, second_alternative.text
    linked = client.post(
        f"{graph_base}/edges",
        headers=headers,
        json={
            "from_node_id": evidence.json()["id"],
            "to_node_id": hypothesis.json()["id"],
            "edge_type": "supports",
            "provenance": {"human_curated": True},
        },
    )
    assert linked.status_code == 201, linked.text

    blocked = client.patch(
        f"/api/organizations/{organization_id}/mission-intelligence/missions/{mission_payload['id']}",
        headers=headers,
        json={
            "expected_revision": mission_payload["revision"],
            "lifecycle_state": "completed",
            "change_note": "Tentativa deliberadamente prematura.",
        },
    )
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["detail"]["code"] == "mission_completion_blocked"

    decision = client.post(
        "/api/pilot/decision-cycles",
        headers=headers,
        json={
            "mission_code": mission_payload["code"],
            "decision": "Adotar o percurso persistente do Pilot V1.",
            "action": "Reabrir a missão depois de uma nova autenticação.",
            "owner": "Pilot Journey",
            "due_date": "2026-09-01",
            "expected_outcome": "A missão reaparece com o mesmo contexto.",
            "evidence_node_id": evidence.json()["id"],
        },
    )
    assert decision.status_code == 201, decision.text
    completed_cycle = client.patch(
        f"/api/pilot/decision-cycles/{decision.json()['id']}",
        headers=headers,
        json={
            "status": "completed",
            "action": "Reabrir a missão depois de uma nova autenticação.",
            "owner": "Pilot Journey",
            "due_date": "2026-09-01",
            "expected_outcome": "A missão reaparece com o mesmo contexto.",
            "actual_outcome": "A missão, o documento e o grafo reapareceram.",
            "learning": "A continuidade deve ser validada pelo estado persistente e não pelo ecrã.",
        },
    )
    assert completed_cycle.status_code == 200, completed_cycle.text
    materialized = client.post(
        f"/api/pilot/decision-cycles/{decision.json()['id']}/materialize-learning",
        headers=headers,
    )
    assert materialized.status_code == 201, materialized.text
    assert materialized.json()["decision_node_id"] != evidence.json()["id"]
    learning_node_id = materialized.json()["learning_node_id"]
    lineage_graph = client.get(graph_base, headers=headers)
    assert lineage_graph.status_code == 200, lineage_graph.text
    assert any(
        edge["from_node_id"] == evidence.json()["id"]
        and edge["to_node_id"] == materialized.json()["decision_node_id"]
        and edge["edge_type"] == "informs"
        for edge in lineage_graph.json()["edges"]
    )
    accepted = client.patch(
        f"{graph_base}/nodes/{learning_node_id}",
        headers=headers,
        json={"status": "accepted"},
    )
    assert accepted.status_code == 200, accepted.text
    published = client.post(
        f"/api/pilot/learning/missions/{mission_payload['code']}/publish/{learning_node_id}",
        headers=headers,
    )
    assert published.status_code == 201, published.text

    readiness = client.get(
        f"/api/pilot/missions/{mission_payload['code']}/completion-readiness",
        headers=headers,
    )
    assert readiness.status_code == 200, readiness.text
    assert readiness.json()["ready"] is True
    assert all(check["passed"] for check in readiness.json()["checks"])

    completed_mission = client.patch(
        f"/api/organizations/{organization_id}/mission-intelligence/missions/{mission_payload['id']}",
        headers=headers,
        json={
            "expected_revision": mission_payload["revision"],
            "lifecycle_state": "completed",
            "change_note": "Ciclo completo, revisto e publicado.",
        },
    )
    assert completed_mission.status_code == 200, completed_mission.text
    assert completed_mission.json()["lifecycle_state"] == "completed"

    sub_mission = client.post(
        f"/api/organizations/{organization_id}/mission-intelligence/missions",
        headers=headers,
        json={
            "title": "Sub-missão persistente do percurso",
            "objective": "Confirmar que o trabalho pode ser decomposto sem perder linhagem.",
            "central_question": "A sub-missão preserva a relação com a missão concluída?",
            "context": "Validação funcional do percurso hierárquico do Pilot V1.",
            "parent_mission_id": mission_payload["id"],
            "mission_kind": "mission",
            "domain": "pilot_validation",
            "priority": "standard",
        },
    )
    assert sub_mission.status_code == 201, sub_mission.text
    assert sub_mission.json()["parent_code"] == mission_payload["code"]
    candidates = client.get(
        f"/api/pilot/learning/missions/{sub_mission.json()['code']}/candidates",
        headers=headers,
    )
    assert candidates.status_code == 200, candidates.text
    packet = next(
        row
        for row in candidates.json()["candidates"]
        if row["source_mission"]["code"] == mission_payload["code"]
    )
    reviewed = client.post(
        f"/api/pilot/learning/missions/{sub_mission.json()['code']}/candidates/{packet['id']}/review",
        headers=headers,
        json={
            "disposition": "still_valid",
            "rationale": "A sub-missão partilha o mesmo contrato de persistência.",
            "context_change": "",
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    inherited = client.get(
        f"/api/pilot/learning/missions/{sub_mission.json()['code']}/active-context",
        headers=headers,
    )
    assert inherited.status_code == 200, inherited.text
    assert "continuidade" in inherited.json()["context_text"].lower()

    summary = client.get("/api/pilot/workspace-summary", headers=headers)
    assert summary.status_code == 200, summary.text
    summary_mission = next(row for row in summary.json()["missions"] if row["id"] == mission_payload["id"])
    assert summary_mission["progress_percent"] == 100
    assert summary_mission["published_learning"] == 1
    revisions = client.get(
        f"/api/organizations/{organization_id}/mission-intelligence/missions/{mission_payload['id']}/revisions",
        headers=headers,
    )
    assert revisions.status_code == 200, revisions.text
    assert [row["revision"] for row in revisions.json()] == [2, 1]

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


def test_tourism_advance_profile_normalizes_and_governs_impact(monkeypatch) -> None:
    monkeypatch.setenv("SRIS_PUBLIC_SIGNUP_ENABLED", "true")
    suffix = uuid4().hex[:10]
    registered = client.post(
        "/api/pilot/register",
        json={
            "full_name": "Tourism Pilot Reviewer",
            "organization_name": f"Tourism Validation {suffix}",
            "email": f"tourism-validation-{suffix}@example.com",
            "password": "tourism-validation-123",
        },
    )
    assert registered.status_code == 201, registered.text
    headers = auth_headers(registered.json()["access_token"])
    profile = client.get("/api/pilot/profile", headers=headers)
    organization_id = profile.json()["organization"]["id"]

    mission = client.post(
        f"/api/organizations/{organization_id}/mission-intelligence/missions",
        headers=headers,
        json={
            "title": "Reduzir água normalizada pela atividade real",
            "objective": "Validar uma intervenção operacional pequena, mensurável e reversível.",
            "central_question": "A intervenção reduz água por quarto ocupado sem degradar a operação?",
            "context": "Piloto Tourism Advance numa unidade de alojamento.",
            "mission_kind": "mission",
            "domain": "hospitality_resource_efficiency",
            "priority": "strategic",
            "horizon": "90 dias",
            "validation_profile": "tourism_advance_resource_efficiency",
            "stakeholders": [],
        },
    )
    assert mission.status_code == 201, mission.text
    mission_payload = mission.json()
    assert mission_payload["validation_profile"] == "tourism_advance_resource_efficiency"
    validation_base = f"/api/pilot/validation/missions/{mission_payload['code']}"

    seeded = client.get(validation_base, headers=headers)
    assert seeded.status_code == 200, seeded.text
    seeded_payload = seeded.json()
    assert seeded_payload["required"] is True
    assert seeded_payload["profile"] == "tourism_advance_resource_efficiency"
    assert seeded_payload["protocol"]["denominator_name"] == "Quartos ocupados"

    protocol = client.put(
        f"{validation_base}/protocol",
        headers=headers,
        json={
            "expected_revision": seeded_payload["protocol"]["revision"],
            "profile": "tourism_advance_resource_efficiency",
            "subject": "Hotel piloto · edifício principal",
            "subject_type": "Unidade de alojamento",
            "problem_statement": "Consumo de água acima da baseline operacional normalizada.",
            "indicator_name": "Consumo de água",
            "indicator_unit": "m³",
            "desired_direction": "decrease",
            "denominator_name": "Quartos ocupados",
            "denominator_unit": "quarto ocupado",
            "target_value": 0.08,
            "target_description": "Atingir no máximo 0,08 m³ por quarto ocupado no período de revisão.",
            "guardrails": "Sem aumento material de reclamações, custo ou consumo noutro recurso.",
            "intervention_description": "Ajustar rotinas de lavandaria e testar deteção diária de fugas.",
            "intervention_start_date": "2026-02-01",
            "intervention_end_date": "2026-02-28",
            "review_date": "2026-04-01",
            "attribution_method": "Comparação antes/depois normalizada, com ocupação e fatores externos revistos.",
        },
    )
    assert protocol.status_code == 200, protocol.text

    graph_base = f"/api/pilot/evidence-graph/missions/{mission_payload['code']}"
    baseline_evidence = client.post(
        f"{graph_base}/nodes",
        headers=headers,
        json={
            "node_type": "evidence",
            "label": "Leituras e ocupação · janeiro",
            "body": "100 m³ e 1 000 quartos ocupados, conferidos pela operação.",
            "status": "verified",
            "provenance": {"source": "operational_records", "human_reviewed": True},
        },
    )
    result_evidence = client.post(
        f"{graph_base}/nodes",
        headers=headers,
        json={
            "node_type": "evidence",
            "label": "Leituras e ocupação · março",
            "body": "70 m³ e 1 000 quartos ocupados, conferidos pela operação.",
            "status": "verified",
            "provenance": {"source": "operational_records", "human_reviewed": True},
        },
    )
    assert baseline_evidence.status_code == 201, baseline_evidence.text
    assert result_evidence.status_code == 201, result_evidence.text

    baseline = client.put(
        f"{validation_base}/measurements/baseline",
        headers=headers,
        json={
            "expected_revision": protocol.json()["protocol"]["revision"],
            "period_start": "2026-01-01",
            "period_end": "2026-01-31",
            "numerator_value": 100,
            "denominator_value": 1000,
            "evidence_node_id": baseline_evidence.json()["id"],
            "data_quality": "high",
            "notes": "Período completo anterior à intervenção.",
        },
    )
    assert baseline.status_code == 200, baseline.text
    assert baseline.json()["baseline"]["normalized_value"] == 0.1

    result = client.put(
        f"{validation_base}/measurements/result",
        headers=headers,
        json={
            "expected_revision": baseline.json()["protocol"]["revision"],
            "period_start": "2026-03-01",
            "period_end": "2026-03-31",
            "numerator_value": 70,
            "denominator_value": 1000,
            "evidence_node_id": result_evidence.json()["id"],
            "data_quality": "high",
            "notes": "Período completo posterior à intervenção.",
        },
    )
    assert result.status_code == 200, result.text
    analysis = result.json()["analysis"]
    assert analysis["comparable"] is True
    assert analysis["result_value"] == 0.07
    assert round(analysis["percent_change"], 6) == -30.0
    assert analysis["target_status"] == "met"

    current_protocol = result.json()["protocol"]
    protocol_fields = (
        "profile",
        "subject",
        "subject_type",
        "problem_statement",
        "indicator_name",
        "indicator_unit",
        "desired_direction",
        "denominator_name",
        "denominator_unit",
        "target_value",
        "target_description",
        "guardrails",
        "intervention_description",
        "intervention_start_date",
        "intervention_end_date",
        "review_date",
        "attribution_method",
    )
    changed_contract = {key: current_protocol[key] for key in protocol_fields}
    changed_contract["expected_revision"] = current_protocol["revision"]
    changed_contract["denominator_name"] = "Hóspedes-noite"
    locked = client.put(
        f"{validation_base}/protocol",
        headers=headers,
        json=changed_contract,
    )
    assert locked.status_code == 409, locked.text
    assert locked.json()["detail"]["code"] == "validation_measurement_contract_locked"

    reviewed = client.post(
        f"{validation_base}/review",
        headers=headers,
        json={
            "expected_revision": result.json()["protocol"]["revision"],
            "attribution_confidence": "moderate",
            "review_rationale": "A normalização mantém a atividade comparável e a intervenção antecede o resultado.",
            "limitations": "Piloto curto, sem grupo de controlo e sujeito a sazonalidade residual.",
            "external_factors": "Ocupação estável; sem obras ou alterações relevantes de mix.",
            "implementation_deviation": "Uma rotina começou três dias depois do previsto.",
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    reviewed_payload = reviewed.json()
    assert reviewed_payload["readiness"]["ready"] is True
    assert all(check["passed"] for check in reviewed_payload["readiness"]["checks"])
    assert len(reviewed_payload["protocol"]["content_hash"]) == 64
    assert reviewed_payload["history"][0]["event_type"] == "attribution_reviewed"

    overall = client.get(
        f"/api/pilot/missions/{mission_payload['code']}/completion-readiness",
        headers=headers,
    )
    assert overall.status_code == 200, overall.text
    assert overall.json()["validation"]["ready"] is True
    assert overall.json()["ready"] is False
