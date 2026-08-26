from __future__ import annotations

import hashlib
import json
import re
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.atlas_platform.auth import current_user
from app.atlas_platform.database import get_db
from app.atlas_platform.models import Membership, User
from app.mission_intelligence.models import CanonicalMission
from app.pilot_mission_state import record_module_review
from app.pilot_serialization import as_iso
from app.pilot_text import normalize_generated_title

router = APIRouter(prefix="/api/pilot/learning", tags=["pilot-learning-lineage"])

Applicability = Literal["reuse", "requires_revalidation", "not_applicable"]
LegacyDisposition = Literal["still_valid", "requires_revalidation", "invalidated"]


class LearningReviewRequest(BaseModel):
    applicability: Applicability | None = None
    disposition: LegacyDisposition | None = None
    rationale: str = Field(min_length=3, max_length=10000)
    context_change: str = Field(default="", max_length=10000)

    @model_validator(mode="after")
    def validate_contextual_review(self) -> "LearningReviewRequest":
        if self.applicability is None and self.disposition is None:
            raise ValueError("Indique a aplicabilidade da aprendizagem nesta missão.")
        if self.applicability is not None and self.disposition is not None:
            raise ValueError("Use apenas applicability; disposition existe apenas para compatibilidade.")
        if self.effective_applicability == "requires_revalidation" and not self.context_change.strip():
            raise ValueError("Indique o que mudou no contexto e precisa de ser revalidado.")
        return self

    @property
    def effective_applicability(self) -> Applicability:
        if self.applicability is not None:
            return self.applicability
        return {
            "still_valid": "reuse",
            "requires_revalidation": "requires_revalidation",
            "invalidated": "not_applicable",
        }[self.disposition]


def _membership(db: Session, user_id: str) -> Membership | None:
    return (
        db.query(Membership)
        .filter(Membership.user_id == user_id)
        .order_by(Membership.created_at.asc())
        .first()
    )


def _ensure_schema(db: Session) -> None:
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS pilot_learning_packets (
            id VARCHAR(64) PRIMARY KEY,
            organization_id VARCHAR(64) NOT NULL,
            source_mission_id VARCHAR(64) NOT NULL,
            source_mission_code VARCHAR(80) NOT NULL,
            source_learning_node_id VARCHAR(64) NOT NULL,
            title VARCHAR(300) NOT NULL,
            statement TEXT NOT NULL,
            graph_snapshot_json TEXT NOT NULL,
            lineage_sha256 VARCHAR(64) NOT NULL,
            created_by_user_id VARCHAR(64) NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (organization_id, source_mission_id, source_learning_node_id)
        )
    """))
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_pilot_learning_packets_org_created
        ON pilot_learning_packets (organization_id, created_at DESC)
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS pilot_learning_reviews (
            id VARCHAR(64) PRIMARY KEY,
            organization_id VARCHAR(64) NOT NULL,
            target_mission_id VARCHAR(64) NOT NULL,
            target_mission_code VARCHAR(80) NOT NULL,
            learning_packet_id VARCHAR(64) NOT NULL,
            disposition VARCHAR(40) NOT NULL,
            rationale TEXT NOT NULL,
            context_change TEXT NOT NULL DEFAULT '',
            reviewed_by_user_id VARCHAR(64) NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (organization_id, target_mission_id, learning_packet_id)
        )
    """))
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_pilot_learning_reviews_target
        ON pilot_learning_reviews (organization_id, target_mission_id, disposition)
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


def _tokens(*values: str) -> set[str]:
    stop = {"para", "como", "mais", "esta", "este", "isso", "sobre", "entre", "pela", "pelo", "uma", "que", "com", "sem", "dos", "das"}
    joined = " ".join(values).casefold()
    return {
        token
        for token in re.findall(r"[a-zA-ZÀ-ÿ0-9_-]{4,}", joined)
        if token not in stop
    }


def _graph_snapshot(db: Session, *, organization_id: str, mission_id: str, learning_node_id: str) -> dict:
    learning = db.execute(text("""
        SELECT * FROM pilot_evidence_graph_nodes
        WHERE organization_id=:org AND mission_id=:mission AND id=:node
          AND node_type='learning'
        LIMIT 1
    """), {"org": organization_id, "mission": mission_id, "node": learning_node_id}).mappings().first()
    if learning is None:
        raise HTTPException(status_code=404, detail="A aprendizagem não existe no Evidence Graph desta missão.")
    if learning["status"] not in {"accepted", "verified"}:
        raise HTTPException(
            status_code=409,
            detail="A aprendizagem só pode ser publicada depois de revisão humana (accepted ou verified).",
        )

    all_nodes = db.execute(text("""
        SELECT * FROM pilot_evidence_graph_nodes
        WHERE organization_id=:org AND mission_id=:mission
    """), {"org": organization_id, "mission": mission_id}).mappings().all()
    all_edges = db.execute(text("""
        SELECT * FROM pilot_evidence_graph_edges
        WHERE organization_id=:org AND mission_id=:mission
    """), {"org": organization_id, "mission": mission_id}).mappings().all()
    node_by_id = {row["id"]: row for row in all_nodes}

    selected = {learning_node_id}
    frontier = {learning_node_id}
    lineage_edges: list[dict] = []
    allowed = {"supports", "contradicts", "informs", "derived_from", "tests", "leads_to", "validates", "invalidates", "supersedes", "learned_from"}
    for _ in range(5):
        next_frontier: set[str] = set()
        for edge in all_edges:
            if edge["edge_type"] not in allowed:
                continue
            left, right = edge["from_node_id"], edge["to_node_id"]
            if left in frontier or right in frontier:
                if left in node_by_id and right in node_by_id:
                    lineage_edges.append(dict(edge))
                    if left not in selected:
                        next_frontier.add(left)
                    if right not in selected:
                        next_frontier.add(right)
        if not next_frontier:
            break
        selected.update(next_frontier)
        frontier = next_frontier

    nodes = []
    for node_id in selected:
        row = node_by_id[node_id]
        nodes.append({
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
        })
    edges = [
        {
            "id": edge["id"],
            "from_node_id": edge["from_node_id"],
            "to_node_id": edge["to_node_id"],
            "edge_type": edge["edge_type"],
            "provenance": json.loads(edge["provenance_json"] or "{}"),
        }
        for edge in {edge["id"]: edge for edge in lineage_edges}.values()
    ]
    raw_counts = {
        kind: sum(1 for node in nodes if node["node_type"] == kind)
        for kind in ("evidence", "claim", "hypothesis", "decision", "outcome", "learning")
    }

    def governed_entities(kind: str) -> list[dict]:
        candidates = [node for node in nodes if node["node_type"] == kind]
        if kind == "decision":
            committed = [
                node for node in candidates
                if node["provenance"].get("role") == "committed_decision"
                or (
                    node.get("source_kind") == "decision_cycle"
                    and str(node.get("source_id") or "").startswith("decision:")
                )
            ]
            if committed:
                candidates = committed
        elif kind == "outcome":
            observed = [
                node for node in candidates
                if node["provenance"].get("role") == "observed_outcome"
                or (
                    node.get("source_kind") == "decision_cycle"
                    and str(node.get("source_id") or "").startswith("outcome:")
                )
            ]
            if observed:
                candidates = observed
        elif kind == "learning":
            candidates = [node for node in candidates if node["id"] == learning_node_id]

        unique: dict[tuple, dict] = {}
        for node in candidates:
            identity = (
                node.get("source_kind") or "",
                node.get("source_id")
                or node.get("attachment_id")
                or node.get("source_sha256")
                or node["id"],
            )
            unique[identity] = node
        return list(unique.values())

    entity_counts = {
        kind: len(governed_entities(kind))
        for kind in ("evidence", "claim", "hypothesis", "decision", "outcome", "learning")
    }
    return {
        "learning_node_id": learning_node_id,
        "nodes": sorted(nodes, key=lambda n: (n["node_type"], n["id"])),
        "edges": sorted(edges, key=lambda e: e["id"]),
        "counts": entity_counts,
        "entity_counts": entity_counts,
        "raw_node_counts": raw_counts,
        "counting_policy": "Entidades únicas e governadas; nós técnicos ou candidatos não contam como decisões executivas.",
        "principle": "A aprendizagem é transportada com a cadeia de evidência e decisão que a originou.",
    }


def _packet_view(row) -> dict:
    snapshot = json.loads(row["graph_snapshot_json"] or "{}")
    return {
        "id": row["id"],
        "source_mission": {
            "id": row["source_mission_id"],
            "code": row["source_mission_code"],
        },
        "source_learning_node_id": row["source_learning_node_id"],
        "title": normalize_generated_title(row["title"]),
        "statement": row["statement"],
        # A published packet is canonically valid independently from any
        # target mission's contextual applicability review.
        "canonical_status": "valid",
        "lineage_sha256": row["lineage_sha256"],
        "lineage": snapshot,
        "created_at": as_iso(row["created_at"]),
    }


def inherited_learning_context(db: Session, *, organization_id: str, target_mission_id: str) -> tuple[str, dict]:
    """Return only human-reviewed inheritance that is allowed to alter a future mission."""
    _ensure_schema(db)
    rows = db.execute(text("""
        SELECT p.*,
               CASE r.disposition
                   WHEN 'still_valid' THEN 'reuse'
                   WHEN 'requires_revalidation' THEN 'requires_revalidation'
                   WHEN 'invalidated' THEN 'not_applicable'
                   ELSE 'pending'
               END AS applicability,
               r.rationale, r.context_change, r.updated_at AS reviewed_at
        FROM pilot_learning_packets p
        JOIN pilot_learning_reviews r ON r.learning_packet_id=p.id
        WHERE p.organization_id=:org AND r.organization_id=:org
          AND r.target_mission_id=:target
          AND r.disposition IN ('still_valid','requires_revalidation')
        ORDER BY r.updated_at DESC
    """), {"org": organization_id, "target": target_mission_id}).mappings().all()
    valid, revalidation = [], []
    for row in rows:
        item = {
            "packet_id": row["id"],
            "source_mission_code": row["source_mission_code"],
            "title": normalize_generated_title(row["title"]),
            "statement": row["statement"],
            "lineage_sha256": row["lineage_sha256"],
            "lineage_counts": (json.loads(row["graph_snapshot_json"] or "{}").get("counts") or {}),
            "rationale": row["rationale"],
            "context_change": row["context_change"],
        }
        (valid if row["applicability"] == "reuse" else revalidation).append(item)
    parts = []
    if valid:
        parts.append("APRENDIZAGEM ORGANIZACIONAL HERDADA — VALIDADA NESTE CONTEXTO:\n" + "\n".join(
            f"- [{item['source_mission_code']}] {item['title']}: {item['statement']} (lineage {item['lineage_sha256'][:12]})"
            for item in valid
        ))
    if revalidation:
        parts.append("APRENDIZAGENS QUE NÃO PODEM SER ASSUMIDAS SEM REVALIDAÇÃO:\n" + "\n".join(
            f"- [{item['source_mission_code']}] {item['title']}: {item['statement']} | mudança: {item['context_change']}"
            for item in revalidation
        ))
    return "\n\n".join(parts), {
        "valid": valid,
        "requires_revalidation": revalidation,
        "policy": "Only explicit human applicability reviews may alter future mission context.",
    }


@router.post("/missions/{mission_code}/publish/{learning_node_id}", status_code=201)
def publish_learning_packet(
    mission_code: str,
    learning_node_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _membership(db, user.id)
    if membership is None:
        raise HTTPException(status_code=403, detail="A conta não tem um workspace associado.")
    _ensure_schema(db)
    mission = _mission(db, membership.organization_id, mission_code)
    snapshot = _graph_snapshot(
        db,
        organization_id=membership.organization_id,
        mission_id=mission.id,
        learning_node_id=learning_node_id,
    )
    learning = next(node for node in snapshot["nodes"] if node["id"] == learning_node_id)
    canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    lineage_sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    existing = db.execute(text("""
        SELECT * FROM pilot_learning_packets
        WHERE organization_id=:org AND source_mission_id=:mission AND source_learning_node_id=:node
        LIMIT 1
    """), {"org": membership.organization_id, "mission": mission.id, "node": learning_node_id}).mappings().first()
    if existing:
        db.execute(text("""
            UPDATE pilot_learning_packets
            SET title=:title, statement=:statement, graph_snapshot_json=:snapshot,
                lineage_sha256=:sha, updated_at=CURRENT_TIMESTAMP
            WHERE id=:id
        """), {
            "id": existing["id"], "title": normalize_generated_title(learning["label"]), "statement": learning["body"],
            "snapshot": canonical, "sha": lineage_sha,
        })
        packet_id = existing["id"]
    else:
        packet_id = str(uuid4())
        db.execute(text("""
            INSERT INTO pilot_learning_packets
            (id, organization_id, source_mission_id, source_mission_code, source_learning_node_id,
             title, statement, graph_snapshot_json, lineage_sha256, created_by_user_id)
            VALUES (:id, :org, :mission, :code, :node, :title, :statement, :snapshot, :sha, :user_id)
        """), {
            "id": packet_id, "org": membership.organization_id, "mission": mission.id,
            "code": mission.code, "node": learning_node_id, "title": normalize_generated_title(learning["label"]),
            "statement": learning["body"], "snapshot": canonical, "sha": lineage_sha,
            "user_id": user.id,
        })
    record_module_review(
        db,
        organization_id=membership.organization_id,
        mission_id=mission.id,
        mission_code=mission.code,
        module_key="learning",
        module_revision=None,
        module_content_hash=None,
        rationale=(
            "Aprendizagem publicada por decisão humana com a cadeia de decisão, "
            "ação, resultado e evidência preservada."
        ),
        user_id=user.id,
    )
    db.commit()
    row = db.execute(text("SELECT * FROM pilot_learning_packets WHERE id=:id"), {"id": packet_id}).mappings().one()
    return _packet_view(row)


@router.get("/missions/{mission_code}/candidates")
def learning_candidates(
    mission_code: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _membership(db, user.id)
    if membership is None:
        raise HTTPException(status_code=403, detail="A conta não tem um workspace associado.")
    _ensure_schema(db)
    target = _mission(db, membership.organization_id, mission_code)
    try:
        target_doc = json.loads(target.document_json or "{}")
    except Exception:
        target_doc = {}
    target_terms = _tokens(target.title, target.domain, str(target_doc.get("context") or ""), str(target_doc.get("central_question") or ""))
    rows = db.execute(text("""
        SELECT p.*, m.title AS source_title, m.domain AS source_domain,
               CASE r.disposition
                   WHEN 'still_valid' THEN 'reuse'
                   WHEN 'requires_revalidation' THEN 'requires_revalidation'
                   WHEN 'invalidated' THEN 'not_applicable'
                   ELSE 'pending'
               END AS applicability,
               r.rationale, r.context_change, r.updated_at AS reviewed_at
        FROM pilot_learning_packets p
        JOIN mi_missions m ON m.id=p.source_mission_id
        LEFT JOIN pilot_learning_reviews r
          ON r.learning_packet_id=p.id AND r.target_mission_id=:target
             AND r.organization_id=:org
        WHERE p.organization_id=:org AND p.source_mission_id<>:target
        ORDER BY p.updated_at DESC
    """), {"org": membership.organization_id, "target": target.id}).mappings().all()
    candidates = []
    for row in rows:
        source_terms = _tokens(row["source_title"] or "", row["source_domain"] or "", row["title"], row["statement"])
        overlap = len(target_terms & source_terms) / max(1, len(target_terms | source_terms)) if target_terms and source_terms else 0.0
        domain_bonus = 0.45 if row["source_domain"] == target.domain else 0.0
        relevance = min(1.0, domain_bonus + overlap)
        packet = _packet_view(row)
        packet["source_mission"]["title"] = row["source_title"]
        packet["source_mission"]["domain"] = row["source_domain"]
        packet["relevance_score"] = round(relevance, 4)
        packet["review"] = None if row["applicability"] in {None, "pending"} else {
            "applicability": row["applicability"],
            "rationale": row["rationale"],
            "context_change": row["context_change"],
            "reviewed_at": as_iso(row["reviewed_at"]),
        }
        candidates.append(packet)
    candidates.sort(key=lambda item: item["relevance_score"], reverse=True)
    return {
        "target_mission": {"id": target.id, "code": target.code, "title": target.title, "domain": target.domain},
        "principle": "A validade canónica pertence à aprendizagem; a revisão humana decide separadamente se ela é aplicável nesta missão.",
        "candidates": candidates,
        "summary": {
            "candidate_count": len(candidates),
            "reviewed_count": sum(1 for item in candidates if item["review"]),
            "canonically_valid_count": sum(1 for item in candidates if item["canonical_status"] == "valid"),
            "reusable_count": sum(1 for item in candidates if (item["review"] or {}).get("applicability") == "reuse"),
            "requires_revalidation_count": sum(1 for item in candidates if (item["review"] or {}).get("applicability") == "requires_revalidation"),
            "not_applicable_count": sum(1 for item in candidates if (item["review"] or {}).get("applicability") == "not_applicable"),
        },
    }


@router.post("/missions/{mission_code}/candidates/{packet_id}/review")
def review_learning_candidate(
    mission_code: str,
    packet_id: str,
    payload: LearningReviewRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _membership(db, user.id)
    if membership is None:
        raise HTTPException(status_code=403, detail="A conta não tem um workspace associado.")
    _ensure_schema(db)
    target = _mission(db, membership.organization_id, mission_code)
    packet = db.execute(text("""
        SELECT * FROM pilot_learning_packets WHERE id=:id AND organization_id=:org LIMIT 1
    """), {"id": packet_id, "org": membership.organization_id}).mappings().first()
    if packet is None or packet["source_mission_id"] == target.id:
        raise HTTPException(status_code=404, detail="A aprendizagem candidata não existe para esta missão.")
    applicability = payload.effective_applicability
    legacy_disposition = {
        "reuse": "still_valid",
        "requires_revalidation": "requires_revalidation",
        "not_applicable": "invalidated",
    }[applicability]
    review_id = str(uuid4())
    db.execute(text("""
        INSERT INTO pilot_learning_reviews
        (id, organization_id, target_mission_id, target_mission_code, learning_packet_id,
         disposition, rationale, context_change, reviewed_by_user_id)
        VALUES (:id, :org, :target, :code, :packet, :disposition, :rationale, :context_change, :user_id)
        ON CONFLICT (organization_id, target_mission_id, learning_packet_id)
        DO UPDATE SET disposition=EXCLUDED.disposition, rationale=EXCLUDED.rationale,
                      context_change=EXCLUDED.context_change, reviewed_by_user_id=EXCLUDED.reviewed_by_user_id,
                      updated_at=CURRENT_TIMESTAMP
    """), {
        "id": review_id, "org": membership.organization_id, "target": target.id,
        "code": target.code, "packet": packet_id, "disposition": legacy_disposition,
        "rationale": payload.rationale, "context_change": payload.context_change,
        "user_id": user.id,
    })
    db.commit()
    return {
        "status": "reviewed",
        "target_mission_code": target.code,
        "learning_packet_id": packet_id,
        "canonical_status": "valid",
        "applicability": applicability,
        "context_effect": (
            "will_influence_future_ai_context" if applicability == "reuse"
            else "will_be_presented_as_revalidation_question" if applicability == "requires_revalidation"
            else "not_used_in_this_mission"
        ),
    }


@router.get("/missions/{mission_code}/active-context")
def active_learning_context(
    mission_code: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _membership(db, user.id)
    if membership is None:
        raise HTTPException(status_code=403, detail="A conta não tem um workspace associado.")
    target = _mission(db, membership.organization_id, mission_code)
    context, manifest = inherited_learning_context(
        db,
        organization_id=membership.organization_id,
        target_mission_id=target.id,
    )
    db.commit()
    return {"mission_code": target.code, "context_text": context, "inheritance": manifest}
