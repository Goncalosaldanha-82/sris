from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.atlas_platform.audit import record_audit
from app.atlas_platform.auth import current_user
from app.atlas_platform.database import get_db
from app.atlas_platform.models import Membership, Role, User
from app.mission_intelligence.models import CanonicalMission
from app.evidence_graph import _require_mission_mutable
from app.pilot_serialization import as_iso


router = APIRouter(
    prefix="/api/pilot/mission-state",
    tags=["pilot-governed-mission-state"],
)

STATE_SCHEMA = "sris.governed-mission-state.v1"
AI_CONTEXT_SCHEMA = "sris.governed-ai-context.v1"
APPLICABILITY = {"required", "optional", "not_applicable"}
REVIEWER_ROLES = {Role.OWNER.value, Role.ADMIN.value, Role.REVIEWER.value}

MODULE_LABELS = {
    "mission": "Identidade e finalidade",
    "documents": "Documentos e fontes",
    "evidence": "Evidência e raciocínio",
    "comparison": "Alternativas e comparação",
    "economics": "Economia e recursos",
    "validation": "Medição e validação",
    "decision": "Decisão",
    "action": "Ação e execução",
    "outcome": "Resultado",
    "learning": "Aprendizagem",
    "memory": "Memória organizacional",
    "intelligence": "Assistência de IA",
}

# A review is valid for the exact upstream snapshots used at that moment.
# Intelligence is deliberately absent: AI output may support review, but never
# becomes an authoritative upstream dependency by itself.
REVIEW_UPSTREAMS = {
    "comparison": ("governance_policy", "mission", "decision_evidence", "economics"),
    "economics": ("governance_policy", "mission", "decision_evidence", "validation"),
    "validation": ("governance_policy", "mission", "decision_evidence"),
    "decision": ("governance_policy", "mission", "decision_evidence", "comparison", "economics", "validation"),
    "learning": ("governance_policy", "decision", "action", "outcome", "evidence"),
}
REVIEW_ORDER = ("validation", "economics", "comparison", "decision", "learning")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _stable_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove operational timestamps from semantic state projections."""

    return [
        {
            key: value
            for key, value in row.items()
            if key not in {"created_at", "updated_at"}
        }
        for row in rows
    ]


def _loads(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


def _table_exists(db: Session, table_name: str) -> bool:
    return inspect(db.get_bind()).has_table(table_name)


def _rows(db: Session, statement: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in db.execute(text(statement), params).mappings().all()]


def _membership(db: Session, user_id: str) -> Membership:
    membership = (
        db.query(Membership)
        .filter(Membership.user_id == user_id)
        .order_by(Membership.created_at.asc())
        .first()
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="A conta não tem um workspace associado.")
    return membership


def _mission(db: Session, organization_id: str, mission_code: str) -> CanonicalMission:
    mission = (
        db.query(CanonicalMission)
        .filter(
            CanonicalMission.organization_id == organization_id,
            CanonicalMission.code == mission_code,
        )
        .one_or_none()
    )
    if mission is None:
        raise HTTPException(status_code=404, detail="A missão indicada não existe neste workspace.")
    return mission


def _ensure_schema(db: Session) -> None:
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS pilot_mission_governance_policies (
                id VARCHAR(64) PRIMARY KEY,
                organization_id VARCHAR(64) NOT NULL,
                mission_id VARCHAR(64) NOT NULL,
                mission_code VARCHAR(80) NOT NULL,
                alternatives_applicability VARCHAR(30) NOT NULL DEFAULT 'required',
                economics_applicability VARCHAR(30) NOT NULL DEFAULT 'required',
                measurement_applicability VARCHAR(30) NOT NULL DEFAULT 'optional',
                rationale TEXT NOT NULL DEFAULT '',
                mission_revision INTEGER NOT NULL,
                mission_content_hash VARCHAR(64) NOT NULL,
                mission_governance_hash VARCHAR(64) NULL,
                revision INTEGER NOT NULL DEFAULT 1,
                content_hash VARCHAR(64) NOT NULL DEFAULT '',
                reviewed_by_user_id VARCHAR(64) NULL,
                reviewed_at TIMESTAMP NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (organization_id, mission_id)
            )
            """
        )
    )
    policy_columns = {
        item["name"]
        for item in inspect(db.get_bind()).get_columns(
            "pilot_mission_governance_policies"
        )
    }
    if "mission_governance_hash" not in policy_columns:
        db.execute(
            text(
                "ALTER TABLE pilot_mission_governance_policies "
                "ADD COLUMN mission_governance_hash VARCHAR(64) NULL"
            )
        )
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS pilot_mission_module_reviews (
                id VARCHAR(64) PRIMARY KEY,
                organization_id VARCHAR(64) NOT NULL,
                mission_id VARCHAR(64) NOT NULL,
                mission_code VARCHAR(80) NOT NULL,
                module_key VARCHAR(40) NOT NULL,
                module_revision INTEGER NULL,
                module_content_hash VARCHAR(64) NOT NULL,
                upstream_hashes_json TEXT NOT NULL DEFAULT '{}',
                rationale TEXT NOT NULL DEFAULT '',
                reviewed_by_user_id VARCHAR(64) NULL,
                reviewed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )
    db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_pilot_mission_module_reviews_latest
            ON pilot_mission_module_reviews
               (organization_id, mission_id, module_key, reviewed_at)
            """
        )
    )


def _validation_profile(mission: CanonicalMission) -> str:
    document = _loads(mission.document_json, {})
    return str((document.get("metadata") or {}).get("validation_profile") or "none")


def mission_governance_hash(mission: CanonicalMission) -> str:
    """Hash decision-relevant mission content, excluding lifecycle administration.

    Completing, pausing or archiving a mission changes its full canonical state,
    but cannot by itself invalidate the evidence and reviews that justified that
    transition. Any substantive change to purpose, context or records remains in
    this projection and therefore still invalidates downstream reviews.
    """

    document = _loads(mission.document_json, {})
    if not isinstance(document, dict):
        return str(mission.content_hash or "")
    projection = json.loads(_canonical_json(document))
    projection.pop("lifecycle_state", None)
    metadata = projection.get("metadata")
    if isinstance(metadata, dict):
        metadata.pop("lifecycle_state", None)
    return _hash(projection)


def _default_policy(mission: CanonicalMission) -> dict[str, Any]:
    measurement = "required" if _validation_profile(mission) != "none" else "optional"
    policy = {
        "id": None,
        "source": "platform_default",
        "revision": 0,
        "alternatives_applicability": "required",
        "economics_applicability": "required",
        "measurement_applicability": measurement,
        "rationale": (
            "Política transversal do SRIS: toda a missão explicita alternativas e "
            "economia/recursos; a medição quantitativa é obrigatória quando existe "
            "um perfil de validação mensurável."
        ),
        "mission_revision": mission.revision,
        "mission_content_hash": mission.content_hash,
        "mission_governance_hash": mission_governance_hash(mission),
        "content_hash": None,
        "reviewed_by_user_id": None,
        "reviewed_at": None,
        "current": True,
        "stale_reason": None,
    }
    policy["content_hash"] = _hash(
        {
            key: policy[key]
            for key in (
                "alternatives_applicability",
                "economics_applicability",
                "measurement_applicability",
                "rationale",
                "mission_governance_hash",
            )
        }
    )
    return policy


def _policy(db: Session, mission: CanonicalMission) -> dict[str, Any]:
    _ensure_schema(db)
    row = db.execute(
        text(
            """
            SELECT * FROM pilot_mission_governance_policies
            WHERE organization_id=:org AND mission_id=:mission
            """
        ),
        {"org": mission.organization_id, "mission": mission.id},
    ).mappings().first()
    if row is None:
        return _default_policy(mission)
    policy = dict(row)
    current = bool(
        str(
            policy.get("mission_governance_hash")
            or policy.get("mission_content_hash")
            or ""
        )
        == mission_governance_hash(mission)
    )
    policy.update(
        source="human_reviewed_override",
        current=current,
        stale_reason=(
            None
            if current
            else "A finalidade ou o contexto da missão mudou depois desta política de aplicabilidade."
        ),
        reviewed_at=as_iso(policy.get("reviewed_at")),
    )
    return policy


def mission_axis_policy(
    db: Session,
    *,
    organization_id: str,
    mission_id: str,
    mission_code: str,
) -> dict[str, Any]:
    mission = (
        db.query(CanonicalMission)
        .filter(
            CanonicalMission.organization_id == organization_id,
            CanonicalMission.id == mission_id,
            CanonicalMission.code == mission_code,
        )
        .one_or_none()
    )
    if mission is None:
        raise HTTPException(status_code=404, detail="A missão indicada não existe neste workspace.")
    return _policy(db, mission)


def _module_payloads(db: Session, mission: CanonicalMission) -> dict[str, Any]:
    params = {"org": mission.organization_id, "mission": mission.id, "code": mission.code}
    documents = _rows(
        db,
        """
        SELECT id, original_filename, media_type, byte_size, sha256,
               extraction_status, extraction_error, created_at
        FROM mi_mission_attachments
        WHERE organization_id=:org AND mission_id=:mission
        ORDER BY id
        """,
        params,
    )

    graph_nodes: list[dict[str, Any]] = []
    graph_edges: list[dict[str, Any]] = []
    if _table_exists(db, "pilot_evidence_graph_nodes"):
        graph_nodes = _rows(
            db,
            """
            SELECT id, node_type, label, body, status, confidence, source_kind,
                   source_id, attachment_id, char_start, char_end, source_sha256,
                   provenance_json, updated_at
            FROM pilot_evidence_graph_nodes
            WHERE organization_id=:org AND mission_id=:mission
            ORDER BY id
            """,
            params,
        )
    if _table_exists(db, "pilot_evidence_graph_edges"):
        graph_edges = _rows(
            db,
            """
            SELECT id, from_node_id, to_node_id, edge_type, provenance_json
            FROM pilot_evidence_graph_edges
            WHERE organization_id=:org AND mission_id=:mission
            ORDER BY id
            """,
            params,
        )

    matrices: list[dict[str, Any]] = []
    if _table_exists(db, "pilot_alternative_matrices"):
        matrices = _rows(
            db,
            """
            SELECT id, revision, status, snapshot_json, content_hash,
                   reviewed_by_user_id, reviewed_at, created_at
            FROM pilot_alternative_matrices
            WHERE organization_id=:org AND mission_id=:mission
            ORDER BY revision DESC LIMIT 1
            """,
            params,
        )

    business_cases: list[dict[str, Any]] = []
    business_items: list[dict[str, Any]] = []
    if _table_exists(db, "pilot_business_cases"):
        business_cases = _rows(
            db,
            """
            SELECT * FROM pilot_business_cases
            WHERE organization_id=:org AND mission_id=:mission
            """,
            params,
        )
    if business_cases and _table_exists(db, "pilot_business_case_items"):
        business_items = _rows(
            db,
            """
            SELECT id, kind, financial_treatment, category, label, description,
                   phase, unit, amount_basis, planned_quantity, actual_quantity,
                   conservative_amount, base_amount, favorable_amount,
                   committed_amount, realized_amount, forecast_amount,
                   start_month, end_month, recurrence, source_label,
                   evidence_node_id, alternative_node_id, responsible,
                   operational_status, blocker, assumption, confidence,
                   include_in_totals, updated_at, retired_at
            FROM pilot_business_case_items
            WHERE organization_id=:org AND mission_id=:mission
            ORDER BY id
            """,
            params,
        )

    protocols: list[dict[str, Any]] = []
    measurements: list[dict[str, Any]] = []
    if _table_exists(db, "pilot_validation_protocols"):
        protocols = _rows(
            db,
            """
            SELECT * FROM pilot_validation_protocols
            WHERE organization_id=:org AND mission_id=:mission
            """,
            params,
        )
    if _table_exists(db, "pilot_validation_measurements"):
        measurements = _rows(
            db,
            """
            SELECT * FROM pilot_validation_measurements
            WHERE organization_id=:org AND mission_id=:mission
            ORDER BY phase, id
            """,
            params,
        )

    cycles: list[dict[str, Any]] = []
    if _table_exists(db, "pilot_decision_cycles"):
        cycles = _rows(
            db,
            """
            SELECT * FROM pilot_decision_cycles
            WHERE organization_id=:org AND mission_code=:code
            ORDER BY created_at, id
            """,
            params,
        )

    packets: list[dict[str, Any]] = []
    if _table_exists(db, "pilot_learning_packets") and _table_exists(
        db, "pilot_evidence_graph_nodes"
    ):
        packets = _rows(
            db,
            """
            SELECT packet.id, packet.source_learning_node_id, packet.title,
                   packet.statement, packet.lineage_sha256,
                   packet.created_at, packet.updated_at
            FROM pilot_learning_packets packet
            JOIN pilot_evidence_graph_nodes source_node
              ON source_node.id=packet.source_learning_node_id
             AND source_node.organization_id=packet.organization_id
             AND source_node.mission_id=packet.source_mission_id
            WHERE packet.organization_id=:org
              AND packet.source_mission_id=:mission
              AND source_node.status IN ('accepted','verified')
            ORDER BY packet.id
            """,
            params,
        )

    memory: list[dict[str, Any]] = []
    if _table_exists(db, "mi_memory_items"):
        memory = _rows(
            db,
            """
            SELECT id, canonical_record_id, item_type, title, summary, state,
                   confidence, source_revision, source_content_hash, updated_at
            FROM mi_memory_items
            WHERE organization_id=:org AND mission_id=:mission
            ORDER BY id
            """,
            params,
        )

    intelligence: list[dict[str, Any]] = []
    if _table_exists(db, "mi_intelligence_runs"):
        intelligence = _rows(
            db,
            """
            SELECT id, execution_mode, status, engine_version, provider, model,
                   snapshot_hash, review_status, reviewed_by_user_id,
                   reviewed_at, created_at
            FROM mi_intelligence_runs
            WHERE organization_id=:org AND mission_id=:mission
            ORDER BY created_at DESC LIMIT 20
            """,
            params,
        )

    active_nodes = [
        row for row in graph_nodes if row.get("status") not in {"rejected", "superseded"}
    ]
    action_nodes = [row for row in active_nodes if row.get("node_type") == "action"]
    outcome_nodes = [row for row in active_nodes if row.get("node_type") == "outcome"]
    learning_nodes = [row for row in active_nodes if row.get("node_type") == "learning"]
    return {
        "mission": {
            "id": mission.id,
            "code": mission.code,
            "title": mission.title,
            "lifecycle_state": mission.lifecycle_state,
            "revision": mission.revision,
            "content_hash": mission.content_hash,
            "governance_content_hash": mission_governance_hash(mission),
            "document_json": mission.document_json,
        },
        "documents": documents,
        "evidence": {"nodes": graph_nodes, "edges": graph_edges},
        "comparison": matrices[0] if matrices else None,
        "economics": {
            "case": business_cases[0] if business_cases else None,
            "items": business_items,
        },
        "validation": {
            "protocol": protocols[0] if protocols else None,
            "measurements": measurements,
        },
        "decision": cycles,
        "action": action_nodes,
        "outcome": outcome_nodes,
        "learning": {"nodes": learning_nodes, "packets": packets},
        "memory": memory,
        "intelligence": intelligence,
    }


def _module_hashes(payloads: dict[str, Any]) -> dict[str, str | None]:
    mission = payloads["mission"]
    comparison = payloads["comparison"]
    economics = payloads["economics"]
    validation = payloads["validation"]
    cycles = payloads["decision"]
    epistemic_types = {
        "observation",
        "evidence",
        "claim",
        "assumption",
        "constraint",
        "gap",
        "hypothesis",
        "target",
        "alternative",
    }
    epistemic_nodes = [
        row
        for row in payloads["evidence"]["nodes"]
        if row.get("node_type") in epistemic_types
    ]
    epistemic_ids = {row.get("id") for row in epistemic_nodes}
    epistemic_edges = [
        row
        for row in payloads["evidence"]["edges"]
        if row.get("from_node_id") in epistemic_ids
        and row.get("to_node_id") in epistemic_ids
    ]
    evidence_projection = {
        "nodes": _stable_rows(epistemic_nodes),
        "edges": _stable_rows(epistemic_edges),
    }
    decision_epistemic_nodes = [
        row
        for row in epistemic_nodes
        if _loads(row.get("provenance_json"), {}).get("governance_role")
        != "outcome_evidence"
    ]
    decision_epistemic_ids = {row.get("id") for row in decision_epistemic_nodes}
    decision_evidence_projection = {
        "nodes": _stable_rows(decision_epistemic_nodes),
        "edges": _stable_rows(
            [
                row
                for row in epistemic_edges
                if row.get("from_node_id") in decision_epistemic_ids
                and row.get("to_node_id") in decision_epistemic_ids
            ]
        ),
    }
    decision_projection = [
        {
            "id": row.get("id"),
            "mission_code": row.get("mission_code"),
            "decision": row.get("decision"),
            "action": row.get("action"),
            "owner": row.get("owner"),
            "due_date": row.get("due_date"),
            "status": (
                "governed"
                if row.get("status") in {"committed", "in_progress", "completed"}
                else row.get("status")
            ),
            "expected_outcome": row.get("expected_outcome"),
            "evidence_node_id": row.get("evidence_node_id"),
            "mission_revision": row.get("mission_revision"),
            "mission_content_hash": row.get("mission_content_hash"),
            "mission_governance_hash": row.get("mission_governance_hash"),
            "matrix_revision": row.get("matrix_revision"),
            "matrix_content_hash": row.get("matrix_content_hash"),
            "business_case_revision": row.get("business_case_revision"),
            "business_case_content_hash": row.get("business_case_content_hash"),
            "validation_revision": row.get("validation_revision"),
            "validation_content_hash": row.get("validation_content_hash"),
        }
        for row in cycles
    ]
    action_projection = {
        "cycles": [
            {
                key: row.get(key)
                for key in (
                    "id",
                    "action",
                    "owner",
                    "due_date",
                    "action_started_at",
                    "status",
                )
            }
            for row in cycles
            if row.get("status") in {"in_progress", "completed"}
            and row.get("action_started_at")
        ],
        "nodes": _stable_rows(payloads["action"]),
    }
    outcome_projection = {
        "cycles": [
            {
                key: row.get(key)
                for key in (
                    "id",
                    "actual_outcome",
                    "actual_outcome_at",
                    "outcome_evidence_node_id",
                )
            }
            for row in cycles
            if row.get("status") == "completed"
        ],
        "nodes": _stable_rows(payloads["outcome"]),
    }
    learning_projection = {
        "cycles": [
            {"id": row.get("id"), "learning": row.get("learning")}
            for row in cycles
            if row.get("status") == "completed" and row.get("learning")
        ],
        "nodes": _stable_rows(payloads["learning"]["nodes"]),
        "packets": _stable_rows(payloads["learning"]["packets"]),
    }
    hashes: dict[str, str | None] = {
        "mission": str(mission.get("governance_content_hash") or "") or None,
        "documents": _hash(_stable_rows(payloads["documents"])) if payloads["documents"] else None,
        "evidence": _hash(evidence_projection) if epistemic_nodes or epistemic_edges else None,
        "decision_evidence": (
            _hash(decision_evidence_projection)
            if decision_epistemic_nodes or decision_evidence_projection["edges"]
            else None
        ),
        "comparison": str(comparison.get("content_hash") or "") if comparison else None,
        "economics": (
            str((economics.get("case") or {}).get("content_hash") or "") or None
        ),
        "validation": (
            str((validation.get("protocol") or {}).get("content_hash") or "") or None
        ),
        "decision": _hash(decision_projection) if decision_projection else None,
        "action": _hash(action_projection) if action_projection["cycles"] or action_projection["nodes"] else None,
        "outcome": _hash(outcome_projection) if outcome_projection["cycles"] or outcome_projection["nodes"] else None,
        "learning": _hash(learning_projection) if (
            learning_projection["cycles"] or learning_projection["nodes"] or learning_projection["packets"]
        ) else None,
        "memory": _hash(_stable_rows(payloads["memory"])) if payloads["memory"] else None,
        # Assistance is a support projection. It has its own hash and is not
        # folded into the governed canonical state hash below.
        "intelligence": _hash(payloads["intelligence"]) if payloads["intelligence"] else None,
    }
    return hashes


def _latest_reviews(
    db: Session,
    mission: CanonicalMission,
    module_hashes: dict[str, str | None],
) -> dict[str, dict[str, Any]]:
    _ensure_schema(db)
    rows = _rows(
        db,
        """
        SELECT * FROM pilot_mission_module_reviews
        WHERE organization_id=:org AND mission_id=:mission
        ORDER BY reviewed_at DESC, created_at DESC
        """,
        {"org": mission.organization_id, "mission": mission.id},
    )
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row["module_key"])
        selected = latest.get(key)
        if selected is None:
            latest[key] = row
            continue
        # Older SQLite bootstraps recorded timestamps only to the second.  If
        # two reviews therefore tie exactly, prefer the one bound to the
        # current projection instead of exposing a false stale state.
        row_time = (str(row.get("reviewed_at") or ""), str(row.get("created_at") or ""))
        selected_time = (
            str(selected.get("reviewed_at") or ""),
            str(selected.get("created_at") or ""),
        )
        if (
            row_time == selected_time
            and row.get("module_content_hash") == module_hashes.get(key)
            and selected.get("module_content_hash") != module_hashes.get(key)
        ):
            latest[key] = row
    return latest


def _review_status(
    *,
    module_key: str,
    module_hashes: dict[str, str | None],
    dependency_hashes: dict[str, str | None],
    reviews: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    review = reviews.get(module_key)
    if review is None:
        return {
            "status": "unreviewed",
            "current": False,
            "reviewed_at": None,
            "reviewed_by_user_id": None,
            "rationale": "",
            "stale_dependencies": [],
        }
    upstream_at_review = _loads(review.get("upstream_hashes_json"), {})
    stale_dependencies = [
        key
        for key, saved_hash in upstream_at_review.items()
        if dependency_hashes.get(key) != saved_hash
    ]
    module_current = module_hashes.get(module_key) == review.get("module_content_hash")
    current = bool(module_current and not stale_dependencies)
    return {
        "status": "current" if current else "stale",
        "current": current,
        "reviewed_at": as_iso(review.get("reviewed_at")),
        "reviewed_by_user_id": review.get("reviewed_by_user_id"),
        "rationale": review.get("rationale") or "",
        "module_revision": review.get("module_revision"),
        "reviewed_module_hash": review.get("module_content_hash"),
        "stale_dependencies": stale_dependencies,
        "module_changed": not module_current,
    }


def _review_bundle(
    *,
    module_hashes: dict[str, str | None],
    reviews: dict[str, dict[str, Any]],
    applicability: dict[str, str],
) -> tuple[dict[str, dict[str, Any]], dict[str, str | None]]:
    """Resolve human-review validity in dependency order.

    A downstream review binds not only to upstream content, but also to whether
    that content had a current human review. This makes invalidation cascade
    without making a repeated review of unchanged content invalidate everything.
    """

    dependency_hashes = dict(module_hashes)
    statuses: dict[str, dict[str, Any]] = {}
    for module_key in REVIEW_ORDER:
        status = _review_status(
            module_key=module_key,
            module_hashes=module_hashes,
            dependency_hashes=dependency_hashes,
            reviews=reviews,
        )
        statuses[module_key] = status
        if applicability.get(module_key) == "not_applicable":
            dependency_hashes[module_key] = None
        elif module_hashes.get(module_key):
            dependency_hashes[module_key] = _hash(
                {
                    "content_hash": module_hashes[module_key],
                    "human_review": status["status"],
                }
            )
    for module_key in MODULE_LABELS:
        if module_key in statuses:
            continue
        statuses[module_key] = _review_status(
            module_key=module_key,
            module_hashes=module_hashes,
            dependency_hashes=dependency_hashes,
            reviews=reviews,
        )
    return statuses, dependency_hashes


def record_module_review(
    db: Session,
    *,
    organization_id: str,
    mission_id: str,
    mission_code: str,
    module_key: str,
    module_revision: int | None,
    module_content_hash: str | None,
    rationale: str,
    user_id: str | None,
) -> None:
    """Bind a human review to the exact governed upstream state it used."""

    if module_key not in REVIEW_UPSTREAMS:
        raise ValueError(f"Unsupported governed module review: {module_key}")
    mission = (
        db.query(CanonicalMission)
        .filter(
            CanonicalMission.organization_id == organization_id,
            CanonicalMission.id == mission_id,
            CanonicalMission.code == mission_code,
        )
        .one()
    )
    _ensure_schema(db)
    hashes = _module_hashes(_module_payloads(db, mission))
    policy = _policy(db, mission)
    hashes["governance_policy"] = str(policy.get("content_hash") or "") or _hash(
        _default_policy(mission)
    )
    applicability = _applicability_map(policy)
    reviews = _latest_reviews(db, mission, hashes)
    _review_statuses, dependency_hashes = _review_bundle(
        module_hashes=hashes,
        reviews=reviews,
        applicability=applicability,
    )
    current_module_hash = hashes.get(module_key)
    if not current_module_hash:
        raise ValueError(f"Cannot review an empty governed module: {module_key}")
    if module_content_hash and module_content_hash != current_module_hash:
        raise ValueError(f"The reviewed {module_key} hash is not the current governed projection")
    upstream = {
        key: dependency_hashes.get(key) for key in REVIEW_UPSTREAMS[module_key]
    }
    db.execute(
        text(
            """
            INSERT INTO pilot_mission_module_reviews
                (id, organization_id, mission_id, mission_code, module_key,
                 module_revision, module_content_hash, upstream_hashes_json,
                 rationale, reviewed_by_user_id, reviewed_at)
            VALUES
                (:id, :org, :mission, :code, :module, :revision, :hash,
                 :upstream, :rationale, :user, :reviewed_at)
            """
        ),
        {
            "id": str(uuid4()),
            "org": organization_id,
            "mission": mission_id,
            "code": mission_code,
            "module": module_key,
            "revision": module_revision,
            "hash": current_module_hash,
            "upstream": _canonical_json(upstream),
            "rationale": rationale.strip(),
            "user": user_id,
            "reviewed_at": _utcnow(),
        },
    )


def _module_counts(payloads: dict[str, Any]) -> dict[str, int]:
    nodes = payloads["evidence"]["nodes"]
    active_nodes = [row for row in nodes if row.get("status") not in {"rejected", "superseded"}]
    cycles = payloads["decision"]
    started_cycle_ids = {
        str(row["id"])
        for row in cycles
        if row.get("status") in {"in_progress", "completed"}
        and row.get("action_started_at")
    }
    outcome_cycle_ids = {
        str(row["id"])
        for row in cycles
        if row.get("status") == "completed" and row.get("actual_outcome")
    }
    learning_cycle_ids = {
        str(row["id"])
        for row in cycles
        if row.get("status") == "completed" and row.get("learning")
    }
    return {
        "mission": 1,
        "documents": len(payloads["documents"]),
        "evidence": len(active_nodes),
        "comparison": 1 if payloads["comparison"] else 0,
        "economics": 1 if payloads["economics"]["case"] else 0,
        "validation": len(payloads["validation"]["measurements"]),
        "decision": len(cycles),
        "action": max(len(started_cycle_ids), len(payloads["action"])),
        "outcome": max(len(outcome_cycle_ids), len(payloads["outcome"])),
        "learning": max(len(learning_cycle_ids), len(payloads["learning"]["nodes"])),
        "memory": len(payloads["memory"]),
        "intelligence": len(payloads["intelligence"]),
    }


def _applicability_map(policy: dict[str, Any]) -> dict[str, str]:
    return {
        "mission": "required",
        "documents": "required",
        "evidence": "required",
        "comparison": str(policy["alternatives_applicability"]),
        "economics": str(policy["economics_applicability"]),
        "validation": str(policy["measurement_applicability"]),
        "decision": "required",
        "action": "required",
        "outcome": "required",
        "learning": "required",
        "memory": "required",
        "intelligence": "optional",
    }


def _native_reviewed(module_key: str, payloads: dict[str, Any]) -> bool:
    if module_key == "comparison":
        return bool(payloads["comparison"] and payloads["comparison"].get("status") == "reviewed")
    if module_key == "economics":
        case = payloads["economics"]["case"] or {}
        return bool(case.get("status") == "reviewed")
    if module_key == "validation":
        protocol = payloads["validation"]["protocol"] or {}
        return bool(protocol.get("reviewed_at") and protocol.get("attribution_confidence"))
    return False


def _structured_conflicts(
    *,
    mission: CanonicalMission,
    policy: dict[str, Any],
    payloads: dict[str, Any],
    hashes: dict[str, str | None],
    review_statuses: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []

    def add(
        code: str,
        severity: Literal["critical", "warning", "info"],
        title: str,
        detail: str,
        modules: list[str],
        object_ids: list[str] | None = None,
    ) -> None:
        issues.append(
            {
                "id": f"CONFLICT:{code}",
                "code": code,
                "severity": severity,
                "title": title,
                "detail": detail,
                "modules": modules,
                "object_ids": object_ids or [],
                "requires_human_resolution": severity != "info",
            }
        )

    if not policy.get("current", True):
        add(
            "governance_policy_stale",
            "critical",
            "Aplicabilidade por rever",
            str(policy.get("stale_reason") or "A política já não corresponde à revisão atual da missão."),
            ["mission"],
        )

    open_cycles = [
        row
        for row in payloads["decision"]
        if row.get("status") not in {"completed", "abandoned"}
    ]
    if mission.lifecycle_state == "completed" and open_cycles:
        add(
            "completed_mission_with_open_decision_cycle",
            "critical",
            "Missão concluída com decisão ainda aberta",
            "Uma decisão foi reaberta ou continua em curso. Reative a missão, corrija a cadeia e só depois volte a concluí-la.",
            ["mission", "decision", "action", "outcome", "learning"],
            [f"CYCLE:{row['id']}" for row in open_cycles],
        )

    economics_required = policy["economics_applicability"] == "required"
    measurement_required = policy["measurement_applicability"] == "required"
    comparison_required = policy["alternatives_applicability"] == "required"
    applicability_records = (
        ("comparison", "alternatives_applicability", payloads["comparison"]),
        ("economics", "economics_applicability", payloads["economics"]["case"]),
        ("validation", "measurement_applicability", payloads["validation"]["protocol"]),
    )
    for module_key, policy_key, record in applicability_records:
        if policy[policy_key] == "not_applicable" and record:
            add(
                f"{module_key}_present_but_not_applicable",
                "warning",
                f"{MODULE_LABELS[module_key]} contém registos apesar da exceção",
                "A pessoa revisora deve confirmar se estes registos são históricos, "
                "se devem ser retirados do âmbito ou se a aplicabilidade deve ser reposta.",
                ["mission", module_key],
            )
    if economics_required and not payloads["economics"]["case"]:
        add(
            "required_economics_missing",
            "critical",
            "Economia e recursos obrigatórios, mas não iniciados",
            "A ausência de dados económicos não equivale a custo zero e bloqueia a conclusão governada.",
            ["mission", "economics"],
        )
    if measurement_required and not payloads["validation"]["protocol"]:
        add(
            "required_validation_missing",
            "critical",
            "Medição obrigatória, mas sem protocolo",
            "A missão declarou uma necessidade mensurável sem preservar baseline, resultado e regras de atribuição.",
            ["mission", "validation"],
        )
    active_alternatives = [
        row
        for row in payloads["evidence"]["nodes"]
        if row.get("node_type") == "alternative"
        and row.get("status") not in {"rejected", "superseded"}
    ]
    if comparison_required and len(active_alternatives) < 2:
        add(
            "required_alternatives_missing",
            "critical",
            "Alternativas insuficientes",
            "Uma decisão governada exige pelo menos duas opções reais e comparáveis.",
            ["evidence", "comparison"],
        )

    matrix = payloads["comparison"] or {}
    case = payloads["economics"]["case"] or {}
    if matrix and economics_required and not case:
        add(
            "matrix_without_economics",
            "critical",
            "Comparação concluída sem fundamento económico",
            "A matriz não pode tratar Custo como critério completo enquanto o business case obrigatório não existe.",
            ["comparison", "economics"],
            [f"MATRIX:{matrix.get('id')}"] if matrix.get("id") else None,
        )
    if matrix and case and policy["economics_applicability"] != "not_applicable":
        snapshot = _loads(matrix.get("snapshot_json"), {})
        saved = str(snapshot.get("business_case_content_hash") or "")
        current = str(case.get("content_hash") or "")
        if not saved or saved != current:
            add(
                "matrix_economics_stale",
                "critical",
                "A matriz usa uma revisão económica ultrapassada",
                "Regrave e reveja a comparação depois de atualizar custos, benefícios ou recursos.",
                ["comparison", "economics"],
                [f"MATRIX:{matrix.get('id')}", f"BC:{case.get('id')}"] ,
            )

    for module_key in ("comparison", "economics", "validation"):
        applicability_key = {
            "comparison": "alternatives_applicability",
            "economics": "economics_applicability",
            "validation": "measurement_applicability",
        }[module_key]
        if _native_reviewed(module_key, payloads) and review_statuses[module_key]["status"] == "unreviewed":
            add(
                f"{module_key}_legacy_review_unbound",
                "warning",
                f"{MODULE_LABELS[module_key]} revisto sem fotografia transversal",
                "A revisão humana existe, mas ainda não está ligada às revisões dos módulos que a fundamentaram.",
                [module_key, *REVIEW_UPSTREAMS[module_key]],
            )
        elif review_statuses[module_key]["status"] == "stale":
            stale = ", ".join(
                MODULE_LABELS.get(
                    key,
                    "Aplicabilidade da missão"
                    if key == "governance_policy"
                    else "Evidência usada na decisão"
                    if key == "decision_evidence"
                    else key,
                )
                for key in review_statuses[module_key].get("stale_dependencies", [])
            )
            add(
                f"{module_key}_review_stale",
                "critical",
                f"Revisão de {MODULE_LABELS[module_key].lower()} invalidada",
                f"Mudou o próprio módulo ou um fundamento posterior à revisão{': ' + stale if stale else ''}.",
                [module_key, *review_statuses[module_key].get("stale_dependencies", [])],
            )
        elif (
            hashes.get(module_key)
            and policy[applicability_key] != "not_applicable"
            and review_statuses[module_key]["status"] == "unreviewed"
        ):
            add(
                f"{module_key}_human_review_missing",
                "warning",
                f"{MODULE_LABELS[module_key]} ainda sem revisão humana",
                "O conteúdo existe, mas ainda não foi validado sobre a fotografia transversal atual da missão.",
                [module_key, *REVIEW_UPSTREAMS[module_key]],
            )

    active_node_by_id = {
        str(row["id"]): row
        for row in payloads["evidence"]["nodes"]
        if row.get("status") not in {"rejected", "superseded"}
    }
    active_evidence_ids = {
        node_id
        for node_id, row in active_node_by_id.items()
        if row.get("node_type") == "evidence"
    }
    reviewed_evidence_ids = {
        node_id
        for node_id, row in active_node_by_id.items()
        if row.get("node_type") == "evidence"
        and row.get("status") in {"accepted", "verified"}
    }
    governed_cycles = [
        row
        for row in payloads["decision"]
        if row.get("status") in {"committed", "in_progress", "completed"}
    ]
    if governed_cycles and review_statuses["decision"]["status"] != "current":
        add(
            "decision_review_missing_or_stale",
            "critical",
            "Decisão sem revisão transversal atual",
            "A decisão comprometida tem de permanecer ligada às revisões atuais de missão, evidência, alternativas, economia e medição.",
            ["decision", *REVIEW_UPSTREAMS["decision"]],
            [f"CYCLE:{row['id']}" for row in governed_cycles],
        )
    snapshot_dependencies = (
        ("mission", "mission_governance_hash", "required"),
        ("comparison", "matrix_content_hash", policy["alternatives_applicability"]),
        ("economics", "business_case_content_hash", policy["economics_applicability"]),
        ("validation", "validation_content_hash", policy["measurement_applicability"]),
    )
    for cycle in governed_cycles:
        cycle_id = str(cycle.get("id"))
        foundation_evidence = str(cycle.get("evidence_node_id") or "")
        if not foundation_evidence:
            add(
                f"decision_evidence_missing:{cycle_id}",
                "critical",
                "Decisão sem evidência de fundamento",
                "Uma decisão governada tem de preservar a evidência humana que sustentou o compromisso.",
                ["evidence", "decision"],
                [f"CYCLE:{cycle_id}"],
            )
        elif foundation_evidence not in active_evidence_ids:
            add(
                f"decision_evidence_unavailable:{cycle_id}",
                "critical",
                "Evidência da decisão indisponível",
                "A decisão governada não aponta para uma evidência ativa da própria missão.",
                ["evidence", "decision"],
                [f"CYCLE:{cycle_id}", f"GRAPH:{foundation_evidence}"],
            )
        elif foundation_evidence not in reviewed_evidence_ids:
            add(
                f"decision_evidence_unreviewed:{cycle_id}",
                "critical",
                "Evidência da decisão ainda não revista",
                "Uma proposta factual não pode fundamentar uma decisão governada sem revisão humana explícita.",
                ["evidence", "decision"],
                [f"CYCLE:{cycle_id}", f"GRAPH:{foundation_evidence}"],
            )
        stale_inputs: list[str] = []
        for module_key, snapshot_field, applicability in snapshot_dependencies:
            if applicability == "not_applicable":
                continue
            saved_hash = str(cycle.get(snapshot_field) or "") or None
            current_hash = hashes.get(module_key)
            required_or_present = applicability == "required" or current_hash is not None
            if required_or_present and saved_hash != current_hash:
                stale_inputs.append(module_key)
        if stale_inputs:
            add(
                f"decision_snapshot_stale:{cycle['id']}",
                "critical",
                "Fundamentos da decisão mudaram após o compromisso",
                "A decisão preserva a fotografia usada, mas já não coincide com: "
                + ", ".join(MODULE_LABELS[key] for key in stale_inputs)
                + ". A pessoa responsável tem de confirmar, corrigir ou reabrir a decisão.",
                ["decision", *stale_inputs],
                [f"CYCLE:{cycle['id']}"],
            )
    if payloads["learning"]["packets"] and review_statuses["learning"]["status"] != "current":
        add(
            "learning_review_missing_or_stale",
            "critical",
            "Aprendizagem publicada sem revisão transversal atual",
            "A aprendizagem reutilizável tem de continuar ligada à decisão, ação, resultado e evidência que a produziram.",
            ["learning", *REVIEW_UPSTREAMS["learning"]],
            [f"LEARNING:{row['id']}" for row in payloads["learning"]["packets"]],
        )

    today = date.today()
    for cycle in payloads["decision"]:
        if cycle.get("status") != "completed":
            continue
        cycle_id = str(cycle.get("id"))
        action_started = cycle.get("action_started_at")
        outcome_at = cycle.get("actual_outcome_at")
        foundation_evidence = str(cycle.get("evidence_node_id") or "")
        outcome_evidence = str(cycle.get("outcome_evidence_node_id") or "")
        missing = [
            label
            for label, value in (
                ("evidência que fundamenta a decisão", cycle.get("evidence_node_id")),
                ("ação executada", cycle.get("action")),
                ("responsável", cycle.get("owner")),
                ("prazo", cycle.get("due_date")),
                ("resultado esperado", cycle.get("expected_outcome")),
                ("início real da ação", action_started),
                ("resultado observado", cycle.get("actual_outcome")),
                ("data do resultado", outcome_at),
                ("evidência do resultado", outcome_evidence),
                ("aprendizagem", cycle.get("learning")),
            )
            if not str(value or "").strip()
        ]
        if missing:
            add(
                f"completed_cycle_missing_governance:{cycle_id}",
                "critical",
                "Ciclo concluído sem execução observável completa",
                "Falta " + ", ".join(missing) + ". Preenchimento textual não prova execução.",
                ["decision", "action", "outcome"],
                [f"CYCLE:{cycle_id}"],
            )
        if action_started and outcome_at and str(outcome_at) < str(action_started):
            add(
                f"outcome_before_action:{cycle_id}",
                "critical",
                "Resultado anterior à ação",
                "A cronologia registada não permite atribuir este resultado à ação.",
                ["action", "outcome"],
                [f"CYCLE:{cycle_id}"],
            )
        if outcome_at and str(outcome_at) > today.isoformat():
            add(
                f"future_outcome:{cycle_id}",
                "critical",
                "Resultado observado no futuro",
                "Uma previsão não pode ser registada como resultado realizado.",
                ["outcome"],
                [f"CYCLE:{cycle_id}"],
            )
        if outcome_evidence and outcome_evidence not in active_evidence_ids:
            add(
                f"outcome_evidence_unavailable:{cycle_id}",
                "critical",
                "Evidência do resultado indisponível",
                "O resultado concluído não aponta para uma evidência ativa da própria missão.",
                ["evidence", "outcome"],
                [f"CYCLE:{cycle_id}", f"GRAPH:{outcome_evidence}"],
            )
        elif outcome_evidence and outcome_evidence not in reviewed_evidence_ids:
            add(
                f"outcome_evidence_unreviewed:{cycle_id}",
                "critical",
                "Evidência do resultado ainda não revista",
                "Um resultado não pode ser consolidado como facto sem revisão humana explícita da evidência que o comprova.",
                ["evidence", "outcome"],
                [f"CYCLE:{cycle_id}", f"GRAPH:{outcome_evidence}"],
            )
        if outcome_evidence and outcome_evidence == str(cycle.get("evidence_node_id") or ""):
            add(
                f"outcome_reuses_decision_evidence:{cycle_id}",
                "critical",
                "Resultado apoiado pela evidência anterior à ação",
                "O fundamento da decisão não pode, por si só, comprovar o resultado posterior da execução.",
                ["evidence", "decision", "outcome"],
                [f"CYCLE:{cycle_id}", f"GRAPH:{outcome_evidence}"],
            )
        action_node_id = str(cycle.get("action_node_id") or "")
        materialized_action = active_node_by_id.get(action_node_id)
        if not materialized_action or materialized_action.get("node_type") != "action":
            add(
                f"action_not_materialized:{cycle_id}",
                "critical",
                "Ação ausente do grafo governado",
                "A decisão tem texto de ação, mas ainda não existe um objeto Ação entre decisão e resultado.",
                ["decision", "action", "outcome"],
                [f"CYCLE:{cycle_id}"],
            )

    protocol = payloads["validation"]["protocol"] or {}
    gap_nodes = [
        row
        for row in payloads["evidence"]["nodes"]
        if row.get("node_type") == "gap" and row.get("status") not in {"rejected", "superseded"}
    ]
    limitations_present = any(
        str(protocol.get(key) or "").strip()
        for key in ("limitations", "external_factors", "implementation_deviation")
    )
    if limitations_present and not gap_nodes:
        add(
            "validation_limits_not_materialized",
            "warning",
            "Limitações sem objeto governado",
            "As limitações da validação existem em texto, mas não foram convertidas em lacunas acompanháveis.",
            ["validation", "evidence"],
        )

    result_measurement = next(
        (row for row in payloads["validation"]["measurements"] if row.get("phase") == "result"),
        None,
    )
    if case and protocol and result_measurement:
        bc_unit = str(case.get("outcome_unit") or "").strip().casefold()
        indicator_unit = str(protocol.get("indicator_unit") or "").strip().casefold()
        bc_actual = case.get("actual_outcome_quantity")
        measured = result_measurement.get("normalized_value")
        if bc_unit and bc_unit == indicator_unit and bc_actual is not None and measured is not None:
            if abs(float(bc_actual) - float(measured)) > 1e-9:
                add(
                    "structured_result_value_conflict",
                    "critical",
                    "Resultado quantitativo divergente",
                    "O business case e a medição usam a mesma unidade, mas registam valores realizados diferentes.",
                    ["economics", "validation", "outcome"],
                    [f"BC:{case.get('id')}", f"MEASURE:{result_measurement.get('id')}"] ,
                )

    return issues


def _dependencies(
    *,
    applicability: dict[str, str],
    hashes: dict[str, str | None],
    review_statuses: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    edges = (
        ("mission", "documents"),
        ("documents", "evidence"),
        ("evidence", "comparison"),
        ("evidence", "economics"),
        ("evidence", "validation"),
        ("comparison", "decision"),
        ("economics", "decision"),
        ("validation", "decision"),
        ("decision", "action"),
        ("action", "outcome"),
        ("validation", "outcome"),
        ("economics", "outcome"),
        ("outcome", "learning"),
        ("evidence", "learning"),
        ("learning", "memory"),
    )
    dependencies: list[dict[str, Any]] = []
    for source, target in edges:
        source_app = applicability.get(source, "required")
        target_app = applicability.get(target, "required")
        required = source_app == "required" and target_app != "not_applicable"
        source_present = bool(hashes.get(source))
        review = review_statuses.get(source, {})
        stale = review.get("status") == "stale"
        status = (
            "not_applicable"
            if source_app == "not_applicable" or target_app == "not_applicable"
            else "stale"
            if stale
            else "ready"
            if source_present
            else "blocked"
            if required
            else "optional_missing"
        )
        dependencies.append(
            {
                "id": f"DEP:{source}->{target}",
                "from": source,
                "to": target,
                "required": required,
                "status": status,
            }
        )
    return dependencies


def build_mission_state(
    db: Session,
    *,
    organization_id: str,
    mission_id: str,
    mission_code: str,
) -> dict[str, Any]:
    mission = (
        db.query(CanonicalMission)
        .filter(
            CanonicalMission.organization_id == organization_id,
            CanonicalMission.id == mission_id,
            CanonicalMission.code == mission_code,
        )
        .one_or_none()
    )
    if mission is None:
        raise HTTPException(status_code=404, detail="A missão indicada não existe neste workspace.")
    _ensure_schema(db)
    payloads = _module_payloads(db, mission)
    hashes = _module_hashes(payloads)
    policy = _policy(db, mission)
    hashes["governance_policy"] = str(policy.get("content_hash") or "") or _hash(
        _default_policy(mission)
    )
    applicability = _applicability_map(policy)
    reviews = _latest_reviews(db, mission, hashes)
    review_statuses, _dependency_hashes = _review_bundle(
        module_hashes=hashes,
        reviews=reviews,
        applicability=applicability,
    )
    counts = _module_counts(payloads)
    conflicts = _structured_conflicts(
        mission=mission,
        policy=policy,
        payloads=payloads,
        hashes=hashes,
        review_statuses=review_statuses,
    )
    dependencies = _dependencies(
        applicability=applicability,
        hashes=hashes,
        review_statuses=review_statuses,
    )
    modules = []
    for key, label in MODULE_LABELS.items():
        app = applicability[key]
        present = bool(hashes.get(key))
        review = review_statuses[key]
        status = (
            "not_applicable"
            if app == "not_applicable"
            else "stale"
            if review.get("status") == "stale"
            else "present"
            if present
            else "missing"
            if app == "required"
            else "optional"
        )
        modules.append(
            {
                "key": key,
                "label": label,
                "applicability": app,
                "status": status,
                "count": counts[key],
                "content_hash": hashes.get(key),
                "review": review,
            }
        )

    canonical_hashes = {
        key: value
        for key, value in hashes.items()
        if key in MODULE_LABELS and key != "intelligence"
    }
    state_hash = _hash(
        {
            "schema": STATE_SCHEMA,
            "mission_id": mission.id,
            "policy_hash": policy.get("content_hash") or _hash(_default_policy(mission)),
            "module_hashes": canonical_hashes,
            "canonical_mission_content_hash": mission.content_hash,
            "lifecycle_state": mission.lifecycle_state,
        }
    )
    critical = sum(1 for item in conflicts if item["severity"] == "critical")
    warnings = sum(1 for item in conflicts if item["severity"] == "warning")
    missing_required = [
        item["key"]
        for item in modules
        if item["applicability"] == "required" and item["status"] == "missing"
    ]
    stale_modules = [item["key"] for item in modules if item["status"] == "stale"]
    health_status = (
        "requires_resolution"
        if critical
        else "requires_review"
        if warnings or stale_modules
        else "in_progress"
        if missing_required
        else "governed"
    )
    return {
        "schema": STATE_SCHEMA,
        "generated_at": _utcnow().isoformat(),
        "state_hash": state_hash,
        "mission": {
            "id": mission.id,
            "code": mission.code,
            "title": mission.title,
            "lifecycle_state": mission.lifecycle_state,
            "revision": mission.revision,
            "content_hash": mission.content_hash,
            "governance_content_hash": hashes.get("mission"),
            "validation_profile": _validation_profile(mission),
        },
        "policy": policy,
        "health": {
            "status": health_status,
            "critical_conflicts": critical,
            "warnings": warnings,
            "missing_required_modules": missing_required,
            "stale_modules": stale_modules,
            "human_resolution_required": bool(critical or warnings or stale_modules),
        },
        "modules": modules,
        "dependencies": dependencies,
        "conflicts": conflicts,
        "ai_governance": {
            "role": "assistive_only",
            "canonical_mutation": "prohibited_without_explicit_human_promotion",
            "human_review_required": True,
            "source_rule": (
                "A IA cita objetos governados e fontes recuperadas; integridade da fonte "
                "não é tratada automaticamente como veracidade factual."
            ),
            "allowed_support": [
                "extração",
                "classificação",
                "pesquisa com fontes",
                "ligações semânticas",
                "deteção de contradições e lacunas",
                "comparação",
                "síntese para revisão humana",
            ],
            "prohibited": [
                "decidir",
                "aprovar",
                "ocultar incerteza",
                "converter inferência em evidência",
                "reescrever histórico",
            ],
        },
    }


def _trim(value: Any, limit: int = 1600) -> str:
    raw = _canonical_json(value) if isinstance(value, (dict, list)) else str(value or "")
    text_value = " ".join(raw.split())
    return text_value if len(text_value) <= limit else text_value[: limit - 1].rstrip() + "…"


def governed_ai_context(
    db: Session,
    *,
    organization_id: str,
    mission_id: str,
    mission_code: str,
) -> dict[str, Any]:
    """Return the bounded, cited mission state consumed by Mission Intelligence."""

    state = build_mission_state(
        db,
        organization_id=organization_id,
        mission_id=mission_id,
        mission_code=mission_code,
    )
    mission = (
        db.query(CanonicalMission)
        .filter(CanonicalMission.id == mission_id, CanonicalMission.organization_id == organization_id)
        .one()
    )
    payloads = _module_payloads(db, mission)
    objects: list[dict[str, Any]] = []
    citation_ids: set[str] = set()

    def add(citation_id: str, module: str, kind: str, title: str, content: Any, **extra: Any) -> None:
        citation_ids.add(citation_id)
        objects.append(
            {
                "citation_id": citation_id,
                "module": module,
                "kind": kind,
                "title": _trim(title, 500),
                "content": _trim(content),
                **extra,
            }
        )

    add(
        f"MISSION:{mission.id}",
        "mission",
        "mission_snapshot",
        mission.title,
        _trim(mission.document_json, 5000),
        revision=mission.revision,
        content_hash=mission.content_hash,
        epistemic_status="canonical",
    )
    add(
        f"POLICY:{state['policy'].get('id') or mission.id}",
        "mission",
        "governance_policy",
        "Aplicabilidade e exceções da missão",
        {
            key: state["policy"].get(key)
            for key in (
                "alternatives_applicability",
                "economics_applicability",
                "measurement_applicability",
                "rationale",
                "current",
                "stale_reason",
            )
        },
        revision=state["policy"].get("revision"),
        content_hash=state["policy"].get("content_hash"),
        epistemic_status="human_reviewed" if state["policy"].get("source") == "human_reviewed_override" else "platform_default",
    )
    for row in payloads["documents"][:200]:
        add(
            f"DOC:{row['id']}",
            "documents",
            "source",
            row.get("original_filename") or "Documento",
            "Fonte preservada na missão.",
            sha256=row.get("sha256"),
            extraction_status=row.get("extraction_status"),
            source_integrity_verified=bool(row.get("sha256")),
            factual_validation="not_assessed",
        )
    for row in payloads["evidence"]["nodes"][:500]:
        if row.get("status") in {"rejected", "superseded"}:
            continue
        provenance = _loads(row.get("provenance_json"), {})
        node_type = str(row.get("node_type") or "record")
        graph_module = {
            "alternative": "comparison",
            "decision": "decision",
            "action": "action",
            "outcome": "outcome",
            "learning": "learning",
        }.get(node_type, "evidence")
        add(
            f"GRAPH:{row['id']}",
            graph_module,
            node_type,
            row.get("label") or "Objeto da missão",
            row.get("body") or "",
            status=row.get("status"),
            confidence=row.get("confidence"),
            source_kind=row.get("source_kind"),
            source_id=row.get("source_id"),
            attachment_id=row.get("attachment_id"),
            char_start=row.get("char_start"),
            char_end=row.get("char_end"),
            source_sha256=row.get("source_sha256"),
            source_integrity_verified=bool(
                provenance.get("source_integrity_verified")
            ),
            factual_validation=str(
                provenance.get("factual_validation") or "not_assessed"
            ),
            provenance=provenance,
        )
    matrix = payloads["comparison"]
    if matrix:
        add(
            f"MATRIX:{matrix['id']}",
            "comparison",
            "comparison_snapshot",
            f"Matriz de alternativas · revisão {matrix.get('revision')}",
            matrix.get("snapshot_json") or "",
            status=matrix.get("status"),
            content_hash=matrix.get("content_hash"),
        )
    case = payloads["economics"]["case"]
    if case:
        add(
            f"BC:{case['id']}",
            "economics",
            "business_case",
            "Business case vivo",
            {
                key: case.get(key)
                for key in (
                    "case_kind",
                    "decision_context",
                    "baseline",
                    "counterfactual",
                    "outcome_name",
                    "outcome_unit",
                    "planned_outcome_quantity",
                    "actual_outcome_quantity",
                    "notes",
                )
            },
            revision=case.get("revision"),
            status=case.get("status"),
            content_hash=case.get("content_hash"),
        )
        for row in payloads["economics"]["items"][:300]:
            if row.get("retired_at"):
                continue
            add(
                f"BCITEM:{row['id']}",
                "economics",
                str(row.get("kind") or "economic_line"),
                row.get("label") or "Linha económica",
                {
                    key: row.get(key)
                    for key in (
                        "description",
                        "phase",
                        "unit",
                        "planned_quantity",
                        "actual_quantity",
                        "base_amount",
                        "committed_amount",
                        "realized_amount",
                        "forecast_amount",
                        "source_label",
                        "assumption",
                        "confidence",
                    )
                },
                evidence_node_id=row.get("evidence_node_id"),
                alternative_node_id=row.get("alternative_node_id"),
            )
    protocol = payloads["validation"]["protocol"]
    if protocol:
        add(
            f"PROTOCOL:{protocol['id']}",
            "validation",
            "validation_protocol",
            protocol.get("subject") or "Protocolo de validação",
            {
                key: protocol.get(key)
                for key in (
                    "problem_statement",
                    "indicator_name",
                    "indicator_unit",
                    "target_value",
                    "target_description",
                    "guardrails",
                    "attribution_method",
                    "attribution_confidence",
                    "review_rationale",
                    "limitations",
                    "external_factors",
                    "implementation_deviation",
                )
            },
            revision=protocol.get("revision"),
            content_hash=protocol.get("content_hash"),
        )
    for row in payloads["validation"]["measurements"]:
        add(
            f"MEASURE:{row['id']}",
            "validation",
            "measurement",
            f"Medição · {row.get('phase')}",
            {
                key: row.get(key)
                for key in (
                    "period_start",
                    "period_end",
                    "numerator_value",
                    "denominator_value",
                    "normalized_value",
                    "data_quality",
                    "notes",
                )
            },
            evidence_node_id=row.get("evidence_node_id"),
        )
    for row in payloads["decision"][:200]:
        add(
            f"CYCLE:{row['id']}",
            "decision",
            "decision_cycle",
            row.get("decision") or "Decisão",
            {
                key: row.get(key)
                for key in (
                    "action",
                    "owner",
                    "due_date",
                    "status",
                    "expected_outcome",
                    "actual_outcome",
                    "learning",
                    "action_started_at",
                    "actual_outcome_at",
                )
            },
            evidence_node_id=row.get("evidence_node_id"),
            outcome_evidence_node_id=row.get("outcome_evidence_node_id"),
        )
    for row in payloads["learning"]["packets"][:100]:
        add(
            f"LEARNING:{row['id']}",
            "learning",
            "published_learning",
            row.get("title") or "Aprendizagem",
            row.get("statement") or "",
            status="valid",
            lineage_sha256=row.get("lineage_sha256"),
        )
    for row in payloads["memory"][:200]:
        add(
            f"MEMORY:{row['id']}",
            "memory",
            str(row.get("item_type") or "memory_item"),
            row.get("title") or "Memória organizacional",
            row.get("summary") or "",
            status=row.get("state"),
            confidence=row.get("confidence"),
            canonical_record_id=row.get("canonical_record_id"),
            revision=row.get("source_revision"),
            content_hash=row.get("source_content_hash"),
            epistemic_status="organizational_memory_for_contextual_review",
        )

    return {
        "schema": AI_CONTEXT_SCHEMA,
        "state_hash": state["state_hash"],
        "mission": state["mission"],
        "policy": state["policy"],
        "health": state["health"],
        "modules": state["modules"],
        "dependencies": state["dependencies"],
        "conflicts": state["conflicts"],
        "objects": objects,
        "citation_ids": sorted(citation_ids),
        "boundary": state["ai_governance"],
    }


class MissionGovernanceUpdate(BaseModel):
    expected_revision: int = Field(ge=0)
    alternatives_applicability: Literal["required", "optional", "not_applicable"] = "required"
    economics_applicability: Literal["required", "optional", "not_applicable"] = "required"
    measurement_applicability: Literal["required", "optional", "not_applicable"] = "optional"
    rationale: str = Field(min_length=10, max_length=5000)

    @model_validator(mode="after")
    def require_explicit_exception_rationale(self) -> "MissionGovernanceUpdate":
        if len(self.rationale.strip()) < 10:
            raise ValueError("A revisão de aplicabilidade exige uma justificação concreta.")
        if "not_applicable" in {
            self.alternatives_applicability,
            self.economics_applicability,
            self.measurement_applicability,
        } and len(self.rationale.strip()) < 30:
            raise ValueError("Uma exceção 'não aplicável' exige uma justificação concreta.")
        return self


@router.get("/missions/{mission_code}")
def get_governed_mission_state(
    mission_code: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    membership = _membership(db, user.id)
    mission = _mission(db, membership.organization_id, mission_code)
    result = build_mission_state(
        db,
        organization_id=membership.organization_id,
        mission_id=mission.id,
        mission_code=mission.code,
    )
    db.commit()
    return result


@router.get("/missions/{mission_code}/ai-context")
def get_governed_ai_context(
    mission_code: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    membership = _membership(db, user.id)
    mission = _mission(db, membership.organization_id, mission_code)
    result = governed_ai_context(
        db,
        organization_id=membership.organization_id,
        mission_id=mission.id,
        mission_code=mission.code,
    )
    db.commit()
    return result


@router.put("/missions/{mission_code}/policy")
def update_governance_policy(
    mission_code: str,
    payload: MissionGovernanceUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    membership = _membership(db, user.id)
    if membership.role not in REVIEWER_ROLES:
        raise HTTPException(
            status_code=403,
            detail="A aplicabilidade da missão exige a função de revisor ou administrador.",
        )
    mission = _mission(db, membership.organization_id, mission_code)
    _require_mission_mutable(mission)
    _ensure_schema(db)
    values = payload.model_dump(exclude={"expected_revision"})
    snapshot = {
        **values,
        "mission_id": mission.id,
        "mission_governance_hash": mission_governance_hash(mission),
    }
    digest = _hash(snapshot)
    current = db.execute(
        text(
            """
            SELECT id, revision FROM pilot_mission_governance_policies
            WHERE organization_id=:org AND mission_id=:mission
            """
        ),
        {"org": membership.organization_id, "mission": mission.id},
    ).mappings().first()
    current_revision = int(current["revision"] or 0) if current is not None else 0
    if payload.expected_revision != current_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "mission_governance_revision_conflict",
                "message": (
                    "A aplicabilidade foi revista noutra sessão. Recarregue o estado "
                    "antes de voltar a guardar."
                ),
                "expected_revision": payload.expected_revision,
                "current_revision": current_revision,
            },
        )
    if current is None:
        policy_id = str(uuid4())
        revision = 1
        db.execute(
            text(
                """
                INSERT INTO pilot_mission_governance_policies
                    (id, organization_id, mission_id, mission_code,
                     alternatives_applicability, economics_applicability,
                     measurement_applicability, rationale, mission_revision,
                     mission_content_hash, mission_governance_hash, revision, content_hash,
                     reviewed_by_user_id, reviewed_at)
                VALUES
                    (:id, :org, :mission, :code, :alternatives, :economics,
                     :measurement, :rationale, :mission_revision,
                     :mission_content_hash, :mission_hash, :revision, :hash, :user, :reviewed_at)
                """
            ),
            {
                "id": policy_id,
                "org": membership.organization_id,
                "mission": mission.id,
                "code": mission.code,
                "alternatives": payload.alternatives_applicability,
                "economics": payload.economics_applicability,
                "measurement": payload.measurement_applicability,
                "rationale": payload.rationale.strip(),
                "mission_revision": mission.revision,
                "mission_content_hash": mission.content_hash,
                "mission_hash": mission_governance_hash(mission),
                "revision": revision,
                "hash": digest,
                "user": user.id,
                "reviewed_at": _utcnow(),
            },
        )
    else:
        policy_id = str(current["id"])
        revision = int(current["revision"] or 0) + 1
        db.execute(
            text(
                """
                UPDATE pilot_mission_governance_policies SET
                    alternatives_applicability=:alternatives,
                    economics_applicability=:economics,
                    measurement_applicability=:measurement,
                    rationale=:rationale,
                    mission_revision=:mission_revision,
                    mission_content_hash=:mission_content_hash,
                    mission_governance_hash=:mission_hash,
                    revision=:revision,
                    content_hash=:hash,
                    reviewed_by_user_id=:user,
                    reviewed_at=:reviewed_at,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=:id AND organization_id=:org
                """
            ),
            {
                "id": policy_id,
                "org": membership.organization_id,
                "alternatives": payload.alternatives_applicability,
                "economics": payload.economics_applicability,
                "measurement": payload.measurement_applicability,
                "rationale": payload.rationale.strip(),
                "mission_revision": mission.revision,
                "mission_content_hash": mission.content_hash,
                "mission_hash": mission_governance_hash(mission),
                "revision": revision,
                "hash": digest,
                "user": user.id,
                "reviewed_at": _utcnow(),
            },
        )
    record_audit(
        db,
        action="pilot.mission_state.policy_reviewed",
        resource_type="mission_governance_policy",
        resource_id=policy_id,
        organization_id=membership.organization_id,
        user_id=user.id,
        payload={
            "mission_code": mission.code,
            "revision": revision,
            "content_hash": digest,
            **values,
        },
    )
    db.commit()
    return build_mission_state(
        db,
        organization_id=membership.organization_id,
        mission_id=mission.id,
        mission_code=mission.code,
    )
