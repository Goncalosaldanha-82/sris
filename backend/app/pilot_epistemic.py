from __future__ import annotations

import hashlib
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.atlas_platform.auth import current_user
from app.atlas_platform.database import get_db
from app.atlas_platform.models import Role, User
from app.evidence_graph import (
    _edge_view,
    _ensure_schema,
    _membership,
    _mission,
    _node_view,
    _upsert_edge,
    _upsert_node,
    get_mission_graph as legacy_get_mission_graph,
    router as legacy_router,
)
from app.mission_intelligence.mission_archive import _decrypt_chunk
from app.mission_intelligence.models import MissionArchiveChunk, MissionAttachment


NodeType = Literal[
    "observation",
    "evidence",
    "claim",
    "assumption",
    "constraint",
    "gap",
    "hypothesis",
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


def _require_writer(membership) -> None:
    if membership.role not in WRITER_ROLES:
        raise HTTPException(status_code=403, detail="A sua função permite consultar, mas não alterar evidência.")


class GraphNodeCreate(BaseModel):
    node_type: NodeType
    label: str = Field(min_length=2, max_length=300)
    body: str = Field(default="", max_length=50000)
    status: NodeStatus = "proposed"
    confidence: float | None = Field(default=None, ge=0, le=1)
    provenance: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_meaningful_content(self) -> "GraphNodeCreate":
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
        if not self.chunk_id and not str(self.body or "").strip():
            raise ValueError("Descreva a observação humana feita sobre a fonte visual.")
        return self


# Reuse every mature Evidence Graph route except the three operations whose
# public contract is extended below. This avoids duplicate runtime routes while
# preserving synchronization, review and update behavior already in production.
router = APIRouter(tags=["pilot-evidence-graph"])
_replaced = {
    ("/api/pilot/evidence-graph/missions/{mission_code}", "GET"),
    ("/api/pilot/evidence-graph/missions/{mission_code}/nodes", "POST"),
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
    db.commit()
    row = db.execute(
        text("SELECT * FROM pilot_evidence_graph_nodes WHERE id=:id"),
        {"id": node_id},
    ).mappings().one()
    return _node_view(row)


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
        status="verified",
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
            "authoritative_source": True,
        },
        user_id=user.id,
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
    db.commit()
    row = db.execute(
        text("SELECT * FROM pilot_evidence_graph_edges WHERE id=:id"),
        {"id": edge_id},
    ).mappings().one()
    return _edge_view(row)
