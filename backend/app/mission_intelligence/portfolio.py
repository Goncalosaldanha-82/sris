from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.atlas_platform.audit import record_audit
from app.pilot_readiness import mission_completion_readiness

from .contracts import MissionCreateRequest, MissionDocumentV13, MissionUpdateRequest
from .models import CanonicalMission, MissionRevision

MAX_MISSION_DEPTH = 6


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(document: MissionDocumentV13) -> str:
    payload = _json(document.model_dump(mode="json")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _document(row: CanonicalMission) -> MissionDocumentV13:
    try:
        return MissionDocumentV13.model_validate_json(row.document_json)
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "invalid_mission_document",
                "message": "A missão canónica não passou a validação de integridade.",
            },
        ) from exc


def _mission_or_404(
    db: Session,
    *,
    organization_id: str,
    mission_id: str,
) -> CanonicalMission:
    row = (
        db.query(CanonicalMission)
        .filter(
            CanonicalMission.id == mission_id,
            CanonicalMission.organization_id == organization_id,
        )
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return row


def _lineage(
    db: Session,
    *,
    organization_id: str,
    row: CanonicalMission,
) -> list[CanonicalMission]:
    lineage: list[CanonicalMission] = []
    seen = {row.id}
    parent_id = row.parent_mission_id
    while parent_id:
        parent = (
            db.query(CanonicalMission)
            .filter(
                CanonicalMission.id == parent_id,
                CanonicalMission.organization_id == organization_id,
            )
            .one_or_none()
        )
        if parent is None or parent.id in seen:
            break
        lineage.append(parent)
        seen.add(parent.id)
        parent_id = parent.parent_mission_id
    lineage.reverse()
    return lineage


def _descendant_height(
    db: Session,
    *,
    organization_id: str,
    mission_id: str,
) -> int:
    """Return the longest number of edges below a mission."""

    rows = (
        db.query(CanonicalMission.id, CanonicalMission.parent_mission_id)
        .filter(CanonicalMission.organization_id == organization_id)
        .all()
    )
    children: dict[str, list[str]] = {}
    for child_id, parent_id in rows:
        if parent_id:
            children.setdefault(parent_id, []).append(child_id)

    height = 0
    stack = [(mission_id, 0)]
    seen: set[str] = set()
    while stack:
        current_id, current_depth = stack.pop()
        if current_id in seen:
            continue
        seen.add(current_id)
        height = max(height, current_depth)
        stack.extend(
            (child_id, current_depth + 1)
            for child_id in children.get(current_id, [])
        )
    return height


def _validated_parent(
    db: Session,
    *,
    organization_id: str,
    parent_mission_id: str | None,
    mission: CanonicalMission | None = None,
) -> CanonicalMission | None:
    if parent_mission_id is None:
        return None
    parent = _mission_or_404(
        db,
        organization_id=organization_id,
        mission_id=parent_mission_id,
    )
    if mission is not None and parent.id == mission.id:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "mission_hierarchy_cycle",
                "message": "Uma missão não pode ser subordinada a si própria.",
            },
        )

    seen = {mission.id} if mission is not None else set()
    cursor: CanonicalMission | None = parent
    depth = 1
    while cursor is not None:
        if cursor.id in seen:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "mission_hierarchy_cycle",
                    "message": "A alteração criaria um ciclo na árvore de missões.",
                },
            )
        seen.add(cursor.id)
        if depth >= MAX_MISSION_DEPTH:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "mission_hierarchy_too_deep",
                    "message": (
                        f"A hierarquia admite no máximo {MAX_MISSION_DEPTH} níveis."
                    ),
                },
            )
        if cursor.parent_mission_id is None:
            break
        cursor = (
            db.query(CanonicalMission)
            .filter(
                CanonicalMission.id == cursor.parent_mission_id,
                CanonicalMission.organization_id == organization_id,
            )
            .one_or_none()
        )
        depth += 1

    if mission is not None:
        descendant_height = _descendant_height(
            db,
            organization_id=organization_id,
            mission_id=mission.id,
        )
        if depth + descendant_height >= MAX_MISSION_DEPTH:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "mission_hierarchy_too_deep",
                    "message": (
                        "A alteração colocaria uma sub-missão para além dos "
                        f"{MAX_MISSION_DEPTH} níveis admitidos."
                    ),
                },
            )
    return parent


def _next_code(db: Session, *, organization_id: str, mission_kind: str) -> str:
    # Institutional codes deliberately avoid the governed public-demo namespace
    # (P-xxx/M-xxx), so creating a mission can never hide a demonstration case.
    prefix = "PRG" if mission_kind == "program" else "MIS"
    codes = (
        db.query(CanonicalMission.code)
        .filter(CanonicalMission.organization_id == organization_id)
        .all()
    )
    pattern = re.compile(rf"^{prefix}-(\d+)$", re.IGNORECASE)
    used = {
        int(match.group(1))
        for (code,) in codes
        if (match := pattern.match(code or "")) is not None
    }
    number = 1
    while number in used:
        number += 1
    return f"{prefix}-{number:03d}"


def _normalise_code(value: str) -> str:
    return value.strip().upper()


def _initial_document(
    *,
    code: str,
    payload: MissionCreateRequest,
    parent: CanonicalMission | None,
) -> MissionDocumentV13:
    return MissionDocumentV13(
        mission_id=code,
        title=payload.title,
        context=payload.context,
        central_question=payload.central_question,
        records=[],
        relations=[],
        metadata={
            "source_format": "institutional_mission_builder",
            "objective": payload.objective,
            "mission_kind": payload.mission_kind,
            "domain": payload.domain,
            "priority": payload.priority,
            "horizon": payload.horizon,
            "stakeholders": payload.stakeholders,
            "validation_profile": payload.validation_profile,
            "hierarchy": {
                "parent_mission_id": parent.id if parent else None,
                "parent_mission_code": parent.code if parent else None,
            },
            "analysis_requirements": {
                "context_research_required": True,
                "human_review_required": True,
                "evidence_register_required": True,
            },
            "epistemic_boundary": (
                "O objetivo, o contexto e a pergunta central são declarações de "
                "enquadramento. Não constituem evidência até serem suportados por "
                "registos com proveniência e revisão humana."
            ),
        },
    )


def create_mission(
    db: Session,
    *,
    organization_id: str,
    user_id: str,
    payload: MissionCreateRequest,
) -> dict[str, Any]:
    parent = _validated_parent(
        db,
        organization_id=organization_id,
        parent_mission_id=payload.parent_mission_id,
    )
    code = _normalise_code(
        payload.code
        or _next_code(
            db,
            organization_id=organization_id,
            mission_kind=payload.mission_kind,
        )
    )
    existing = (
        db.query(CanonicalMission.id)
        .filter(
            CanonicalMission.organization_id == organization_id,
            CanonicalMission.code == code,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "mission_code_exists",
                "message": "Já existe uma missão com este código na organização.",
            },
        )

    document = _initial_document(code=code, payload=payload, parent=parent)
    document_json = _json(document.model_dump(mode="json"))
    content_hash = _hash(document)
    row = CanonicalMission(
        organization_id=organization_id,
        parent_mission_id=parent.id if parent else None,
        code=code,
        title=payload.title,
        mission_kind=payload.mission_kind,
        domain=payload.domain,
        priority=payload.priority,
        schema_version=document.schema_version,
        document_json=document_json,
        content_hash=content_hash,
        revision=1,
        lifecycle_state="active",
        created_by_user_id=user_id,
    )
    db.add(row)
    db.flush()
    if payload.validation_profile != "none":
        from app.pilot_validation import seed_validation_protocol

        seed_validation_protocol(
            db,
            organization_id=organization_id,
            mission=row,
            profile=payload.validation_profile,
            user_id=user_id,
        )
    db.add(
        MissionRevision(
            mission_id=row.id,
            revision=1,
            document_json=document_json,
            content_hash=content_hash,
            change_note="Missão criada no construtor institucional.",
            created_by_user_id=user_id,
        )
    )
    record_audit(
        db,
        action="mission_intelligence.mission_created",
        resource_type="mission",
        resource_id=row.id,
        organization_id=organization_id,
        user_id=user_id,
        payload={
            "code": code,
            "mission_kind": payload.mission_kind,
            "parent_mission_id": row.parent_mission_id,
            "revision": 1,
        },
    )
    db.commit()
    db.refresh(row)
    return mission_view(db, organization_id=organization_id, row=row)


def _updated_document(
    *,
    row: CanonicalMission,
    document: MissionDocumentV13,
    payload: MissionUpdateRequest,
    parent: CanonicalMission | None,
) -> MissionDocumentV13:
    metadata = dict(document.metadata)
    hierarchy = dict(metadata.get("hierarchy") or {})
    hierarchy.update(
        parent_mission_id=parent.id if parent else None,
        parent_mission_code=parent.code if parent else None,
    )
    metadata["hierarchy"] = hierarchy
    for field in (
        "objective",
        "mission_kind",
        "domain",
        "priority",
        "horizon",
        "validation_profile",
    ):
        value = getattr(payload, field)
        if value is not None:
            metadata[field] = value
    if payload.stakeholders is not None:
        metadata["stakeholders"] = payload.stakeholders
    metadata["lifecycle_state"] = payload.lifecycle_state or row.lifecycle_state

    return document.model_copy(
        update={
            "title": payload.title or document.title,
            "context": payload.context or document.context,
            "central_question": payload.central_question or document.central_question,
            "metadata": metadata,
        }
    )


def update_mission(
    db: Session,
    *,
    organization_id: str,
    mission_id: str,
    user_id: str,
    payload: MissionUpdateRequest,
) -> dict[str, Any]:
    row = _mission_or_404(
        db,
        organization_id=organization_id,
        mission_id=mission_id,
    )
    if row.revision != payload.expected_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "mission_revision_conflict",
                "message": (
                    "A missão foi alterada por outra operação. Atualize a página e "
                    "repita a edição sobre a revisão mais recente."
                ),
                "current_revision": row.revision,
            },
        )

    if row.lifecycle_state in {"completed", "archived"}:
        substantive_fields = payload.model_fields_set - {
            "expected_revision",
            "lifecycle_state",
            "change_note",
        }
        lifecycle_changes = (
            payload.lifecycle_state is not None
            and payload.lifecycle_state != row.lifecycle_state
        )
        if substantive_fields or not lifecycle_changes:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "mission_reactivation_required",
                    "message": (
                        "Reative primeiro a missão numa alteração própria. A versão "
                        "concluída ou arquivada não pode ser reescrita juntamente com "
                        "conteúdo novo."
                    ),
                    "lifecycle_state": row.lifecycle_state,
                },
            )

    if payload.lifecycle_state == "completed" and row.lifecycle_state != "completed":
        readiness = mission_completion_readiness(
            db,
            organization_id=organization_id,
            mission_id=row.id,
            mission_code=row.code,
        )
        if not readiness["ready"]:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "mission_completion_blocked",
                    "message": (
                        "A missão ainda não pode ser concluída. Complete o percurso "
                        "documento → evidência → hipótese → alternativa → decisão → "
                        "resultado → aprendizagem revista e publicada."
                    ),
                    "readiness": readiness,
                },
            )

    parent_id = row.parent_mission_id
    if payload.clear_parent:
        parent_id = None
    elif payload.parent_mission_id is not None:
        parent_id = payload.parent_mission_id
    parent = _validated_parent(
        db,
        organization_id=organization_id,
        parent_mission_id=parent_id,
        mission=row,
    )

    document = _document(row)
    updated = _updated_document(
        row=row,
        document=document,
        payload=payload,
        parent=parent,
    )
    document_json = _json(updated.model_dump(mode="json"))
    content_hash = _hash(updated)

    row.parent_mission_id = parent.id if parent else None
    row.title = updated.title
    row.mission_kind = payload.mission_kind or row.mission_kind
    row.domain = payload.domain or row.domain
    row.priority = payload.priority or row.priority
    row.lifecycle_state = payload.lifecycle_state or row.lifecycle_state
    row.document_json = document_json
    row.content_hash = content_hash
    row.revision += 1
    validation_profile = str(updated.metadata.get("validation_profile") or "none")
    if validation_profile != "none":
        from app.pilot_validation import seed_validation_protocol

        seed_validation_protocol(
            db,
            organization_id=organization_id,
            mission=row,
            profile=validation_profile,
            user_id=user_id,
        )
    db.add(
        MissionRevision(
            mission_id=row.id,
            revision=row.revision,
            document_json=document_json,
            content_hash=content_hash,
            change_note=payload.change_note,
            created_by_user_id=user_id,
        )
    )
    record_audit(
        db,
        action="mission_intelligence.mission_revised",
        resource_type="mission",
        resource_id=row.id,
        organization_id=organization_id,
        user_id=user_id,
        payload={
            "code": row.code,
            "revision": row.revision,
            "lifecycle_state": row.lifecycle_state,
            "parent_mission_id": row.parent_mission_id,
            "change_note": payload.change_note,
        },
    )
    db.commit()
    db.refresh(row)
    return mission_view(db, organization_id=organization_id, row=row)


def mission_view(
    db: Session,
    *,
    organization_id: str,
    row: CanonicalMission,
    children_counts: Counter[str] | None = None,
) -> dict[str, Any]:
    document = _document(row)
    metadata = document.metadata
    lineage = _lineage(db, organization_id=organization_id, row=row)
    if children_counts is None:
        children_counts = Counter(
            parent_id
            for (parent_id,) in db.query(CanonicalMission.parent_mission_id)
            .filter(
                CanonicalMission.organization_id == organization_id,
                CanonicalMission.parent_mission_id.isnot(None),
            )
            .all()
            if parent_id
        )
    parent = lineage[-1] if lineage else None
    record_counts = Counter(record.kind.value for record in document.records)
    records = [
        {
            "canonical_id": record.canonical_id,
            "kind": record.kind.value,
            "title": record.title,
            "description": record.description,
            "state": record.state,
            "confidence": record.confidence.value,
            "provenance": record.provenance.model_dump(mode="json"),
        }
        for record in document.records
    ]
    return {
        "id": row.id,
        "code": row.code,
        "title": row.title,
        "objective": str(metadata.get("objective") or ""),
        "context": document.context,
        "central_question": document.central_question,
        "mission_kind": row.mission_kind,
        "domain": row.domain,
        "priority": row.priority,
        "horizon": str(metadata.get("horizon") or ""),
        "stakeholders": list(metadata.get("stakeholders") or []),
        "validation_profile": str(metadata.get("validation_profile") or "none"),
        "parent_mission_id": row.parent_mission_id,
        "parent_code": parent.code if parent else None,
        "depth": len(lineage),
        "path_codes": [ancestor.code for ancestor in lineage] + [row.code],
        "children_count": children_counts[row.id],
        "schema_version": row.schema_version,
        "revision": row.revision,
        "content_hash": row.content_hash,
        "lifecycle_state": row.lifecycle_state,
        "record_counts": dict(record_counts),
        "records": records,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_mission_portfolio(
    db: Session,
    *,
    organization_id: str,
) -> list[dict[str, Any]]:
    rows = (
        db.query(CanonicalMission)
        .filter(CanonicalMission.organization_id == organization_id)
        .order_by(
            CanonicalMission.sort_order.asc(),
            CanonicalMission.created_at.asc(),
        )
        .all()
    )
    children_counts = Counter(
        row.parent_mission_id for row in rows if row.parent_mission_id is not None
    )
    views = [
        mission_view(
            db,
            organization_id=organization_id,
            row=row,
            children_counts=children_counts,
        )
        for row in rows
    ]
    return sorted(
        views,
        key=lambda item: (
            item["path_codes"],
            0 if item["mission_kind"] == "program" else 1,
            item["title"].casefold(),
        ),
    )
