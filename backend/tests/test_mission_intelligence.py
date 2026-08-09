from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest
from app.atlas_platform.config import Settings, validate_security_settings
from app.atlas_platform.database import Base, SessionLocal, engine
from app.atlas_platform.models import Membership, Role
from app.main import app
from app.mission_intelligence import ai as mission_ai
from app.mission_intelligence import api as mission_api
from app.mission_intelligence import service
from app.mission_intelligence.ai import (
    AIExecution,
    AIProviderUsage,
    AIUnavailableError,
    PreparedAIRequest,
)
from app.mission_intelligence.contracts import (
    AIAdvisory,
    AIInference,
    AIOption,
    ConfidenceLevel,
)
from app.mission_intelligence.governance import (
    AIGovernanceBlocked,
    reserve_ai_usage,
    settle_ai_usage,
)
from fastapi.testclient import TestClient
from pydantic import ValidationError

os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("SRIS_AI_PILOT_ORGANIZATION_ID", None)
os.environ["SRIS_AI_ENABLED"] = "false"

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
client = TestClient(app)


def _owner() -> tuple[dict[str, str], str]:
    register = client.post(
        "/api/auth/register",
        json={
            "email": "mi-owner@example.com",
            "full_name": "Mission Owner",
            "password": "strong-password-123",
        },
    )
    assert register.status_code == 201, register.text
    login = client.post(
        "/api/auth/login",
        json={"email": "mi-owner@example.com", "password": "strong-password-123"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    organization = client.post(
        "/api/organizations",
        headers=headers,
        json={"name": "Mission Intelligence Lab", "slug": "mission-intelligence-lab"},
    )
    assert organization.status_code == 201, organization.text
    return headers, organization.json()["id"]


def _owner_named(suffix: str) -> tuple[dict[str, str], str]:
    register = client.post(
        "/api/auth/register",
        json={
            "email": f"mi-owner-{suffix}@example.com",
            "full_name": f"Mission Owner {suffix}",
            "password": "strong-password-123",
        },
    )
    assert register.status_code == 201, register.text
    login = client.post(
        "/api/auth/login",
        json={
            "email": f"mi-owner-{suffix}@example.com",
            "password": "strong-password-123",
        },
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    organization = client.post(
        "/api/organizations",
        headers=headers,
        json={
            "name": f"Mission Intelligence Lab {suffix}",
            "slug": f"mission-intelligence-lab-{suffix}",
        },
    )
    assert organization.status_code == 201, organization.text
    return headers, organization.json()["id"]


def _analysis_payload(**patch):
    payload = {
        "title": "M-001 — decisão de gestão florestal",
        "context": "Parcela florestal com decisão de gestão por tomar.",
        "central_question": "Qual é a próxima decisão defensável?",
        "available_evidence": "OBS-0001, OBS-0002 e OBS-0003.",
        "unknowns": "ASS-0001, ASS-0002, RST-0001 e RST-0002.",
        "use_ai": False,
    }
    payload.update(patch)
    return payload


def test_public_demo_runs_real_deterministic_mission_intelligence() -> None:
    status = client.get("/api/mission-intelligence/status")
    assert status.status_code == 200
    assert status.json()["foundation_version"] == "1.3"
    assert status.json()["human_review_required"] is True
    assert status.json()["ai_pilot_gate"] == "single_organization"
    assert status.json()["ai_pilot_organization_configured"] is False
    assert status.json()["institutional_onboarding_closed"] is False

    response = client.post(
        "/api/mission-intelligence/demo/missions/M-001/analyze",
        json=_analysis_payload(),
    )
    assert response.status_code == 200, response.text
    data = response.json()
    report = data["deterministic"]
    assert data["execution_mode"] == "deterministic"
    assert data["snapshot_hash"]
    assert report["mission_status"] == "requires_attention"
    assert report["mission_trend"] == "not_evaluable"
    assert report["decision_confidence"] == "moderate"
    gap_codes = {gap["code"] for gap in report["gaps"]}
    assert {"MI-ASSUMPTIONS-OPEN", "MI-CONSTRAINTS-OPEN", "MI-NO-BASELINE"}.issubset(gap_codes)
    assert any("Não se infere resultado" in item for item in report["non_inferences"])


def test_public_demo_never_spends_ai_without_authentication() -> None:
    response = client.post(
        "/api/mission-intelligence/demo/missions/M-001/analyze",
        json=_analysis_payload(use_ai=True),
    )
    assert response.status_code == 200
    assert response.json()["ai"] is None
    assert response.json()["ai_status"] == "authentication_required"


def test_free_text_claim_cannot_become_canonical_baseline() -> None:
    response = client.post(
        "/api/mission-intelligence/demo/missions/M-001/analyze",
        json=_analysis_payload(
            available_evidence="Declaro que existe uma linha de base medida."
        ),
    )
    assert response.status_code == 200
    gap_codes = {gap["code"] for gap in response.json()["deterministic"]["gaps"]}
    assert "MI-NO-BASELINE" in gap_codes


def test_authenticated_run_is_persisted_versioned_and_human_reviewed() -> None:
    headers, organization_id = _owner()
    endpoint = f"/api/organizations/{organization_id}/mission-intelligence/demo/M-001/analyze"
    first = client.post(endpoint, headers=headers, json=_analysis_payload(use_ai=True))
    assert first.status_code == 200, first.text
    first_data = first.json()
    assert first_data["ai_status"] == "not_configured"
    assert first_data["mission_revision"] == 1
    assert first_data["review_status"] == "required"

    same = client.post(endpoint, headers=headers, json=_analysis_payload())
    assert same.status_code == 200
    assert same.json()["mission_revision"] == 1

    changed = client.post(
        endpoint,
        headers=headers,
        json=_analysis_payload(context="Contexto revisto e aceite como nova revisão."),
    )
    assert changed.status_code == 200
    assert changed.json()["mission_revision"] == 2

    mission_list = client.get(
        f"/api/organizations/{organization_id}/mission-intelligence/missions",
        headers=headers,
    )
    assert mission_list.status_code == 200
    assert mission_list.json()[0]["revision"] == 2

    review = client.post(
        f"/api/organizations/{organization_id}/mission-intelligence/runs/{first_data['run_id']}/review",
        headers=headers,
        json={
            "decision": "approved",
            "comment": "Relatório revisto; aprovação não equivale a aceitar qualquer alternativa.",
        },
    )
    assert review.status_code == 200, review.text
    assert review.json()["review_status"] == "approved"


def test_health_checks_database_and_security_headers_are_present() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-request-id"]


def test_ai_failure_never_removes_the_deterministic_report(monkeypatch) -> None:
    monkeypatch.setattr(service, "is_ai_configured", lambda: True)

    def fail_provider(*_args, **_kwargs):
        raise AIUnavailableError("AI provider request failed")

    monkeypatch.setattr(service, "analyze_with_openai", fail_provider)
    result = service.analyze_demo(
        "M-001",
        service.AnalysisInput(**_analysis_payload(use_ai=True)),
        allow_ai=True,
    )
    assert result["ai_status"] == "failed"
    assert result["execution_mode"] == "deterministic"
    assert result["deterministic"]["mission_status"] == "requires_attention"
    assert result["ai"] is None


def test_every_ai_option_requires_a_canonical_basis() -> None:
    with pytest.raises(ValidationError):
        AIOption(
            title="Opção sem base",
            rationale="Não deve atravessar o contrato.",
            risks=[],
            prerequisites=[],
            based_on_ids=[],
        )


def test_frontend_and_openapi_expose_the_new_capability() -> None:
    frontend = client.get("/")
    assert frontend.status_code == 200
    assert "UI-R2 · MI-1" in frontend.text
    assert "Executar Mission Intelligence" in frontend.text
    assert "aiGovernanceStatus?.organization_authorized" in frontend.text

    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    assert spec.json()["info"]["title"] == "SRIS Mission Intelligence API"
    assert spec.json()["info"]["version"] == "1.4.0"
    assert "/api/mission-intelligence/demo/missions/{mission_code}/analyze" in spec.json()["paths"]
    governance_path = (
        "/api/organizations/{organization_id}/mission-intelligence/ai-governance"
    )
    policy_path = governance_path + "/policy"
    events_path = governance_path + "/events"
    assert governance_path in spec.json()["paths"]
    assert policy_path in spec.json()["paths"]
    assert events_path in spec.json()["paths"]
    assert "put" in spec.json()["paths"][policy_path]


def test_ai_requires_explicit_org_policy_and_enforces_monthly_quota(monkeypatch) -> None:
    headers, organization_id = _owner_named("governance")
    endpoint = f"/api/organizations/{organization_id}/mission-intelligence/demo/M-001/analyze"

    monkeypatch.setattr(service, "is_ai_configured", lambda: True)
    monkeypatch.setattr(mission_api, "is_ai_configured", lambda: True)

    provider_calls = 0

    def fake_provider(*_args, **_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        return AIExecution(
            advisory=AIAdvisory(
                executive_summary="Análise provisória baseada no snapshot.",
                inferences=[
                    AIInference(
                        statement="A linha de base continua insuficiente.",
                        based_on_ids=["OBS-0001"],
                        uncertainty="Sem série temporal.",
                        confidence=ConfidenceLevel.MODERATE,
                    )
                ],
                critical_gaps=["Série temporal em falta."],
                decision_options=[
                    AIOption(
                        title="Medir antes de intervir",
                        rationale="Reduzir a incerteza.",
                        risks=["Atraso na decisão."],
                        prerequisites=["Instrumentação."],
                        based_on_ids=["OBS-0001"],
                    )
                ],
                recommended_next_step="Instalar a linha de base.",
                cautions=["Não constitui decisão."],
            ),
            provider="openai",
            model="gpt-5.6",
            provider_response_id="resp_test_governed",
            usage=AIProviderUsage(
                input_tokens=1_000,
                cached_input_tokens=100,
                output_tokens=200,
                total_tokens=1_200,
            ),
        )

    monkeypatch.setattr(service, "analyze_with_openai", fake_provider)
    monkeypatch.setattr(service, "count_openai_input_tokens", lambda _request: 1_000)

    blocked = client.post(endpoint, headers=headers, json=_analysis_payload(use_ai=True))
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["ai_status"] == "governance_blocked"
    assert blocked.json()["ai_governance"]["code"] == "policy_required"
    assert blocked.json()["deterministic"]
    assert provider_calls == 0

    policy = client.put(
        f"/api/organizations/{organization_id}/mission-intelligence/ai-governance/policy",
        headers=headers,
        json={
            "enabled": True,
            "monthly_request_limit": 1,
            "monthly_input_token_limit": 100_000,
            "monthly_output_token_limit": 10_000,
            "monthly_budget_usd": "1.00",
            "per_request_input_token_limit": 60_000,
            "per_request_output_token_limit": 3_000,
            "max_concurrent_requests": 1,
        },
    )
    assert policy.status_code == 200, policy.text
    assert policy.json()["ready"] is True

    completed = client.post(endpoint, headers=headers, json=_analysis_payload(use_ai=True))
    assert completed.status_code == 200, completed.text
    completed_data = completed.json()
    assert completed_data["ai_status"] == "completed"
    assert completed_data["execution_mode"] == "hybrid"
    assert completed_data["ai_usage"]["input_tokens"] == 1_000
    assert completed_data["ai_usage"]["cached_input_tokens"] == 100
    assert completed_data["ai_usage"]["output_tokens"] == 200
    assert completed_data["ai_usage"]["estimated_cost_usd"] == "0.010550"
    assert completed_data["ai_usage"]["cost_basis"] == "provider_reported_usage"
    assert provider_calls == 1

    usage = client.get(
        f"/api/organizations/{organization_id}/mission-intelligence/ai-governance",
        headers=headers,
    )
    assert usage.status_code == 200
    assert usage.json()["ready"] is False
    assert usage.json()["readiness_reason"] == "monthly_request_limit"
    assert usage.json()["current_period"]["request_count"] == 1
    assert usage.json()["current_period"]["active_reservations"] == 0
    assert usage.json()["current_period"]["estimated_cost_usd"] == "0.010550"

    exhausted = client.post(endpoint, headers=headers, json=_analysis_payload(use_ai=True))
    assert exhausted.status_code == 200, exhausted.text
    assert exhausted.json()["ai_status"] == "governance_blocked"
    assert exhausted.json()["ai_governance"]["code"] == "monthly_request_limit"
    assert exhausted.json()["deterministic"]
    assert provider_calls == 1

    events = client.get(
        f"/api/organizations/{organization_id}/mission-intelligence/ai-governance/events",
        headers=headers,
    )
    assert events.status_code == 200
    assert len(events.json()) == 1
    assert events.json()[0]["intelligence_run_id"] == completed_data["run_id"]


def test_non_pilot_organization_never_crosses_the_provider_gate(monkeypatch) -> None:
    headers, organization_id = _owner_named("pilot-denied")
    endpoint = f"/api/organizations/{organization_id}/mission-intelligence/demo/M-001/analyze"
    monkeypatch.setattr(service, "is_ai_configured", lambda: True)
    monkeypatch.setattr(service, "is_ai_organization_authorized", lambda _org: False)

    def must_not_call_provider(*_args, **_kwargs):
        raise AssertionError("An unauthorized organization crossed the pilot gate")

    monkeypatch.setattr(service, "analyze_with_openai", must_not_call_provider)
    response = client.post(
        endpoint,
        headers=headers,
        json=_analysis_payload(use_ai=True),
    )
    assert response.status_code == 200, response.text
    assert response.json()["ai_status"] == "governance_blocked"
    assert response.json()["ai_governance"]["code"] == "organization_not_authorized"
    assert response.json()["deterministic"]


def test_non_pilot_owner_cannot_enable_an_ai_policy(monkeypatch) -> None:
    headers, organization_id = _owner_named("policy-denied")
    monkeypatch.setattr(
        mission_api,
        "is_ai_organization_authorized",
        lambda _organization_id: False,
    )
    response = client.put(
        f"/api/organizations/{organization_id}/mission-intelligence/ai-governance/policy",
        headers=headers,
        json={
            "enabled": True,
            "monthly_request_limit": 20,
            "monthly_input_token_limit": 250_000,
            "monthly_output_token_limit": 50_000,
            "monthly_budget_usd": "5.00",
            "per_request_input_token_limit": 60_000,
            "per_request_output_token_limit": 3_000,
            "max_concurrent_requests": 1,
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "organization_not_authorized"


def test_operator_can_close_public_registration_and_organization_creation(
    monkeypatch,
) -> None:
    headers, _ = _owner_named("closed-onboarding")
    monkeypatch.setenv("ATLAS_SELF_REGISTRATION_ENABLED", "false")
    monkeypatch.setenv("ATLAS_ORGANIZATION_CREATION_ENABLED", "false")

    register = client.post(
        "/api/auth/register",
        json={
            "email": "blocked-registration@example.com",
            "full_name": "Blocked Registration",
            "password": "strong-password-123",
        },
    )
    assert register.status_code == 403
    assert register.json()["detail"] == "Self-registration is disabled"

    organization = client.post(
        "/api/organizations",
        headers=headers,
        json={"name": "Blocked Organization", "slug": "blocked-organization"},
    )
    assert organization.status_code == 403
    assert organization.json()["detail"] == "Organization creation is disabled"


def test_provider_failure_is_charged_conservatively_and_releases_reservation(monkeypatch) -> None:
    headers, organization_id = _owner_named("provider-failure")
    endpoint = f"/api/organizations/{organization_id}/mission-intelligence/demo/M-001/analyze"
    monkeypatch.setattr(service, "is_ai_configured", lambda: True)
    monkeypatch.setattr(service, "count_openai_input_tokens", lambda _request: 1_000)

    policy = client.put(
        f"/api/organizations/{organization_id}/mission-intelligence/ai-governance/policy",
        headers=headers,
        json={
            "enabled": True,
            "monthly_request_limit": 5,
            "monthly_input_token_limit": 100_000,
            "monthly_output_token_limit": 20_000,
            "monthly_budget_usd": "5.00",
            "per_request_input_token_limit": 60_000,
            "per_request_output_token_limit": 3_000,
            "max_concurrent_requests": 1,
        },
    )
    assert policy.status_code == 200

    def fail_provider(*_args, **_kwargs):
        raise AIUnavailableError("AI provider request failed")

    monkeypatch.setattr(service, "analyze_with_openai", fail_provider)
    response = client.post(endpoint, headers=headers, json=_analysis_payload(use_ai=True))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ai_status"] == "failed"
    assert data["execution_mode"] == "deterministic"
    assert data["ai_usage"]["status"] == "provider_error"
    assert data["ai_usage"]["cost_basis"] == "conservative_failure_reservation"

    usage = client.get(
        f"/api/organizations/{organization_id}/mission-intelligence/ai-governance",
        headers=headers,
    ).json()["current_period"]
    assert usage["active_reservations"] == 0
    assert usage["request_count"] == 1
    assert usage["input_tokens"] == 1_000
    assert usage["output_tokens"] == 3_000


def test_contributor_can_run_deterministic_analysis_but_cannot_spend_ai(monkeypatch) -> None:
    headers, organization_id = _owner_named("contributor-gate")
    policy = client.put(
        f"/api/organizations/{organization_id}/mission-intelligence/ai-governance/policy",
        headers=headers,
        json={
            "enabled": True,
            "monthly_request_limit": 5,
            "monthly_input_token_limit": 100_000,
            "monthly_output_token_limit": 20_000,
            "monthly_budget_usd": "5.00",
            "per_request_input_token_limit": 60_000,
            "per_request_output_token_limit": 3_000,
            "max_concurrent_requests": 1,
        },
    )
    assert policy.status_code == 200

    with SessionLocal() as db:
        membership = (
            db.query(Membership)
            .filter(Membership.organization_id == organization_id)
            .one()
        )
        membership.role = Role.CONTRIBUTOR.value
        db.commit()

    monkeypatch.setattr(service, "is_ai_configured", lambda: True)

    def must_not_call_provider(*_args, **_kwargs):
        raise AssertionError("Contributor crossed the AI spending gate")

    monkeypatch.setattr(service, "analyze_with_openai", must_not_call_provider)
    response = client.post(
        f"/api/organizations/{organization_id}/mission-intelligence/demo/M-001/analyze",
        headers=headers,
        json=_analysis_payload(use_ai=True),
    )
    assert response.status_code == 200, response.text
    assert response.json()["ai_status"] == "governance_blocked"
    assert response.json()["ai_governance"]["code"] == "role_not_allowed"
    assert response.json()["deterministic"]


def test_active_reservation_blocks_a_second_concurrent_request() -> None:
    headers, organization_id = _owner_named("concurrency")
    policy = client.put(
        f"/api/organizations/{organization_id}/mission-intelligence/ai-governance/policy",
        headers=headers,
        json={
            "enabled": True,
            "monthly_request_limit": 5,
            "monthly_input_token_limit": 100_000,
            "monthly_output_token_limit": 20_000,
            "monthly_budget_usd": "5.00",
            "per_request_input_token_limit": 60_000,
            "per_request_output_token_limit": 3_000,
            "max_concurrent_requests": 1,
        },
    )
    assert policy.status_code == 200

    with SessionLocal() as db:
        membership = (
            db.query(Membership)
            .filter(Membership.organization_id == organization_id)
            .one()
        )
        first = reserve_ai_usage(
            db,
            organization_id=organization_id,
            user_id=membership.user_id,
            model="gpt-5.6",
            input_tokens=1_000,
            output_tokens=1_000,
        )
        with pytest.raises(AIGovernanceBlocked) as blocked:
            reserve_ai_usage(
                db,
                organization_id=organization_id,
                user_id=membership.user_id,
                model="gpt-5.6",
                input_tokens=1_000,
                output_tokens=1_000,
            )
        assert blocked.value.code == "concurrency_limit"
        db.rollback()
        settled = settle_ai_usage(
            db,
            reservation=first,
            provider_response_id="resp_concurrency_test",
            input_tokens=800,
            cached_input_tokens=0,
            output_tokens=100,
            total_tokens=900,
        )
        assert settled.status == "completed"


def test_provider_input_token_count_uses_the_full_structured_request(monkeypatch) -> None:
    captured: dict = {}

    class FakeInputTokens:
        def count(self, **kwargs):
            captured.update(kwargs)
            return type("Count", (), {"input_tokens": 1_234})()

    class FakeResponses:
        input_tokens = FakeInputTokens()

    class FakeOpenAI:
        responses = FakeResponses()

        def __init__(self, **_kwargs):
            pass

    monkeypatch.setenv("SRIS_AI_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-never-sent")
    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    request = PreparedAIRequest(
        model="gpt-5.6",
        instructions="Governed instructions",
        input_text='{"mission":"M-001"}',
        text_config={
            "format": {
                "type": "json_schema",
                "name": "AIAdvisory",
                "strict": True,
                "schema": {"type": "object", "additionalProperties": False},
            }
        },
        max_output_tokens=3_000,
    )

    assert mission_ai.count_openai_input_tokens(request) == 1_234
    assert captured["model"] == "gpt-5.6"
    assert captured["instructions"] == "Governed instructions"
    assert captured["input"] == '{"mission":"M-001"}'
    assert captured["reasoning"] == {"effort": "low"}
    assert captured["text"] == request.text_config


def test_production_rejects_a_weak_jwt_secret() -> None:
    with pytest.raises(RuntimeError, match="at least 32 bytes"):
        validate_security_settings(
            Settings(
                database_url="sqlite+pysqlite:///:memory:",
                jwt_secret="too-short",
                environment="production",
            )
        )


def test_managed_production_ai_requires_one_canonical_pilot_organization(
    monkeypatch,
) -> None:
    pilot_id = "5f1392db-f4da-441d-9e2e-e863dbca2c42"
    other_id = "b84fa4f7-e013-4fd0-87da-728ab01bc7b0"
    monkeypatch.setenv("ATLAS_ENV", "production")
    monkeypatch.setenv("SRIS_AI_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-never-sent")
    monkeypatch.delenv("SRIS_AI_PILOT_ORGANIZATION_ID", raising=False)

    assert mission_ai.is_ai_configured() is False
    assert mission_ai.is_ai_organization_authorized(pilot_id) is False

    monkeypatch.setenv("SRIS_AI_PILOT_ORGANIZATION_ID", "not-a-uuid")
    assert mission_ai.is_ai_configured() is False

    monkeypatch.setenv("SRIS_AI_PILOT_ORGANIZATION_ID", pilot_id)
    assert mission_ai.is_ai_configured() is False

    monkeypatch.setenv("ATLAS_SELF_REGISTRATION_ENABLED", "false")
    monkeypatch.setenv("ATLAS_ORGANIZATION_CREATION_ENABLED", "false")
    assert mission_ai.is_ai_configured() is True
    assert mission_ai.is_ai_organization_authorized(pilot_id) is True
    assert mission_ai.is_ai_organization_authorized(other_id) is False

    status = client.get("/api/mission-intelligence/status")
    assert status.status_code == 200
    assert status.json()["ai_configured"] is True
    assert status.json()["ai_pilot_organization_configured"] is True
    assert status.json()["institutional_onboarding_closed"] is True
    assert pilot_id not in status.text


def test_emergency_password_recovery_is_scoped_one_time_and_fail_closed(
    monkeypatch,
) -> None:
    suffix = uuid4().hex[:8]
    email = f"mi-owner-{suffix}@example.com"
    old_password = "strong-password-123"
    new_password = "new-strong-password-456"
    recovery_token = "a" * 64
    endpoint = "/api/auth/emergency-password-recovery"
    request = {
        "email": email,
        "recovery_token": recovery_token,
        "new_password": new_password,
    }

    monkeypatch.delenv("SRIS_PASSWORD_RECOVERY_EMAIL", raising=False)
    monkeypatch.delenv("SRIS_PASSWORD_RECOVERY_TOKEN", raising=False)
    assert client.post(endpoint, json=request).status_code == 404
    assert endpoint not in client.get("/openapi.json").json()["paths"]

    _, organization_id = _owner_named(suffix)
    monkeypatch.setenv("SRIS_PASSWORD_RECOVERY_EMAIL", email)
    monkeypatch.setenv("SRIS_PASSWORD_RECOVERY_TOKEN", recovery_token)

    wrong_token = dict(request, recovery_token="b" * 64)
    assert client.post(endpoint, json=wrong_token).status_code == 404

    monkeypatch.setenv("SRIS_AI_PILOT_ORGANIZATION_ID", str(uuid4()))
    assert client.post(endpoint, json=request).status_code == 404

    monkeypatch.setenv("SRIS_AI_PILOT_ORGANIZATION_ID", organization_id)
    recovered = client.post(endpoint, json=request)
    assert recovered.status_code == 200, recovered.text
    assert recovered.json() == {"status": "password_updated"}

    old_login = client.post(
        "/api/auth/login",
        json={"email": email, "password": old_password},
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/api/auth/login",
        json={"email": email, "password": new_password},
    )
    assert new_login.status_code == 200

    replay = client.post(
        endpoint,
        json=dict(request, new_password="another-strong-password-789"),
    )
    assert replay.status_code == 409

    still_new_login = client.post(
        "/api/auth/login",
        json={"email": email, "password": new_password},
    )
    assert still_new_login.status_code == 200

    monkeypatch.delenv("SRIS_PASSWORD_RECOVERY_EMAIL")
    monkeypatch.delenv("SRIS_PASSWORD_RECOVERY_TOKEN")
    assert client.post(endpoint, json=request).status_code == 404


def test_password_recovery_script_cleanup_cannot_mask_api_error() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / "scripts" / "RESET_MI_PILOT_PASSWORD.ps1").read_text(
        encoding="utf-8"
    )

    assert '"" | Set-Clipboard' not in script
    assert "Get-RecoveryFailureMessage" in script
    assert (
        'Set-Clipboard -Value "[SRIS: segredo temporario removido]" '
        "-ErrorAction Stop"
    ) in script
    assert 'Write-Warning "Nao foi possivel limpar automaticamente' in script
