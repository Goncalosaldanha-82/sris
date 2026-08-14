from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from app.atlas_platform.config import Settings, validate_security_settings
from app.atlas_platform.database import Base, SessionLocal, engine
from app.atlas_platform.models import Membership, Role, User
from app.main import app
from app.mission_intelligence import ai as mission_ai
from app.mission_intelligence import api as mission_api
from app.mission_intelligence import dialogue_service, service
from app.mission_intelligence import interactive as interactive_ai
from app.mission_intelligence.ai import (
    AIExecution,
    AIProviderUsage,
    AIUnavailableError,
    PreparedAIRequest,
)
from app.mission_intelligence.canonical import legacy_to_canonical
from app.mission_intelligence.catalog import demo_mission
from app.mission_intelligence.contracts import (
    AIAdvisory,
    AIInference,
    AIOption,
    AIResearchBundle,
    AnalysisInput,
    ConfidenceLevel,
    ContextClaim,
    ContextDossier,
    ContextGap,
    ContextSource,
    MIInteractionIntent,
    MIInteractiveOutput,
    MIInteractiveResearchBundle,
)
from app.mission_intelligence.engine import analyze_mission
from app.mission_intelligence.governance import (
    AIGovernanceBlocked,
    reserve_ai_usage,
    settle_ai_usage,
)
from app.mission_intelligence.interactive import MIInteractiveExecution
from fastapi.testclient import TestClient
from openai import BadRequestError, OpenAI
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


def _canonical_analysis(mission_code: str):
    legacy = demo_mission(mission_code)
    assert legacy is not None
    document = legacy_to_canonical(
        legacy,
        AnalysisInput(
            **_analysis_payload(
                title=f"{mission_code} — análise governada",
            )
        ),
    )
    return document, analyze_mission(document)


def _research_bundle(document) -> AIResearchBundle:
    basis_id = document.records[0].canonical_id
    source_url = "https://example.gov.pt/dragos-study"
    archaeology_url = "https://example.edu.pt/dragos-archaeology"
    return AIResearchBundle(
        context_dossier=ContextDossier(
            mission_id=document.mission_id,
            scope="Envolvente histórica e hidrogeológica da missão.",
            synthesis="Existe uma pista documental; a ligação funcional continua por provar.",
            domains=["arqueologia", "hidrogeologia", "governação"],
            sources=[
                ContextSource(
                    source_id="SRC-TEST-001",
                    title="Estudo oficial de enquadramento",
                    url=source_url,
                    publisher="Entidade pública de teste",
                    source_type="official",
                    authority="primary",
                    limitations="Não inclui análise laboratorial da água.",
                ),
                ContextSource(
                    source_id="SRC-TEST-002",
                    title="Estudo arqueológico de enquadramento",
                    url=archaeology_url,
                    publisher="Universidade pública de teste",
                    source_type="academic",
                    authority="primary",
                    limitations="Não demonstra uma ligação funcional à nascente.",
                ),
            ],
            claims=[
                ContextClaim(
                    claim_id="CLM-TEST-001",
                    statement="O topónimo está documentado na área da missão.",
                    domain="história local",
                    epistemic_status="supported",
                    source_ids=["SRC-TEST-001"],
                    relevance="Justifica investigação espacial dirigida.",
                    limitations="Não demonstra uso romano da água.",
                ),
                ContextClaim(
                    claim_id="CLM-TEST-002",
                    statement="Existe presença material romana na área alargada.",
                    domain="arqueologia",
                    epistemic_status="partially_supported",
                    source_ids=["SRC-TEST-002"],
                    relevance="Torna a hipótese histórica materialmente relevante.",
                    limitations="Proximidade não prova uso da nascente.",
                ),
                ContextClaim(
                    claim_id="CLM-TEST-003",
                    statement="A água teria sido utilizada pelos romanos.",
                    domain="história da água",
                    epistemic_status="unverified",
                    source_ids=[],
                    relevance="A confirmação alteraria o valor patrimonial da missão.",
                    limitations="Não foi localizada prova específica.",
                ),
            ],
            gaps=[
                ContextGap(
                    gap_id="GAP-TEST-001",
                    question="A água possui propriedades tecnicamente caracterizadas?",
                    domain="hidrogeologia",
                    why_it_matters="A qualificação medicinal exige prova própria.",
                    evidence_needed="Análises por laboratório acreditado.",
                    priority="critical",
                ),
                ContextGap(
                    gap_id="GAP-TEST-002",
                    question="Qual é a relação espacial entre os vestígios e a nascente?",
                    domain="cartografia",
                    why_it_matters="A proximidade tem de ser medida.",
                    evidence_needed="Levantamento georreferenciado.",
                    priority="critical",
                ),
                ContextGap(
                    gap_id="GAP-TEST-003",
                    question="Que entidades têm competência sobre o local?",
                    domain="governação",
                    why_it_matters="A investigação requer legitimidade.",
                    evidence_needed="Verificação documental e institucional.",
                    priority="high",
                ),
            ],
            limits=["Dossier preliminar sujeito a validação competente."],
            research_status="in_review",
            review_required=True,
        ),
        advisory=AIAdvisory(
            executive_summary="A hipótese merece investigação, não conclusão.",
            inferences=[
                AIInference(
                    statement="O contexto disponível não prova uso romano da nascente.",
                    based_on_ids=[basis_id],
                    uncertainty="Falta contexto arqueológico funcional.",
                    confidence=ConfidenceLevel.LOW,
                )
            ],
            critical_gaps=["Análise hidrogeológica em falta."],
            decision_options=[
                AIOption(
                    title="Investigar antes de intervir",
                    rationale="Preservar a integridade científica da missão.",
                    risks=["A investigação pode não confirmar a hipótese."],
                    prerequisites=["Autorização e equipa competente."],
                    based_on_ids=[basis_id],
                )
            ],
            recommended_next_step="Georreferenciar e validar as fontes existentes.",
            cautions=["Não apresentar a hipótese como facto."],
        ),
    )


def _interactive_output(
    document,
    intent: MIInteractionIntent = MIInteractionIntent.DIAGNOSE,
) -> MIInteractiveOutput:
    basis = [record.canonical_id for record in document.records]
    assert len(basis) >= 7
    return MIInteractiveOutput.model_validate(
        {
            "intent": intent.value,
            "direct_answer": {
                "answer": (
                    "A missão ainda não deve escolher uma intervenção; deve primeiro "
                    "separar legitimidade, risco imediato e aprendizagem comparativa."
                ),
                "status": "conditional",
                "what_changed": (
                    "O turno acrescenta uma contra-hipótese, uma alternativa-piloto "
                    "reversível e regras explícitas para decidir após medição."
                ),
            },
            "mission_reading": {
                "decision_problem": "Escolher uma gestão territorial defensável.",
                "current_blocker": "A autorização e a linha de base estão em aberto.",
                "key_tension": "Reduzir combustível sem destruir a capacidade de aprender.",
                "blind_spot": "A urgência operacional ainda não foi separada da causalidade hídrica.",
                "based_on_ids": [basis[0], basis[1], basis[2]],
            },
            "questions": [
                {
                    "question_id": "Q-AI-001",
                    "question": "Qual é o resultado prioritário que pode excluir os restantes?",
                    "why_it_matters": "Sem hierarquia não existe comparação coerente.",
                    "priority": "critical",
                    "answer_type": "single_choice",
                    "options": ["Risco de incêndio", "Regime hídrico", "Biodiversidade"],
                    "decision_unlocked": "Ponderação dos critérios.",
                    "based_on_ids": [basis[0], basis[2]],
                },
                {
                    "question_id": "Q-AI-002",
                    "question": "Existe autorização para instrumentar sem intervir?",
                    "why_it_matters": "A medição também exige legitimidade.",
                    "priority": "critical",
                    "answer_type": "yes_no",
                    "options": [],
                    "decision_unlocked": "Início legal da linha de base.",
                    "based_on_ids": [basis[6]],
                },
                {
                    "question_id": "Q-AI-003",
                    "question": "Que área pode servir de comparação sem intervenção?",
                    "why_it_matters": "Sem comparador a causalidade fica fraca.",
                    "priority": "high",
                    "answer_type": "free_text",
                    "options": [],
                    "decision_unlocked": "Desenho quase experimental.",
                    "based_on_ids": [basis[0], basis[1]],
                },
            ],
            "hypotheses": [
                {
                    "proposal_id": "HYP-AI-001",
                    "statement": "A água observada é sobretudo sazonal.",
                    "rationale": "Existe apenas uma observação pontual em abril.",
                    "what_is_new": "Separa a permanência da água da presença observada num único momento.",
                    "based_on_ids": [basis[1]],
                    "evidence_needed": ["Série de nível e caudal durante um ciclo sazonal."],
                    "disconfirming_evidence": ["Escoamento estável no período seco em anos comparáveis."],
                    "confidence": "low",
                    "impact_if_true": "Reduz o peso da hipótese de nascente permanente.",
                },
                {
                    "proposal_id": "HYP-AI-002",
                    "statement": "A carga arbustiva domina o risco imediato, não a densidade arbórea.",
                    "rationale": "O estrato arbustivo existe, mas ainda não foi quantificado.",
                    "what_is_new": "Cria uma contra-hipótese operacional à intervenção centrada no povoamento.",
                    "based_on_ids": [basis[2]],
                    "evidence_needed": ["Inventário de combustível por estrato."],
                    "disconfirming_evidence": ["Avaliação que localize o risco dominante no estrato arbóreo."],
                    "confidence": "low",
                    "impact_if_true": "Favorece uma intervenção seletiva de menor perturbação.",
                },
            ],
            "alternative_proposals": [
                {
                    "proposal_id": "ALT-AI-001",
                    "title": "Piloto adaptativo com área de controlo",
                    "description": "Intervenção seletiva numa parcela pequena, mantendo referência e exclusão ripícola.",
                    "difference_from_existing": "Acrescenta comparação simultânea, reversibilidade e uma porta de expansão condicionada.",
                    "potential_value": ["Aprendizagem antes de escalar.", "Menor exposição irreversível."],
                    "risks": ["A parcela-piloto pode não representar a área total."],
                    "prerequisites": ["Autorização.", "Delimitação técnica das parcelas."],
                    "reversibility": "high",
                    "based_on_ids": [basis[0], basis[1], basis[2]],
                }
            ],
            "decision_criteria": [
                {
                    "proposal_id": "CRT-AI-001",
                    "name": "Risco de combustível",
                    "definition": "Mudança material na continuidade e carga combustível.",
                    "measurement": "Inventário por estrato e continuidade espacial.",
                    "threshold_or_rule": "Definir limiar técnico antes da intervenção.",
                    "trade_off": "Redução de combustível pode aumentar perturbação do solo.",
                    "based_on_ids": [basis[2]],
                },
                {
                    "proposal_id": "CRT-AI-002",
                    "name": "Regime hídrico",
                    "definition": "Mudança de nível ou caudal além da variabilidade de referência.",
                    "measurement": "Série temporal sincronizada com precipitação.",
                    "threshold_or_rule": "Não atribuir mudança sem comparador e janela definida.",
                    "trade_off": "A espera por uma série sazonal atrasa a decisão.",
                    "based_on_ids": [basis[1]],
                },
                {
                    "proposal_id": "CRT-AI-003",
                    "name": "Reversibilidade",
                    "definition": "Capacidade de suspender ou corrigir a intervenção.",
                    "measurement": "Área, intensidade e compromissos irreversíveis.",
                    "threshold_or_rule": "Preferir opção reversível quando a incerteza é material.",
                    "trade_off": "Pode reduzir a velocidade de execução.",
                    "based_on_ids": [basis[6]],
                },
            ],
            "experiment_proposals": [
                {
                    "proposal_id": "EXP-AI-001",
                    "title": "Piloto comparativo sazonal",
                    "question": "A intervenção seletiva altera combustível sem degradar solo e água?",
                    "target_hypothesis_ids": ["HYP-AI-002"],
                    "design": "Comparar parcela-piloto, referência e faixa de exclusão com medição anterior e posterior.",
                    "baseline": "Um ciclo sazonal anterior à decisão de expansão.",
                    "comparator": "Parcela comparável sem intervenção.",
                    "measures": ["Carga combustível.", "Humidade do solo.", "Nível ou caudal.", "Solo exposto."],
                    "success_or_decision_rules": ["Expandir apenas se os limiares pré-definidos forem cumpridos."],
                    "stop_conditions": ["Erosão material.", "Intervenção sem autorização válida."],
                    "timeframe": "Um ciclo sazonal completo, sujeito a revisão técnica.",
                    "limitations": ["Um único ciclo pode não representar anos extremos."],
                    "based_on_ids": [basis[0], basis[1], basis[2], basis[5], basis[6]],
                }
            ],
            "challenges": [
                {
                    "challenge_id": "CHL-AI-001",
                    "target": "A centralidade imediata da água na decisão.",
                    "objection": "O risco de incêndio pode exigir ação independente da causalidade hídrica.",
                    "why_it_matters": "Misturar horizontes pode bloquear uma ação preventiva legítima.",
                    "response_needed": "Separar medidas urgentes e experiência causal.",
                    "based_on_ids": [basis[1], basis[2]],
                }
            ],
            "recommended_actions": [
                {
                    "action_id": "ACT-AI-001",
                    "action": "Confirmar autorização para observar e instrumentar.",
                    "purpose": "Estabelecer legitimidade antes de atividade no terreno.",
                    "owner_role": "Promotor e titular.",
                    "dependencies": [],
                    "urgency": "now",
                    "decision_effect": "Desbloqueia ou impede toda a linha de base.",
                    "based_on_ids": [basis[6]],
                },
                {
                    "action_id": "ACT-AI-002",
                    "action": "Definir parcelas e métricas com competência técnica.",
                    "purpose": "Converter hipóteses em desenho comparável.",
                    "owner_role": "Responsável técnico.",
                    "dependencies": ["Autorização."],
                    "urgency": "next",
                    "decision_effect": "Torna a alternativa-piloto avaliável.",
                    "based_on_ids": [basis[0], basis[1], basis[2]],
                },
            ],
            "recommended_next_move": "Responder às três perguntas e validar a autorização antes de desenhar o protocolo final.",
            "boundary": {
                "statement": "Tudo o que foi acrescentado é proposta sujeita a revisão humana; nenhum facto ou decisão foi criado.",
            },
        }
    )


def test_public_demo_runs_real_deterministic_mission_intelligence() -> None:
    status = client.get("/api/mission-intelligence/status")
    assert status.status_code == 200
    assert status.json()["foundation_version"] == "1.3"
    assert status.json()["engine_version"] == "mission-intelligence-deterministic-1.2"
    assert status.json()["interactive_mission_intelligence"] == "available"
    assert status.json()["interactive_contract_version"] == "2.0"
    assert status.json()["interactive_state"] == "locally_persisted"
    assert status.json()["proposal_review"] == "granular_human_review"
    assert status.json()["canonical_auto_mutation"] is False
    assert status.json()["human_review_required"] is True
    assert status.json()["ai_pilot_gate"] == "single_organization"
    assert status.json()["ai_pilot_organization_configured"] is False
    assert status.json()["institutional_onboarding_closed"] is False
    assert status.json()["context_research_engine"] == "installed"
    assert status.json()["context_research_configured"] is False
    assert status.json()["context_research_requires_human_review"] is True

    response = client.post(
        "/api/mission-intelligence/demo/missions/M-001/analyze",
        json=_analysis_payload(),
    )
    assert response.status_code == 200, response.text
    data = response.json()
    report = data["deterministic"]
    assert data["execution_mode"] == "deterministic"
    assert data["snapshot_hash"]
    assert data["review_allowed"] is False
    assert report["mission_status"] == "requires_attention"
    assert report["mission_trend"] == "not_evaluable"
    assert report["decision_confidence"] == "moderate"
    gap_codes = {gap["code"] for gap in report["gaps"]}
    assert {
        "MI-ASSUMPTIONS-OPEN",
        "MI-CONSTRAINTS-OPEN",
        "MI-NO-BASELINE",
        "MI-CONTEXT-NOT-RESEARCHED",
    }.issubset(gap_codes)
    assert any("Não se infere resultado" in item for item in report["non_inferences"])


def test_public_demo_never_spends_ai_without_authentication() -> None:
    response = client.post(
        "/api/mission-intelligence/demo/missions/M-001/analyze",
        json=_analysis_payload(use_ai=True),
    )
    assert response.status_code == 200
    assert response.json()["ai"] is None
    assert response.json()["ai_status"] == "authentication_required"


def test_public_demo_never_runs_external_context_research() -> None:
    response = client.post(
        "/api/mission-intelligence/demo/missions/M-002/analyze",
        json=_analysis_payload(use_ai=True, research_context=True),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ai"] is None
    assert data["ai_status"] == "authentication_required"
    assert data["context_dossier"]["research_status"] == "preliminary"
    assert data["context_dossier_provenance"]["origin_type"] == "governed_catalog"


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


def test_every_mission_requires_context_research_unless_explicitly_exempted() -> None:
    legacy = deepcopy(demo_mission("M-001"))
    assert legacy is not None
    legacy["analysis_requirements"].pop("context_research")
    document = legacy_to_canonical(legacy, AnalysisInput(**_analysis_payload()))
    requirement = document.metadata["analysis_requirements"]["context_research"]
    assert requirement["required"] is True
    gap_codes = {gap.code for gap in analyze_mission(document).gaps}
    assert "MI-CONTEXT-NOT-RESEARCHED" in gap_codes


def test_case_intake_does_not_inherit_field_intervention_rules() -> None:
    response = client.post(
        "/api/mission-intelligence/demo/missions/M-002/analyze",
        json=_analysis_payload(),
    )
    assert response.status_code == 200, response.text
    report = response.json()["deterministic"]
    gap_codes = {gap["code"] for gap in report["gaps"]}
    assert report["decision_confidence"] == "not_evaluable"
    assert report["counts"]["observation"] == 1
    assert report["counts"]["constraint"] == 2
    assert report["context_assessment"]["status"] == "preliminary"
    assert report["context_assessment"]["source_count"] == 2
    assert report["context_assessment"]["hypothesis_count"] == 1
    assert report["context_assessment"]["unverified_claim_count"] == 1
    assert "MI-CONSTRAINTS-OPEN" in gap_codes
    assert "MI-CONTEXT-REVIEW-PENDING" in gap_codes
    assert "MI-NO-BASELINE" not in gap_codes
    rendered = str(
        {
            "risk": report["principal_risk"],
            "next": report["next_decision"],
            "gaps": report["gaps"],
            "non_inferences": report["non_inferences"],
        }
    ).casefold()
    assert "linha de base" not in rendered
    assert "intervir antes de medir" not in rendered
    assert "titularidade e competências por confirmar" in rendered
    assert "licenciamento" not in rendered
    factors = {item["factor"]: item for item in report["confidence_factors"]}
    assert factors["alternatives"]["assessment"] == "not_applicable"
    assert factors["context_coverage"]["assessment"] == "partial"


def test_every_mission_declares_context_research_or_justifies_non_applicability() -> None:
    catalog = client.get("/api/mission-intelligence/demo/missions").json()
    for mission_code, mission in catalog["missions"].items():
        requirement = mission["analysis_requirements"]["context_research"]
        assert isinstance(requirement["required"], bool)
        assert requirement["reason"].strip()
        response = client.post(
            f"/api/mission-intelligence/demo/missions/{mission_code}/analyze",
            json=_analysis_payload(title=f"{mission_code} — context check"),
        )
        assert response.status_code == 200, response.text
        assessment = response.json()["deterministic"]["context_assessment"]
        if requirement["required"]:
            assert assessment["status"] != "not_required"
        else:
            assert assessment["status"] == "not_required"


def test_public_catalog_declares_methodological_boundaries() -> None:
    response = client.get("/api/mission-intelligence/demo/missions")
    assert response.status_code == 200
    catalog = response.json()
    assert catalog["catalog_version"] == "2026-08-13"
    program = catalog["missions"]["P-001"]
    m1 = catalog["missions"]["M-001"]
    m2 = catalog["missions"]["M-002"]
    m3 = catalog["missions"]["M-003"]
    m4 = catalog["missions"]["M-004"]
    award = catalog["missions"]["CA-AWARD-APPLICATION"]
    assert program["mission_kind"] == "program"
    assert program["children"] == ["M-002", "M-001", "M-003", "M-004"]
    assert m1["title"] == "Paisagem Resiliente"
    assert m1["parent_id"] == "P-001"
    assert m2["featured_rank"] == 1
    assert m3["parent_id"] == "P-001"
    assert "não clínica" in m4["method_notice"]
    assert "Caso real aberto" in m1["method_notice"]
    assert m1["analysis_requirements"]["context_research"]["required"] is True
    assert "não compromisso" in m2["method_notice"]
    dossier = m2["context_dossier"]
    assert dossier["research_status"] == "preliminary"
    assert {source["source_id"] for source in dossier["sources"]} == {
        "SRC-M002-001",
        "SRC-M002-002",
    }
    medicinal = next(
        claim for claim in dossier["claims"] if claim["claim_id"] == "CLM-M002-004"
    )
    assert medicinal["epistemic_status"] == "unverified"
    assert medicinal["source_ids"] == []
    assert any(
        "utilizada pelos romanos" in claim["statement"]
        for claim in dossier["claims"]
    )
    assert award["status"] == "Submetida · avaliação pendente"
    assert award["analysis_requirements"]["context_research"]["required"] is True
    assert "sris-production.up.railway.app" in award["analysis"]["context"]
    assert "sris-staging.up.railway.app" in award["analysis"]["context"]
    assert "não existe ainda decisão do júri" in award["method_notice"]


def test_completed_application_uses_its_own_decision_chain() -> None:
    response = client.post(
        "/api/mission-intelligence/demo/missions/CA-AWARD-APPLICATION/analyze",
        json=_analysis_payload(),
    )
    assert response.status_code == 200, response.text
    report = response.json()["deterministic"]
    gap_codes = {gap["code"] for gap in report["gaps"]}
    factors = {item["factor"]: item for item in report["confidence_factors"]}
    assert report["mission_status"] == "requires_attention"
    assert report["decision_confidence"] == "high"
    assert report["counts"]["alternative"] == 3
    assert len(report["alternatives"]) == 3
    assert report["counts"]["decision"] == 1
    assert report["counts"]["action"] == 1
    assert factors["assumptions"]["assessment"] == "not_applicable"
    assert factors["constraints"]["assessment"] == "not_applicable"
    assert factors["alternatives"]["assessment"] == "strong"
    assert "2 rejeitadas" in factors["alternatives"]["explanation"]
    assert "MI-NO-BASELINE" not in gap_codes
    assert "MI-NO-ALTERNATIVES" not in gap_codes
    assert "MI-CONTEXT-NOT-RESEARCHED" in gap_codes
    assert factors["context_coverage"]["assessment"] == "weak"
    rendered = str(
        {
            "risk": report["principal_risk"],
            "next": report["next_decision"],
            "gaps": report["gaps"],
            "non_inferences": report["non_inferences"],
        }
    ).casefold()
    assert "linha de base" not in rendered
    assert "intervir antes de medir" not in rendered


def test_authenticated_run_is_persisted_versioned_and_human_reviewed() -> None:
    headers, organization_id = _owner()
    endpoint = f"/api/organizations/{organization_id}/mission-intelligence/demo/M-001/analyze"
    first = client.post(endpoint, headers=headers, json=_analysis_payload(use_ai=True))
    assert first.status_code == 200, first.text
    first_data = first.json()
    assert first_data["ai_status"] == "not_configured"
    assert first_data["review_allowed"] is True
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


def test_context_research_requires_ai_and_prepares_governed_web_search() -> None:
    with pytest.raises(ValidationError, match="Context research requires governed AI"):
        AnalysisInput(research_context=True)

    document, deterministic = _canonical_analysis("M-002")
    prepared = mission_ai.prepare_ai_request(
        document,
        deterministic,
        research_context=True,
    )
    assert prepared.response_model is AIResearchBundle
    assert prepared.research_context is True
    assert prepared.max_output_tokens == 6_000
    assert prepared.tools == (
        {
            "type": "web_search",
            "external_web_access": True,
        },
    )
    assert prepared.tool_choice == "required"
    assert prepared.max_tool_calls == 6
    assert prepared.include == ("web_search_call.action.sources",)
    assert prepared.reasoning_effort == "medium"
    assert prepared.text_config["format"]["name"] == "AIResearchBundle"

    policy_capped = mission_ai.prepare_ai_request(
        document,
        deterministic,
        max_output_tokens=3_000,
        research_context=True,
    )
    assert policy_capped.max_output_tokens == 3_000


def test_context_research_accepts_only_retrieved_sources_and_stays_in_review(
    monkeypatch,
) -> None:
    document, deterministic = _canonical_analysis("M-002")
    bundle = _research_bundle(document)
    captured: dict = {}

    class FakeResponse:
        id = "resp_context_research"
        model = "gpt-5.6"
        output_parsed = bundle
        usage = {
            "input_tokens": 1_000,
            "output_tokens": 500,
            "total_tokens": 1_500,
            "input_tokens_details": {"cached_tokens": 0},
        }

        def model_dump(self, **_kwargs):
            return {
                "output": [
                    {
                        "type": "web_search_call",
                        "action": {
                            "sources": [
                                {"url": "https://example.gov.pt/dragos-study"},
                                {"url": "https://example.edu.pt/dragos-archaeology"},
                            ],
                            "query": "Dragos nascente arqueologia hidrogeologia",
                        },
                    }
                ]
            }

    class FakeResponses:
        def parse(self, **kwargs):
            captured.update(kwargs)
            return FakeResponse()

    class FakeOpenAI:
        responses = FakeResponses()

        def __init__(self, **_kwargs):
            pass

    monkeypatch.setattr(mission_ai, "is_ai_configured", lambda: True)
    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    execution = mission_ai.analyze_with_openai(
        document,
        deterministic,
        research_context=True,
    )
    assert execution.context_dossier == bundle.context_dossier
    assert execution.context_dossier.research_status == "in_review"
    assert execution.web_search_calls == 1
    assert execution.search_queries == (
        "Dragos nascente arqueologia hidrogeologia",
    )
    assert execution.prompt_version == "sris-mi-context-research-1.0"
    assert captured["tool_choice"] == "required"
    assert captured["max_tool_calls"] == 6
    assert captured["include"] == ["web_search_call.action.sources"]
    assert captured["text_format"] is AIResearchBundle
    assert captured["reasoning"] == {"effort": "medium"}


def test_openai_sdk_serializes_the_context_research_contract() -> None:
    document, deterministic = _canonical_analysis("M-002")
    prepared = mission_ai.prepare_ai_request(
        document,
        deterministic,
        research_context=True,
    )
    captured: dict = {}

    def reject_after_capture(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            400,
            request=request,
            json={
                "error": {
                    "message": "contract captured",
                    "type": "invalid_request_error",
                    "param": None,
                    "code": None,
                }
            },
        )

    http_client = httpx.Client(transport=httpx.MockTransport(reject_after_capture))
    sdk = OpenAI(
        api_key="sk-test",
        base_url="https://api.openai.invalid/v1",
        http_client=http_client,
        max_retries=0,
    )
    with pytest.raises(BadRequestError, match="contract captured"):
        sdk.responses.parse(
            model=prepared.model,
            instructions=prepared.instructions,
            input=prepared.input_text,
            text_format=prepared.response_model,
            reasoning={"effort": prepared.reasoning_effort},
            max_output_tokens=prepared.max_output_tokens,
            store=False,
            tools=list(prepared.tools),
            tool_choice=prepared.tool_choice,
            include=list(prepared.include),
            max_tool_calls=prepared.max_tool_calls,
        )
    assert captured["tools"] == [
        {"type": "web_search", "external_web_access": True}
    ]
    assert captured["tool_choice"] == "required"
    assert captured["max_tool_calls"] == 6
    assert captured["include"] == ["web_search_call.action.sources"]
    assert captured["reasoning"] == {"effort": "medium"}
    assert captured["text"]["format"]["type"] == "json_schema"
    assert captured["text"]["format"]["strict"] is True


def test_context_research_rejects_a_source_not_retrieved_in_that_execution(
    monkeypatch,
) -> None:
    document, deterministic = _canonical_analysis("M-002")
    bundle = _research_bundle(document)

    class FakeResponse:
        id = "resp_context_bad_source"
        model = "gpt-5.6"
        output_parsed = bundle
        usage = {
            "input_tokens": 1_000,
            "output_tokens": 500,
            "total_tokens": 1_500,
        }

        def model_dump(self, **_kwargs):
            return {
                "output": [
                    {
                        "type": "web_search_call",
                        "action": {
                            "sources": [
                                {"url": "https://example.gov.pt/different-source"}
                            ]
                        },
                    }
                ]
            }

    class FakeResponses:
        def parse(self, **_kwargs):
            return FakeResponse()

    class FakeOpenAI:
        responses = FakeResponses()

        def __init__(self, **_kwargs):
            pass

    monkeypatch.setattr(mission_ai, "is_ai_configured", lambda: True)
    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    with pytest.raises(AIUnavailableError, match="sources not retrieved") as blocked:
        mission_ai.analyze_with_openai(
            document,
            deterministic,
            research_context=True,
        )
    assert blocked.value.failure_code == "provider_output_invalid"
    assert blocked.value.web_search_calls == 1


def test_context_research_rejects_a_structurally_shallow_dossier(
    monkeypatch,
) -> None:
    document, deterministic = _canonical_analysis("M-002")
    complete = _research_bundle(document)
    shallow_dossier = complete.context_dossier.model_copy(
        update={
            "domains": complete.context_dossier.domains[:1],
            "sources": complete.context_dossier.sources[:1],
            "claims": complete.context_dossier.claims[:1],
            "gaps": complete.context_dossier.gaps[:1],
        }
    )
    shallow = complete.model_copy(update={"context_dossier": shallow_dossier})

    class FakeResponse:
        id = "resp_context_shallow"
        model = "gpt-5.6"
        output_parsed = shallow
        usage = {
            "input_tokens": 1_000,
            "output_tokens": 300,
            "total_tokens": 1_300,
        }

        def model_dump(self, **_kwargs):
            return {
                "output": [
                    {
                        "type": "web_search_call",
                        "action": {
                            "query": "Dragos",
                            "sources": [
                                {"url": "https://example.gov.pt/dragos-study"}
                            ],
                        },
                    }
                ]
            }

    class FakeResponses:
        def parse(self, **_kwargs):
            return FakeResponse()

    class FakeOpenAI:
        responses = FakeResponses()

        def __init__(self, **_kwargs):
            pass

    monkeypatch.setattr(mission_ai, "is_ai_configured", lambda: True)
    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    with pytest.raises(AIUnavailableError, match="minimum depth contract") as blocked:
        mission_ai.analyze_with_openai(
            document,
            deterministic,
            research_context=True,
        )
    assert blocked.value.failure_code == "provider_output_too_shallow"
    assert blocked.value.web_search_calls == 1


def test_interactive_contract_for_m001_adds_real_decision_intelligence() -> None:
    document, deterministic = _canonical_analysis("M-001")
    output = _interactive_output(document)
    request = interactive_ai.prepare_interactive_request(
        document,
        deterministic,
        intent=MIInteractionIntent.DIAGNOSE,
        message="Interage com esta missão e acrescenta inteligência útil.",
        answers=[],
        history=[],
        proposal_reviews=[],
    )

    assert issubclass(request.response_model, MIInteractiveOutput)
    assert request.reasoning_effort == "medium"
    assert "Não és um redator de" in request.instructions
    assert "Podes criar hipóteses, alternativas, critérios e experiências" in (
        request.instructions
    )
    assert "minimum_output_counts" in request.input_text
    schema = request.response_model.model_json_schema()
    assert schema["properties"]["questions"]["minItems"] == 3
    assert schema["properties"]["hypotheses"]["minItems"] == 2
    assert schema["properties"]["decision_criteria"]["minItems"] == 3
    assert interactive_ai._quality_failures(
        output,
        MIInteractionIntent.DIAGNOSE,
    ) == []
    assert len(output.questions) == 3
    assert len(output.hypotheses) == 2
    assert len(output.alternative_proposals) == 1
    assert len(output.decision_criteria) == 3
    assert len(output.experiment_proposals) == 1
    assert output.boundary.facts_added is False
    assert output.boundary.human_review_required is True


def test_interactive_provider_schema_enforces_each_intent_quality_minimum() -> None:
    document, deterministic = _canonical_analysis("M-001")

    for intent, minimums in interactive_ai.INTERACTION_MINIMUMS.items():
        request = interactive_ai.prepare_interactive_request(
            document,
            deterministic,
            intent=intent,
            message="Executa o trabalho cognitivo pedido.",
            answers=[],
            history=[],
            proposal_reviews=[],
        )
        schema = request.response_model.model_json_schema()
        payload = json.loads(request.input_text)

        assert payload["requested_turn"]["minimum_output_counts"] == minimums
        for field_name, minimum in minimums.items():
            assert schema["properties"][field_name]["minItems"] == minimum


def test_interactive_research_schema_enforces_nested_quality_minimums() -> None:
    document, deterministic = _canonical_analysis("M-001")
    request = interactive_ai.prepare_interactive_request(
        document,
        deterministic,
        intent=MIInteractionIntent.DIAGNOSE,
        message="Diagnostica a missão com investigação contextual.",
        answers=[],
        history=[],
        proposal_reviews=[],
        research_context=True,
    )
    schema = request.response_model.model_json_schema()
    intelligence_ref = schema["properties"]["intelligence"]["$ref"]
    intelligence_schema = schema["$defs"][intelligence_ref.rsplit("/", 1)[-1]]

    assert issubclass(request.response_model, MIInteractiveResearchBundle)
    assert intelligence_schema["properties"]["questions"]["minItems"] == 3
    assert intelligence_schema["properties"]["hypotheses"]["minItems"] == 2
    assert intelligence_schema["properties"]["decision_criteria"]["minItems"] == 3


def test_interactive_provider_schema_rejects_shallow_diagnosis_before_quality_gate(
) -> None:
    document, deterministic = _canonical_analysis("M-001")
    request = interactive_ai.prepare_interactive_request(
        document,
        deterministic,
        intent=MIInteractionIntent.DIAGNOSE,
        message="Diagnostica a missão.",
        answers=[],
        history=[],
        proposal_reviews=[],
    )
    shallow = _interactive_output(document).model_dump(mode="json")
    shallow["questions"] = shallow["questions"][:2]
    shallow["decision_criteria"] = shallow["decision_criteria"][:2]

    with pytest.raises(ValidationError) as blocked:
        request.response_model.model_validate(shallow)

    errors = {item["loc"][0] for item in blocked.value.errors()}
    assert {"questions", "decision_criteria"}.issubset(errors)


def test_interactive_m001_domain_eval_preserves_epistemic_and_decision_boundaries(
) -> None:
    rubric = json.loads(
        (
            Path(__file__).parent
            / "fixtures"
            / "mission_intelligence_m001_eval.json"
        ).read_text(encoding="utf-8")
    )
    document, _deterministic = _canonical_analysis(rubric["mission_code"])
    output = _interactive_output(document, MIInteractionIntent(rubric["intent"]))

    for field, minimum in rubric["minimum_counts"].items():
        assert len(getattr(output, field)) >= minimum

    referenced = set(output.mission_reading.based_on_ids)
    for group in (
        output.questions,
        output.hypotheses,
        output.alternative_proposals,
        output.decision_criteria,
        output.experiment_proposals,
        output.challenges,
        output.recommended_actions,
    ):
        for item in group:
            referenced.update(item.based_on_ids)
    assert set(rubric["required_canonical_anchors"]).issubset(referenced)

    rendered = json.dumps(output.model_dump(mode="json"), ensure_ascii=False).casefold()
    for theme in rubric["required_operational_themes"]:
        assert theme.casefold() in rendered
    for prohibited in rubric["prohibited_claims"]:
        assert prohibited.casefold() not in rendered

    boundaries = rubric["required_boundaries"]
    assert output.boundary.facts_added is boundaries["facts_added"]
    assert (
        output.boundary.human_review_required
        is boundaries["human_review_required"]
    )
    assert output.boundary.canonical_mutation == boundaries["canonical_mutation"]
    assert rubric["decision_selection_allowed"] is False


def test_interactive_quality_gate_rejects_a_report_shaped_diagnosis() -> None:
    document, _deterministic = _canonical_analysis("M-001")
    complete = _interactive_output(document)
    shallow = complete.model_copy(
        update={
            "questions": [],
            "hypotheses": [],
            "alternative_proposals": [],
            "decision_criteria": [],
            "experiment_proposals": [],
            "challenges": [],
            "recommended_actions": [],
        }
    )

    failures = interactive_ai._quality_failures(
        shallow,
        MIInteractionIntent.DIAGNOSE,
    )
    assert "questions requires at least 3 item(s)" in failures
    assert "hypotheses requires at least 2 item(s)" in failures
    assert "alternative_proposals requires at least 1 item(s)" in failures
    assert "experiment_proposals requires at least 1 item(s)" in failures


def test_interactive_context_is_compacted_below_the_default_pilot_limit() -> None:
    document, deterministic = _canonical_analysis("M-001")
    intelligence = _interactive_output(document).model_dump(mode="json")
    long_text = "incerteza-á-" * 1_000
    intelligence["direct_answer"]["answer"] = long_text
    intelligence["direct_answer"]["what_changed"] = long_text
    for field in (
        "decision_problem",
        "current_blocker",
        "key_tension",
        "blind_spot",
    ):
        intelligence["mission_reading"][field] = long_text
    for item in intelligence["questions"]:
        item["question"] = long_text
        item["decision_unlocked"] = long_text
    for item in intelligence["hypotheses"]:
        item["statement"] = long_text
    for item in intelligence["alternative_proposals"]:
        item["description"] = long_text
        item["difference_from_existing"] = long_text
    for item in intelligence["decision_criteria"]:
        item["threshold_or_rule"] = long_text
    for item in intelligence["experiment_proposals"]:
        item["question"] = long_text
        item["success_or_decision_rules"] = [long_text] * 10
    for item in intelligence["challenges"]:
        item["objection"] = long_text
    intelligence["recommended_next_move"] = long_text

    history = [
        {
            "sequence": sequence,
            "intent": "diagnose",
            "user_message": long_text,
            "answers": [
                {"question_id": f"Q-{index}", "answer": long_text}
                for index in range(12)
            ],
            "intelligence": intelligence,
        }
        for sequence in range(1, 11)
    ]
    reviews = [
        {
            "proposal_id": f"ALT-AI-{index}",
            "proposal_type": "alternative",
            "decision": "deferred",
            "comment": long_text,
        }
        for index in range(50)
    ]
    request = interactive_ai.prepare_interactive_request(
        document,
        deterministic,
        intent=MIInteractionIntent.DIAGNOSE,
        message="Mantém o diagnóstico vivo.",
        answers=[],
        history=history,
        proposal_reviews=reviews,
        research_context=True,
    )
    prompt_payload = json.loads(request.input_text)

    assert prompt_payload["recent_dialogue"][-1]["sequence"] == 10
    assert len(prompt_payload["recent_dialogue"]) <= interactive_ai.MAX_HISTORY_TURNS
    assert (
        len(
            json.dumps(
                prompt_payload["recent_dialogue"],
                ensure_ascii=False,
            ).encode("utf-8")
        )
        <= interactive_ai.MAX_HISTORY_BYTES
    )
    assert (
        len(
            json.dumps(
                prompt_payload["human_proposal_reviews"],
                ensure_ascii=False,
            ).encode("utf-8")
        )
        <= interactive_ai.MAX_REVIEW_BYTES
    )
    assert request.max_output_tokens == 6_000
    assert mission_ai.conservative_input_token_reservation(request) <= 60_000


def test_interactive_provider_rejects_unknown_canonical_references(monkeypatch) -> None:
    document, deterministic = _canonical_analysis("M-001")
    invalid_payload = _interactive_output(document).model_dump(mode="json")
    invalid_payload["mission_reading"]["based_on_ids"] = ["OBS-INVENTED"]
    invalid = MIInteractiveOutput.model_validate(invalid_payload)

    class FakeResponse:
        id = "resp_interactive_invalid"
        model = "gpt-5.6"
        usage = {
            "input_tokens": 1_000,
            "output_tokens": 500,
            "total_tokens": 1_500,
            "input_tokens_details": {"cached_tokens": 0},
        }
        output_parsed = invalid

    class FakeResponses:
        def parse(self, **_kwargs):
            return FakeResponse()

    class FakeOpenAI:
        responses = FakeResponses()

        def __init__(self, **_kwargs):
            pass

    monkeypatch.setattr(interactive_ai, "is_ai_configured", lambda: True)
    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    with pytest.raises(AIUnavailableError, match="unknown canonical IDs") as blocked:
        interactive_ai.analyze_interactively(
            document,
            deterministic,
            intent=MIInteractionIntent.DIAGNOSE,
            message="Diagnostica.",
            answers=[],
            history=[],
            proposal_reviews=[],
        )
    assert blocked.value.failure_code == "provider_output_invalid"
    assert blocked.value.provider_response_id == "resp_interactive_invalid"


def test_interactive_research_validates_and_returns_a_retrieved_context_dossier(
    monkeypatch,
) -> None:
    document, deterministic = _canonical_analysis("M-002")
    research = _research_bundle(document)
    parsed = MIInteractiveResearchBundle(
        context_dossier=research.context_dossier,
        intelligence=_interactive_output(document),
    )

    class FakeResponse:
        id = "resp_interactive_research"
        model = "gpt-5.6"
        output_parsed = parsed
        usage = {
            "input_tokens": 1_500,
            "output_tokens": 900,
            "total_tokens": 2_400,
            "input_tokens_details": {"cached_tokens": 0},
        }

        def model_dump(self, **_kwargs):
            return {
                "output": [
                    {
                        "type": "web_search_call",
                        "action": {
                            "query": "Dragos enquadramento oficial e arqueológico",
                            "sources": [
                                {"url": source.url}
                                for source in research.context_dossier.sources
                            ],
                        },
                    }
                ]
            }

    class FakeResponses:
        def parse(self, **_kwargs):
            return FakeResponse()

    class FakeOpenAI:
        responses = FakeResponses()

        def __init__(self, **_kwargs):
            pass

    monkeypatch.setattr(interactive_ai, "is_ai_configured", lambda: True)
    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    execution = interactive_ai.analyze_interactively(
        document,
        deterministic,
        intent=MIInteractionIntent.DIAGNOSE,
        message="Investiga a envolvente e atualiza as hipóteses.",
        answers=[],
        history=[],
        proposal_reviews=[],
        research_context=True,
    )

    assert execution.context_dossier == research.context_dossier
    assert execution.intelligence.intent == MIInteractionIntent.DIAGNOSE
    assert execution.web_search_calls == 1
    assert execution.search_queries == (
        "Dragos enquadramento oficial e arqueológico",
    )


def test_interactive_experiment_must_target_an_actual_hypothesis() -> None:
    document, _deterministic = _canonical_analysis("M-001")
    payload = _interactive_output(document).model_dump(mode="json")
    observation_id = next(
        record.canonical_id
        for record in document.records
        if record.kind.value == "observation"
    )
    payload["experiment_proposals"][0]["target_hypothesis_ids"] = [observation_id]
    output = MIInteractiveOutput.model_validate(payload)

    with pytest.raises(
        AIUnavailableError,
        match="unknown or non-hypothesis IDs",
    ):
        interactive_ai._validate_references(output, document)


def test_interactive_dialogue_persists_turns_and_reviews_proposals_individually(
    monkeypatch,
) -> None:
    suffix = f"interactive-{uuid4().hex[:8]}"
    headers, organization_id = _owner_named(suffix)
    endpoint = (
        f"/api/organizations/{organization_id}/mission-intelligence/demo/M-001/interact"
    )
    monkeypatch.setattr(dialogue_service, "is_ai_configured", lambda: True)
    monkeypatch.setattr(mission_api, "is_ai_configured", lambda: True)
    monkeypatch.setattr(
        dialogue_service,
        "count_openai_input_tokens",
        lambda _request: 1_200,
    )
    captured_history_lengths: list[int] = []

    def fake_provider(document, _deterministic, **kwargs):
        captured_history_lengths.append(len(kwargs["history"]))
        return MIInteractiveExecution(
            intelligence=_interactive_output(document, kwargs["intent"]),
            provider="openai",
            model="gpt-5.6",
            provider_response_id=f"resp_interactive_{len(captured_history_lengths)}",
            usage=AIProviderUsage(
                input_tokens=1_200,
                cached_input_tokens=100,
                output_tokens=1_000,
                total_tokens=2_200,
            ),
        )

    monkeypatch.setattr(dialogue_service, "analyze_interactively", fake_provider)

    policy = client.put(
        f"/api/organizations/{organization_id}/mission-intelligence/ai-governance/policy",
        headers=headers,
        json={
            "enabled": True,
            "monthly_request_limit": 5,
            "monthly_input_token_limit": 500_000,
            "monthly_output_token_limit": 50_000,
            "monthly_budget_usd": "2.00",
            "per_request_input_token_limit": 100_000,
            "per_request_output_token_limit": 6_000,
            "max_concurrent_requests": 1,
        },
    )
    assert policy.status_code == 200, policy.text
    assert policy.json()["ready"] is True

    mission_input = _analysis_payload(use_ai=False, research_context=False)
    first = client.post(
        endpoint,
        headers=headers,
        json={
            "intent": "diagnose",
            "message": "Diagnostica e cria hipóteses, alternativas e um teste.",
            "answers": [],
            "mission_input": mission_input,
            "research_context": False,
        },
    )
    assert first.status_code == 200, first.text
    first_data = first.json()
    assert first_data["schema_version"] == "2.0"
    assert first_data["ai_status"] == "completed"
    assert first_data["execution_mode"] == "interactive"
    assert first_data["intelligence"]["response_version"] == "2.0"
    assert first_data["intelligence"]["alternative_proposals"][0][
        "epistemic_status"
    ] == "alternative_proposal"
    assert first_data["canonical_mutation"] == "none"
    assert first_data["ai_usage"]["intelligence_run_id"] == first_data["run_id"]
    assert captured_history_lengths == [0]

    review_url = (
        f"/api/organizations/{organization_id}/mission-intelligence/dialogues/"
        f"{first_data['session_id']}/turns/{first_data['turn_id']}/proposals/"
        "ALT-AI-001/review"
    )
    reviewed = client.put(
        review_url,
        headers=headers,
        json={
            "decision": "accepted_as_draft",
            "comment": "Alternativa relevante para desenvolver, ainda não validada.",
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["decision"] == "accepted_as_draft"
    assert reviewed.json()["canonical_effect"] == "none"

    second = client.post(
        endpoint,
        headers=headers,
        json={
            "session_id": first_data["session_id"],
            "intent": "answer",
            "message": "Atualiza o diagnóstico com esta resposta.",
            "answers": [
                {
                    "question_id": "Q-AI-002",
                    "answer": "Ainda não existe autorização escrita.",
                }
            ],
            "mission_input": mission_input,
            "research_context": False,
        },
    )
    assert second.status_code == 200, second.text
    second_data = second.json()
    assert second_data["turn_sequence"] == 2
    assert second_data["intelligence"]["intent"] == "answer"
    assert captured_history_lengths == [0, 1]

    changed_input = deepcopy(mission_input)
    changed_input["context"] += " Nova revisão humana posterior ao diálogo."
    canonical_change = client.post(
        f"/api/organizations/{organization_id}/mission-intelligence/demo/M-001/analyze",
        headers=headers,
        json=changed_input,
    )
    assert canonical_change.status_code == 200, canonical_change.text
    missions_before_conflict = client.get(
        f"/api/organizations/{organization_id}/mission-intelligence/missions",
        headers=headers,
    ).json()
    changed_mission = next(item for item in missions_before_conflict if item["code"] == "M-001")
    assert changed_mission["revision"] == 2

    stale_resume = client.post(
        endpoint,
        headers=headers,
        json={
            "session_id": first_data["session_id"],
            "intent": "answer",
            "message": "Tenta continuar sobre o snapshot anterior.",
            "answers": [],
            "mission_input": mission_input,
            "research_context": False,
        },
    )
    assert stale_resume.status_code == 409, stale_resume.text
    assert stale_resume.json()["detail"]["code"] == "mission_snapshot_changed"
    assert captured_history_lengths == [0, 1]
    missions_after_conflict = client.get(
        f"/api/organizations/{organization_id}/mission-intelligence/missions",
        headers=headers,
    ).json()
    preserved_mission = next(item for item in missions_after_conflict if item["code"] == "M-001")
    assert preserved_mission["revision"] == 2
    assert preserved_mission["content_hash"] == changed_mission["content_hash"]

    dialogue = client.get(
        f"/api/organizations/{organization_id}/mission-intelligence/dialogues/{first_data['session_id']}",
        headers=headers,
    )
    assert dialogue.status_code == 200, dialogue.text
    assert len(dialogue.json()["turns"]) == 2
    assert dialogue.json()["turns"][0]["proposal_reviews"][0][
        "canonical_effect"
    ] == "none"


def test_failed_interactive_turn_remains_visible_in_session_history(monkeypatch) -> None:
    suffix = f"interactive-failure-{uuid4().hex[:8]}"
    headers, organization_id = _owner_named(suffix)
    endpoint = (
        f"/api/organizations/{organization_id}/mission-intelligence/demo/M-001/interact"
    )
    monkeypatch.setattr(dialogue_service, "is_ai_configured", lambda: True)
    monkeypatch.setattr(mission_api, "is_ai_configured", lambda: True)
    monkeypatch.setattr(
        dialogue_service,
        "count_openai_input_tokens",
        lambda _request: 1_200,
    )

    policy = client.put(
        f"/api/organizations/{organization_id}/mission-intelligence/ai-governance/policy",
        headers=headers,
        json={
            "enabled": True,
            "monthly_request_limit": 5,
            "monthly_input_token_limit": 500_000,
            "monthly_output_token_limit": 50_000,
            "monthly_budget_usd": "2.00",
            "per_request_input_token_limit": 100_000,
            "per_request_output_token_limit": 6_000,
            "max_concurrent_requests": 1,
        },
    )
    assert policy.status_code == 200, policy.text

    def reject_provider(*_args, **_kwargs):
        raise AIUnavailableError(
            "The provider response failed the interactive quality contract",
            failure_code="provider_output_invalid",
            provider_response_id="resp_interactive_rejected",
            usage=AIProviderUsage(
                input_tokens=1_200,
                cached_input_tokens=0,
                output_tokens=700,
                total_tokens=1_900,
            ),
        )

    monkeypatch.setattr(dialogue_service, "analyze_interactively", reject_provider)
    response = client.post(
        endpoint,
        headers=headers,
        json={
            "intent": "diagnose",
            "message": "Diagnostica a missão sem ocultar falhas do fornecedor.",
            "answers": [],
            "mission_input": _analysis_payload(
                use_ai=False,
                research_context=False,
            ),
            "research_context": False,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ai_status"] == "failed"
    assert data["session_id"]
    assert data["turn_id"]
    assert data["ai_error"] == (
        "The provider response failed the interactive quality contract"
    )
    assert data["ai_usage"]["failure_code"] == "provider_output_invalid"

    historical = client.get(
        f"/api/organizations/{organization_id}/mission-intelligence/dialogues/{data['session_id']}",
        headers=headers,
    )
    assert historical.status_code == 200, historical.text
    turn = historical.json()["turns"][0]
    assert turn["ai_status"] == "failed"
    assert turn["ai_error"] == data["ai_error"]
    assert turn["ai_usage"]["failure_code"] == "provider_output_invalid"
    assert turn["user_message"] == (
        "Diagnostica a missão sem ocultar falhas do fornecedor."
    )


def test_frontend_and_openapi_expose_the_new_capability() -> None:
    frontend = client.get("/")
    assert frontend.status_code == 200
    assert "UI-R2 · MI-1" in frontend.text
    assert "Iniciar Mission Intelligence" in frontend.text
    assert "Mission Intelligence v2" in frontend.text
    assert "Pensar com a missão, não apenas escrever sobre ela" in frontend.text
    assert "data-mi-intent=\"design_experiment\"" in frontend.text
    assert "data-mi-review=\"accepted_as_draft\"" in frontend.text
    assert "Fronteira canónica" in frontend.text
    assert '${result.context_dossier?renderContextDossier(result):""}' in frontend.text
    assert "aiGovernanceStatus?.organization_authorized" in frontend.text
    assert "Proposta de investigação" in frontend.text
    assert "Fundamentação declarada" in frontend.text
    assert "data-review-decision" in frontend.text
    assert "Decision Confidence" not in frontend.text
    assert 'id="analysisMode" class="analysis-mode is-unavailable hidden"' in frontend.text
    assert 'id="analysisResearch" type="checkbox" disabled' in frontend.text
    assert "contextRequired=mission(activeMissionId)" in frontend.text
    assert "renderContextDossier(result)" in frontend.text
    assert "web_search_cost_usd" in frontend.text
    assert "demonstração pública do" in frontend.text
    assert "demonstração preparada para o" not in frontend.text
    assert "Importar visualização" in frontend.text
    assert "async function refreshAIGovernanceStatus(token)" in frontend.text
    assert "async function recoverLatestDialogueSession(missionId)" in frontend.text
    assert "result.ai_usage?.failure_code" in frontend.text
    submit_dialogue = frontend.text.split(
        "async function submitMIDialogue()", 1
    )[1].split("function renderAll()", 1)[0]
    assert "await refreshAIGovernanceStatus(token);" in submit_dialogue
    assert "await loadSessionContext(token);" not in submit_dialogue
    assert "if(data.session_id&&data.turn_id)" in submit_dialogue

    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    assert spec.json()["info"]["title"] == "SRIS Mission Intelligence API"
    assert spec.json()["info"]["version"] == "1.6.0"
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
    interact_path = (
        "/api/organizations/{organization_id}/mission-intelligence/"
        "demo/{mission_code}/interact"
    )
    dialogue_path = (
        "/api/organizations/{organization_id}/mission-intelligence/"
        "dialogues/{session_id}"
    )
    proposal_review_path = dialogue_path + (
        "/turns/{turn_id}/proposals/{proposal_id}/review"
    )
    assert interact_path in spec.json()["paths"]
    assert dialogue_path in spec.json()["paths"]
    assert proposal_review_path in spec.json()["paths"]


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


def test_governed_context_research_accounts_for_search_and_persists_the_dossier(
    monkeypatch,
) -> None:
    headers, organization_id = _owner_named("context-research")
    endpoint = (
        f"/api/organizations/{organization_id}/mission-intelligence/demo/M-002/analyze"
    )
    monkeypatch.setattr(service, "is_ai_configured", lambda: True)
    monkeypatch.setattr(service, "is_context_research_configured", lambda: True)
    monkeypatch.setattr(service, "count_openai_input_tokens", lambda _request: 1_000)
    monkeypatch.setattr(mission_api, "is_ai_configured", lambda: True)

    policy = client.put(
        f"/api/organizations/{organization_id}/mission-intelligence/ai-governance/policy",
        headers=headers,
        json={
            "enabled": True,
            "monthly_request_limit": 5,
            "monthly_input_token_limit": 500_000,
            "monthly_output_token_limit": 50_000,
            "monthly_budget_usd": "1.00",
            "per_request_input_token_limit": 200_000,
            "per_request_output_token_limit": 6_000,
            "max_concurrent_requests": 1,
        },
    )
    assert policy.status_code == 200, policy.text

    captured: dict = {}

    def fake_provider(document, _deterministic, **kwargs):
        captured.update(kwargs)
        bundle = _research_bundle(document)
        return AIExecution(
            advisory=bundle.advisory,
            provider="openai",
            model="gpt-5.6",
            provider_response_id="resp_context_governed",
            usage=AIProviderUsage(
                input_tokens=1_000,
                cached_input_tokens=0,
                output_tokens=500,
                total_tokens=1_500,
            ),
            prompt_version="sris-mi-context-research-1.0",
            context_dossier=bundle.context_dossier,
            web_search_calls=2,
        )

    monkeypatch.setattr(service, "analyze_with_openai", fake_provider)
    response = client.post(
        endpoint,
        headers=headers,
        json=_analysis_payload(use_ai=True, research_context=True),
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["execution_mode"] == "hybrid"
    assert data["ai_status"] == "completed"
    assert data["ai_governance"]["reserved_web_search_calls"] == 6
    assert data["context_dossier"]["research_status"] == "in_review"
    assert data["context_dossier_provenance"]["origin_type"] == (
        "ai_model_with_web_search"
    )
    assert data["ai"]["context_dossier"] == data["context_dossier"]
    assert data["ai_usage"]["web_search_calls"] == 2
    assert data["ai_usage"]["web_search_cost_usd"] == "0.020000"
    assert data["ai_usage"]["estimated_cost_usd"] == "0.040000"
    assert captured["research_context"] is True
    assert captured["prepared_request"].max_output_tokens == 6_000

    historical = client.get(
        f"/api/organizations/{organization_id}/mission-intelligence/runs/{data['run_id']}",
        headers=headers,
    )
    assert historical.status_code == 200, historical.text
    assert historical.json()["context_dossier"] == data["context_dossier"]

    usage = client.get(
        f"/api/organizations/{organization_id}/mission-intelligence/ai-governance",
        headers=headers,
    )
    assert usage.status_code == 200
    period = usage.json()["current_period"]
    assert period["web_search_calls"] == 2
    assert period["reserved_web_search_calls"] == 0
    assert period["estimated_cost_usd"] == "0.040000"


def test_rejected_context_output_still_charges_observed_searches(monkeypatch) -> None:
    headers, organization_id = _owner_named("context-rejected")
    monkeypatch.setattr(service, "is_ai_configured", lambda: True)
    monkeypatch.setattr(service, "is_context_research_configured", lambda: True)
    monkeypatch.setattr(service, "count_openai_input_tokens", lambda _request: 1_000)

    policy = client.put(
        f"/api/organizations/{organization_id}/mission-intelligence/ai-governance/policy",
        headers=headers,
        json={
            "enabled": True,
            "monthly_request_limit": 5,
            "monthly_input_token_limit": 500_000,
            "monthly_output_token_limit": 50_000,
            "monthly_budget_usd": "1.00",
            "per_request_input_token_limit": 200_000,
            "per_request_output_token_limit": 6_000,
            "max_concurrent_requests": 1,
        },
    )
    assert policy.status_code == 200, policy.text

    def reject_provider(*_args, **_kwargs):
        raise AIUnavailableError(
            "Context research cited sources not retrieved in this execution",
            failure_code="provider_output_invalid",
            provider_response_id="resp_context_rejected",
            usage=AIProviderUsage(
                input_tokens=1_000,
                cached_input_tokens=0,
                output_tokens=500,
                total_tokens=1_500,
            ),
            web_search_calls=2,
        )

    monkeypatch.setattr(service, "analyze_with_openai", reject_provider)
    response = client.post(
        f"/api/organizations/{organization_id}/mission-intelligence/demo/M-002/analyze",
        headers=headers,
        json=_analysis_payload(use_ai=True, research_context=True),
    )
    assert response.status_code == 200, response.text
    usage = response.json()["ai_usage"]
    assert response.json()["ai_status"] == "failed"
    assert usage["status"] == "provider_output_rejected"
    assert usage["failure_code"] == "provider_output_invalid"
    assert usage["web_search_calls"] == 2
    assert usage["web_search_cost_usd"] == "0.020000"
    assert usage["estimated_cost_usd"] == "0.040000"


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

    interactive = client.post(
        f"/api/organizations/{organization_id}/mission-intelligence/demo/M-001/interact",
        headers=headers,
        json={
            "intent": "diagnose",
            "message": "Tenta iniciar um diálogo com consumo de IA.",
            "answers": [],
            "mission_input": _analysis_payload(
                use_ai=False,
                research_context=False,
            ),
            "research_context": False,
        },
    )
    assert interactive.status_code == 403


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

    _owner_named(suffix)
    monkeypatch.setenv("SRIS_PASSWORD_RECOVERY_EMAIL", email)
    monkeypatch.setenv("SRIS_PASSWORD_RECOVERY_TOKEN", recovery_token)

    wrong_token = dict(request, recovery_token="b" * 64)
    assert client.post(endpoint, json=wrong_token).status_code == 404

    # Credential recovery is deliberately independent from the separate AI
    # authorization UUID. A stale or missing pilot UUID must not lock the user
    # out of the account needed to repair that configuration.
    monkeypatch.setenv("SRIS_AI_PILOT_ORGANIZATION_ID", str(uuid4()))
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


def test_emergency_password_recovery_does_not_require_an_organization(
    monkeypatch,
) -> None:
    suffix = uuid4().hex[:8]
    email = f"recovery-only-{suffix}@example.com"
    old_password = "strong-password-123"
    new_password = "new-strong-password-456"
    recovery_token = "c" * 64
    endpoint = "/api/auth/emergency-password-recovery"

    registered = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "full_name": "Recovery Only User",
            "password": old_password,
        },
    )
    assert registered.status_code == 201, registered.text

    monkeypatch.setenv("SRIS_PASSWORD_RECOVERY_EMAIL", email)
    monkeypatch.setenv("SRIS_PASSWORD_RECOVERY_TOKEN", recovery_token)
    monkeypatch.delenv("SRIS_AI_PILOT_ORGANIZATION_ID", raising=False)

    recovered = client.post(
        endpoint,
        json={
            "email": email,
            "recovery_token": recovery_token,
            "new_password": new_password,
        },
    )
    assert recovered.status_code == 200, recovered.text

    new_login = client.post(
        "/api/auth/login",
        json={"email": email, "password": new_password},
    )
    assert new_login.status_code == 200


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


def test_emergency_access_activation_creates_owner_and_is_single_use(
    monkeypatch,
) -> None:
    suffix = uuid4().hex[:8]
    email = f"institutional-owner-{suffix}@example.com"
    password = "institutional-password-123"
    activation_token = "d" * 64
    organization_slug = f"sris-{suffix}"
    endpoint = "/api/auth/emergency-access-activation"
    request = {
        "email": email,
        "activation_token": activation_token,
        "new_password": password,
        "full_name": "Institutional Owner",
        "organization_name": f"SRIS {suffix}",
        "organization_slug": organization_slug,
    }

    monkeypatch.delenv("SRIS_ACCESS_ACTIVATION_EMAIL", raising=False)
    monkeypatch.delenv("SRIS_ACCESS_ACTIVATION_TOKEN", raising=False)
    assert client.post(endpoint, json=request).status_code == 404
    assert endpoint not in client.get("/openapi.json").json()["paths"]

    monkeypatch.setenv("SRIS_ACCESS_ACTIVATION_EMAIL", email)
    monkeypatch.setenv("SRIS_ACCESS_ACTIVATION_TOKEN", activation_token)

    wrong_token = dict(request, activation_token="e" * 64)
    assert client.post(endpoint, json=wrong_token).status_code == 404

    activated = client.post(endpoint, json=request)
    assert activated.status_code == 200, activated.text
    assert activated.json() == {"status": "institutional_access_activated"}

    login = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    assert me.json()["email"] == email
    assert me.json()["full_name"] == "Institutional Owner"

    organizations = client.get("/api/organizations", headers=headers)
    assert organizations.status_code == 200, organizations.text
    organization = next(
        item for item in organizations.json() if item["slug"] == organization_slug
    )
    memberships = client.get(
        f"/api/organizations/{organization['id']}/memberships",
        headers=headers,
    )
    assert memberships.status_code == 200, memberships.text
    assert any(
        row["user_id"] == me.json()["id"] and row["role"] == Role.OWNER.value
        for row in memberships.json()
    )

    replay = client.post(
        endpoint,
        json=dict(request, new_password="replacement-password-456"),
    )
    assert replay.status_code == 409

    original_password_still_works = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert original_password_still_works.status_code == 200


def test_emergency_access_activation_repairs_legacy_password_hash(
    monkeypatch,
) -> None:
    suffix = uuid4().hex[:8]
    email = f"legacy-owner-{suffix}@example.com"
    password = "repaired-password-123"
    activation_token = "f" * 64

    with SessionLocal() as db:
        db.add(
            User(
                email=email,
                full_name="Legacy Owner",
                password_hash="pbkdf2_sha256$legacy$hash",
                is_active=True,
            )
        )
        db.commit()

    invalid_legacy_login = client.post(
        "/api/auth/login",
        json={"email": email, "password": "irrelevant-password"},
    )
    assert invalid_legacy_login.status_code == 401

    monkeypatch.setenv("SRIS_ACCESS_ACTIVATION_EMAIL", email)
    monkeypatch.setenv("SRIS_ACCESS_ACTIVATION_TOKEN", activation_token)
    activated = client.post(
        "/api/auth/emergency-access-activation",
        json={
            "email": email,
            "activation_token": activation_token,
            "new_password": password,
            "full_name": "Repaired Owner",
            "organization_name": f"Repaired SRIS {suffix}",
            "organization_slug": f"repaired-sris-{suffix}",
        },
    )
    assert activated.status_code == 200, activated.text

    repaired_login = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert repaired_login.status_code == 200, repaired_login.text


def test_railway_managed_runtime_closes_public_onboarding_by_default(
    monkeypatch,
) -> None:
    suffix = uuid4().hex[:8]
    email = f"managed-{suffix}@example.com"
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", f"test-{suffix}")
    monkeypatch.delenv("ATLAS_SELF_REGISTRATION_ENABLED", raising=False)

    blocked = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "full_name": "Managed User",
            "password": "strong-password-123",
        },
    )
    assert blocked.status_code == 403

    monkeypatch.setenv("ATLAS_SELF_REGISTRATION_ENABLED", "true")
    explicitly_enabled = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "full_name": "Managed User",
            "password": "strong-password-123",
        },
    )
    assert explicitly_enabled.status_code == 201, explicitly_enabled.text


def test_institutional_activation_script_verifies_full_session_contract() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script = (
        repo_root / "scripts" / "ACTIVATE_SRIS_INSTITUTIONAL_ACCESS.ps1"
    ).read_text(encoding="utf-8")

    assert "/api/auth/emergency-access-activation" in script
    assert "/api/auth/login" in script
    assert "/api/auth/me" in script
    assert "/api/organizations" in script
    assert "/memberships" in script
    assert "ACESSO INSTITUCIONAL CONFIRMADO" in script
    assert "Read-Host \"Cole o token temporario do Railway\" -AsSecureString" in script
    assert "Read-Host \"Defina a nova palavra-passe" in script
    assert "activation_token = $plainToken" in script

    frontend = (repo_root / "frontend" / "atlas-os" / "index.html").read_text(
        encoding="utf-8"
    )
    assert 'fetch("/api/auth/me"' in frontend
    assert '"Demonstração pública"' in frontend
    assert '"Sem sessão institucional"' in frontend
    assert 'openApp({mode:"institutional",...session})' in frontend
    assert 'function openApp(name="Gonçalo Saldanha")' not in frontend


def test_institutional_mission_portfolio_creation_hierarchy_and_analysis() -> None:
    suffix = uuid4().hex[:8]
    headers, organization_id = _owner_named(f"portfolio-{suffix}")
    base = f"/api/organizations/{organization_id}/mission-intelligence"

    program = client.post(
        f"{base}/missions",
        headers=headers,
        json={
            "title": "Território Preparado 2035",
            "objective": "Aumentar a capacidade territorial para antecipar riscos sistémicos.",
            "context": "Programa institucional em estruturação, ainda sem execução ou resultados.",
            "central_question": "Que portefólio de missões reduz vulnerabilidade sem transferir risco?",
            "mission_kind": "program",
            "domain": "territorial_resilience",
            "priority": "critical",
            "horizon": "2026–2035",
            "stakeholders": ["Município", "Universidade", "Comunidade"],
        },
    )
    assert program.status_code == 201, program.text
    program_row = program.json()
    assert program_row["code"] == "PRG-001"
    assert program_row["depth"] == 0
    assert program_row["record_counts"] == {}

    mission = client.post(
        f"{base}/missions",
        headers=headers,
        json={
            "title": "Preparação para incêndios extremos",
            "objective": "Reduzir exposição e melhorar prontidão sem degradar solo e habitat.",
            "context": "Risco territorial a caracterizar com entidades e população local.",
            "central_question": "Que combinação de prevenção e prontidão reduz o risco total?",
            "parent_mission_id": program_row["id"],
            "mission_kind": "mission",
            "domain": "wildfire_landscape",
            "priority": "critical",
        },
    )
    assert mission.status_code == 201, mission.text
    mission_row = mission.json()
    assert mission_row["code"] == "MIS-001"
    assert mission_row["parent_code"] == "PRG-001"
    assert mission_row["depth"] == 1

    child = client.post(
        f"{base}/missions",
        headers=headers,
        json={
            "title": "Rede local de alerta e apoio",
            "objective": "Definir uma experiência reversível de alerta e apoio de proximidade.",
            "context": "Sub-missão ainda sem protocolo, participantes ou dados pessoais.",
            "central_question": "Qual é o teste mínimo seguro para validar a rede local?",
            "parent_mission_id": mission_row["id"],
            "mission_kind": "mission",
            "domain": "human_wellbeing",
            "priority": "strategic",
        },
    )
    assert child.status_code == 201, child.text
    child_row = child.json()
    assert child_row["code"] == "MIS-002"
    assert child_row["depth"] == 2
    assert child_row["path_codes"] == ["PRG-001", "MIS-001", "MIS-002"]

    portfolio = client.get(f"{base}/missions", headers=headers)
    assert portfolio.status_code == 200, portfolio.text
    rows = {row["code"]: row for row in portfolio.json()}
    assert rows["PRG-001"]["children_count"] == 1
    assert rows["MIS-001"]["children_count"] == 1

    analyzed = client.post(
        f"{base}/missions/MIS-001/analyze",
        headers=headers,
        json={
            "title": "Preparação para incêndios extremos",
            "context": "Risco territorial a caracterizar com entidades e população local.",
            "central_question": "Que combinação de prevenção e prontidão reduz o risco total?",
            "available_evidence": "Ainda sem registos canónicos de evidência.",
            "unknowns": "Exposição, capacidade, tempos de resposta e efeitos distributivos.",
            "use_ai": False,
            "research_context": False,
        },
    )
    assert analyzed.status_code == 200, analyzed.text
    assert analyzed.json()["mission_id"] == "MIS-001"
    assert analyzed.json()["mission_revision"] == 2

    edited = client.patch(
        f"{base}/missions/{mission_row['id']}",
        headers=headers,
        json={
            "expected_revision": 2,
            "title": "Preparação integrada para incêndios extremos",
            "priority": "strategic",
            "change_note": "Clarificação do âmbito após a primeira análise.",
        },
    )
    assert edited.status_code == 200, edited.text
    edited_row = edited.json()
    assert edited_row["title"] == "Preparação integrada para incêndios extremos"
    assert edited_row["priority"] == "strategic"
    assert edited_row["revision"] == 3

    dialogue = client.post(
        f"{base}/missions/MIS-001/interact",
        headers=headers,
        json={
            "intent": "diagnose",
            "message": "Estrutura as perguntas e salvaguardas desta missão.",
            "answers": [],
            "mission_input": {
                "title": "Preparação integrada para incêndios extremos",
                "context": (
                    "Risco territorial a caracterizar com entidades e população local."
                ),
                "central_question": (
                    "Que combinação de prevenção e prontidão reduz o risco total?"
                ),
                "available_evidence": (
                    "Ainda sem registos canónicos de evidência."
                ),
                "unknowns": (
                    "Exposição, capacidade, tempos de resposta e efeitos distributivos."
                ),
                "use_ai": False,
                "research_context": False,
            },
            "research_context": False,
        },
    )
    assert dialogue.status_code == 200, dialogue.text
    assert dialogue.json()["mission_id"] == "MIS-001"
    assert dialogue.json()["ai_status"] == "not_configured"

    deepest_parent_id = child_row["id"]
    for expected_depth in range(3, 6):
        deeper = client.post(
            f"{base}/missions",
            headers=headers,
            json={
                "title": f"Camada territorial {expected_depth}",
                "objective": "Preservar uma decomposição governada e verificável.",
                "context": "Sub-missão de teste ainda sem execução nem resultados.",
                "central_question": "A profundidade mantém-se dentro do limite governado?",
                "parent_mission_id": deepest_parent_id,
                "mission_kind": "mission",
                "domain": "territorial_resilience",
                "priority": "standard",
            },
        )
        assert deeper.status_code == 201, deeper.text
        assert deeper.json()["depth"] == expected_depth
        deepest_parent_id = deeper.json()["id"]

    second_program = client.post(
        f"{base}/missions",
        headers=headers,
        json={
            "title": "Programa independente",
            "objective": "Validar movimentos de árvores completas sem perder integridade.",
            "context": "Programa de teste independente e ainda sem sub-missões.",
            "central_question": "Uma árvore profunda pode ser movida para este programa?",
            "mission_kind": "program",
            "domain": "institutional_innovation",
            "priority": "standard",
        },
    )
    assert second_program.status_code == 201, second_program.text
    too_deep = client.patch(
        f"{base}/missions/{program_row['id']}",
        headers=headers,
        json={
            "expected_revision": 1,
            "parent_mission_id": second_program.json()["id"],
            "change_note": "Mover a árvore completa para testar o limite de profundidade.",
        },
    )
    assert too_deep.status_code == 409
    assert too_deep.json()["detail"]["code"] == "mission_hierarchy_too_deep"

    stale = client.patch(
        f"{base}/missions/{mission_row['id']}",
        headers=headers,
        json={
            "expected_revision": 1,
            "priority": "strategic",
            "change_note": "Tentativa baseada numa revisão antiga.",
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "mission_revision_conflict"

    cycle = client.patch(
        f"{base}/missions/{program_row['id']}",
        headers=headers,
        json={
            "expected_revision": 1,
            "parent_mission_id": child_row["id"],
            "change_note": "Esta relação deveria ser rejeitada por criar um ciclo.",
        },
    )
    assert cycle.status_code == 409
    assert cycle.json()["detail"]["code"] == "mission_hierarchy_cycle"

    other_headers, other_organization_id = _owner_named(f"portfolio-other-{suffix}")
    cross_organization = client.post(
        f"/api/organizations/{other_organization_id}/mission-intelligence/missions",
        headers=other_headers,
        json={
            "title": "Missão com pai inacessível",
            "objective": "Confirmar que a hierarquia permanece isolada por organização.",
            "context": "O identificador pertence deliberadamente a outra organização.",
            "central_question": "A plataforma rejeita a relação entre organizações?",
            "parent_mission_id": program_row["id"],
            "mission_kind": "mission",
            "domain": "cross_domain",
            "priority": "standard",
        },
    )
    assert cross_organization.status_code == 404
