from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.atlas_platform.audit import record_audit
from app.pilot_mission_state import governed_ai_context

from .attachments import (
    AttachmentError,
    attachment_chunk_counts,
    backfill_mission_archive_index,
    prepare_turn_attachment_rows,
    prepare_turn_attachments,
)
from .ai import (
    MAX_CONTEXT_WEB_SEARCH_CALLS,
    AIUnavailableError,
    conservative_input_token_reservation,
    count_openai_input_tokens,
    is_ai_configured,
    is_ai_organization_authorized,
    is_context_research_configured,
)
from .contracts import MIInteractionInput, MIProposalReviewRequest, MissionDocumentV13
from .canonical import legacy_to_canonical
from .catalog import demo_mission
from .engine import ENGINE_VERSION, analyze_mission
from .governance import (
    AIGovernanceBlocked,
    apply_exact_input_count,
    microusd_to_usd,
    reserve_ai_usage,
    settle_ai_usage,
    usage_event_view,
)
from .interactive import (
    DEFAULT_INTERACTIVE_OUTPUT_TOKENS,
    DEFAULT_INTERACTIVE_RESEARCH_OUTPUT_TOKENS,
    DEFAULT_MISSION_PATH_OUTPUT_TOKENS,
    MIInteractiveExecution,
    analyze_interactively,
    prepare_interactive_request,
    validate_attachment_citations,
)
from .models import (
    AIOrganizationPolicy,
    AIUsageEvent,
    CanonicalMission,
    IntelligenceRun,
    MissionDialogueSession,
    MissionDialogueTurn,
    MissionProposalReview,
)
from .mission_archive import (
    backfill_mission_run_archive,
    index_intelligence_run,
    retrieve_mission_archive,
)
from .service import _hash, _json, apply_analysis_input, persist_mission


class MIDialogueConflict(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _resume_session_or_conflict(
    db: Session,
    *,
    organization_id: str,
    mission_code: str,
    payload: MIInteractionInput,
) -> tuple[MissionDialogueSession, CanonicalMission, MissionDocumentV13]:
    """Resume an immutable snapshot without re-persisting stale form input."""

    session = (
        db.query(MissionDialogueSession)
        .filter(
            MissionDialogueSession.id == payload.session_id,
            MissionDialogueSession.organization_id == organization_id,
        )
        .one_or_none()
    )
    if session is None:
        raise MIDialogueConflict(
            "session_not_found",
            "A sessão de Mission Intelligence não foi encontrada.",
        )
    if session.mission_code != mission_code:
        raise MIDialogueConflict(
            "session_mission_mismatch",
            "A sessão de diálogo pertence a outra missão.",
        )
    if session.status != "active":
        raise MIDialogueConflict(
            "session_not_active",
            "A sessão de Mission Intelligence já não está ativa.",
        )
    mission = (
        db.query(CanonicalMission)
        .filter(
            CanonicalMission.id == session.mission_id,
            CanonicalMission.organization_id == organization_id,
        )
        .one_or_none()
    )
    if mission is None:
        raise MIDialogueConflict(
            "mission_not_found",
            "A missão canónica associada à sessão não foi encontrada.",
        )
    if session.snapshot_hash != mission.content_hash:
        raise MIDialogueConflict(
            "mission_snapshot_changed",
            "A missão canónica mudou. Inicie uma nova sessão sobre a nova revisão.",
        )

    document = MissionDocumentV13.model_validate_json(mission.document_json)
    if _hash(document) != mission.content_hash:
        raise MIDialogueConflict(
            "mission_snapshot_invalid",
            "O snapshot canónico persistido falhou a verificação de integridade.",
        )

    submitted_document = apply_analysis_input(document, payload.mission_input)
    if _hash(submitted_document) != session.snapshot_hash:
        raise MIDialogueConflict(
            "dialogue_input_changed",
            "Os dados do formulário diferem do snapshot desta sessão. Inicie uma nova sessão para os usar.",
        )

    return session, mission, document


def _create_session(
    db: Session,
    *,
    organization_id: str,
    mission: CanonicalMission,
    user_id: str,
    payload: MIInteractionInput,
) -> MissionDialogueSession:
    session = MissionDialogueSession(
        organization_id=organization_id,
        mission_id=mission.id,
        mission_code=mission.code,
        title=f"Mission Intelligence · {mission.code}",
        objective=payload.message,
        snapshot_hash=mission.content_hash,
        created_by_user_id=user_id,
    )
    db.add(session)
    db.flush()
    record_audit(
        db,
        action="mission_intelligence.dialogue_started",
        resource_type="mission_dialogue_session",
        resource_id=session.id,
        organization_id=organization_id,
        user_id=user_id,
        payload={
            "mission_code": mission.code,
            "snapshot_hash": mission.content_hash,
        },
    )
    return session


def _dialogue_history(
    db: Session,
    session_id: str,
) -> list[dict[str, Any]]:
    turns = (
        db.query(MissionDialogueTurn)
        .filter(MissionDialogueTurn.session_id == session_id)
        .order_by(MissionDialogueTurn.sequence.asc())
        .all()
    )
    history: list[dict[str, Any]] = []
    for turn in turns:
        ai = json.loads(turn.intelligence_run.ai_json) if turn.intelligence_run.ai_json else {}
        intelligence = ai.get("intelligence")
        if not intelligence:
            continue
        history.append(
            {
                "sequence": turn.sequence,
                "intent": turn.intent,
                "user_message": turn.user_message,
                "answers": json.loads(turn.answers_json),
                "attachment_ids": json.loads(turn.attachment_ids_json),
                "intelligence": intelligence,
            }
        )
    return history


def _proposal_review_view(row: MissionProposalReview) -> dict[str, Any]:
    return {
        "id": row.id,
        "session_id": row.session_id,
        "turn_id": row.turn_id,
        "proposal_id": row.proposal_id,
        "proposal_type": row.proposal_type,
        "decision": row.decision,
        "comment": row.comment,
        "reviewed_by_user_id": row.reviewed_by_user_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "canonical_effect": (
            "human_validated_proposal"
            if row.decision == "human_validated"
            else "none"
        ),
    }


def _proposal_reviews_for_prompt(
    db: Session,
    session_id: str,
) -> list[dict[str, Any]]:
    rows = (
        db.query(MissionProposalReview)
        .filter(MissionProposalReview.session_id == session_id)
        .order_by(MissionProposalReview.updated_at.asc())
        .all()
    )
    return [
        {
            "turn_sequence": row.turn.sequence,
            "proposal_id": row.proposal_id,
            "proposal_type": row.proposal_type,
            "decision": row.decision,
            "comment": row.comment,
        }
        for row in rows
    ]


def _governance_block(
    *,
    code: str,
    message: str,
    base: dict[str, Any],
) -> dict[str, Any]:
    base.update(
        ai_status="governance_blocked",
        ai_governance={"allowed": False, "code": code, "message": message},
    )
    return base


def _base_interaction_result(
    *,
    session: MissionDialogueSession,
    mission: CanonicalMission,
    document: MissionDocumentV13,
    deterministic: Any,
) -> dict[str, Any]:
    return {
        "schema": "sris_mission_intelligence_interaction",
        "schema_version": "2.3",
        "session_id": session.id,
        "mission_id": document.mission_id,
        "mission_revision": mission.revision,
        "snapshot_hash": mission.content_hash,
        "execution_mode": "interactive",
        "deterministic": deterministic.model_dump(mode="json"),
        "intelligence": None,
        "ai_status": "not_requested",
        "ai_governance": None,
        "ai_usage": None,
        "human_review_required": True,
        "canonical_mutation": "none",
    }


def _unavailable_interaction_result(
    db: Session,
    *,
    organization_id: str,
    mission_code: str,
    payload: MIInteractionInput,
    code: str,
    message: str,
    status: str = "not_configured",
) -> dict[str, Any]:
    """Describe an unavailable AI turn without creating canonical state.

    Opening the assistant is a read operation until an actual provider-backed
    turn can run.  In particular, provider configuration, role or pilot-policy
    failures must not create a dialogue session or a mission revision.
    """

    session: MissionDialogueSession | None = None
    mission: CanonicalMission | None = None
    if payload.session_id:
        session, mission, document = _resume_session_or_conflict(
            db,
            organization_id=organization_id,
            mission_code=mission_code,
            payload=payload,
        )
    else:
        mission = (
            db.query(CanonicalMission)
            .filter(
                CanonicalMission.organization_id == organization_id,
                CanonicalMission.code == mission_code,
            )
            .one_or_none()
        )
        if mission is not None:
            document = MissionDocumentV13.model_validate_json(mission.document_json)
        else:
            legacy = demo_mission(mission_code)
            if legacy is None:
                raise KeyError(mission_code)
            document = legacy_to_canonical(legacy, payload.mission_input)

    deterministic = analyze_mission(document)
    canonical_hash = mission.content_hash if mission is not None else _hash(document)
    return {
        "schema": "sris_mission_intelligence_interaction",
        "schema_version": "2.3",
        "session_id": session.id if session is not None else None,
        "turn_id": None,
        "turn_persisted": False,
        "mission_id": document.mission_id,
        "mission_revision": int(mission.revision) if mission is not None else 0,
        "snapshot_hash": canonical_hash,
        "canonical_mission_hash": canonical_hash,
        "execution_mode": "unavailable",
        "deterministic": deterministic.model_dump(mode="json"),
        "intelligence": None,
        "ai_status": status,
        "ai_governance": {
            "allowed": False,
            "code": code,
            "message": message,
        },
        "ai_usage": None,
        "intent": payload.intent.value,
        "user_message": payload.message,
        "attachments": [],
        "human_review_required": True,
        "canonical_mutation": "none",
    }


def _apply_execution(
    result: dict[str, Any],
    execution: MIInteractiveExecution,
) -> dict[str, Any]:
    result.update(
        ai_status="completed",
        execution_mode=(
            "interactive_research" if execution.context_dossier else "interactive"
        ),
        intelligence=execution.intelligence.model_dump(mode="json"),
        provenance={
            "origin_type": "ai_model",
            "provider": execution.provider,
            "model_or_system": execution.model,
            "model": execution.model,
            "version": execution.prompt_version,
            "prompt_version": execution.prompt_version,
            "provider_response_id": execution.provider_response_id,
            "verification_status": "in_review",
            "web_search_calls": execution.web_search_calls,
            "search_queries": list(execution.search_queries),
            "limitations": (
                "Saída interativa provisória. Todo o percurso preparado pela IA permanece "
                "proposta; não constitui facto, decisão, autorização, resultado observado "
                "ou encerramento e não altera automaticamente a missão."
            ),
        },
        context_manifest=execution.context_manifest or result.get("context_manifest"),
        context_retry_count=execution.context_retry_count,
        confidence_calibration=list(execution.confidence_calibration),
    )
    if execution.context_dossier:
        result["context_dossier"] = execution.context_dossier.model_dump(mode="json")
        result["context_dossier_provenance"] = {
            "origin_type": "ai_model_with_web_search",
            "provider": execution.provider,
            "model_or_system": execution.model,
            "version": execution.prompt_version,
            "provider_response_id": execution.provider_response_id,
            "verification_status": "in_review",
            "web_search_calls": execution.web_search_calls,
            "search_queries": list(execution.search_queries),
        }
    return result


def _attachment_summary(
    attachment: Any,
    *,
    archive_chunk_count: int = 0,
) -> dict[str, Any]:
    archive_chunk_count = max(0, int(archive_chunk_count))
    filename = getattr(
        attachment,
        "filename",
        getattr(attachment, "original_filename", "anexo"),
    )
    return {
        "id": attachment.id,
        "evidence_id": f"ATT-{attachment.id[:8].upper()}",
        "filename": filename,
        "media_type": attachment.media_type,
        "byte_size": attachment.byte_size,
        "sha256": attachment.sha256,
        "question_id": attachment.question_id,
        "extraction_status": getattr(
            attachment,
            "extraction_status",
            "ready" if getattr(attachment, "extracted_text", "") else "unknown",
        ),
        "extraction_error": getattr(attachment, "extraction_error", ""),
        "archive_indexed": archive_chunk_count > 0,
        "archive_chunk_count": archive_chunk_count,
        "verification_status": "in_review",
    }


def _attachment_trace_details(
    *,
    citation_trace: list[dict[str, Any]],
    requested_attachments: list[Any],
    archive_chunk_counts: dict[str, int],
) -> list[dict[str, Any]]:
    cited_by_id = {
        item["attachment_id"]: item
        for item in citation_trace
        if isinstance(item.get("attachment_id"), str)
    }
    trace: list[dict[str, Any]] = []
    for attachment in requested_attachments:
        summary = _attachment_summary(
            attachment,
            archive_chunk_count=archive_chunk_counts.get(attachment.id, 0),
        )
        cited = cited_by_id.get(attachment.id)
        if cited is None:
            trace.append(
                {
                    **summary,
                    "status": "preserved_not_selected",
                    "delivery_mode": "preserved_archive",
                    "selected_chunk_ids": [],
                    "citation_locations": [],
                    "selection_note": (
                        "O anexo permanece preservado e pesquisável, mas não entrou "
                        "na janela de trabalho deste turno."
                    ),
                }
            )
            continue
        trace.append(
            {
                **summary,
                **cited,
                "status": "used_and_cited",
                "selection_note": (
                    "O conteúdo entrou na janela de trabalho e foi citado na "
                    "resposta estruturada."
                ),
            }
        )
    return trace


def _epistemic_ledger(
    *,
    document: MissionDocumentV13,
    payload: MIInteractionInput,
    execution: MIInteractiveExecution,
    attachments: list[Any],
) -> dict[str, Any]:
    verified_facts = [
        {
            "id": record.canonical_id,
            "statement": record.title,
            "source": record.provenance.source,
        }
        for record in document.records
        if record.provenance.verification_status == "confirmed"
    ][:8]
    user_statements = [
        {
            "id": answer.question_id,
            "statement": answer.answer,
            "source": "Resposta do utilizador neste turno",
        }
        for answer in payload.answers
    ]
    user_statements.extend(
        {
            "id": attachment.id,
            "statement": (
                "Documento fornecido: "
                + str(
                    getattr(
                        attachment,
                        "filename",
                        getattr(attachment, "original_filename", "anexo"),
                    )
                )
            ),
            "source": "Anexo do utilizador; conteúdo sujeito a verificação",
        }
        for attachment in attachments
    )
    hypotheses = [
        {
            "id": item.proposal_id,
            "statement": item.statement,
            "confidence": item.confidence.value,
        }
        for item in execution.intelligence.hypotheses
    ]
    update = execution.intelligence.decision_update
    decisions = [
        {
            "id": "DECISION-UPDATE",
            "statement": update.decision_now,
            "confidence": update.confidence_now.value,
            "status": "provisional",
        }
    ]
    evidence_needed: list[dict[str, str]] = []
    seen: set[str] = set()
    for hypothesis in execution.intelligence.hypotheses:
        for item in hypothesis.evidence_needed:
            key = item.strip().casefold()
            if key and key not in seen:
                seen.add(key)
                evidence_needed.append(
                    {
                        "id": hypothesis.proposal_id,
                        "statement": item,
                    }
                )
    if execution.context_dossier:
        for gap in execution.context_dossier.gaps:
            item = gap.evidence_needed or gap.question
            key = item.strip().casefold()
            if key and key not in seen:
                seen.add(key)
                evidence_needed.append({"id": gap.gap_id, "statement": item})
    return {
        "verified_facts": verified_facts,
        "user_statements": user_statements,
        "hypotheses": hypotheses,
        "decisions": decisions,
        "evidence_needed": evidence_needed[:12],
        "external_source_status": (
            "researched_with_traceable_sources"
            if execution.context_dossier
            else "not_researched_in_this_turn"
        ),
    }


def run_interactive_turn(
    db: Session,
    *,
    organization_id: str,
    user_id: str,
    user_role: str,
    mission_code: str,
    payload: MIInteractionInput,
) -> dict[str, Any]:
    if user_role not in {"owner", "admin", "reviewer"}:
        return _unavailable_interaction_result(
            db,
            organization_id=organization_id,
            mission_code=mission_code,
            payload=payload,
            code="role_not_allowed",
            message="A sua função no workspace não tem autorização para consumir orçamento de IA.",
            status="governance_blocked",
        )
    if payload.research_context and not is_context_research_configured():
        return _unavailable_interaction_result(
            db,
            organization_id=organization_id,
            mission_code=mission_code,
            payload=payload,
            code="context_research_not_configured",
            message="A pesquisa externa governada ainda não está ativa e configurada.",
        )
    if not is_ai_configured():
        return _unavailable_interaction_result(
            db,
            organization_id=organization_id,
            mission_code=mission_code,
            payload=payload,
            code="provider_not_configured",
            message="O fornecedor de IA ainda não está ativo e configurado neste ambiente.",
        )
    if not is_ai_organization_authorized(organization_id):
        return _unavailable_interaction_result(
            db,
            organization_id=organization_id,
            mission_code=mission_code,
            payload=payload,
            code="organization_not_authorized",
            message="Este workspace ainda não está autorizado para o piloto de IA.",
            status="governance_blocked",
        )

    if payload.session_id:
        session, mission, document = _resume_session_or_conflict(
            db,
            organization_id=organization_id,
            mission_code=mission_code,
            payload=payload,
        )
    else:
        mission, document = persist_mission(
            db,
            organization_id=organization_id,
            user_id=user_id,
            mission_code=mission_code,
            payload=payload.mission_input,
        )
        session = _create_session(
            db,
            organization_id=organization_id,
            mission=mission,
            user_id=user_id,
            payload=payload,
        )
    db.commit()
    db.refresh(mission)
    db.refresh(session)

    turn_attachment_rows = prepare_turn_attachment_rows(
        db,
        organization_id=organization_id,
        mission_id=mission.id,
        attachment_ids=payload.attachment_ids,
    )
    turn_attachment_chunk_counts = attachment_chunk_counts(
        db,
        turn_attachment_rows,
    )
    deterministic = analyze_mission(document)
    result = _base_interaction_result(
        session=session,
        mission=mission,
        document=document,
        deterministic=deterministic,
    )
    result["intent"] = payload.intent.value
    result["user_message"] = payload.message
    result["attachments"] = [
        _attachment_summary(
            item,
            archive_chunk_count=turn_attachment_chunk_counts.get(item.id, 0),
        )
        for item in turn_attachment_rows
    ]
    governed_context = governed_ai_context(
        db,
        organization_id=organization_id,
        mission_id=mission.id,
        mission_code=mission.code,
    )
    result["canonical_mission_hash"] = mission.content_hash
    result["snapshot_hash"] = governed_context["state_hash"]
    result["governed_mission_state"] = {
        "schema": governed_context["schema"],
        "state_hash": governed_context["state_hash"],
        "health": governed_context["health"],
        "policy": governed_context["policy"],
        "modules": governed_context["modules"],
        "dependencies": governed_context["dependencies"],
        "conflicts": governed_context["conflicts"],
        "object_count": len(governed_context["objects"]),
        "boundary": governed_context["boundary"],
    }

    history = _dialogue_history(db, session.id)
    proposal_reviews = _proposal_reviews_for_prompt(db, session.id)
    policy = (
        db.query(AIOrganizationPolicy)
        .filter(AIOrganizationPolicy.organization_id == organization_id)
        .one_or_none()
    )
    backfilled = backfill_mission_archive_index(
        db,
        organization_id=organization_id,
        mission_id=mission.id,
        priority_attachment_ids=payload.attachment_ids,
    )
    backfilled_runs = backfill_mission_run_archive(
        db,
        organization_id=organization_id,
        mission_id=mission.id,
    )
    if backfilled or backfilled_runs:
        db.commit()
    if backfilled:
        turn_attachment_chunk_counts = attachment_chunk_counts(
            db,
            turn_attachment_rows,
        )
        result["attachments"] = [
            _attachment_summary(
                item,
                archive_chunk_count=turn_attachment_chunk_counts.get(item.id, 0),
            )
            for item in turn_attachment_rows
        ]
    retrieval_query = "\n".join(
        filter(
            None,
            (
                document.title,
                document.central_question,
                payload.message,
                *(item.answer for item in payload.answers),
            ),
        )
    )
    archive_context = retrieve_mission_archive(
        db,
        organization_id=organization_id,
        mission_id=mission.id,
        query_text=retrieval_query,
        priority_attachment_ids=payload.attachment_ids,
    )
    direct_attachments = prepare_turn_attachments(
        db,
        organization_id=organization_id,
        mission_id=mission.id,
        attachment_ids=list(archive_context.direct_binary_attachment_ids),
    )
    requested_output = (
        DEFAULT_INTERACTIVE_RESEARCH_OUTPUT_TOKENS
        if payload.research_context
        else DEFAULT_MISSION_PATH_OUTPUT_TOKENS
        if payload.intent.value == "build_mission_path"
        else DEFAULT_INTERACTIVE_OUTPUT_TOKENS
    )
    output_limit = min(
        requested_output,
        policy.per_request_output_token_limit if policy else requested_output,
    )
    input_limit = (
        policy.per_request_input_token_limit
        if policy
        else 60_000
    )
    prepared = prepare_interactive_request(
        document,
        deterministic,
        intent=payload.intent,
        message=payload.message,
        answers=payload.answers,
        history=history,
        proposal_reviews=proposal_reviews,
        attachments=direct_attachments,
        archive_context=archive_context,
        governed_state=governed_context,
        max_output_tokens=output_limit,
        max_input_tokens=input_limit,
        research_context=payload.research_context,
    )
    missing_attachment_ids = [
        item
        for item in (prepared.context_manifest or {}).get(
            "current_turn_missing_attachment_ids",
            [],
        )
        if isinstance(item, str)
    ]
    if missing_attachment_ids:
        attachment_names = {
            item.id: item.original_filename for item in turn_attachment_rows
        }
        missing_names = [
            attachment_names.get(item, item)
            for item in missing_attachment_ids
        ]
        raise AttachmentError(
            "attachment_context_incomplete",
            "Não foi possível incluir todos os anexos selecionados neste turno: "
            + ", ".join(missing_names)
            + ". Reduza o número de anexos visuais ou divida a análise em mais "
            "do que um turno; nenhum anexo foi apresentado como lido.",
        )
    working_attachments = prepare_turn_attachments(
        db,
        organization_id=organization_id,
        mission_id=mission.id,
        attachment_ids=list(
            (prepared.context_manifest or {}).get(
                "selected_attachment_ids",
                [],
            )
        ),
    )
    result["context_manifest"] = prepared.context_manifest
    conservative_input = conservative_input_token_reservation(prepared)
    usage_event: AIUsageEvent | None = None
    execution: MIInteractiveExecution | None = None
    error: str | None = None

    try:
        reservation = reserve_ai_usage(
            db,
            organization_id=organization_id,
            user_id=user_id,
            model=prepared.model,
            input_tokens=conservative_input,
            output_tokens=output_limit,
            web_search_calls=(
                MAX_CONTEXT_WEB_SEARCH_CALLS if payload.research_context else 0
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
            execution = analyze_interactively(
                document,
                deterministic,
                intent=payload.intent,
                message=payload.message,
                answers=payload.answers,
                history=history,
                proposal_reviews=proposal_reviews,
                attachments=working_attachments,
                archive_context=archive_context,
                governed_state=governed_context,
                prepared_request=prepared,
                max_input_tokens=input_limit,
                research_context=payload.research_context,
            )
            citation_trace = validate_attachment_citations(
                execution.intelligence,
                execution.context_manifest or prepared.context_manifest,
            )
            _apply_execution(result, execution)
            result["attachment_trace"] = _attachment_trace_details(
                citation_trace=citation_trace,
                requested_attachments=turn_attachment_rows,
                archive_chunk_counts=turn_attachment_chunk_counts,
            )
            result["epistemic_ledger"] = _epistemic_ledger(
                document=document,
                payload=payload,
                execution=execution,
                attachments=turn_attachment_rows,
            )
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
            error = str(exc)
            failure_usage = exc.usage
            usage_event = settle_ai_usage(
                db,
                reservation=reservation,
                provider_response_id=exc.provider_response_id,
                input_tokens=failure_usage.input_tokens if failure_usage else None,
                cached_input_tokens=(
                    failure_usage.cached_input_tokens if failure_usage else None
                ),
                output_tokens=failure_usage.output_tokens if failure_usage else None,
                total_tokens=failure_usage.total_tokens if failure_usage else None,
                web_search_calls=exc.web_search_calls,
                failure_code=exc.failure_code,
            )
            result.update(ai_status="failed", ai_error=error)
            execution = None
        result["ai_usage"] = usage_event_view(usage_event)
    except AIGovernanceBlocked as exc:
        db.rollback()
        return _governance_block(code=exc.code, message=exc.message, base=result)

    # Serialize turn numbering per session on databases that support row locks.
    # The pilot policy also keeps organizational concurrency at one request.
    session = (
        db.query(MissionDialogueSession)
        .filter(MissionDialogueSession.id == session.id)
        .with_for_update()
        .one()
    )
    current_sequence = (
        db.query(func.max(MissionDialogueTurn.sequence))
        .filter(MissionDialogueTurn.session_id == session.id)
        .scalar()
        or 0
    )
    provenance = result.get("provenance") or {}
    ai_payload: dict[str, Any] | None = None
    if execution:
        ai_payload = {
            "intelligence": result["intelligence"],
            "provenance": provenance,
            "attachments": result.get("attachments", []),
            "epistemic_ledger": result.get("epistemic_ledger"),
            "attachment_trace": result.get("attachment_trace") or [],
            "context_manifest": result.get("context_manifest"),
            "context_retry_count": result.get("context_retry_count", 0),
            "confidence_calibration": result.get("confidence_calibration") or [],
            "governed_mission_state": result.get("governed_mission_state"),
        }
        if result.get("context_dossier"):
            ai_payload["context_dossier"] = result["context_dossier"]
            ai_payload["context_dossier_provenance"] = result.get(
                "context_dossier_provenance"
            )

    run = IntelligenceRun(
        organization_id=organization_id,
        mission_id=mission.id,
        mission_code=mission_code,
        execution_mode=result["execution_mode"],
        status="completed" if execution else "completed_with_warning",
        engine_version=ENGINE_VERSION,
        provider=provenance.get("provider"),
        model=provenance.get("model_or_system"),
        provider_response_id=provenance.get("provider_response_id"),
        snapshot_hash=governed_context["state_hash"],
        input_json=_json(payload.model_dump(mode="json")),
        deterministic_json=_json(result["deterministic"]),
        ai_json=_json(ai_payload) if ai_payload else None,
        error=error,
        review_status="required",
        created_by_user_id=user_id,
    )
    db.add(run)
    db.flush()
    index_intelligence_run(db, run=run)
    turn = MissionDialogueTurn(
        session_id=session.id,
        intelligence_run_id=run.id,
        sequence=current_sequence + 1,
        intent=payload.intent.value,
        user_message=payload.message,
        answers_json=_json([item.model_dump(mode="json") for item in payload.answers]),
        attachment_ids_json=_json(payload.attachment_ids),
        created_by_user_id=user_id,
    )
    db.add(turn)
    session.updated_at = datetime.now(timezone.utc)
    if usage_event is not None:
        usage_event.intelligence_run_id = run.id
        db.add(usage_event)
    record_audit(
        db,
        action="mission_intelligence.dialogue_turn_executed",
        resource_type="mission_dialogue_turn",
        resource_id=turn.id,
        organization_id=organization_id,
        user_id=user_id,
        payload={
            "session_id": session.id,
            "run_id": run.id,
            "mission_code": mission_code,
            "intent": payload.intent.value,
            "ai_status": result["ai_status"],
            "snapshot_hash": governed_context["state_hash"],
            "canonical_mission_hash": mission.content_hash,
            "governed_state_schema": governed_context["schema"],
            "canonical_mutation": "none",
            "attachment_ids": payload.attachment_ids,
            "context_profile": (result.get("context_manifest") or {}).get(
                "context_profile"
            ),
            "context_retry_count": result.get("context_retry_count", 0),
        },
    )
    db.commit()
    if usage_event is not None:
        db.refresh(usage_event)
        result["ai_usage"] = usage_event_view(usage_event)
    result.update(
        run_id=run.id,
        turn_id=turn.id,
        turn_persisted=True,
        turn_sequence=turn.sequence,
        review_status=run.review_status,
        proposal_reviews=[],
    )
    return result


def _turn_view(turn: MissionDialogueTurn) -> dict[str, Any]:
    run = turn.intelligence_run
    ai = json.loads(run.ai_json) if run.ai_json else {}
    return {
        "turn_id": turn.id,
        "run_id": run.id,
        "sequence": turn.sequence,
        "intent": turn.intent,
        "user_message": turn.user_message,
        "answers": json.loads(turn.answers_json),
        "attachment_ids": json.loads(turn.attachment_ids_json),
        "ai_status": "completed" if ai.get("intelligence") else "failed",
        "ai_error": run.error,
        "intelligence": ai.get("intelligence"),
        "provenance": ai.get("provenance"),
        "context_dossier": ai.get("context_dossier"),
        "context_dossier_provenance": ai.get("context_dossier_provenance"),
        "attachments": ai.get("attachments") or [],
        "epistemic_ledger": ai.get("epistemic_ledger"),
        "attachment_trace": ai.get("attachment_trace") or [],
        "context_manifest": ai.get("context_manifest"),
        "context_retry_count": ai.get("context_retry_count", 0),
        "confidence_calibration": ai.get("confidence_calibration") or [],
        "governed_mission_state": ai.get("governed_mission_state"),
        "deterministic": json.loads(run.deterministic_json),
        "ai_usage": usage_event_view(run.ai_usage_event) if run.ai_usage_event else None,
        "review_status": run.review_status,
        "proposal_reviews": [
            _proposal_review_view(row) for row in turn.proposal_reviews
        ],
        "created_at": turn.created_at,
    }


def dialogue_session_view(session: MissionDialogueSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "mission_code": session.mission_code,
        "title": session.title,
        "objective": session.objective,
        "status": session.status,
        "snapshot_hash": session.snapshot_hash,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "turns": [_turn_view(turn) for turn in session.turns],
    }


def list_dialogue_sessions(
    db: Session,
    *,
    organization_id: str,
    mission_code: str | None = None,
) -> list[dict[str, Any]]:
    query = db.query(MissionDialogueSession).filter(
        MissionDialogueSession.organization_id == organization_id
    )
    if mission_code:
        query = query.filter(MissionDialogueSession.mission_code == mission_code)
    rows = query.order_by(MissionDialogueSession.updated_at.desc()).all()
    return [
        {
            "id": row.id,
            "mission_code": row.mission_code,
            "title": row.title,
            "objective": row.objective,
            "status": row.status,
            "snapshot_hash": row.snapshot_hash,
            "turn_count": len(row.turns),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]


def get_dialogue_session(
    db: Session,
    *,
    organization_id: str,
    session_id: str,
) -> MissionDialogueSession | None:
    return (
        db.query(MissionDialogueSession)
        .filter(
            MissionDialogueSession.id == session_id,
            MissionDialogueSession.organization_id == organization_id,
        )
        .one_or_none()
    )


def _find_proposal(
    intelligence: dict[str, Any],
    proposal_id: str,
) -> tuple[str, dict[str, Any]] | None:
    sections = {
        "hypothesis": "hypotheses",
        "alternative": "alternative_proposals",
        "criterion": "decision_criteria",
        "experiment": "experiment_proposals",
        "action": "recommended_actions",
    }
    for proposal_type, section in sections.items():
        for item in intelligence.get(section) or []:
            item_id = item.get("proposal_id") or item.get("action_id")
            if item_id == proposal_id:
                return proposal_type, item
    mission_path = intelligence.get("mission_path") or {}
    if isinstance(mission_path, dict):
        for stage, item in mission_path.items():
            if isinstance(item, dict) and item.get("proposal_id") == proposal_id:
                return f"mission_path:{stage}", item
    return None


def review_dialogue_proposal(
    db: Session,
    *,
    organization_id: str,
    session_id: str,
    turn_id: str,
    proposal_id: str,
    user_id: str,
    payload: MIProposalReviewRequest,
) -> dict[str, Any]:
    turn = (
        db.query(MissionDialogueTurn)
        .join(MissionDialogueSession)
        .filter(
            MissionDialogueTurn.id == turn_id,
            MissionDialogueTurn.session_id == session_id,
            MissionDialogueSession.organization_id == organization_id,
        )
        .one_or_none()
    )
    if turn is None:
        raise MIDialogueConflict(
            "turn_not_found",
            "O turno de Mission Intelligence não foi encontrado.",
        )
    ai = json.loads(turn.intelligence_run.ai_json) if turn.intelligence_run.ai_json else {}
    found = _find_proposal(ai.get("intelligence") or {}, proposal_id)
    if found is None:
        raise MIDialogueConflict(
            "proposal_not_found",
            "A proposta não foi encontrada neste turno de diálogo.",
        )
    proposal_type, proposal = found
    review = (
        db.query(MissionProposalReview)
        .filter(
            MissionProposalReview.turn_id == turn_id,
            MissionProposalReview.proposal_id == proposal_id,
        )
        .one_or_none()
    )
    if review is None:
        review = MissionProposalReview(
            organization_id=organization_id,
            session_id=session_id,
            turn_id=turn_id,
            proposal_id=proposal_id,
            proposal_type=proposal_type,
            decision=payload.decision,
            comment=payload.comment,
            reviewed_by_user_id=user_id,
        )
        db.add(review)
    else:
        review.decision = payload.decision
        review.comment = payload.comment
        review.reviewed_by_user_id = user_id
        review.updated_at = datetime.now(timezone.utc)
    db.flush()
    record_audit(
        db,
        action="mission_intelligence.proposal_reviewed",
        resource_type="mission_proposal_review",
        resource_id=review.id,
        organization_id=organization_id,
        user_id=user_id,
        payload={
            "session_id": session_id,
            "turn_id": turn_id,
            "proposal_id": proposal_id,
            "proposal_type": proposal_type,
            "decision": payload.decision,
            "canonical_effect": (
                "human_validated_proposal"
                if payload.decision == "human_validated"
                else "none"
            ),
            "mission_revision": turn.session.mission.revision,
            "mission_content_hash": turn.session.mission.content_hash,
            "proposal_snapshot": proposal,
        },
    )
    db.commit()
    db.refresh(review)
    return _proposal_review_view(review)
