from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.atlas_platform.audit import record_audit
from .lifecycle import require_mutable_mission

from .ai import (
    DEFAULT_CONTEXT_RESEARCH_OUTPUT_TOKENS,
    DEFAULT_MAX_OUTPUT_TOKENS,
    MAX_CONTEXT_WEB_SEARCH_CALLS,
    AIExecution,
    AIUnavailableError,
    analyze_with_openai,
    conservative_input_token_reservation,
    count_openai_input_tokens,
    is_ai_configured,
    is_ai_organization_authorized,
    is_context_research_configured,
    prepare_ai_request,
)
from .canonical import legacy_to_canonical
from .catalog import demo_mission
from .contracts import AnalysisInput, MissionDocumentV13
from .engine import ENGINE_VERSION, analyze_mission
from .governance import (
    AIGovernanceBlocked,
    apply_exact_input_count,
    microusd_to_usd,
    reserve_ai_usage,
    settle_ai_usage,
    usage_event_view,
)
from .models import (
    AIOrganizationPolicy,
    AIUsageEvent,
    CanonicalMission,
    IntelligenceRun,
    MissionRevision,
)
from .mission_archive import index_intelligence_run


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(document: MissionDocumentV13) -> str:
    return hashlib.sha256(_json(document.model_dump(mode="json")).encode("utf-8")).hexdigest()


def _legacy_or_error(mission_code: str) -> dict[str, Any]:
    mission = demo_mission(mission_code)
    if mission is None:
        raise KeyError(mission_code)
    return mission


def _base_result(
    document: MissionDocumentV13,
    deterministic: Any,
) -> dict[str, Any]:
    governed_context = document.metadata.get("context_dossier") or None
    return {
        "schema": "sris_mission_intelligence_result",
        "schema_version": "1.0",
        "mission_id": document.mission_id,
        "snapshot_hash": _hash(document),
        "execution_mode": "deterministic",
        "deterministic": deterministic.model_dump(mode="json"),
        "ai": None,
        "ai_status": "not_requested",
        "ai_governance": None,
        "ai_usage": None,
        "context_dossier": governed_context,
        "context_dossier_provenance": (
            {
                "origin_type": "governed_catalog",
                "verification_status": (
                    governed_context.get("research_status", "in_review")
                ),
                "limitations": (
                    "Snapshot contextual preliminar. As fontes e alegações mantêm "
                    "o estatuto declarado no dossier e não substituem revisão competente."
                ),
            }
            if governed_context
            else None
        ),
        "human_review_required": True,
        "review_allowed": False,
    }


def _apply_ai_execution(result: dict[str, Any], execution: AIExecution) -> None:
    result.update(
        execution_mode="hybrid",
        ai_status="completed",
        ai={
            "advisory": execution.advisory.model_dump(mode="json"),
            "provenance": {
                "origin_type": "ai_model",
                "provider": execution.provider,
                "model_or_system": execution.model,
                "version": execution.prompt_version,
                "provider_response_id": execution.provider_response_id,
                "verification_status": "in_review",
                "limitations": (
                    "Saída assistiva sujeita a erro; não constitui evidência, "
                    "decisão ou validação independente."
                ),
                "web_search_calls": execution.web_search_calls,
                "search_queries": list(execution.search_queries),
            },
        },
    )
    if execution.context_dossier is not None:
        dossier = execution.context_dossier.model_dump(mode="json")
        dossier_provenance = {
            "origin_type": "ai_model_with_web_search",
            "provider": execution.provider,
            "model_or_system": execution.model,
            "version": execution.prompt_version,
            "provider_response_id": execution.provider_response_id,
            "verification_status": "in_review",
            "web_search_calls": execution.web_search_calls,
            "search_queries": list(execution.search_queries),
            "limitations": (
                "Investigação assistida com fontes recuperadas nesta execução. O dossier "
                "é preliminar, pode conter erros e não altera a missão canónica sem revisão."
            ),
        }
        result["context_dossier"] = dossier
        result["context_dossier_provenance"] = dossier_provenance
        # Preserve the researched dossier inside ai_json so historical run
        # retrieval cannot lose the contextual output returned at execution.
        result["ai"]["context_dossier"] = dossier
        result["ai"]["context_dossier_provenance"] = dossier_provenance


def analyze_demo(
    mission_code: str,
    payload: AnalysisInput,
    *,
    allow_ai: bool = False,
) -> dict[str, Any]:
    legacy = _legacy_or_error(mission_code)
    document = legacy_to_canonical(legacy, payload)
    deterministic = analyze_mission(document)
    result = _base_result(document, deterministic)
    if payload.use_ai and not allow_ai:
        result["ai_status"] = "authentication_required"
    elif payload.use_ai and allow_ai:
        if payload.research_context and not is_context_research_configured():
            result["ai_status"] = "not_configured"
        elif not is_ai_configured():
            result["ai_status"] = "not_configured"
        else:
            try:
                execution = analyze_with_openai(
                    document,
                    deterministic,
                    research_context=payload.research_context,
                )
                _apply_ai_execution(result, execution)
            except AIUnavailableError as exc:
                result["ai_status"] = "failed"
                result["ai_error"] = str(exc)
    return result


def apply_analysis_input(
    document: MissionDocumentV13,
    payload: AnalysisInput,
) -> MissionDocumentV13:
    """Apply declared analysis context without promoting prose to evidence."""

    # An empty analysis payload is the default used by the mission dialogue.
    # Treating it as new information used to replace the stored contextual
    # claims with empty strings and, consequently, create a canonical revision
    # merely because somebody tried to open the AI assistant.  Empty input is
    # absence of an instruction, not a governed change.
    has_declared_context = any(
        str(value or "").strip()
        for value in (
            payload.context,
            payload.central_question,
            payload.available_evidence,
            payload.unknowns,
        )
    )
    if not has_declared_context:
        return document

    metadata = dict(document.metadata)
    metadata["unstructured_input"] = {
        "available_evidence_claim": payload.available_evidence,
        "unknowns_claim": payload.unknowns,
        "epistemic_status": "context_only_not_canonical_evidence",
    }
    return document.model_copy(
        update={
            # Analysis labels must not silently rename the canonical mission.
            # Identity changes use the explicit, revision-checked PATCH route.
            "title": document.title,
            "context": payload.context or document.context,
            "central_question": (
                payload.central_question or document.central_question
            ),
            "metadata": metadata,
        }
    )


def persist_mission(
    db: Session,
    *,
    organization_id: str,
    user_id: str,
    mission_code: str,
    payload: AnalysisInput,
) -> tuple[CanonicalMission, MissionDocumentV13]:
    mission = (
        db.query(CanonicalMission)
        .filter(
            CanonicalMission.organization_id == organization_id,
            CanonicalMission.code == mission_code,
        )
        .one_or_none()
    )

    legacy: dict[str, Any] | None = None
    if mission is None:
        legacy = _legacy_or_error(mission_code)
        document = legacy_to_canonical(legacy, payload)
    else:
        document = apply_analysis_input(
            MissionDocumentV13.model_validate_json(mission.document_json),
            payload,
        )

    document_json = _json(document.model_dump(mode="json"))
    content_hash = _hash(document)
    if mission is None:
        assert legacy is not None
        mission = CanonicalMission(
            organization_id=organization_id,
            code=mission_code,
            title=document.title,
            mission_kind=str(legacy.get("mission_kind") or "mission"),
            domain=str(legacy.get("domain") or "cross_domain"),
            priority=str(legacy.get("priority") or "strategic"),
            sort_order=int(legacy.get("featured_rank") or 0),
            schema_version=document.schema_version,
            document_json=document_json,
            content_hash=content_hash,
            revision=1,
            created_by_user_id=user_id,
        )
        db.add(mission)
        db.flush()
        db.add(
            MissionRevision(
                mission_id=mission.id,
                revision=1,
                document_json=document_json,
                content_hash=content_hash,
                change_note="Initial canonical import from the governed demo catalog.",
                created_by_user_id=user_id,
            )
        )
    elif mission.content_hash != content_hash:
        require_mutable_mission(mission)
        mission.revision += 1
        mission.title = document.title
        mission.schema_version = document.schema_version
        mission.document_json = document_json
        mission.content_hash = content_hash
        db.add(
            MissionRevision(
                mission_id=mission.id,
                revision=mission.revision,
                document_json=document_json,
                content_hash=content_hash,
                change_note="Analysis input accepted as a new canonical mission revision.",
                created_by_user_id=user_id,
            )
        )
    db.flush()
    return mission, document


def persist_demo_mission(
    db: Session,
    *,
    organization_id: str,
    user_id: str,
    mission_code: str,
    payload: AnalysisInput,
) -> tuple[CanonicalMission, MissionDocumentV13]:
    """Backward-compatible alias for callers using the v1 demo route."""

    return persist_mission(
        db,
        organization_id=organization_id,
        user_id=user_id,
        mission_code=mission_code,
        payload=payload,
    )


def run_organizational_analysis(
    db: Session,
    *,
    organization_id: str,
    user_id: str,
    user_role: str,
    mission_code: str,
    payload: AnalysisInput,
) -> dict[str, Any]:
    mission, document = persist_mission(
        db,
        organization_id=organization_id,
        user_id=user_id,
        mission_code=mission_code,
        payload=payload,
    )
    # Canonical mission revisions must survive an AI governance rejection. The
    # provider-budget transaction starts only after this authoritative state is
    # durable.
    db.commit()
    db.refresh(mission)
    deterministic = analyze_mission(document)
    result = _base_result(document, deterministic)
    result["review_allowed"] = user_role in {"owner", "admin", "reviewer"}
    usage_event: AIUsageEvent | None = None

    if payload.use_ai:
        if user_role not in {"owner", "admin", "reviewer"}:
            result["ai_status"] = "governance_blocked"
            result["ai_governance"] = {
                "allowed": False,
                "code": "role_not_allowed",
                "message": "This organizational role cannot consume AI budget",
            }
        elif payload.research_context and not is_context_research_configured():
            result["ai_status"] = "not_configured"
            result["ai_governance"] = {
                "allowed": False,
                "code": "context_research_not_configured",
                "message": "Governed context research is not enabled and configured",
            }
        elif not is_ai_configured():
            result["ai_status"] = "not_configured"
            result["ai_governance"] = {
                "allowed": False,
                "code": "provider_not_configured",
                "message": "The AI provider is not enabled and configured",
            }
        elif not is_ai_organization_authorized(organization_id):
            result["ai_status"] = "governance_blocked"
            result["ai_governance"] = {
                "allowed": False,
                "code": "organization_not_authorized",
                "message": "This organization is not authorized for the AI pilot",
            }
        else:
            policy = (
                db.query(AIOrganizationPolicy)
                .filter(AIOrganizationPolicy.organization_id == organization_id)
                .one_or_none()
            )
            requested_output = (
                DEFAULT_CONTEXT_RESEARCH_OUTPUT_TOKENS
                if payload.research_context
                else DEFAULT_MAX_OUTPUT_TOKENS
            )
            output_limit = min(
                requested_output,
                policy.per_request_output_token_limit if policy else requested_output,
            )
            prepared = prepare_ai_request(
                document,
                deterministic,
                max_output_tokens=output_limit,
                research_context=payload.research_context,
            )
            conservative_input = conservative_input_token_reservation(prepared)
            try:
                reservation = reserve_ai_usage(
                    db,
                    organization_id=organization_id,
                    user_id=user_id,
                    model=prepared.model,
                    input_tokens=conservative_input,
                    output_tokens=output_limit,
                    web_search_calls=(
                        MAX_CONTEXT_WEB_SEARCH_CALLS
                        if payload.research_context
                        else 0
                    ),
                )
                exact_input = count_openai_input_tokens(prepared)
                if exact_input is not None:
                    reservation = apply_exact_input_count(
                        db,
                        reservation=reservation,
                        exact_input_tokens=exact_input,
                    )
                result["ai_governance"] = {
                    "allowed": True,
                    "usage_event_id": reservation.event_id,
                    "reserved_input_tokens": reservation.input_tokens,
                    "reserved_output_tokens": reservation.output_tokens,
                    "reserved_web_search_calls": reservation.web_search_calls,
                    "reserved_cost_usd": microusd_to_usd(
                        reservation.estimated_cost_microusd
                    ),
                    "monthly_limit_warnings": list(
                        reservation.monthly_limit_warnings
                    ),
                    "input_count_method": (
                        "provider_exact" if exact_input is not None else "conservative"
                    ),
                }
                try:
                    execution = analyze_with_openai(
                        document,
                        deterministic,
                        prepared_request=prepared,
                        research_context=payload.research_context,
                    )
                    _apply_ai_execution(result, execution)
                    usage_event = settle_ai_usage(
                        db,
                        reservation=reservation,
                        provider_response_id=execution.provider_response_id,
                        input_tokens=execution.usage.input_tokens,
                        cached_input_tokens=execution.usage.cached_input_tokens,
                        output_tokens=execution.usage.output_tokens,
                        total_tokens=execution.usage.total_tokens,
                        web_search_calls=execution.web_search_calls,
                    )
                except AIUnavailableError as exc:
                    failure_usage = exc.usage
                    usage_event = settle_ai_usage(
                        db,
                        reservation=reservation,
                        provider_response_id=exc.provider_response_id,
                        input_tokens=(
                            failure_usage.input_tokens if failure_usage else None
                        ),
                        cached_input_tokens=(
                            failure_usage.cached_input_tokens if failure_usage else None
                        ),
                        output_tokens=(
                            failure_usage.output_tokens if failure_usage else None
                        ),
                        total_tokens=(
                            failure_usage.total_tokens if failure_usage else None
                        ),
                        web_search_calls=exc.web_search_calls,
                        failure_code=exc.failure_code,
                    )
                    result["ai_status"] = "failed"
                    result["ai_error"] = str(exc)
                result["ai_usage"] = usage_event_view(usage_event)
            except AIGovernanceBlocked as exc:
                db.rollback()
                result["ai_status"] = "governance_blocked"
                result["ai_governance"] = {
                    "allowed": False,
                    "code": exc.code,
                    "message": exc.message,
                }

    ai = result.get("ai") or {}
    provenance = ai.get("provenance") or {}
    if result["ai_status"] == "failed":
        status = "completed_with_warning"
    elif result["ai_status"] == "governance_blocked":
        status = "completed_with_constraint"
    else:
        status = "completed"
    run = IntelligenceRun(
        organization_id=organization_id,
        mission_id=mission.id,
        mission_code=mission_code,
        execution_mode=result["execution_mode"],
        status=status,
        engine_version=ENGINE_VERSION,
        provider=provenance.get("provider"),
        model=provenance.get("model_or_system"),
        provider_response_id=provenance.get("provider_response_id"),
        snapshot_hash=result["snapshot_hash"],
        input_json=_json(payload.model_dump(mode="json")),
        deterministic_json=_json(result["deterministic"]),
        ai_json=_json(ai) if ai else None,
        error=result.get("ai_error"),
        review_status="required",
        created_by_user_id=user_id,
    )
    db.add(run)
    db.flush()
    index_intelligence_run(db, run=run)
    if usage_event is not None:
        usage_event.intelligence_run_id = run.id
        db.add(usage_event)
    record_audit(
        db,
        action="mission_intelligence.executed",
        resource_type="intelligence_run",
        resource_id=run.id,
        organization_id=organization_id,
        user_id=user_id,
        payload={
            "mission_code": mission_code,
            "execution_mode": result["execution_mode"],
            "ai_status": result["ai_status"],
            "ai_governance": result.get("ai_governance"),
            "ai_usage_event_id": usage_event.id if usage_event else None,
            "snapshot_hash": result["snapshot_hash"],
        },
    )
    db.commit()
    result["run_id"] = run.id
    result["mission_revision"] = mission.revision
    result["review_status"] = run.review_status
    return result


def review_run(
    db: Session,
    *,
    run: IntelligenceRun,
    user_id: str,
    decision: str,
    comment: str,
) -> IntelligenceRun:
    if run.review_status != "required":
        raise ValueError("This intelligence run has already been reviewed")
    run.review_status = decision
    run.reviewed_by_user_id = user_id
    run.review_comment = comment
    run.reviewed_at = datetime.now(timezone.utc)
    record_audit(
        db,
        action=f"mission_intelligence.{decision}",
        resource_type="intelligence_run",
        resource_id=run.id,
        organization_id=run.organization_id,
        user_id=user_id,
        payload={"comment": comment},
    )
    db.commit()
    db.refresh(run)
    return run


def run_view(run: IntelligenceRun) -> dict[str, Any]:
    ai = json.loads(run.ai_json) if run.ai_json else None
    view = {
        "id": run.id,
        "mission_code": run.mission_code,
        "execution_mode": run.execution_mode,
        "status": run.status,
        "engine_version": run.engine_version,
        "provider": run.provider,
        "model": run.model,
        "snapshot_hash": run.snapshot_hash,
        "deterministic": json.loads(run.deterministic_json),
        "ai": ai,
        "ai_usage": usage_event_view(run.ai_usage_event) if run.ai_usage_event else None,
        "error": run.error,
        "review_status": run.review_status,
        "review_comment": run.review_comment,
        "created_at": run.created_at,
        "reviewed_at": run.reviewed_at,
    }
    if ai and ai.get("context_dossier"):
        view["context_dossier"] = ai["context_dossier"]
        view["context_dossier_provenance"] = ai.get(
            "context_dossier_provenance"
        )
    return view
