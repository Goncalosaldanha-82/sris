from __future__ import annotations

import hashlib
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.atlas_platform.auth import current_user
from app.atlas_platform.audit import record_audit
from app.atlas_platform.database import get_db
from app.atlas_platform.models import Role, User
from app.evidence_graph import (
    GraphNodeUpdate,
    _edge_view,
    _ensure_schema,
    _membership,
    _mission,
    _require_mission_mutable,
    _node_view,
    _upsert_edge,
    _upsert_node,
    get_mission_graph as legacy_get_mission_graph,
    router as legacy_router,
    sync_mission_graph as legacy_sync_mission_graph,
)
from app.mission_intelligence.mission_archive import _decrypt_chunk
from app.mission_intelligence.models import MissionArchiveChunk, MissionAttachment
from app.pilot_intelligence import _ensure_interaction_schema


NodeType = Literal[
    "observation",
    "evidence",
    "claim",
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
]
NodeStatus = Literal["proposed", "verified", "accepted", "rejected", "superseded"]
EdgeType = Literal[
    "supports",
    "contradicts",
    "informs",
    "derived_from",
    "tests",
    "leads_to",
    "validates",
    "invalidates",
    "supersedes",
    "learned_from",
    "depends_on",
    "constrained_by",
    "assumes",
    "requires",
    "addresses",
]

NODE_TYPES: list[str] = [
    "observation",
    "evidence",
    "claim",
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
]
EDGE_TYPES: list[str] = [
    "supports",
    "contradicts",
    "informs",
    "derived_from",
    "tests",
    "leads_to",
    "validates",
    "invalidates",
    "supersedes",
    "learned_from",
    "depends_on",
    "constrained_by",
    "assumes",
    "requires",
    "addresses",
]
WRITER_ROLES = {
    Role.OWNER.value,
    Role.ADMIN.value,
    Role.REVIEWER.value,
    Role.CONTRIBUTOR.value,
}
REVIEWER_ROLES = {
    Role.OWNER.value,
    Role.ADMIN.value,
    Role.REVIEWER.value,
}


def _require_writer(membership) -> None:
    if membership.role not in WRITER_ROLES:
        raise HTTPException(status_code=403, detail="A sua função permite consultar, mas não alterar evidência.")


def _require_reviewer(membership) -> None:
    if membership.role not in REVIEWER_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Aceitar, verificar, rejeitar ou substituir um objeto exige a função de revisor ou administrador.",
        )


class GraphNodeCreate(BaseModel):
    node_type: NodeType
    label: str = Field(min_length=2, max_length=300)
    body: str = Field(default="", max_length=50000)
    status: NodeStatus = "proposed"
    confidence: float | None = Field(default=None, ge=0, le=1)
    provenance: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_meaningful_content(self) -> "GraphNodeCreate":
        self.label = " ".join(self.label.split())
        if len(str(self.label or "").strip()) < 2:
            raise ValueError("Identifique este objeto com um rótulo legível.")
        if len(str(self.body or "").strip()) < 2:
            raise ValueError("Descreva o conteúdo deste objeto antes de o guardar.")
        return self


class GraphEdgeCreate(BaseModel):
    from_node_id: str = Field(min_length=8, max_length=64)
    to_node_id: str = Field(min_length=8, max_length=64)
    edge_type: EdgeType
    provenance: dict = Field(default_factory=dict)


class DocumentEvidenceCreate(BaseModel):
    chunk_id: str | None = Field(default=None, min_length=8, max_length=64)
    attachment_id: str | None = Field(default=None, min_length=8, max_length=64)
    label: str | None = Field(default=None, min_length=2, max_length=300)
    body: str | None = Field(default=None, max_length=10000)

    @model_validator(mode="after")
    def require_source(self) -> "DocumentEvidenceCreate":
        if not self.chunk_id and not self.attachment_id:
            raise ValueError("Indique um excerto extraído ou uma fonte visual.")
        if self.label is not None and len(self.label.strip()) < 2:
            raise ValueError("Identifique a evidência com um rótulo legível.")
        if self.label is not None:
            self.label = " ".join(self.label.split())
        if not self.chunk_id and not str(self.body or "").strip():
            raise ValueError("Descreva a observação humana feita sobre a fonte visual.")
        return self


# Reuse every mature Evidence Graph route except the operations whose
# public contract is extended below. This avoids duplicate runtime routes while
# preserving synchronization, review and update behavior already in production.
router = APIRouter(tags=["pilot-evidence-graph"])
_replaced = {
    ("/api/pilot/evidence-graph/missions/{mission_code}/sync", "POST"),
    ("/api/pilot/evidence-graph/missions/{mission_code}", "GET"),
    ("/api/pilot/evidence-graph/missions/{mission_code}/nodes", "POST"),
    ("/api/pilot/evidence-graph/missions/{mission_code}/nodes/{node_id}", "PATCH"),
    ("/api/pilot/evidence-graph/missions/{mission_code}/edges", "POST"),
}
for route in legacy_router.routes:
    methods = set(getattr(route, "methods", set()) or set())
    if any((route.path, method) in _replaced for method in methods):
        continue
    router.routes.append(route)


@router.get("/api/pilot/evidence-graph/missions/{mission_code}")
def get_mission_graph(
    mission_code: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    document = legacy_get_mission_graph(mission_code=mission_code, user=user, db=db)
    contract = document.setdefault("contract", {})
    contract["node_types"] = NODE_TYPES
    contract["edge_types"] = EDGE_TYPES
    contract["canonical_layers"] = {
        "main_chain": [
            "observation",
            "evidence",
            "hypothesis",
            "target",
            "alternative",
            "decision",
            "action",
            "outcome",
            "learning",
        ],
        "transverse": [
            "assumption",
            "constraint",
            "gap",
            "confidence",
            "provenance",
        ],
    }
    return document


@router.post("/api/pilot/evidence-graph/missions/{mission_code}/sync")
def sync_mission_graph(
    mission_code: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Materialize AI candidates only after an authorized human requests it."""

    membership = _membership(db, user.id)
    if membership is None:
        raise HTTPException(status_code=403, detail="A conta não tem um workspace associado.")
    _require_writer(membership)
    mission = _mission(db, membership.organization_id, mission_code)
    _require_mission_mutable(mission)
    _ensure_interaction_schema(db)
    result = legacy_sync_mission_graph(mission_code=mission_code, user=user, db=db)
    record_audit(
        db,
        action="pilot.evidence_graph.synchronized",
        resource_type="mission_evidence_graph",
        resource_id=str(result.get("mission_code") or mission_code),
        organization_id=membership.organization_id,
        user_id=user.id,
        payload={
            "mission_code": str(result.get("mission_code") or mission_code),
            "interactions_scanned": int(result.get("interactions_scanned") or 0),
            "nodes_created": int(result.get("nodes_created") or 0),
            "edges_created": int(result.get("edges_created") or 0),
            "human_initiated": True,
        },
    )
    db.commit()
    return result


@router.post(
    "/api/pilot/evidence-graph/missions/{mission_code}/nodes",
    status_code=201,
)
def create_graph_node(
    mission_code: str,
    payload: GraphNodeCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _membership(db, user.id)
    if membership is None:
        raise HTTPException(status_code=403, detail="A conta não tem um workspace associado.")
    _require_writer(membership)
    _ensure_schema(db)
    mission = _mission(db, membership.organization_id, mission_code)
    _require_mission_mutable(mission)
    if payload.status != "proposed":
        _require_reviewer(membership)
    node_id = _upsert_node(
        db,
        organization_id=membership.organization_id,
        mission=mission,
        node_type=payload.node_type,
        label=payload.label,
        body=payload.body,
        status=payload.status,
        confidence=payload.confidence,
        source_kind="human_entry",
        source_id=f"human:{uuid4()}",
        attachment_id=None,
        char_start=None,
        char_end=None,
        source_sha256=None,
        provenance={
            **payload.provenance,
            "human_authored": True,
            "canonical_kind": payload.node_type,
        },
        user_id=user.id,
    )
    record_audit(
        db,
        action="pilot.evidence_graph.node_created",
        resource_type="evidence_graph_node",
        resource_id=node_id,
        organization_id=membership.organization_id,
        user_id=user.id,
        payload={
            "mission_code": mission.code,
            "node_type": payload.node_type,
            "status": payload.status,
            "label": payload.label,
            "source_kind": "human_entry",
        },
    )
    db.commit()
    row = db.execute(
        text("SELECT * FROM pilot_evidence_graph_nodes WHERE id=:id"),
        {"id": node_id},
    ).mappings().one()
    return _node_view(row)


@router.patch("/api/pilot/evidence-graph/missions/{mission_code}/nodes/{node_id}")
def update_graph_node(
    mission_code: str,
    node_id: str,
    payload: GraphNodeUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _membership(db, user.id)
    if membership is None:
        raise HTTPException(status_code=403, detail="A conta não tem um workspace associado.")
    _require_writer(membership)
    _ensure_schema(db)
    mission = _mission(db, membership.organization_id, mission_code)
    _require_mission_mutable(mission)
    row = db.execute(
        text(
            """
            SELECT * FROM pilot_evidence_graph_nodes
            WHERE id=:id AND organization_id=:org AND mission_id=:mission
            """
        ),
        {"id": node_id, "org": membership.organization_id, "mission": mission.id},
    ).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Nó não encontrado.")
    values = payload.model_dump(exclude_unset=True)
    if not values:
        return _node_view(row)
    if "status" in values and values["status"] != row["status"]:
        _require_reviewer(membership)
        allowed_status_transitions = {
            "proposed": {"accepted", "verified", "rejected", "superseded"},
            "accepted": {"proposed", "verified", "rejected", "superseded"},
            "verified": {"proposed", "accepted", "rejected", "superseded"},
            "rejected": set(),
            "superseded": set(),
        }
        if values["status"] not in allowed_status_transitions.get(row["status"], set()):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "terminal_evidence_state",
                    "message": (
                        "Um objeto rejeitado ou substituído permanece histórico. "
                        "Crie uma nova proposta para voltar a trabalhar esse conteúdo."
                    ),
                },
            )
    content_fields = {"label", "body", "confidence"} & set(values)
    if content_fields and row["status"] != "proposed":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "reviewed_node_version_required",
                "message": (
                    "O conteúdo revisto é imutável. Substitua esta versão e crie "
                    "uma nova proposta para preservar a história da revisão."
                ),
            },
        )
    null_forbidden = [
        field for field in ("label", "body", "status")
        if field in values and values[field] is None
    ]
    if null_forbidden:
        raise HTTPException(
            status_code=422,
            detail="Rótulo, conteúdo e estado não podem ser apagados com um valor nulo.",
        )
    if "label" in values and len(str(values["label"] or "").strip()) < 2:
        raise HTTPException(
            status_code=422,
            detail="Identifique este objeto com um rótulo legível.",
        )
    if "label" in values:
        values["label"] = " ".join(str(values["label"]).split())
    if "body" in values and len(str(values["body"] or "").strip()) < 2:
        raise HTTPException(
            status_code=422,
            detail="Descreva o conteúdo deste objeto antes de o guardar.",
        )

    before = _node_view(row)
    assignments = [f"{key}=:{key}" for key in values]
    assignments.append("updated_at=CURRENT_TIMESTAMP")
    db.execute(
        text(f"UPDATE pilot_evidence_graph_nodes SET {', '.join(assignments)} WHERE id=:id"),
        {"id": node_id, **values},
    )
    updated = db.execute(
        text("SELECT * FROM pilot_evidence_graph_nodes WHERE id=:id"),
        {"id": node_id},
    ).mappings().one()
    after = _node_view(updated)
    def audit_view(item: dict) -> dict:
        return {
            "label": item.get("label"),
            "status": item.get("status"),
            "confidence": item.get("confidence"),
            "body_sha256": hashlib.sha256(
                str(item.get("body") or "").encode("utf-8")
            ).hexdigest(),
        }
    record_audit(
        db,
        action="pilot.evidence_graph.node_updated",
        resource_type="evidence_graph_node",
        resource_id=node_id,
        organization_id=membership.organization_id,
        user_id=user.id,
        payload={
            "mission_code": mission.code,
            "changed_fields": sorted(values),
            "before": audit_view(before),
            "after": audit_view(after),
        },
    )
    db.commit()
    return after


@router.post(
    "/api/pilot/evidence-graph/missions/{mission_code}/document-evidence",
    status_code=201,
)
def promote_document_evidence(
    mission_code: str,
    payload: DocumentEvidenceCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Promote a reviewed document excerpt or visual observation without AI."""

    membership = _membership(db, user.id)
    if membership is None:
        raise HTTPException(status_code=403, detail="A conta não tem um workspace associado.")
    _require_writer(membership)
    _ensure_schema(db)
    mission = _mission(db, membership.organization_id, mission_code)
    _require_mission_mutable(mission)
    chunk = None
    if payload.chunk_id:
        chunk = (
            db.query(MissionArchiveChunk)
            .filter(
                MissionArchiveChunk.id == payload.chunk_id,
                MissionArchiveChunk.organization_id == membership.organization_id,
                MissionArchiveChunk.mission_id == mission.id,
                MissionArchiveChunk.source_type == "attachment",
                MissionArchiveChunk.attachment_id.is_not(None),
            )
            .one_or_none()
        )
        if chunk is None:
            raise HTTPException(status_code=404, detail="O excerto não pertence a esta missão.")
    attachment_id = chunk.attachment_id if chunk is not None else payload.attachment_id
    attachment = (
        db.query(MissionAttachment)
        .filter(
            MissionAttachment.id == attachment_id,
            MissionAttachment.organization_id == membership.organization_id,
            MissionAttachment.mission_id == mission.id,
        )
        .one_or_none()
    )
    if attachment is None:
        raise HTTPException(status_code=404, detail="A fonte original não está disponível.")
    if chunk is not None:
        try:
            excerpt = _decrypt_chunk(chunk)
        except Exception as exc:
            raise HTTPException(status_code=409, detail="O excerto falhou a verificação de integridade.") from exc
        source_kind = "document_chunk"
        source_id = f"archive_chunk:{chunk.id}:{chunk.content_sha256}"
        label = payload.label or f"{attachment.original_filename} · excerto {chunk.ordinal}"
        char_start = chunk.char_start
        char_end = chunk.char_end
        source_provenance = {
            "source": "document_extraction",
            "archive_chunk_id": chunk.id,
            "ordinal": chunk.ordinal,
            "char_start": chunk.char_start,
            "char_end": chunk.char_end,
            "content_sha256": chunk.content_sha256,
        }
    else:
        excerpt = str(payload.body or "").strip()
        source_kind = "visual_document"
        observation_sha256 = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
        source_id = f"visual_attachment:{attachment.id}:{attachment.sha256}:{observation_sha256}"
        label = payload.label or f"{attachment.original_filename} · observação visual"
        char_start = None
        char_end = None
        source_provenance = {
            "source": "human_visual_review",
            "visual_review": True,
            "observation_sha256": observation_sha256,
        }

    node_id = _upsert_node(
        db,
        organization_id=membership.organization_id,
        mission=mission,
        node_type="evidence",
        label=label,
        body=excerpt,
        # Selecting an excerpt verifies its identity, position and integrity;
        # it does not verify the factual truth of the excerpt.  Documentary
        # content remains proposed until a separate human factual review.
        status="proposed",
        confidence=None,
        source_kind=source_kind,
        source_id=source_id,
        attachment_id=attachment.id,
        char_start=char_start,
        char_end=char_end,
        source_sha256=attachment.sha256,
        provenance={
            **source_provenance,
            "filename": attachment.original_filename,
            "attachment_id": attachment.id,
            "source_sha256": attachment.sha256,
            "human_promoted": True,
            "source_selection_reviewed_by_human": True,
            "source_integrity_verified": True,
            "factual_validation": "not_assessed",
            "authoritative_source": False,
            "epistemic_separation_version": "20260824-1",
        },
        user_id=user.id,
    )
    record_audit(
        db,
        action="pilot.evidence_graph.document_evidence_promoted",
        resource_type="evidence_graph_node",
        resource_id=node_id,
        organization_id=membership.organization_id,
        user_id=user.id,
        payload={
            "mission_code": mission.code,
            "node_type": "evidence",
            "status": "proposed",
            "label": label,
            "attachment_id": attachment.id,
            "chunk_id": chunk.id if chunk is not None else None,
            "source_kind": source_kind,
            "factual_validation": "not_assessed",
        },
    )
    db.commit()
    row = db.execute(
        text("SELECT * FROM pilot_evidence_graph_nodes WHERE id=:id"),
        {"id": node_id},
    ).mappings().one()
    return _node_view(row)


@router.post(
    "/api/pilot/evidence-graph/missions/{mission_code}/edges",
    status_code=201,
)
def create_graph_edge(
    mission_code: str,
    payload: GraphEdgeCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _membership(db, user.id)
    if membership is None:
        raise HTTPException(status_code=403, detail="A conta não tem um workspace associado.")
    _require_writer(membership)
    _ensure_schema(db)
    mission = _mission(db, membership.organization_id, mission_code)
    _require_mission_mutable(mission)
    if payload.from_node_id == payload.to_node_id:
        raise HTTPException(
            status_code=422,
            detail="Uma relação tem de ligar dois objetos diferentes.",
        )
    ids = db.execute(
        text(
            """
            SELECT id FROM pilot_evidence_graph_nodes
            WHERE organization_id=:org AND mission_id=:mission
              AND id IN (:from_id, :to_id)
            """
        ),
        {
            "org": membership.organization_id,
            "mission": mission.id,
            "from_id": payload.from_node_id,
            "to_id": payload.to_node_id,
        },
    ).scalars().all()
    if len(set(ids)) != 2:
        raise HTTPException(status_code=422, detail="Os dois nós têm de pertencer à mesma missão.")

    existing_edge_id = db.execute(
        text(
            """
            SELECT id FROM pilot_evidence_graph_edges
            WHERE organization_id=:org AND mission_id=:mission
              AND from_node_id=:from_id AND to_node_id=:to_id
              AND edge_type=:edge_type
            LIMIT 1
            """
        ),
        {
            "org": membership.organization_id,
            "mission": mission.id,
            "from_id": payload.from_node_id,
            "to_id": payload.to_node_id,
            "edge_type": payload.edge_type,
        },
    ).scalar_one_or_none()

    edge_id = _upsert_edge(
        db,
        organization_id=membership.organization_id,
        mission=mission,
        from_node_id=payload.from_node_id,
        to_node_id=payload.to_node_id,
        edge_type=payload.edge_type,
        provenance={**payload.provenance, "human_curated": True},
        user_id=user.id,
    )
    if existing_edge_id is None:
        record_audit(
            db,
            action="pilot.evidence_graph.edge_created",
            resource_type="evidence_graph_edge",
            resource_id=edge_id,
            organization_id=membership.organization_id,
            user_id=user.id,
            payload={
                "mission_code": mission.code,
                "from_node_id": payload.from_node_id,
                "to_node_id": payload.to_node_id,
                "edge_type": payload.edge_type,
            },
        )
    db.commit()
    row = db.execute(
        text("SELECT * FROM pilot_evidence_graph_edges WHERE id=:id"),
        {"id": edge_id},
    ).mappings().one()
    result = _edge_view(row)
    result["created"] = existing_edge_id is None
    return result


def _scoped_edge_row(
    db: Session,
    *,
    organization_id: str,
    mission_id: str,
    edge_id: str,
):
    row = db.execute(
        text(
            """
            SELECT * FROM pilot_evidence_graph_edges
            WHERE id=:edge_id AND organization_id=:org AND mission_id=:mission
            """
        ),
        {"edge_id": edge_id, "org": organization_id, "mission": mission_id},
    ).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="A relação indicada não existe nesta missão.")
    return row


@router.post(
    "/api/pilot/evidence-graph/missions/{mission_code}/edges/{edge_id}/reverse",
)
def reverse_graph_edge(
    mission_code: str,
    edge_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _membership(db, user.id)
    if membership is None:
        raise HTTPException(status_code=403, detail="A conta não tem um workspace associado.")
    _require_writer(membership)
    _ensure_schema(db)
    mission = _mission(db, membership.organization_id, mission_code)
    _require_mission_mutable(mission)
    row = _scoped_edge_row(
        db,
        organization_id=membership.organization_id,
        mission_id=mission.id,
        edge_id=edge_id,
    )
    before = _edge_view(row)
    collision = db.execute(
        text(
            """
            SELECT id FROM pilot_evidence_graph_edges
            WHERE organization_id=:org AND mission_id=:mission
              AND from_node_id=:from_id AND to_node_id=:to_id
              AND edge_type=:edge_type AND id<>:edge_id
            LIMIT 1
            """
        ),
        {
            "org": membership.organization_id,
            "mission": mission.id,
            "from_id": row["to_node_id"],
            "to_id": row["from_node_id"],
            "edge_type": row["edge_type"],
            "edge_id": edge_id,
        },
    ).scalar_one_or_none()
    if collision is not None:
        raise HTTPException(status_code=409, detail="A relação com a direção inversa já existe.")

    db.execute(
        text(
            """
            UPDATE pilot_evidence_graph_edges
            SET from_node_id=:from_id, to_node_id=:to_id
            WHERE id=:edge_id AND organization_id=:org AND mission_id=:mission
            """
        ),
        {
            "from_id": row["to_node_id"],
            "to_id": row["from_node_id"],
            "edge_id": edge_id,
            "org": membership.organization_id,
            "mission": mission.id,
        },
    )
    updated = _scoped_edge_row(
        db,
        organization_id=membership.organization_id,
        mission_id=mission.id,
        edge_id=edge_id,
    )
    after = _edge_view(updated)
    record_audit(
        db,
        action="pilot.evidence_graph.edge_reversed",
        resource_type="evidence_graph_edge",
        resource_id=edge_id,
        organization_id=membership.organization_id,
        user_id=user.id,
        payload={"mission_code": mission.code, "before": before, "after": after},
    )
    db.commit()
    return {**after, "reversed": True}


@router.delete(
    "/api/pilot/evidence-graph/missions/{mission_code}/edges/{edge_id}",
)
def delete_graph_edge(
    mission_code: str,
    edge_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _membership(db, user.id)
    if membership is None:
        raise HTTPException(status_code=403, detail="A conta não tem um workspace associado.")
    _require_writer(membership)
    _ensure_schema(db)
    mission = _mission(db, membership.organization_id, mission_code)
    _require_mission_mutable(mission)
    row = _scoped_edge_row(
        db,
        organization_id=membership.organization_id,
        mission_id=mission.id,
        edge_id=edge_id,
    )
    before = _edge_view(row)
    record_audit(
        db,
        action="pilot.evidence_graph.edge_deleted",
        resource_type="evidence_graph_edge",
        resource_id=edge_id,
        organization_id=membership.organization_id,
        user_id=user.id,
        payload={"mission_code": mission.code, "before": before},
    )
    db.execute(
        text(
            """
            DELETE FROM pilot_evidence_graph_edges
            WHERE id=:edge_id AND organization_id=:org AND mission_id=:mission
            """
        ),
        {"edge_id": edge_id, "org": membership.organization_id, "mission": mission.id},
    )
    db.commit()
    return {"deleted": True, "id": edge_id, "edge": before}
