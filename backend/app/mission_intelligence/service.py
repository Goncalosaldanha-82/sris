from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.atlas_platform.audit import record_audit

from .ai import AIUnavailableError, analyze_with_openai, is_ai_configured
from .canonical import legacy_to_canonical
from .catalog import demo_mission
from .contracts import AnalysisInput, MissionDocumentV13
from .engine import ENGINE_VERSION, analyze_mission
from .models import CanonicalMission, IntelligenceRun, MissionRevision


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(document: MissionDocumentV13) -> str:
    return hashlib.sha256(_json(document.model_dump(mode="json")).encode("utf-8")).hexdigest()


def _legacy_or_error(mission_code: str) -> dict[str, Any]:
    mission = demo_mission(mission_code)
    if mission is None:
        raise KeyError(mission_code)
    return mission


def analyze_demo(
    mission_code: str,
    payload: AnalysisInput,
    *,
    allow_ai: bool = False,
) -> dict[str, Any]:
    legacy = _legacy_or_error(mission_code)
    document = legacy_to_canonical(legacy, payload)
    deterministic = analyze_mission(document)
    result: dict[str, Any] = {
        "schema": "sris_mission_intelligence_result",
        "schema_version": "1.0",
        "mission_id": document.mission_id,
        "snapshot_hash": _hash(document),
        "execution_mode": "deterministic",
        "deterministic": deterministic.model_dump(mode="json"),
        "ai": None,
        "ai_status": "not_requested",
        "human_review_required": True,
    }
    if payload.use_ai and not allow_ai:
        result["ai_status"] = "authentication_required"
    elif payload.use_ai and allow_ai:
        if not is_ai_configured():
            result["ai_status"] = "not_configured"
        else:
            try:
                execution = analyze_with_openai(document, deterministic)
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
                        },
                    },
                )
            except AIUnavailableError as exc:
                result["ai_status"] = "failed"
                result["ai_error"] = str(exc)
    return result


def persist_demo_mission(
    db: Session,
    *,
    organization_id: str,
    user_id: str,
    mission_code: str,
    payload: AnalysisInput,
) -> tuple[CanonicalMission, MissionDocumentV13]:
    legacy = _legacy_or_error(mission_code)
    document = legacy_to_canonical(legacy, payload)
    document_json = _json(document.model_dump(mode="json"))
    content_hash = _hash(document)
    mission = (
        db.query(CanonicalMission)
        .filter(
            CanonicalMission.organization_id == organization_id,
            CanonicalMission.code == mission_code,
        )
        .one_or_none()
    )
    if mission is None:
        mission = CanonicalMission(
            organization_id=organization_id,
            code=mission_code,
            title=document.title,
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


def run_organizational_analysis(
    db: Session,
    *,
    organization_id: str,
    user_id: str,
    mission_code: str,
    payload: AnalysisInput,
) -> dict[str, Any]:
    mission, document = persist_demo_mission(
        db,
        organization_id=organization_id,
        user_id=user_id,
        mission_code=mission_code,
        payload=payload,
    )
    result = analyze_demo(mission_code, payload, allow_ai=True)
    ai = result.get("ai") or {}
    provenance = ai.get("provenance") or {}
    status = "completed" if result["ai_status"] != "failed" else "completed_with_warning"
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
    return {
        "id": run.id,
        "mission_code": run.mission_code,
        "execution_mode": run.execution_mode,
        "status": run.status,
        "engine_version": run.engine_version,
        "provider": run.provider,
        "model": run.model,
        "snapshot_hash": run.snapshot_hash,
        "deterministic": json.loads(run.deterministic_json),
        "ai": json.loads(run.ai_json) if run.ai_json else None,
        "error": run.error,
        "review_status": run.review_status,
        "review_comment": run.review_comment,
        "created_at": run.created_at,
        "reviewed_at": run.reviewed_at,
    }
