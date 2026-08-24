from __future__ import annotations

import json
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.atlas_platform.auth import current_user
from app.atlas_platform.database import get_db
from app.atlas_platform.models import Membership, User
from app.mission_intelligence.models import CanonicalMission, MissionAttachment
from app.pilot_serialization import as_iso

router = APIRouter(prefix="/api/pilot/evidence-graph", tags=["pilot-evidence-graph"])

NodeType = Literal["evidence", "claim", "hypothesis", "decision", "outcome", "learning"]
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
]


class GraphNodeCreate(BaseModel):
    node_type: NodeType
    label: str = Field(min_length=2, max_length=300)
    body: str = Field(default="", max_length=50000)
    status: NodeStatus = "proposed"
    confidence: float | None = Field(default=None, ge=0, le=1)
    provenance: dict = Field(default_factory=dict)


class GraphNodeUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=2, max_length=300)
    body: str | None = Field(default=None, max_length=50000)
    status: NodeStatus | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class GraphEdgeCreate(BaseModel):
    from_node_id: str = Field(min_length=8, max_length=64)
    to_node_id: str = Field(min_length=8, max_length=64)
    edge_type: EdgeType
    provenance: dict = Field(default_factory=dict)


def _membership(db: Session, user_id: str) -> Membership | None:
    return (
        db.query(Membership)
        .filter(Membership.user_id == user_id)
        .order_by(Membership.created_at.asc())
        .first()
    )


def _ensure_schema(db: Session) -> None:
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS pilot_evidence_graph_nodes (
            id VARCHAR(64) PRIMARY KEY,
            organization_id VARCHAR(64) NOT NULL,
            mission_id VARCHAR(64) NOT NULL,
            mission_code VARCHAR(80) NOT NULL,
            node_type VARCHAR(40) NOT NULL,
            label VARCHAR(300) NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            status VARCHAR(40) NOT NULL DEFAULT 'proposed',
            confidence DOUBLE PRECISION NULL,
            source_kind VARCHAR(60) NULL,
            source_id VARCHAR(300) NULL,
            attachment_id VARCHAR(64) NULL,
            char_start INTEGER NULL,
            char_end INTEGER NULL,
            source_sha256 VARCHAR(64) NULL,
            provenance_json TEXT NOT NULL DEFAULT '{}',
            created_by_user_id VARCHAR(64) NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (organization_id, mission_id, source_kind, source_id)
        )
    """))
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_pilot_evidence_graph_nodes_mission
        ON pilot_evidence_graph_nodes (organization_id, mission_id, node_type, created_at)
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS pilot_evidence_graph_edges (
            id VARCHAR(64) PRIMARY KEY,
            organization_id VARCHAR(64) NOT NULL,
            mission_id VARCHAR(64) NOT NULL,
            mission_code VARCHAR(80) NOT NULL,
            from_node_id VARCHAR(64) NOT NULL,
            to_node_id VARCHAR(64) NOT NULL,
            edge_type VARCHAR(40) NOT NULL,
            provenance_json TEXT NOT NULL DEFAULT '{}',
            created_by_user_id VARCHAR(64) NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (organization_id, mission_id, from_node_id, to_node_id, edge_type)
        )
    """))
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_pilot_evidence_graph_edges_mission
        ON pilot_evidence_graph_edges (organization_id, mission_id, edge_type, created_at)
    """))


def _mission(db: Session, organization_id: str, mission_code: str) -> CanonicalMission:
    row = (
        db.query(CanonicalMission)
        .filter(
            CanonicalMission.organization_id == organization_id,
            CanonicalMission.code == mission_code,
        )
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="A missão indicada não existe neste workspace.")
    return row


def _node_view(row) -> dict:
    return {
        "id": row["id"],
        "node_type": row["node_type"],
        "label": row["label"],
        "body": row["body"],
        "status": row["status"],
        "confidence": row["confidence"],
        "source_kind": row["source_kind"],
        "source_id": row["source_id"],
        "attachment_id": row["attachment_id"],
        "char_start": row["char_start"],
        "char_end": row["char_end"],
        "source_sha256": row["source_sha256"],
        "provenance": json.loads(row["provenance_json"] or "{}"),
        "created_at": as_iso(row["created_at"]),
        "updated_at": as_iso(row["updated_at"]),
    }


def _edge_view(row) -> dict:
    return {
        "id": row["id"],
        "from_node_id": row["from_node_id"],
        "to_node_id": row["to_node_id"],
        "edge_type": row["edge_type"],
        "provenance": json.loads(row["provenance_json"] or "{}"),
        "created_at": as_iso(row["created_at"]),
    }


def _upsert_node(
    db: Session,
    *,
    organization_id: str,
    mission: CanonicalMission,
    node_type: str,
    label: str,
    body: str,
    status: str,
    confidence: float | None,
    source_kind: str | None,
    source_id: str | None,
    attachment_id: str | None,
    char_start: int | None,
    char_end: int | None,
    source_sha256: str | None,
    provenance: dict,
    user_id: str | None,
) -> str:
    node_id = str(uuid4())
    if source_kind and source_id:
        existing = db.execute(text("""
            SELECT id FROM pilot_evidence_graph_nodes
            WHERE organization_id=:org AND mission_id=:mission
              AND source_kind=:source_kind AND source_id=:source_id
            LIMIT 1
        """), {
            "org": organization_id,
            "mission": mission.id,
            "source_kind": source_kind,
            "source_id": source_id,
        }).scalar_one_or_none()
        if existing:
            return str(existing)
    db.execute(text("""
        INSERT INTO pilot_evidence_graph_nodes
        (id, organization_id, mission_id, mission_code, node_type, label, body, status,
         confidence, source_kind, source_id, attachment_id, char_start, char_end,
         source_sha256, provenance_json, created_by_user_id)
        VALUES (:id, :org, :mission, :code, :node_type, :label, :body, :status,
                :confidence, :source_kind, :source_id, :attachment_id, :char_start,
                :char_end, :source_sha256, :provenance, :user_id)
    """), {
        "id": node_id,
        "org": organization_id,
        "mission": mission.id,
        "code": mission.code,
        "node_type": node_type,
        "label": label,
        "body": body,
        "status": status,
        "confidence": confidence,
        "source_kind": source_kind,
        "source_id": source_id,
        "attachment_id": attachment_id,
        "char_start": char_start,
        "char_end": char_end,
        "source_sha256": source_sha256,
        "provenance": json.dumps(provenance, ensure_ascii=False),
        "user_id": user_id,
    })
    return node_id


def _upsert_edge(
    db: Session,
    *,
    organization_id: str,
    mission: CanonicalMission,
    from_node_id: str,
    to_node_id: str,
    edge_type: str,
    provenance: dict,
    user_id: str | None,
) -> str:
    existing = db.execute(text("""
        SELECT id FROM pilot_evidence_graph_edges
        WHERE organization_id=:org AND mission_id=:mission
          AND from_node_id=:from_id AND to_node_id=:to_id AND edge_type=:edge_type
        LIMIT 1
    """), {
        "org": organization_id,
        "mission": mission.id,
        "from_id": from_node_id,
        "to_id": to_node_id,
        "edge_type": edge_type,
    }).scalar_one_or_none()
    if existing:
        return str(existing)
    edge_id = str(uuid4())
    db.execute(text("""
        INSERT INTO pilot_evidence_graph_edges
        (id, organization_id, mission_id, mission_code, from_node_id, to_node_id,
         edge_type, provenance_json, created_by_user_id)
        VALUES (:id, :org, :mission, :code, :from_id, :to_id, :edge_type,
                :provenance, :user_id)
    """), {
        "id": edge_id,
        "org": organization_id,
        "mission": mission.id,
        "code": mission.code,
        "from_id": from_node_id,
        "to_id": to_node_id,
        "edge_type": edge_type,
        "provenance": json.dumps(provenance, ensure_ascii=False),
        "user_id": user_id,
    })
    return edge_id


@router.post("/missions/{mission_code}/sync")
def sync_mission_graph(
    mission_code: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _membership(db, user.id)
    if membership is None:
        raise HTTPException(status_code=403, detail="A conta não tem um workspace associado.")
    _ensure_schema(db)
    mission = _mission(db, membership.organization_id, mission_code)

    interactions = db.execute(text("""
        SELECT id, user_message, answer, context_manifest_json, model, usage_event_id, created_at
        FROM pilot_ai_interactions
        WHERE organization_id=:org AND mission_code=:code
        ORDER BY created_at ASC
    """), {"org": membership.organization_id, "code": mission.code}).mappings().all()

    attachment_cache: dict[str, MissionAttachment | None] = {}
    created_nodes = 0
    created_edges = 0
    for interaction in interactions:
        claim_source = f"interaction:{interaction['id']}"
        before = db.execute(text("""
            SELECT id FROM pilot_evidence_graph_nodes
            WHERE organization_id=:org AND mission_id=:mission
              AND source_kind='ai_interaction' AND source_id=:source_id
        """), {"org": membership.organization_id, "mission": mission.id, "source_id": claim_source}).scalar_one_or_none()
        claim_id = _upsert_node(
            db,
            organization_id=membership.organization_id,
            mission=mission,
            node_type="claim",
            label=(interaction["user_message"] or "Análise de Mission Intelligence")[:300],
            body=interaction["answer"] or "",
            status="proposed",
            confidence=None,
            source_kind="ai_interaction",
            source_id=claim_source,
            attachment_id=None,
            char_start=None,
            char_end=None,
            source_sha256=None,
            provenance={
                "interaction_id": interaction["id"],
                "usage_event_id": interaction["usage_event_id"],
                "model": interaction["model"],
                "role": "ai_generated_candidate_claim",
                "human_review_required": True,
            },
            user_id=user.id,
        )
        if before is None:
            created_nodes += 1

        try:
            manifest = json.loads(interaction["context_manifest_json"] or "{}")
        except Exception:
            manifest = {}
        for source in manifest.get("sources") or []:
            attachment_id = source.get("attachment_id")
            if not attachment_id:
                continue
            if attachment_id not in attachment_cache:
                attachment_cache[attachment_id] = (
                    db.query(MissionAttachment)
                    .filter(
                        MissionAttachment.organization_id == membership.organization_id,
                        MissionAttachment.mission_id == mission.id,
                        MissionAttachment.id == attachment_id,
                    )
                    .one_or_none()
                )
            attachment = attachment_cache[attachment_id]
            start = int(source.get("char_start") or 0)
            end = int(source.get("char_end") or start)
            excerpt = ""
            if attachment is not None and end > start:
                excerpt = (attachment.extracted_text or "")[start:end]
            source_sha = source.get("content_sha256")
            evidence_source_id = f"chunk:{attachment_id}:{start}:{end}:{source_sha or 'unknown'}"
            previous = db.execute(text("""
                SELECT id FROM pilot_evidence_graph_nodes
                WHERE organization_id=:org AND mission_id=:mission
                  AND source_kind='document_chunk' AND source_id=:source_id
            """), {"org": membership.organization_id, "mission": mission.id, "source_id": evidence_source_id}).scalar_one_or_none()
            evidence_id = _upsert_node(
                db,
                organization_id=membership.organization_id,
                mission=mission,
                node_type="evidence",
                label=source.get("filename") or (attachment.original_filename if attachment else "Documento"),
                body=excerpt,
                # Retrieval and attachment integrity do not establish that the
                # retrieved content is factually true.  A documentary source is
                # proposed until a human completes a separate factual review.
                status="proposed",
                confidence=None,
                source_kind="document_chunk",
                source_id=evidence_source_id,
                attachment_id=attachment_id,
                char_start=start,
                char_end=end,
                source_sha256=source_sha,
                provenance={
                    "filename": source.get("filename"),
                    "attachment_id": attachment_id,
                    "char_start": start,
                    "char_end": end,
                    "content_sha256": source_sha,
                    "lexical_rank": source.get("lexical_rank"),
                    "semantic_rank": source.get("semantic_rank"),
                    "hybrid_score": source.get("hybrid_score"),
                    "embedding_model": source.get("embedding_model"),
                    "retrieval": manifest.get("retrieval") or {},
                    "source_integrity_verified": attachment is not None,
                    "factual_validation": "not_assessed",
                    "authoritative_source": False,
                    "epistemic_separation_version": "20260824-1",
                },
                user_id=user.id,
            )
            if previous is None:
                created_nodes += 1
            edge_before = db.execute(text("""
                SELECT id FROM pilot_evidence_graph_edges
                WHERE organization_id=:org AND mission_id=:mission
                  AND from_node_id=:from_id AND to_node_id=:to_id AND edge_type='informs'
            """), {
                "org": membership.organization_id,
                "mission": mission.id,
                "from_id": evidence_id,
                "to_id": claim_id,
            }).scalar_one_or_none()
            _upsert_edge(
                db,
                organization_id=membership.organization_id,
                mission=mission,
                from_node_id=evidence_id,
                to_node_id=claim_id,
                edge_type="informs",
                provenance={
                    "interaction_id": interaction["id"],
                    "meaning": "retrieved_context_only_not_asserted_support",
                },
                user_id=user.id,
            )
            if edge_before is None:
                created_edges += 1

    db.commit()
    return {
        "status": "synced",
        "mission_code": mission.code,
        "interactions_scanned": len(interactions),
        "nodes_created": created_nodes,
        "edges_created": created_edges,
        "principle": "retrieval informs a claim; support or contradiction requires explicit graph curation",
    }


@router.get("/missions/{mission_code}")
def get_mission_graph(
    mission_code: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _membership(db, user.id)
    if membership is None:
        raise HTTPException(status_code=403, detail="A conta não tem um workspace associado.")
    _ensure_schema(db)
    mission = _mission(db, membership.organization_id, mission_code)
    nodes = db.execute(text("""
        SELECT * FROM pilot_evidence_graph_nodes
        WHERE organization_id=:org AND mission_id=:mission
        ORDER BY created_at ASC
    """), {"org": membership.organization_id, "mission": mission.id}).mappings().all()
    edges = db.execute(text("""
        SELECT * FROM pilot_evidence_graph_edges
        WHERE organization_id=:org AND mission_id=:mission
        ORDER BY created_at ASC
    """), {"org": membership.organization_id, "mission": mission.id}).mappings().all()
    counts: dict[str, int] = {}
    for row in nodes:
        counts[row["node_type"]] = counts.get(row["node_type"], 0) + 1
    return {
        "mission": {"id": mission.id, "code": mission.code, "title": mission.title, "revision": mission.revision},
        "nodes": [_node_view(row) for row in nodes],
        "edges": [_edge_view(row) for row in edges],
        "counts": counts,
        "contract": {
            "node_types": ["evidence", "claim", "hypothesis", "decision", "outcome", "learning"],
            "edge_types": ["supports", "contradicts", "informs", "derived_from", "tests", "leads_to", "validates", "invalidates", "supersedes", "learned_from"],
            "retrieval_is_not_support": True,
            "vector_index_is_not_source_of_truth": True,
        },
    }


@router.post("/missions/{mission_code}/nodes", status_code=201)
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
        provenance={**payload.provenance, "human_authored": True},
        user_id=user.id,
    )
    db.commit()
    row = db.execute(text("SELECT * FROM pilot_evidence_graph_nodes WHERE id=:id"), {"id": node_id}).mappings().one()
    return _node_view(row)


@router.patch("/missions/{mission_code}/nodes/{node_id}")
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
    _ensure_schema(db)
    mission = _mission(db, membership.organization_id, mission_code)
    row = db.execute(text("""
        SELECT * FROM pilot_evidence_graph_nodes
        WHERE id=:id AND organization_id=:org AND mission_id=:mission
    """), {"id": node_id, "org": membership.organization_id, "mission": mission.id}).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Nó não encontrado.")
    values = payload.model_dump(exclude_unset=True)
    if not values:
        return _node_view(row)
    assignments = []
    params = {"id": node_id}
    for key, value in values.items():
        assignments.append(f"{key}=:{key}")
        params[key] = value
    assignments.append("updated_at=CURRENT_TIMESTAMP")
    db.execute(text(f"UPDATE pilot_evidence_graph_nodes SET {', '.join(assignments)} WHERE id=:id"), params)
    db.commit()
    updated = db.execute(text("SELECT * FROM pilot_evidence_graph_nodes WHERE id=:id"), {"id": node_id}).mappings().one()
    return _node_view(updated)


@router.post("/missions/{mission_code}/edges", status_code=201)
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
    ids = db.execute(text("""
        SELECT id FROM pilot_evidence_graph_nodes
        WHERE organization_id=:org AND mission_id=:mission AND id IN (:from_id, :to_id)
    """), {
        "org": membership.organization_id,
        "mission": mission.id,
        "from_id": payload.from_node_id,
        "to_id": payload.to_node_id,
    }).scalars().all()
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
    row = db.execute(text("SELECT * FROM pilot_evidence_graph_edges WHERE id=:id"), {"id": edge_id}).mappings().one()
    return _edge_view(row)
