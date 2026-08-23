from __future__ import annotations

from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.atlas_platform.auth import current_user
from app.atlas_platform.database import get_db
from app.atlas_platform.models import User
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


class GraphNodeCreate(BaseModel):
    node_type: NodeType
    label: str = Field(min_length=2, max_length=300)
    body: str = Field(default="", max_length=50000)
    status: NodeStatus = "proposed"
    confidence: float | None = Field(default=None, ge=0, le=1)
    provenance: dict = Field(default_factory=dict)


class GraphEdgeCreate(BaseModel):
    from_node_id: str = Field(min_length=8, max_length=64)
    to_node_id: str = Field(min_length=8, max_length=64)
    edge_type: EdgeType
    provenance: dict = Field(default_factory=dict)


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
