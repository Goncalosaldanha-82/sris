from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import text

from app.atlas_platform.config import Settings, configured_database_url, validate_security_settings
from app.atlas_platform.database import SessionLocal
from app.main import app
from app.pilot_capabilities import PILOT_BUILD
from app.pilot_mission_state import (
    MODULE_LABELS,
    REVIEW_UPSTREAMS,
    _review_bundle,
)


client = TestClient(app)


def auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def test_human_review_invalidation_cascades_across_module_views() -> None:
    hashes = {key: f"{key}-hash-v1" for key in MODULE_LABELS}
    hashes.update(
        governance_policy="policy-hash-v1",
        decision_evidence="decision-evidence-hash-v1",
    )
    applicability = {key: "required" for key in MODULE_LABELS}
    applicability["intelligence"] = "optional"
    reviews: dict[str, dict] = {}

    def bind_review(module_key: str, dependency_hashes: dict[str, str | None]) -> None:
        reviews[module_key] = {
            "module_key": module_key,
            "module_content_hash": hashes[module_key],
            "upstream_hashes_json": {
                key: dependency_hashes.get(key)
                for key in REVIEW_UPSTREAMS[module_key]
            },
            "reviewed_at": "2026-08-26T12:00:00Z",
            "created_at": "2026-08-26T12:00:00Z",
            "reviewed_by_user_id": "human-reviewer",
            "rationale": "Revisão humana ligada ao estado transversal corrente.",
        }

    _statuses, dependency_hashes = _review_bundle(
        module_hashes=hashes,
        reviews=reviews,
        applicability=applicability,
    )
    bind_review("validation", dependency_hashes)
    _statuses, dependency_hashes = _review_bundle(
        module_hashes=hashes,
        reviews=reviews,
        applicability=applicability,
    )
    bind_review("economics", dependency_hashes)
    _statuses, dependency_hashes = _review_bundle(
        module_hashes=hashes,
        reviews=reviews,
        applicability=applicability,
    )
    bind_review("comparison", dependency_hashes)
    statuses, _dependency_hashes = _review_bundle(
        module_hashes=hashes,
        reviews=reviews,
        applicability=applicability,
    )
    assert statuses["validation"]["status"] == "current"
    assert statuses["economics"]["status"] == "current"
    assert statuses["comparison"]["status"] == "current"

    hashes["validation"] = "validation-hash-v2"
    statuses, _dependency_hashes = _review_bundle(
        module_hashes=hashes,
        reviews=reviews,
        applicability=applicability,
    )
    assert statuses["validation"]["status"] == "stale"
    assert statuses["economics"]["status"] == "stale"
    assert statuses["comparison"]["status"] == "stale"


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


def test_public_demo_is_read_only_and_uses_only_fictional_data() -> None:
    page = client.get("/demonstracao")
    assert page.status_code == 200
    assert page.headers["cache-control"].startswith("no-store")
    for marker in (
        "Demonstração pública",
        "Todos os dados, entidades, pessoas, locais e resultados apresentados são fictícios",
        "Só de leitura",
        "Os pilotos reais permanecem separados desta demonstração",
        f"/demonstracao.css?v={PILOT_BUILD}",
        f"/demonstracao.js?v={PILOT_BUILD}",
    ):
        assert marker in page.text

    catalog = client.get("/api/mission-intelligence/demo/fictional/missions")
    assert catalog.status_code == 200
    payload = catalog.json()
    assert payload["schema"] == "sris_fictional_demo_catalog"
    assert list(payload["missions"]) == ["DEMO-MUN-001"]
    mission = payload["missions"]["DEMO-MUN-001"]
    assert mission["organization"] == "Município de Vale Sereno (entidade fictícia)"
    serialized = json.dumps(payload, ensure_ascii=False)
    for real_boundary in ("Podentes", "Penela", "Fernando Saldanha", "517723816"):
        assert real_boundary not in serialized

    detail = client.get("/api/mission-intelligence/demo/fictional/missions/DEMO-MUN-001")
    assert detail.status_code == 200
    assert detail.json()["status"].endswith("dados fictícios")
    assert client.get("/api/mission-intelligence/demo/fictional/missions/UNKNOWN").status_code == 404


def test_entry_separates_invited_access_from_public_demo() -> None:
    page = client.get("/")
    assert "As contas institucionais são criadas por convite" in page.text
    assert 'href="/demonstracao"' in page.text
    assert "A demonstração usa apenas dados fictícios" in page.text


def test_pilot_workspace_loads_only_the_canonical_runtime() -> None:
    response = client.get("/app")
    assert response.status_code == 200
    assert response.headers["x-sris-pilot-build"] == PILOT_BUILD
    assert response.text.count('rel="stylesheet"') == 1

    assets = (
        "/app.js",
        "/mission-workspace-v2.js",
        "/mission-state-v1.js",
        "/evidence-graph.js",
        "/validation-protocol.js",
        "/alternative-matrix-v1.js",
        "/business-case-v1.js",
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
        "Comparar alternativas",
        "Economia e recursos",
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
    assert payload["canonical_mission_chain"] == [
        "context", "observation", "evidence", "hypothesis", "alternatives",
        "decision", "action", "measurement", "outcome", "learning", "memory",
    ]
    assert "billing_mode" not in payload
    assert payload["live_business_case"] is True
    assert payload["scenario_financial_analysis"] is True
    assert payload["human_financial_material_resource_tracking"] is True
    assert payload["post_mission_lifecycle_costs"] is True
    assert payload["governed_mission_state"] is True
    assert payload["cross_module_dependencies"] is True
    assert payload["cross_module_conflict_detection"] is True
    assert payload["human_governed_ai_context"] is True
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
        "createGraphNode(mission.code,'target','Critério de sucesso'",
        "metrics_state==='observed_or_estimated'",
    ):
        assert marker in app_script.text
    assert "billing-balance" not in app_script.text

    learning = client.get("/learning-lineage.js")
    evidence_graph = client.get("/evidence-graph.js")
    validation = client.get("/validation-protocol.js")
    comparison = client.get("/alternative-matrix-v1.js")
    business_case = client.get("/business-case-v1.js")
    mission_state = client.get("/mission-state-v1.js")
    decision = client.get("/decision-cycle-v1.js")
    workspace = client.get("/mission-workspace-v2.js")
    assert "window.fetch=" not in learning.text
    assert evidence_graph.status_code == 200
    assert "Fonte íntegra não significa conteúdo verdadeiro" in evidence_graph.text
    assert "validade factual não avaliada" in evidence_graph.text
    assert validation.status_code == 200
    assert "CÁLCULO DETERMINÍSTICO · SEM IA" in validation.text
    assert "sris:validation-updated" in validation.text
    assert "window.fetch=" not in validation.text
    assert comparison.status_code == 200
    assert "COMPARAÇÃO MULTICRITÉRIO · SEM IA" in comparison.text
    assert "Eficácia" in comparison.text
    assert "Custo" in comparison.text
    assert "Risco" in comparison.text
    assert "Reversibilidade" in comparison.text
    assert "Impacto no utilizador / beneficiário" in comparison.text
    assert "Robustez da evidência" in comparison.text
    assert "sris:alternative-matrix-updated" in comparison.text
    assert "button.dataset.missionTab = TAB" in comparison.text
    assert 'data-open-mission-tab="comparison"' in client.get("/app").text
    assert "comparison:'Comparação'" in client.get("/app.js").text
    assert "window.fetch=" not in comparison.text
    assert business_case.status_code == 200
    assert "BUSINESS CASE VIVO · CÁLCULO DETERMINÍSTICO" in business_case.text
    assert "Custo previsto à conclusão" in business_case.text
    assert "Benefício realizado" in business_case.text
    assert "Encargo anual posterior" in business_case.text
    assert "Confirmar revisão humana" in business_case.text
    assert "sris:business-case-updated" in business_case.text
    assert "window.fetch=" not in business_case.text
    assert mission_state.status_code == 200
    assert "ESTADO GOVERNADO ÚNICO" in mission_state.text
    assert "IA como suporte governado" in mission_state.text
    assert "não transforma inferência em evidência" in mission_state.text
    assert "memory:'memory',intelligence:'intelligence'" in mission_state.text
    assert "sris:memory-updated" in mission_state.text
    assert "MutationObserver" not in decision.text
    assert "sris:evidence-graph-updated" in decision.text
    assert "Reabrir para correção" in decision.text
    assert "model_or_system" not in workspace.text
    assert "credit_eur" not in workspace.text
    assert "sris:memory-updated" in workspace.text
    assert "Inteligência governada de ponta a ponta" in workspace.text
    assert "Estruturar missão completa" in workspace.text
    assert "data-decision=\"human_validated\"" in workspace.text
    assert "sris:mission-state-updated" in workspace.text


def test_pilot_capabilities_report_the_authentication_email_transport(monkeypatch) -> None:
    for name in (
        "SRIS_SMTP_HOST",
        "SRIS_SMTP_USERNAME",
        "SRIS_SMTP_PASSWORD",
        "SRIS_SMTP_FROM_EMAIL",
        "SRIS_PUBLIC_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    unavailable = client.get("/api/pilot/capabilities")
    assert unavailable.status_code == 200
    assert unavailable.json()["transactional_email_ready"] is False
    assert unavailable.json()["invitations_enabled"] is False
    assert unavailable.json()["password_reset_delivery"] == "configuration-required"

    monkeypatch.setenv("SRIS_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SRIS_SMTP_USERNAME", "sris")
    monkeypatch.setenv("SRIS_SMTP_PASSWORD", "test-only-password")
    monkeypatch.setenv("SRIS_SMTP_FROM_EMAIL", "access@example.com")
    monkeypatch.setenv("SRIS_SMTP_SECURITY", "starttls")
    monkeypatch.setenv("SRIS_PUBLIC_BASE_URL", "https://sris.example.com")
    available = client.get("/api/pilot/capabilities")
    assert available.status_code == 200
    assert available.json()["transactional_email_ready"] is True
    assert available.json()["invitations_enabled"] is True
    assert available.json()["password_reset_delivery"] == "email"


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
        "/api/pilot/release-readiness",
        "/api/pilot/release-readiness/checks/{check_key}",
        "/api/pilot/password-reset/request",
        "/api/pilot/password-reset/confirm",
        "/api/pilot/intelligence/ask",
        "/api/pilot/decision-cycles",
        "/api/pilot/decision-cycles/{cycle_id}/reopen",
        "/api/pilot/evidence-graph/missions/{mission_code}",
        "/api/pilot/evidence-graph/missions/{mission_code}/document-evidence",
        "/api/pilot/evidence-graph/missions/{mission_code}/edges/{edge_id}",
        "/api/pilot/evidence-graph/missions/{mission_code}/edges/{edge_id}/reverse",
        "/api/pilot/validation/profiles",
        "/api/pilot/validation/missions/{mission_code}",
        "/api/pilot/validation/missions/{mission_code}/protocol",
        "/api/pilot/validation/missions/{mission_code}/measurements/{phase}",
        "/api/pilot/validation/missions/{mission_code}/review",
        "/api/pilot/alternative-matrices/missions/{mission_code}",
        "/api/pilot/alternative-matrices/missions/{mission_code}/alternatives",
        "/api/pilot/alternative-matrices/missions/{mission_code}/alternatives/{alternative_node_id}/duplicate",
        "/api/pilot/alternative-matrices/missions/{mission_code}/review",
        "/api/pilot/business-cases/missions/{mission_code}",
        "/api/pilot/business-cases/missions/{mission_code}/items",
        "/api/pilot/business-cases/missions/{mission_code}/items/{item_id}",
        "/api/pilot/business-cases/missions/{mission_code}/review",
        "/api/pilot/mission-state/missions/{mission_code}",
        "/api/pilot/mission-state/missions/{mission_code}/ai-context",
        "/api/pilot/mission-state/missions/{mission_code}/policy",
        "/api/pilot/learning/missions/{mission_code}/candidates",
        "/api/pilot/learning/missions/{mission_code}/active-context",
        "/api/pilot/workspace-summary",
        "/api/pilot/audit/missions/{mission_code}",
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
        "target",
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


def test_business_case_successful_save_reenables_rendered_controls() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    source = (repo_root / "frontend" / "pilot-v1" / "business-case-v1.js").read_text(
        encoding="utf-8"
    )
    accept_response = source.split("function acceptResponse", 1)[1].split(
        "function applyGovernedPrefill", 1
    )[0]

    assert accept_response.index("saving = false;") < accept_response.index("render();")


def test_report_numbers_keep_unknown_distinct_from_zero() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    source = (repo_root / "frontend" / "pilot-v1" / "app.js").read_text(
        encoding="utf-8"
    )
    implementation = source.split("function reportNumber", 1)[1].split(
        "function validationReportHtml", 1
    )[0]
    assert "value===null||value===undefined||value===''" in implementation


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

    governance = client.put(
        f"/api/pilot/mission-state/missions/{mission_payload['code']}/policy",
        headers=headers,
        json={
            "expected_revision": 0,
            "alternatives_applicability": "required",
            "economics_applicability": "not_applicable",
            "measurement_applicability": "optional",
            "rationale": (
                "Este percurso testa persistência técnica e não produz um efeito "
                "económico atribuível; a exceção é limitada a esta missão de teste."
            ),
        },
    )
    assert governance.status_code == 200, governance.text
    assert governance.json()["policy"]["source"] == "human_reviewed_override"
    assert governance.json()["policy"]["economics_applicability"] == "not_applicable"
    stale_governance = client.put(
        f"/api/pilot/mission-state/missions/{mission_payload['code']}/policy",
        headers=headers,
        json={
            "expected_revision": 0,
            "alternatives_applicability": "required",
            "economics_applicability": "required",
            "measurement_applicability": "optional",
            "rationale": "Tentativa concorrente sobre uma revisão já substituída.",
        },
    )
    assert stale_governance.status_code == 409, stale_governance.text
    assert stale_governance.json()["detail"]["code"] == "mission_governance_revision_conflict"

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
    synchronized_graph = client.post(f"{graph_base}/sync", headers=headers)
    assert synchronized_graph.status_code == 200, synchronized_graph.text
    assert synchronized_graph.json()["status"] == "synced"
    assert synchronized_graph.json()["interactions_scanned"] == 0
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
    assert evidence.json()["status"] == "proposed"
    assert evidence.json()["provenance"]["source_integrity_verified"] is True
    assert evidence.json()["provenance"]["factual_validation"] == "not_assessed"
    assert evidence.json()["provenance"]["authoritative_source"] is False

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
    assert visual_evidence.json()["status"] == "proposed"
    assert visual_evidence.json()["provenance"]["source_integrity_verified"] is True
    assert visual_evidence.json()["provenance"]["factual_validation"] == "not_assessed"
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

    matrix_alternatives_url = (
        f"/api/pilot/alternative-matrices/missions/{mission_payload['code']}/alternatives"
    )
    prevented_duplicate = client.post(
        matrix_alternatives_url,
        headers=headers,
        json={
            "title": second_alternative.json()["label"],
            "body": second_alternative.json()["body"],
        },
    )
    assert prevented_duplicate.status_code == 200, prevented_duplicate.text
    assert prevented_duplicate.json()["alternative_change"] == {
        "created": False,
        "alternative_id": second_alternative.json()["id"],
        "reason": "exact_duplicate",
    }
    assert len(prevented_duplicate.json()["alternatives"]) == 2

    accidental_duplicate = client.post(
        f"{graph_base}/nodes",
        headers=headers,
        json={
            "node_type": "alternative",
            "label": second_alternative.json()["label"],
            "body": second_alternative.json()["body"],
            "status": "proposed",
        },
    )
    assert accidental_duplicate.status_code == 201, accidental_duplicate.text
    duplicate_matrix = client.get(
        f"/api/pilot/alternative-matrices/missions/{mission_payload['code']}",
        headers=headers,
    )
    assert duplicate_matrix.status_code == 200, duplicate_matrix.text
    marked_duplicates = [
        item for item in duplicate_matrix.json()["alternatives"] if item["duplicate_of_id"]
    ]
    assert len(marked_duplicates) == 1
    duplicate_to_retire = marked_duplicates[0]
    retired_duplicate = client.delete(
        f"{matrix_alternatives_url}/{duplicate_to_retire['id']}/duplicate",
        headers=headers,
    )
    assert retired_duplicate.status_code == 200, retired_duplicate.text
    assert retired_duplicate.json()["alternative_change"]["retired"] is True
    second_active_id = retired_duplicate.json()["alternative_change"]["retained_alternative_id"]
    assert len(retired_duplicate.json()["alternatives"]) == 2
    assert all(not item["duplicate_of_id"] for item in retired_duplicate.json()["alternatives"])

    unique_retirement = client.delete(
        f"{matrix_alternatives_url}/{alternative.json()['id']}/duplicate",
        headers=headers,
    )
    assert unique_retirement.status_code == 409, unique_retirement.text
    assert unique_retirement.json()["detail"] == (
        "Esta alternativa é única e não pode ser retirada como duplicado."
    )
    graph_after_retirement = client.get(graph_base, headers=headers)
    assert graph_after_retirement.status_code == 200, graph_after_retirement.text
    assert graph_after_retirement.json()["counts"]["alternative"] == 2
    retired_node = next(
        item
        for item in graph_after_retirement.json()["nodes"]
        if item["id"] == duplicate_to_retire["id"]
    )
    assert retired_node["status"] == "superseded"

    duplicate_audit = client.get("/api/pilot/admin/audit?limit=100", headers=headers)
    assert duplicate_audit.status_code == 200, duplicate_audit.text
    assert any(
        event["action"] == "pilot.alternative.duplicate_retired"
        and event["resource_id"] == duplicate_to_retire["id"]
        for event in duplicate_audit.json()["events"]
    )
    observation = client.post(
        f"{graph_base}/nodes",
        headers=headers,
        json={
            "node_type": "observation",
            "label": "Observação documental",
            "body": "A fonte preservada descreve continuidade entre sessões.",
            "status": "proposed",
        },
    )
    assert observation.status_code == 201, observation.text
    evidence_to_observation = client.post(
        f"{graph_base}/edges",
        headers=headers,
        json={
            "from_node_id": evidence.json()["id"],
            "to_node_id": observation.json()["id"],
            "edge_type": "informs",
            "provenance": {"human_curated": True},
        },
    )
    assert evidence_to_observation.status_code == 201, evidence_to_observation.text
    observation_to_hypothesis = client.post(
        f"{graph_base}/edges",
        headers=headers,
        json={
            "from_node_id": observation.json()["id"],
            "to_node_id": hypothesis.json()["id"],
            "edge_type": "informs",
            "provenance": {"human_curated": True},
        },
    )
    assert observation_to_hypothesis.status_code == 201, observation_to_hypothesis.text

    indirect_readiness = client.get(
        f"/api/pilot/missions/{mission_payload['code']}/completion-readiness",
        headers=headers,
    )
    assert indirect_readiness.status_code == 200, indirect_readiness.text
    hypothesis_check = next(
        check
        for check in indirect_readiness.json()["checks"]
        if check["key"] == "hypothesis_explicit"
    )
    assert hypothesis_check == {
        "key": "hypothesis_explicit",
        "label": "Hipótese com linhagem explícita até à evidência",
        "passed": True,
        "count": 1,
    }

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
    assert linked.json()["created"] is True

    duplicate_link = client.post(
        f"{graph_base}/edges",
        headers=headers,
        json={
            "from_node_id": evidence.json()["id"],
            "to_node_id": hypothesis.json()["id"],
            "edge_type": "supports",
            "provenance": {"human_curated": True},
        },
    )
    assert duplicate_link.status_code == 201, duplicate_link.text
    assert duplicate_link.json()["id"] == linked.json()["id"]
    assert duplicate_link.json()["created"] is False

    self_link = client.post(
        f"{graph_base}/edges",
        headers=headers,
        json={
            "from_node_id": evidence.json()["id"],
            "to_node_id": evidence.json()["id"],
            "edge_type": "informs",
            "provenance": {"human_curated": True},
        },
    )
    assert self_link.status_code == 422, self_link.text
    assert self_link.json()["detail"] == "Uma relação tem de ligar dois objetos diferentes."

    persisted_graph = client.get(graph_base, headers=headers)
    assert persisted_graph.status_code == 200, persisted_graph.text
    assert any(edge["id"] == linked.json()["id"] for edge in persisted_graph.json()["edges"])

    reversed_link = client.post(
        f"{graph_base}/edges/{linked.json()['id']}/reverse",
        headers=headers,
    )
    assert reversed_link.status_code == 200, reversed_link.text
    assert reversed_link.json()["reversed"] is True
    assert reversed_link.json()["from_node_id"] == hypothesis.json()["id"]
    assert reversed_link.json()["to_node_id"] == evidence.json()["id"]

    graph_after_reverse = client.get(graph_base, headers=headers)
    assert graph_after_reverse.status_code == 200, graph_after_reverse.text
    persisted_reversed = next(
        edge for edge in graph_after_reverse.json()["edges"] if edge["id"] == linked.json()["id"]
    )
    assert persisted_reversed["from_node_id"] == hypothesis.json()["id"]
    assert persisted_reversed["to_node_id"] == evidence.json()["id"]

    deleted_link = client.delete(
        f"{graph_base}/edges/{linked.json()['id']}",
        headers=headers,
    )
    assert deleted_link.status_code == 200, deleted_link.text
    assert deleted_link.json()["deleted"] is True
    assert deleted_link.json()["edge"]["id"] == linked.json()["id"]

    graph_after_delete = client.get(graph_base, headers=headers)
    assert graph_after_delete.status_code == 200, graph_after_delete.text
    assert all(edge["id"] != linked.json()["id"] for edge in graph_after_delete.json()["edges"])

    missing_link = client.delete(
        f"{graph_base}/edges/{linked.json()['id']}",
        headers=headers,
    )
    assert missing_link.status_code == 404, missing_link.text
    assert missing_link.json()["detail"] == "A relação indicada não existe nesta missão."

    relation_audit = client.get("/api/pilot/admin/audit?limit=100", headers=headers)
    assert relation_audit.status_code == 200, relation_audit.text
    relation_actions = {
        event["action"]
        for event in relation_audit.json()["events"]
        if event["resource_id"] == linked.json()["id"]
    }
    assert "pilot.evidence_graph.edge_created" in relation_actions
    assert "pilot.evidence_graph.edge_reversed" in relation_actions
    assert "pilot.evidence_graph.edge_deleted" in relation_actions
    assert any(
        event["action"] == "pilot.evidence_graph.node_created"
        and event["resource_id"] == hypothesis.json()["id"]
        for event in relation_audit.json()["events"]
    )
    assert any(
        event["action"] == "pilot.evidence_graph.document_evidence_promoted"
        and event["resource_id"] == evidence.json()["id"]
        for event in relation_audit.json()["events"]
    )
    assert any(
        event["action"] == "pilot.evidence_graph.synchronized"
        and event["resource_id"] == mission_payload["code"]
        for event in relation_audit.json()["events"]
    )

    restored_link = client.post(
        f"{graph_base}/edges",
        headers=headers,
        json={
            "from_node_id": evidence.json()["id"],
            "to_node_id": hypothesis.json()["id"],
            "edge_type": "supports",
            "provenance": {"human_curated": True, "test_restored": True},
        },
    )
    assert restored_link.status_code == 201, restored_link.text
    assert restored_link.json()["created"] is True

    matrix_url = f"/api/pilot/alternative-matrices/missions/{mission_payload['code']}"
    empty_matrix = client.get(matrix_url, headers=headers)
    assert empty_matrix.status_code == 200, empty_matrix.text
    assert empty_matrix.json()["matrix"] is None
    assert [item["key"] for item in empty_matrix.json()["criteria"]] == [
        "efficacy",
        "cost",
        "risk",
        "reversibility",
        "guest_experience",
        "evidence_robustness",
    ]

    criterion_keys = [item["key"] for item in empty_matrix.json()["criteria"]]

    def matrix_evaluation(alternative_id: str, scores: dict[str, int]) -> dict:
        return {
            "alternative_node_id": alternative_id,
            "scores": [
                {
                    "criterion": criterion,
                    "score": scores[criterion],
                    "rationale": f"Avaliação humana documentada para {criterion}.",
                    "evidence_node_id": evidence.json()["id"],
                }
                for criterion in criterion_keys
            ],
        }

    valid_matrix = {
        "weights": {
            "efficacy": 25,
            "cost": 15,
            "risk": 15,
            "reversibility": 10,
            "guest_experience": 20,
            "evidence_robustness": 15,
        },
        "evaluations": [
            matrix_evaluation(
                alternative.json()["id"],
                {
                    "efficacy": 2,
                    "cost": 4,
                    "risk": 2,
                    "reversibility": 4,
                    "guest_experience": 2,
                    "evidence_robustness": 2,
                },
            ),
            matrix_evaluation(
                second_active_id,
                {
                    "efficacy": 5,
                    "cost": 3,
                    "risk": 4,
                    "reversibility": 4,
                    "guest_experience": 5,
                    "evidence_robustness": 4,
                },
            ),
        ],
    }
    invalid_matrix = json.loads(json.dumps(valid_matrix))
    invalid_matrix["weights"]["efficacy"] = 24
    invalid_save = client.put(matrix_url, headers=headers, json=invalid_matrix)
    assert invalid_save.status_code == 422, invalid_save.text

    boolean_weight_matrix = json.loads(json.dumps(valid_matrix))
    boolean_weight_matrix["weights"]["efficacy"] = True
    boolean_weight_save = client.put(matrix_url, headers=headers, json=boolean_weight_matrix)
    assert boolean_weight_save.status_code == 422, boolean_weight_save.text

    boolean_score_matrix = json.loads(json.dumps(valid_matrix))
    boolean_score_matrix["evaluations"][0]["scores"][0]["score"] = True
    boolean_score_save = client.put(matrix_url, headers=headers, json=boolean_score_matrix)
    assert boolean_score_save.status_code == 422, boolean_score_save.text

    first_matrix = client.put(matrix_url, headers=headers, json=valid_matrix)
    assert first_matrix.status_code == 200, first_matrix.text
    first_matrix_payload = first_matrix.json()
    assert first_matrix_payload["matrix"]["revision"] == 1
    assert first_matrix_payload["matrix"]["status"] == "draft"
    assert len(first_matrix_payload["matrix"]["content_hash"]) == 64
    assert first_matrix_payload["matrix"]["integrity_verified"] is True
    assert first_matrix_payload["readiness"]["passed"] is False
    assert first_matrix_payload["readiness"]["ready_for_review"] is True
    assert first_matrix_payload["readiness"]["count"] == 2
    assert first_matrix_payload["ranking"][0]["alternative_node_id"] == second_active_id
    assert first_matrix_payload["ranking"][0]["weighted_score"] == 86.0
    assert first_matrix_payload["calculation"]["formula"] == "sum(score × weight) / 5"
    assert first_matrix_payload["calculation"]["result_range"] == [20, 100]

    first_review = client.post(f"{matrix_url}/review", headers=headers)
    assert first_review.status_code == 200, first_review.text
    assert first_review.json()["matrix"]["status"] == "reviewed"
    assert first_review.json()["readiness"]["passed"] is True
    assert first_review.json()["matrix"]["reviewed_by_user_id"] == profile.json()["user"]["id"]

    revised_matrix = json.loads(json.dumps(valid_matrix))
    second_assessment = next(
        item
        for item in revised_matrix["evaluations"]
        if item["alternative_node_id"] == second_active_id
    )
    evidence_robustness = next(
        item for item in second_assessment["scores"] if item["criterion"] == "evidence_robustness"
    )
    evidence_robustness["score"] = 5
    evidence_robustness["rationale"] = "A fonte, a posição e o hash estão preservados e foram revistos por uma pessoa."
    second_matrix = client.put(matrix_url, headers=headers, json=revised_matrix)
    assert second_matrix.status_code == 200, second_matrix.text
    second_matrix_payload = second_matrix.json()
    assert second_matrix_payload["matrix"]["revision"] == 2
    assert second_matrix_payload["matrix"]["status"] == "draft"
    assert second_matrix_payload["matrix"]["integrity_verified"] is True
    assert second_matrix_payload["matrix"]["content_hash"] != first_matrix_payload["matrix"]["content_hash"]
    assert [item["revision"] for item in second_matrix_payload["history"]] == [2, 1]
    assert second_matrix_payload["history"][1]["status"] == "reviewed"
    assert all(item["integrity_verified"] is True for item in second_matrix_payload["history"])

    accepted_foundation = client.patch(
        f"{graph_base}/nodes/{evidence.json()['id']}",
        headers=headers,
        json={"status": "accepted"},
    )
    assert accepted_foundation.status_code == 200, accepted_foundation.text
    assert accepted_foundation.json()["status"] == "accepted"

    second_review = client.post(f"{matrix_url}/review", headers=headers)
    assert second_review.status_code == 200, second_review.text
    assert second_review.json()["matrix"]["revision"] == 2
    assert second_review.json()["matrix"]["status"] == "reviewed"
    duplicate_review = client.post(f"{matrix_url}/review", headers=headers)
    assert duplicate_review.status_code == 409, duplicate_review.text
    assert duplicate_review.json()["detail"] == "A revisão mais recente já foi validada por uma pessoa."

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
            "decision": "Adotar o percurso persistente do Pilot V1 com dados reai.",
            "action": "Reabrir a missão depois de uma nova autenticação.",
            "owner": "Pilot Journey",
            "due_date": "2026-09-01",
            "expected_outcome": "A missão reaparece com o mesmo contexto.",
            "evidence_node_id": evidence.json()["id"],
        },
    )
    assert decision.status_code == 201, decision.text
    assert decision.json()["decision_snapshot"]["mission_content_hash"] == mission_payload["content_hash"]
    assert len(decision.json()["decision_snapshot"]["mission_governance_hash"]) == 64
    # The exact value comes from the source document's original filename. In
    # staging this resolves, for example, to
    # "MIS-002 — Resultado de consumo de água — dados demonstrativos.pdf".
    expected_foundation_title = "evidence.txt"
    assert decision.json()["evidence_label"] == expected_foundation_title
    assert decision.json()["evidence_document_title"] == expected_foundation_title
    assert decision.json()["evidence_node_label"] == "Fonte operacional preservada"
    listed_decisions = client.get(
        f"/api/pilot/decision-cycles/missions/{mission_payload['code']}",
        headers=headers,
    )
    assert listed_decisions.status_code == 200, listed_decisions.text
    assert listed_decisions.json()[0]["evidence_label"] == expected_foundation_title
    skipped_governance = client.patch(
        f"/api/pilot/decision-cycles/{decision.json()['id']}",
        headers=headers,
        json={"status": "completed"},
    )
    assert skipped_governance.status_code == 409, skipped_governance.text
    assert "proposta → compromisso → execução → conclusão" in skipped_governance.json()["detail"]
    committed_cycle = client.patch(
        f"/api/pilot/decision-cycles/{decision.json()['id']}",
        headers=headers,
        json={
            "status": "committed",
            "action": "Reabrir a missão depois de uma nova autenticação.",
            "expected_outcome": "A missão reaparece com o mesmo contexto.",
        },
    )
    assert committed_cycle.status_code == 200, committed_cycle.text
    assert committed_cycle.json()["status"] == "committed"
    in_progress_cycle = client.patch(
        f"/api/pilot/decision-cycles/{decision.json()['id']}",
        headers=headers,
        json={
            "status": "in_progress",
            "action": "Reabrir a missão depois de uma nova autenticação.",
            "owner": "Pilot Journey",
            "due_date": "2026-09-01",
            "action_started_at": "2026-08-20",
            "expected_outcome": "A missão reaparece com o mesmo contexto.",
        },
    )
    assert in_progress_cycle.status_code == 200, in_progress_cycle.text
    assert in_progress_cycle.json()["status"] == "in_progress"

    result_evidence = client.post(
        f"{graph_base}/nodes",
        headers=headers,
        json={
            "node_type": "evidence",
            "label": "Verificação posterior da persistência",
            "body": "Observação humana posterior à ação: missão, documento e grafo reapareceram.",
            "status": "proposed",
            "provenance": {"human_authored": True, "observed_after_action": True},
        },
    )
    assert result_evidence.status_code == 201, result_evidence.text
    blocked_unreviewed_outcome = client.patch(
        f"/api/pilot/decision-cycles/{decision.json()['id']}",
        headers=headers,
        json={
            "status": "completed",
            "actual_outcome": "A missão, o documento e o grafo reapareceram.",
            "actual_outcome_at": "2026-08-25",
            "outcome_evidence_node_id": result_evidence.json()["id"],
            "learning": "A continuidade deve ser validada pelo estado persistente e não pelo ecrã.",
        },
    )
    assert blocked_unreviewed_outcome.status_code == 409, blocked_unreviewed_outcome.text
    assert "revista humanamente" in blocked_unreviewed_outcome.json()["detail"]
    accepted_result_evidence = client.patch(
        f"{graph_base}/nodes/{result_evidence.json()['id']}",
        headers=headers,
        json={"status": "accepted"},
    )
    assert accepted_result_evidence.status_code == 200, accepted_result_evidence.text
    assert accepted_result_evidence.json()["status"] == "accepted"
    completed_cycle = client.patch(
        f"/api/pilot/decision-cycles/{decision.json()['id']}",
        headers=headers,
        json={
            "status": "completed",
            "action": "Reabrir a missão depois de uma nova autenticação.",
            "owner": "Pilot Journey",
            "due_date": "2026-09-01",
            "action_started_at": "2026-08-20",
            "expected_outcome": "A missão reaparece com o mesmo contexto.",
            "actual_outcome": "A missão, o documento e o grafo reapareceram.",
            "actual_outcome_at": "2026-08-25",
            "outcome_evidence_node_id": result_evidence.json()["id"],
            "learning": "A continuidade deve ser validada pelo estado persistente e não pelo ecrã.",
        },
    )
    assert completed_cycle.status_code == 200, completed_cycle.text
    assert completed_cycle.json()["decision"].endswith("dados reai.")
    materialized = client.post(
        f"/api/pilot/decision-cycles/{decision.json()['id']}/materialize-learning",
        headers=headers,
    )
    assert materialized.status_code == 201, materialized.text
    assert materialized.json()["already_materialized"] is False
    assert materialized.json()["decision_node_id"] != evidence.json()["id"]
    assert materialized.json()["action_node_id"]
    learning_node_id = materialized.json()["learning_node_id"]
    lineage_graph = client.get(graph_base, headers=headers)
    assert lineage_graph.status_code == 200, lineage_graph.text
    materialized_learning = next(
        node for node in lineage_graph.json()["nodes"] if node["id"] == learning_node_id
    )
    materialized_outcome = next(
        node
        for node in lineage_graph.json()["nodes"]
        if node["id"] == materialized.json()["outcome_node_id"]
    )
    assert materialized_learning["label"].endswith("dados reais.")
    assert materialized_outcome["status"] == "accepted"
    assert materialized_outcome["provenance"]["outcome_evidence_status"] == "accepted"
    repeated_materialization = client.post(
        f"/api/pilot/decision-cycles/{decision.json()['id']}/materialize-learning",
        headers=headers,
    )
    assert repeated_materialization.status_code == 201, repeated_materialization.text
    assert repeated_materialization.json()["already_materialized"] is True
    assert repeated_materialization.json()["learning_node_id"] == learning_node_id
    assert any(
        edge["from_node_id"] == evidence.json()["id"]
        and edge["to_node_id"] == materialized.json()["decision_node_id"]
        and edge["edge_type"] == "informs"
        for edge in lineage_graph.json()["edges"]
    )
    assert any(
        edge["from_node_id"] == result_evidence.json()["id"]
        and edge["to_node_id"] == materialized.json()["outcome_node_id"]
        and edge["edge_type"] == "validates"
        for edge in lineage_graph.json()["edges"]
    )
    refused_nullification = client.patch(
        f"{graph_base}/nodes/{learning_node_id}",
        headers=headers,
        json={"body": None},
    )
    assert refused_nullification.status_code == 422, refused_nullification.text
    accepted = client.patch(
        f"{graph_base}/nodes/{learning_node_id}",
        headers=headers,
        json={"status": "accepted"},
    )
    assert accepted.status_code == 200, accepted.text
    node_update_audit = client.get("/api/pilot/admin/audit?limit=100", headers=headers)
    assert node_update_audit.status_code == 200, node_update_audit.text
    assert any(
        event["action"] == "pilot.evidence_graph.node_updated"
        and event["resource_id"] == learning_node_id
        and event["payload"]["changed_fields"] == ["status"]
        for event in node_update_audit.json()["events"]
    )
    published = client.post(
        f"/api/pilot/learning/missions/{mission_payload['code']}/publish/{learning_node_id}",
        headers=headers,
    )
    assert published.status_code == 201, published.text
    assert published.json()["title"].endswith("dados reais.")

    memory_base = (
        f"/api/organizations/{organization_id}/mission-intelligence/memory"
    )
    memory_sync = client.post(f"{memory_base}/sync", headers=headers)
    assert memory_sync.status_code == 200, memory_sync.text
    assert memory_sync.json()["created"] >= 1
    assert memory_sync.json()["assets_created"] >= 1
    mission_memory = client.get(
        f"{memory_base}/items?limit=500",
        headers=headers,
    )
    assert mission_memory.status_code == 200, mission_memory.text
    memory_items = [
        item for item in mission_memory.json()
        if item["mission_id"] == mission_payload["id"]
    ]
    assert any(item["item_type"] == "evidence" for item in memory_items)
    assert any(item["item_type"] == "hypothesis" for item in memory_items)
    assert any(item["item_type"] == "decision" for item in memory_items)
    assert any(item["item_type"] == "execution" for item in memory_items)
    assert any(item["item_type"] == "outcome" for item in memory_items)
    published_memory = next(
        item for item in memory_items if item["item_type"] == "learning"
    )
    assert published_memory["metadata"]["published_learning"] is True
    assert published_memory["metadata"]["lineage_sha256"] == published.json()["lineage_sha256"]
    assert published_memory["canonical_record_id"] == f"PILOT-{learning_node_id}"
    assert published_memory["title"].endswith("dados reais.")
    memory_status = client.get(f"{memory_base}/status", headers=headers)
    assert memory_status.status_code == 200, memory_status.text
    assert memory_status.json()["assets"] >= 1
    state_before_noop_sync = client.get(
        f"/api/pilot/mission-state/missions/{mission_payload['code']}",
        headers=headers,
    )
    assert state_before_noop_sync.status_code == 200, state_before_noop_sync.text
    repeated_memory_sync = client.post(f"{memory_base}/sync", headers=headers)
    assert repeated_memory_sync.status_code == 200, repeated_memory_sync.text
    assert repeated_memory_sync.json()["created"] == 0
    assert repeated_memory_sync.json()["assets_created"] == 0

    governed_state = client.get(
        f"/api/pilot/mission-state/missions/{mission_payload['code']}",
        headers=headers,
    )
    assert governed_state.status_code == 200, governed_state.text
    governed_payload = governed_state.json()
    assert governed_payload["schema"] == "sris.governed-mission-state.v1"
    assert governed_payload["state_hash"] == state_before_noop_sync.json()["state_hash"]
    assert governed_payload["health"]["status"] == "governed"
    assert governed_payload["health"]["critical_conflicts"] == 0
    assert governed_payload["conflicts"] == []
    assert {item["key"] for item in governed_payload["modules"]} >= {
        "mission", "documents", "evidence", "comparison", "economics",
        "validation", "decision", "action", "outcome", "learning", "memory",
    }
    governed_ai = client.get(
        f"/api/pilot/mission-state/missions/{mission_payload['code']}/ai-context",
        headers=headers,
    )
    assert governed_ai.status_code == 200, governed_ai.text
    ai_payload = governed_ai.json()
    assert ai_payload["schema"] == "sris.governed-ai-context.v1"
    assert ai_payload["state_hash"] == governed_payload["state_hash"]
    assert ai_payload["boundary"]["role"] == "end_to_end_draft_orchestration"
    assert ai_payload["boundary"]["mission_path"]["ai_may_prepare_all_stages"] is True
    assert len(ai_payload["boundary"]["mission_path"]["stages"]) == 10
    assert ai_payload["boundary"]["human_review_required"] is True
    assert ai_payload["boundary"]["canonical_mutation"] == "prohibited_without_explicit_human_promotion"
    assert any(item.startswith("DOC:") for item in ai_payload["citation_ids"])
    assert any(item.startswith("GRAPH:") for item in ai_payload["citation_ids"])
    assert any(item.startswith("MATRIX:") for item in ai_payload["citation_ids"])
    assert any(item.startswith("CYCLE:") for item in ai_payload["citation_ids"])
    assert any(item.startswith("LEARNING:") for item in ai_payload["citation_ids"])
    assert any(item.startswith("MEMORY:") for item in ai_payload["citation_ids"])
    governed_objects = {
        item["citation_id"]: item for item in ai_payload["objects"]
    }
    foundation_object = governed_objects[f"GRAPH:{evidence.json()['id']}"]
    assert foundation_object["attachment_id"] == attachment["id"]
    assert foundation_object["source_sha256"] == attachment["sha256"]
    assert foundation_object["source_integrity_verified"] is True
    assert foundation_object["factual_validation"] == "not_assessed"
    assert governed_objects[
        f"GRAPH:{materialized.json()['action_node_id']}"
    ]["module"] == "action"
    assert governed_objects[
        f"GRAPH:{materialized.json()['outcome_node_id']}"
    ]["module"] == "outcome"
    assert governed_objects[f"MEMORY:{published_memory['id']}"]["module"] == "memory"

    readiness = client.get(
        f"/api/pilot/missions/{mission_payload['code']}/completion-readiness",
        headers=headers,
    )
    assert readiness.status_code == 200, readiness.text
    assert readiness.json()["ready"] is True
    assert all(check["passed"] for check in readiness.json()["checks"])

    unresolved_cycle = client.post(
        "/api/pilot/decision-cycles",
        headers=headers,
        json={
            "mission_code": mission_payload["code"],
            "decision": "Proposta adicional ainda sem compromisso humano.",
            "evidence_node_id": evidence.json()["id"],
        },
    )
    assert unresolved_cycle.status_code == 201, unresolved_cycle.text
    blocked_by_open_cycle = client.patch(
        f"/api/organizations/{organization_id}/mission-intelligence/missions/{mission_payload['id']}",
        headers=headers,
        json={
            "expected_revision": mission_payload["revision"],
            "lifecycle_state": "completed",
            "change_note": "Tentativa com uma proposta de decisão ainda aberta.",
        },
    )
    assert blocked_by_open_cycle.status_code == 409, blocked_by_open_cycle.text
    blocking_keys = blocked_by_open_cycle.json()["detail"]["readiness"]["blocking_keys"]
    assert "decision_cycles_resolved" in blocking_keys
    # Restore the exact precondition for the remainder of this long journey.
    # The focused assertion above verifies the runtime guard; direct cleanup
    # avoids turning the temporary test proposal into governed mission history.
    with SessionLocal() as db:
        db.execute(
            text("DELETE FROM pilot_decision_cycles WHERE id=:id"),
            {"id": unresolved_cycle.json()["id"]},
        )
        db.execute(
            text("DELETE FROM audit_events WHERE resource_id=:id"),
            {"id": unresolved_cycle.json()["id"]},
        )
        db.commit()

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
    completed_state = client.get(
        f"/api/pilot/mission-state/missions/{mission_payload['code']}",
        headers=headers,
    )
    assert completed_state.status_code == 200, completed_state.text
    assert completed_state.json()["health"]["status"] == "governed"
    assert completed_state.json()["health"]["stale_modules"] == []

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
    assert packet["canonical_status"] == "valid"
    assert packet["lineage"]["counts"]["decision"] == 1
    assert packet["lineage"]["raw_node_counts"]["decision"] >= packet["lineage"]["counts"]["decision"]
    reviewed = client.post(
        f"/api/pilot/learning/missions/{sub_mission.json()['code']}/candidates/{packet['id']}/review",
        headers=headers,
        json={
            "applicability": "reuse",
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

    unrelated_target = client.post(
        f"/api/organizations/{organization_id}/mission-intelligence/missions",
        headers=headers,
        json={
            "title": "Missão independente para testar isolamento contextual",
            "objective": "Confirmar que uma revisão humana não transita entre missões.",
            "central_question": "A aplicabilidade continua por rever nesta missão distinta?",
            "context": "Contexto independente sem revisão de aplicabilidade registada.",
            "mission_kind": "mission",
            "domain": "pilot_validation",
            "priority": "standard",
        },
    )
    assert unrelated_target.status_code == 201, unrelated_target.text
    unrelated_candidates = client.get(
        f"/api/pilot/learning/missions/{unrelated_target.json()['code']}/candidates",
        headers=headers,
    )
    assert unrelated_candidates.status_code == 200, unrelated_candidates.text
    unrelated_packet = next(
        row
        for row in unrelated_candidates.json()["candidates"]
        if row["id"] == packet["id"]
    )
    assert unrelated_packet["review"] is None
    assert unrelated_candidates.json()["summary"]["reviewed_count"] == 0
    unrelated_context = client.get(
        f"/api/pilot/learning/missions/{unrelated_target.json()['code']}/active-context",
        headers=headers,
    )
    assert unrelated_context.status_code == 200, unrelated_context.text
    assert unrelated_context.json()["inheritance"]["valid"] == []
    assert unrelated_context.json()["inheritance"]["requires_revalidation"] == []

    not_applicable = client.post(
        f"/api/pilot/learning/missions/{sub_mission.json()['code']}/candidates/{packet['id']}/review",
        headers=headers,
        json={
            "applicability": "not_applicable",
            "rationale": "A aprendizagem permanece válida, mas não se aplica a esta missão.",
            "context_change": "",
        },
    )
    assert not_applicable.status_code == 200, not_applicable.text
    assert not_applicable.json()["canonical_status"] == "valid"
    assert not_applicable.json()["applicability"] == "not_applicable"
    excluded_context = client.get(
        f"/api/pilot/learning/missions/{sub_mission.json()['code']}/active-context",
        headers=headers,
    )
    assert excluded_context.status_code == 200, excluded_context.text
    assert excluded_context.json()["inheritance"]["valid"] == []
    reviewed_candidates = client.get(
        f"/api/pilot/learning/missions/{sub_mission.json()['code']}/candidates",
        headers=headers,
    )
    assert reviewed_candidates.json()["summary"]["not_applicable_count"] == 1

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
    mission_audit = client.get(
        f"/api/pilot/audit/missions/{mission_payload['code']}?limit=300",
        headers=headers,
    )
    assert mission_audit.status_code == 200, mission_audit.text
    audited_actions = {row["action"] for row in mission_audit.json()["events"]}
    assert "mission_intelligence.mission_revised" in audited_actions
    assert "pilot.decision_cycle.lineage_materialized" in audited_actions
    assert "pilot.learning.published" in audited_actions
    assert "pilot.learning.applicability_reviewed" in audited_actions
    assert "pilot.mission_state.policy_reviewed" in audited_actions

    blocked_terminal_edit = client.patch(
        f"/api/pilot/decision-cycles/{decision.json()['id']}",
        headers=headers,
        json={"learning": "Uma decisão terminal não pode ser reescrita silenciosamente."},
    )
    assert blocked_terminal_edit.status_code == 409, blocked_terminal_edit.text
    assert "Reabra explicitamente" in blocked_terminal_edit.json()["detail"]

    blocked_graph_edit = client.patch(
        f"{graph_base}/nodes/{evidence.json()['id']}",
        headers=headers,
        json={"body": "Uma versão encerrada não pode ser alterada sem reativação."},
    )
    assert blocked_graph_edit.status_code == 409, blocked_graph_edit.text
    assert blocked_graph_edit.json()["detail"]["code"] == "mission_reactivation_required"

    blocked_document_upload = client.post(
        f"/api/organizations/{organization_id}/mission-intelligence/missions/{mission_payload['code']}/attachments",
        headers=headers,
        files={"file": ("late.txt", b"late terminal mutation", "text/plain")},
    )
    assert blocked_document_upload.status_code == 409, blocked_document_upload.text
    assert blocked_document_upload.json()["detail"]["code"] == "mission_reactivation_required"

    terminal_document_download = client.get(
        f"/api/organizations/{organization_id}/mission-intelligence/missions/{mission_payload['code']}/attachments/{attachment['id']}/download",
        headers=headers,
    )
    assert terminal_document_download.status_code == 200, terminal_document_download.text

    blocked_document_delete = client.delete(
        f"/api/organizations/{organization_id}/mission-intelligence/missions/{mission_payload['code']}/attachments/{attachment['id']}",
        headers=headers,
    )
    assert blocked_document_delete.status_code == 409, blocked_document_delete.text
    assert blocked_document_delete.json()["detail"]["code"] == "mission_reactivation_required"

    blocked_reopen = client.post(
        f"/api/pilot/decision-cycles/{decision.json()['id']}/reopen",
        headers=headers,
        json={
            "rationale": "A missão tem de ser reativada antes de corrigir a cadeia terminal."
        },
    )
    assert blocked_reopen.status_code == 409, blocked_reopen.text
    assert blocked_reopen.json()["detail"]["code"] == "mission_reactivation_required"

    blocked_mission_rewrite = client.patch(
        f"/api/organizations/{organization_id}/mission-intelligence/missions/{mission_payload['id']}",
        headers=headers,
        json={
            "expected_revision": completed_mission.json()["revision"],
            "title": "Título que não pode reescrever uma missão concluída",
            "change_note": "Tentativa deliberada de reescrita terminal.",
        },
    )
    assert blocked_mission_rewrite.status_code == 409, blocked_mission_rewrite.text
    assert blocked_mission_rewrite.json()["detail"]["code"] == "mission_reactivation_required"

    reactivated_mission = client.patch(
        f"/api/organizations/{organization_id}/mission-intelligence/missions/{mission_payload['id']}",
        headers=headers,
        json={
            "expected_revision": completed_mission.json()["revision"],
            "lifecycle_state": "active",
            "change_note": "Missão reativada explicitamente para corrigir a cadeia preservada.",
        },
    )
    assert reactivated_mission.status_code == 200, reactivated_mission.text
    assert reactivated_mission.json()["lifecycle_state"] == "active"

    suspended_candidates = client.get(
        f"/api/pilot/learning/missions/{unrelated_target.json()['code']}/candidates",
        headers=headers,
    )
    assert suspended_candidates.status_code == 200, suspended_candidates.text
    suspended_packet = next(
        row for row in suspended_candidates.json()["candidates"] if row["id"] == packet["id"]
    )
    assert suspended_packet["canonical_status"] == "suspended"
    assert suspended_packet["review"]["applicability"] == "requires_revalidation"
    assert suspended_candidates.json()["summary"]["canonically_valid_count"] == 0
    assert suspended_candidates.json()["summary"]["reusable_count"] == 0
    assert suspended_candidates.json()["summary"]["requires_revalidation_count"] >= 1

    suspended_reuse = client.post(
        f"/api/pilot/learning/missions/{unrelated_target.json()['code']}/candidates/{packet['id']}/review",
        headers=headers,
        json={
            "applicability": "reuse",
            "rationale": "Tentativa controlada de reutilizar uma origem reaberta.",
            "context_change": "",
        },
    )
    assert suspended_reuse.status_code == 409, suspended_reuse.text

    marked_for_revalidation = client.post(
        f"/api/pilot/learning/missions/{unrelated_target.json()['code']}/candidates/{packet['id']}/review",
        headers=headers,
        json={
            "applicability": "requires_revalidation",
            "rationale": "A origem foi reaberta e deixou de sustentar reutilização direta.",
            "context_change": "Reconciliar a cadeia e concluir novamente a missão de origem.",
        },
    )
    assert marked_for_revalidation.status_code == 200, marked_for_revalidation.text
    assert marked_for_revalidation.json()["canonical_status"] == "suspended"
    suspended_context = client.get(
        f"/api/pilot/learning/missions/{unrelated_target.json()['code']}/active-context",
        headers=headers,
    )
    assert suspended_context.status_code == 200, suspended_context.text
    assert suspended_context.json()["inheritance"]["valid"] == []
    assert any(
        row["packet_id"] == packet["id"]
        for row in suspended_context.json()["inheritance"]["requires_revalidation"]
    )

    suspended_summary = client.get("/api/pilot/workspace-summary", headers=headers)
    suspended_source = next(
        row for row in suspended_summary.json()["missions"] if row["id"] == mission_payload["id"]
    )
    assert suspended_source["published_learning"] == 0
    suspended_memory_sync = client.post(f"{memory_base}/sync", headers=headers)
    assert suspended_memory_sync.status_code == 200, suspended_memory_sync.text
    suspended_memory = client.get(f"{memory_base}/items?limit=500", headers=headers)
    suspended_learning = next(
        item
        for item in suspended_memory.json()
        if item["canonical_record_id"] == f"PILOT-{learning_node_id}"
    )
    assert suspended_learning["state"] == "suspended"
    assert suspended_learning["metadata"]["source_governance_state"] == "source_mission_open"

    reopened = client.post(
        f"/api/pilot/decision-cycles/{decision.json()['id']}/reopen",
        headers=headers,
        json={
            "rationale": "O contrato atual exige reabrir e confirmar novamente toda a cadeia operacional."
        },
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["status"] == "proposed"
    assert all(value is None for value in reopened.json()["graph_nodes"].values())
    graph_after_reopen = client.get(graph_base, headers=headers)
    assert graph_after_reopen.status_code == 200, graph_after_reopen.text
    superseded_ids = {
        node["id"]
        for node in graph_after_reopen.json()["nodes"]
        if node["status"] == "superseded"
    }
    assert {
        materialized.json()["decision_node_id"],
        materialized.json()["action_node_id"],
        materialized.json()["outcome_node_id"],
        materialized.json()["learning_node_id"],
    }.issubset(superseded_ids)
    superseded_candidates = client.get(
        f"/api/pilot/learning/missions/{sub_mission.json()['code']}/candidates",
        headers=headers,
    )
    assert superseded_candidates.status_code == 200, superseded_candidates.text
    superseded_packet = next(
        row for row in superseded_candidates.json()["candidates"] if row["id"] == packet["id"]
    )
    assert superseded_packet["canonical_status"] == "superseded"
    blocked_reuse = client.post(
        f"/api/pilot/learning/missions/{sub_mission.json()['code']}/candidates/{packet['id']}/review",
        headers=headers,
        json={
            "applicability": "reuse",
            "rationale": "Tentativa de reutilizar uma linhagem entretanto substituída.",
            "context_change": "",
        },
    )
    assert blocked_reuse.status_code == 409, blocked_reuse.text

    invalidated_memory_sync = client.post(f"{memory_base}/sync", headers=headers)
    assert invalidated_memory_sync.status_code == 200, invalidated_memory_sync.text
    memory_after_reopen = client.get(f"{memory_base}/items?limit=500", headers=headers)
    invalidated_learning = next(
        item
        for item in memory_after_reopen.json()
        if item["canonical_record_id"] == f"PILOT-{learning_node_id}"
    )
    assert invalidated_learning["state"] == "superseded"
    assert invalidated_learning["metadata"]["source_graph_state"] == "superseded"

    summary_after_reopen = client.get("/api/pilot/workspace-summary", headers=headers)
    reopened_mission_summary = next(
        row
        for row in summary_after_reopen.json()["missions"]
        if row["id"] == mission_payload["id"]
    )
    assert reopened_mission_summary["published_learning"] == 0
    assert reopened_mission_summary["attention"] > 0
    assert summary_after_reopen.json()["metrics"]["missions_attention"] >= 1

    recommitted = client.patch(
        f"/api/pilot/decision-cycles/{decision.json()['id']}",
        headers=headers,
        json={"status": "committed"},
    )
    assert recommitted.status_code == 200, recommitted.text
    restarted = client.patch(
        f"/api/pilot/decision-cycles/{decision.json()['id']}",
        headers=headers,
        json={"status": "in_progress"},
    )
    assert restarted.status_code == 200, restarted.text
    recompleted = client.patch(
        f"/api/pilot/decision-cycles/{decision.json()['id']}",
        headers=headers,
        json={"status": "completed"},
    )
    assert recompleted.status_code == 200, recompleted.text
    rematerialized = client.post(
        f"/api/pilot/decision-cycles/{decision.json()['id']}/materialize-learning",
        headers=headers,
    )
    assert rematerialized.status_code == 201, rematerialized.text
    assert rematerialized.json()["already_materialized"] is False
    old_lineage_ids = {
        materialized.json()["decision_node_id"],
        materialized.json()["action_node_id"],
        materialized.json()["outcome_node_id"],
        materialized.json()["learning_node_id"],
    }
    new_lineage_ids = {
        rematerialized.json()["decision_node_id"],
        rematerialized.json()["action_node_id"],
        rematerialized.json()["outcome_node_id"],
        rematerialized.json()["learning_node_id"],
    }
    assert old_lineage_ids.isdisjoint(new_lineage_ids)
    graph_after_rematerialization = client.get(graph_base, headers=headers)
    active_graph_ids = {
        node["id"]
        for node in graph_after_rematerialization.json()["nodes"]
        if node["status"] not in {"rejected", "superseded"}
    }
    assert new_lineage_ids.issubset(active_graph_ids)
    assert old_lineage_ids.isdisjoint(active_graph_ids)

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
            "central_question": "A intervenção reduz água por quarto-noite ocupado sem degradar a operação?",
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
    assert seeded_payload["protocol"]["denominator_name"] == "Quartos-noite ocupados"
    assert seeded_payload["protocol"]["denominator_unit"] == "quarto-noite ocupado"

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
            "denominator_name": "Quartos-noite ocupados",
            "denominator_unit": "quarto-noite ocupado",
            "target_value": 0.08,
            "target_description": "Atingir no máximo 0,08 m³ por quarto-noite ocupado no período de revisão.",
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
            "body": "100 m³ e 1 000 quartos-noite ocupados, conferidos pela operação.",
            "status": "proposed",
            "provenance": {"source": "operational_records", "human_reviewed": True},
        },
    )
    result_evidence = client.post(
        f"{graph_base}/nodes",
        headers=headers,
        json={
            "node_type": "evidence",
            "label": "Leituras e ocupação · março",
            "body": "70 m³ e 1 000 quartos-noite ocupados, conferidos pela operação.",
            "status": "proposed",
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
    assert result.json()["readiness"]["ready"] is False
    assert result.json()["readiness"]["progress_percent"] < 100
    assert {
        "baseline_evidence_reviewed",
        "result_evidence_reviewed",
    }.issubset(set(result.json()["readiness"]["blocking_keys"]))

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

    for evidence_id in (baseline_evidence.json()["id"], result_evidence.json()["id"]):
        evidence_review = client.patch(
            f"{graph_base}/nodes/{evidence_id}",
            headers=headers,
            json={"status": "verified"},
        )
        assert evidence_review.status_code == 200, evidence_review.text

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
