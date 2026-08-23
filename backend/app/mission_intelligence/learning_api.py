from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.atlas_platform.audit import record_audit
from app.atlas_platform.auth import require_org_role
from app.atlas_platform.database import get_db
from app.atlas_platform.models import Membership, Role

from .contracts import (
    ConfidenceLevel,
    MissionDocumentV13,
    MissionRecord,
    MissionRelation,
    Provenance,
    RecordKind,
)
from .models import CanonicalMission, MissionRevision


router = APIRouter(
    prefix="/api/organizations/{organization_id}/mission-intelligence",
    tags=["Learning Inheritance"],
)

STOPWORDS = {
    "a", "ao", "aos", "as", "de", "da", "das", "do", "dos", "e", "em",
    "na", "nas", "no", "nos", "o", "os", "para", "por", "que", "com",
    "uma", "um", "the", "and", "for", "of", "to", "in", "on",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(document: MissionDocumentV13) -> str:
    payload = _json(document.model_dump(mode="json")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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


def _check_revision(row: CanonicalMission, expected_revision: int) -> None:
    if row.revision != expected_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "mission_revision_conflict",
                "message": (
                    "A missão foi alterada por outra operação. Atualize a aprendizagem "
                    "herdada e repita a revisão sobre a versão mais recente."
                ),
                "current_revision": row.revision,
            },
        )


def _persist_document(
    db: Session,
    *,
    row: CanonicalMission,
    document: MissionDocumentV13,
    organization_id: str,
    user_id: str,
    change_note: str,
    audit_action: str,
    audit_payload: dict[str, Any],
) -> None:
    document_json = _json(document.model_dump(mode="json"))
    content_hash = _hash(document)
    row.document_json = document_json
    row.content_hash = content_hash
    row.revision += 1
    db.add(
        MissionRevision(
            mission_id=row.id,
            revision=row.revision,
            document_json=document_json,
            content_hash=content_hash,
            change_note=change_note,
            created_by_user_id=user_id,
        )
    )
    record_audit(
        db,
        action=audit_action,
        resource_type="mission",
        resource_id=row.id,
        organization_id=organization_id,
        user_id=user_id,
        payload={**audit_payload, "revision": row.revision},
    )
    db.commit()
    db.refresh(row)


def _tokens(*values: str) -> set[str]:
    text = " ".join(values).casefold()
    return {
        token
        for token in re.findall(r"[\wÀ-ÿ-]+", text, flags=re.UNICODE)
        if len(token) >= 4 and token not in STOPWORDS
    }


def _mission_similarity(
    target: CanonicalMission,
    target_document: MissionDocumentV13,
    source: CanonicalMission,
    source_document: MissionDocumentV13,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if target.domain == source.domain:
        score += 40
        reasons.append("mesmo domínio")
    if target.parent_mission_id and target.parent_mission_id == source.parent_mission_id:
        score += 20
        reasons.append("mesma missão-mãe")
    if target.mission_kind == source.mission_kind:
        score += 5

    left = _tokens(target.title, target_document.context, target_document.central_question)
    right = _tokens(source.title, source_document.context, source_document.central_question)
    if left and right:
        overlap = len(left & right) / max(1, len(left | right))
        textual = min(35, round(overlap * 100))
        if textual:
            score += textual
            reasons.append(f"contexto relacionado ({textual}%)")
    return min(100, score), reasons


def _inheritance_key(source_mission_id: str, learning_id: str) -> str:
    return f"{source_mission_id}:{learning_id}"


def _inherited_record_id(source_mission_id: str, learning_id: str) -> str:
    digest = hashlib.sha256(
        f"{source_mission_id}\0{learning_id}".encode("utf-8")
    ).hexdigest()[:18].upper()
    return f"INH-{digest}"


def _decision_store(document: MissionDocumentV13) -> dict[str, Any]:
    container = document.metadata.get("learning_inheritance") or {}
    decisions = container.get("decisions") or {}
    return dict(decisions) if isinstance(decisions, dict) else {}


def _candidate_rows(
    db: Session,
    *,
    organization_id: str,
    target: CanonicalMission,
) -> list[dict[str, Any]]:
    target_document = _document(target)
    decisions = _decision_store(target_document)
    rows = (
        db.query(CanonicalMission)
        .filter(
            CanonicalMission.organization_id == organization_id,
            CanonicalMission.id != target.id,
            CanonicalMission.lifecycle_state != "archived",
        )
        .order_by(CanonicalMission.updated_at.desc())
        .all()
    )
    candidates: list[dict[str, Any]] = []
    for source in rows:
        source_document = _document(source)
        score, reasons = _mission_similarity(
            target,
            target_document,
            source,
            source_document,
        )
        for learning in source_document.records:
            if learning.kind != RecordKind.LEARNING:
                continue
            if learning.metadata.get("inherited_learning"):
                # Do not create recursive copies of inherited records. Mission C
                # should see the original learning plus any genuinely new learning
                # produced in Mission B.
                continue
            key = _inheritance_key(source.id, learning.canonical_id)
            candidates.append(
                {
                    "inheritance_key": key,
                    "relevance_score": score,
                    "relevance_reasons": reasons,
                    "source_mission": {
                        "id": source.id,
                        "code": source.code,
                        "title": source.title,
                        "domain": source.domain,
                        "revision": source.revision,
                        "updated_at": source.updated_at,
                        "context": source_document.context,
                        "horizon": str(source_document.metadata.get("horizon") or ""),
                    },
                    "learning": {
                        "canonical_id": learning.canonical_id,
                        "title": learning.title,
                        "description": learning.description,
                        "state": learning.state,
                        "confidence": learning.confidence.value,
                        "observed_at": learning.observed_at,
                        "metadata": learning.metadata,
                    },
                    "decision": decisions.get(key),
                }
            )
    return sorted(
        candidates,
        key=lambda item: (
            -(item["relevance_score"] or 0),
            str(item["source_mission"]["updated_at"]),
        ),
        reverse=False,
    )


class LearningCreateRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    title: str = Field(min_length=3, max_length=500)
    description: str = Field(min_length=10, max_length=30000)
    based_on_ids: list[str] = Field(default_factory=list, max_length=100)
    validity_conditions: list[str] = Field(default_factory=list, max_length=50)
    invalidation_triggers: list[str] = Field(default_factory=list, max_length=50)
    confidence: Literal["high", "moderate", "low", "not_evaluable"] = "moderate"


class LearningDispositionRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    disposition: Literal[
        "still_valid",
        "requires_revalidation",
        "invalidated",
    ]
    rationale: str = Field(min_length=3, max_length=10000)
    context_change: str = Field(default="", max_length=10000)

    @model_validator(mode="after")
    def context_change_for_non_valid(self) -> "LearningDispositionRequest":
        if self.disposition in {"requires_revalidation", "invalidated"} and not self.context_change:
            raise ValueError(
                "Indique o que mudou no contexto quando a aprendizagem exige revalidação ou é invalidada"
            )
        return self


@router.get("/missions/{mission_id}/learning-inheritance")
def get_learning_inheritance(
    organization_id: str,
    mission_id: str,
    _: Membership = Depends(
        require_org_role(
            Role.OWNER.value,
            Role.ADMIN.value,
            Role.REVIEWER.value,
            Role.CONTRIBUTOR.value,
            Role.OBSERVER.value,
        )
    ),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    target = _mission_or_404(
        db,
        organization_id=organization_id,
        mission_id=mission_id,
    )
    document = _document(target)
    candidates = _candidate_rows(
        db,
        organization_id=organization_id,
        target=target,
    )
    decisions = _decision_store(document)
    accepted = [
        item
        for item in candidates
        if (item.get("decision") or {}).get("disposition") == "still_valid"
    ]
    revalidation = [
        item
        for item in candidates
        if (item.get("decision") or {}).get("disposition") == "requires_revalidation"
    ]
    invalidated = [
        item
        for item in candidates
        if (item.get("decision") or {}).get("disposition") == "invalidated"
    ]
    return {
        "schema": "sris.learning_inheritance",
        "schema_version": "0.1",
        "target_mission": {
            "id": target.id,
            "code": target.code,
            "title": target.title,
            "domain": target.domain,
            "revision": target.revision,
            "updated_at": target.updated_at,
        },
        "principle": (
            "Cada missão começa com aquilo que a organização já aprendeu, sem assumir "
            "que aquilo que era válido antes continua necessariamente válido agora."
        ),
        "candidates": candidates,
        "summary": {
            "candidate_count": len(candidates),
            "reviewed_count": len(decisions),
            "still_valid_count": len(accepted),
            "requires_revalidation_count": len(revalidation),
            "invalidated_count": len(invalidated),
        },
        "mission_context_effect": {
            "inherited_valid": [
                {
                    "source": item["source_mission"]["code"],
                    "learning_id": item["learning"]["canonical_id"],
                    "statement": item["learning"]["description"],
                    "review": item["decision"],
                }
                for item in accepted
            ],
            "open_revalidation_questions": [
                {
                    "source": item["source_mission"]["code"],
                    "learning_id": item["learning"]["canonical_id"],
                    "statement": item["learning"]["description"],
                    "context_change": (item["decision"] or {}).get("context_change", ""),
                }
                for item in revalidation
            ],
        },
    }


@router.post("/missions/{mission_id}/learnings", status_code=201)
def create_canonical_learning(
    organization_id: str,
    mission_id: str,
    payload: LearningCreateRequest,
    membership: Membership = Depends(
        require_org_role(
            Role.OWNER.value,
            Role.ADMIN.value,
            Role.REVIEWER.value,
            Role.CONTRIBUTOR.value,
        )
    ),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row = _mission_or_404(
        db,
        organization_id=organization_id,
        mission_id=mission_id,
    )
    _check_revision(row, payload.expected_revision)
    document = _document(row)
    known_ids = {record.canonical_id for record in document.records}
    unknown = set(payload.based_on_ids) - known_ids
    if unknown:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "unknown_learning_basis",
                "message": "A aprendizagem referencia registos que não existem na missão.",
                "unknown_ids": sorted(unknown),
            },
        )

    learning_id = f"LRN-{uuid4().hex[:12].upper()}"
    record = MissionRecord(
        canonical_id=learning_id,
        kind=RecordKind.LEARNING,
        title=payload.title,
        description=payload.description,
        state="validated_learning",
        confidence=ConfidenceLevel(payload.confidence),
        provenance=Provenance(
            origin_type="human",
            source=f"mission:{row.code}",
            method="Aprendizagem promovida explicitamente por revisão humana.",
            limitations=(
                "A aprendizagem é válida apenas dentro das condições declaradas e "
                "deve ser reavaliada quando o contexto material se altera."
            ),
            verification_status="confirmed",
        ),
        observed_at=_utcnow(),
        metadata={
            "validity_conditions": payload.validity_conditions,
            "invalidation_triggers": payload.invalidation_triggers,
            "based_on_ids": payload.based_on_ids,
            "learning_contract_version": "0.1",
        },
    )
    relations = list(document.relations)
    for basis_id in payload.based_on_ids:
        relations.append(
            MissionRelation(
                relation_id=f"REL-{uuid4().hex[:12].upper()}",
                source_id=learning_id,
                target_id=basis_id,
                relation_type="derived_from",
                explanation="A aprendizagem foi explicitamente ligada a este registo de base.",
                confidence=ConfidenceLevel(payload.confidence),
            )
        )
    updated = document.model_copy(
        update={"records": [*document.records, record], "relations": relations}
    )
    _persist_document(
        db,
        row=row,
        document=updated,
        organization_id=organization_id,
        user_id=membership.user_id,
        change_note=f"Aprendizagem canónica {learning_id} promovida por revisão humana.",
        audit_action="mission_intelligence.learning_created",
        audit_payload={
            "learning_id": learning_id,
            "based_on_ids": payload.based_on_ids,
        },
    )
    return {
        "status": "created",
        "mission_id": row.id,
        "mission_code": row.code,
        "revision": row.revision,
        "learning": record.model_dump(mode="json"),
    }


@router.post(
    "/missions/{mission_id}/learning-inheritance/{source_mission_id}/{learning_id}"
)
def review_inherited_learning(
    organization_id: str,
    mission_id: str,
    source_mission_id: str,
    learning_id: str,
    payload: LearningDispositionRequest,
    membership: Membership = Depends(
        require_org_role(
            Role.OWNER.value,
            Role.ADMIN.value,
            Role.REVIEWER.value,
            Role.CONTRIBUTOR.value,
        )
    ),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    target = _mission_or_404(
        db,
        organization_id=organization_id,
        mission_id=mission_id,
    )
    source = _mission_or_404(
        db,
        organization_id=organization_id,
        mission_id=source_mission_id,
    )
    if target.id == source.id:
        raise HTTPException(status_code=422, detail="A missão não pode herdar de si própria")
    _check_revision(target, payload.expected_revision)

    target_document = _document(target)
    source_document = _document(source)
    source_learning = next(
        (
            record
            for record in source_document.records
            if record.canonical_id == learning_id and record.kind == RecordKind.LEARNING
        ),
        None,
    )
    if source_learning is None or source_learning.metadata.get("inherited_learning"):
        raise HTTPException(status_code=404, detail="Source learning not found")

    key = _inheritance_key(source.id, source_learning.canonical_id)
    inherited_id = _inherited_record_id(source.id, source_learning.canonical_id)
    reviewed_at = _utcnow()
    decision = {
        "inheritance_key": key,
        "source_mission_id": source.id,
        "source_mission_code": source.code,
        "source_mission_revision": source.revision,
        "source_mission_content_hash": source.content_hash,
        "source_learning_id": source_learning.canonical_id,
        "source_learning_title": source_learning.title,
        "disposition": payload.disposition,
        "rationale": payload.rationale,
        "context_change": payload.context_change,
        "reviewed_at": reviewed_at.isoformat(),
        "reviewed_by_user_id": membership.user_id,
    }

    # Replace the prior materialized inheritance object, if any. The historical
    # decision remains preserved in MissionRevision even when its current status changes.
    records = [
        record
        for record in target_document.records
        if record.canonical_id != inherited_id
    ]

    if payload.disposition == "still_valid":
        records.append(
            MissionRecord(
                canonical_id=inherited_id,
                kind=RecordKind.LEARNING,
                title=f"Herdada · {source_learning.title}",
                description=source_learning.description,
                state="inherited_valid",
                confidence=source_learning.confidence,
                provenance=Provenance(
                    origin_type="human",
                    source=f"mission:{source.code}/{source_learning.canonical_id}",
                    method="Revisão humana explícita da aplicabilidade entre missões.",
                    limitations=(
                        "Aprendizagem herdada. A validade depende do contexto atual e "
                        "deve ser reavaliada quando condições materiais mudarem."
                    ),
                    verification_status="confirmed",
                ),
                observed_at=source_learning.observed_at or reviewed_at,
                metadata={
                    "inherited_learning": True,
                    "inheritance_key": key,
                    "source_mission_id": source.id,
                    "source_mission_code": source.code,
                    "source_learning_id": source_learning.canonical_id,
                    "source_revision": source.revision,
                    "source_context_hash": source.content_hash,
                    "reviewed_at": reviewed_at.isoformat(),
                    "rationale": payload.rationale,
                    "original_metadata": source_learning.metadata,
                },
            )
        )
    elif payload.disposition == "requires_revalidation":
        records.append(
            MissionRecord(
                canonical_id=inherited_id,
                kind=RecordKind.HYPOTHESIS,
                title=f"Revalidar aprendizagem · {source_learning.title}",
                description=(
                    f"Aprendizagem anterior potencialmente relevante: {source_learning.description}\n\n"
                    f"Mudança de contexto declarada: {payload.context_change}"
                ),
                state="requires_revalidation",
                confidence=ConfidenceLevel.LOW,
                provenance=Provenance(
                    origin_type="human",
                    source=f"mission:{source.code}/{source_learning.canonical_id}",
                    method="Revisão humana de transferência de aprendizagem entre missões.",
                    limitations=(
                        "Não tratar como aprendizagem válida até existir evidência suficiente "
                        "no contexto da missão atual."
                    ),
                    verification_status="in_review",
                ),
                observed_at=reviewed_at,
                metadata={
                    "inherited_learning": True,
                    "inheritance_key": key,
                    "source_mission_id": source.id,
                    "source_mission_code": source.code,
                    "source_learning_id": source_learning.canonical_id,
                    "source_revision": source.revision,
                    "source_context_hash": source.content_hash,
                    "reviewed_at": reviewed_at.isoformat(),
                    "rationale": payload.rationale,
                    "context_change": payload.context_change,
                    "revalidation_required": True,
                },
            )
        )

    metadata = dict(target_document.metadata)
    inheritance = dict(metadata.get("learning_inheritance") or {})
    decisions = dict(inheritance.get("decisions") or {})
    decisions[key] = decision
    inheritance.update(
        contract_version="0.1",
        decisions=decisions,
        last_reviewed_at=reviewed_at.isoformat(),
        principle=(
            "Cada missão começa com aquilo que a organização já aprendeu, sem assumir "
            "que aquilo que era válido antes continua necessariamente válido agora."
        ),
    )
    metadata["learning_inheritance"] = inheritance
    updated = target_document.model_copy(update={"records": records, "metadata": metadata})

    _persist_document(
        db,
        row=target,
        document=updated,
        organization_id=organization_id,
        user_id=membership.user_id,
        change_note=(
            f"Aprendizagem {source.code}/{source_learning.canonical_id}: "
            f"{payload.disposition}."
        ),
        audit_action="mission_intelligence.learning_inheritance_reviewed",
        audit_payload={
            "source_mission_id": source.id,
            "source_mission_code": source.code,
            "source_learning_id": source_learning.canonical_id,
            "disposition": payload.disposition,
            "materialized_record_id": (
                inherited_id if payload.disposition != "invalidated" else None
            ),
        },
    )
    return {
        "status": "reviewed",
        "target_mission_id": target.id,
        "target_mission_code": target.code,
        "revision": target.revision,
        "decision": decision,
        "materialized_record": (
            inherited_id if payload.disposition != "invalidated" else None
        ),
        "effect": (
            "canonical_learning"
            if payload.disposition == "still_valid"
            else "open_hypothesis"
            if payload.disposition == "requires_revalidation"
            else "not_carried_forward"
        ),
    }
