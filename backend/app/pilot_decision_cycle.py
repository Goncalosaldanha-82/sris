from __future__ import annotations

import json
from datetime import date, datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.atlas_platform.auth import current_user
from app.atlas_platform.audit import record_audit
from app.atlas_platform.database import get_db
from app.atlas_platform.models import Membership, Role, User
from app.mission_intelligence.models import CanonicalMission
from app.evidence_graph import _ensure_schema as _ensure_graph_schema, _mission as _graph_mission, _upsert_edge, _upsert_node
from app.pilot_serialization import as_iso
from app.pilot_text import normalize_generated_title

router = APIRouter(prefix="/api/pilot/decision-cycles", tags=["pilot-decision-cycle"])

WRITER_ROLES = {
    Role.OWNER.value,
    Role.ADMIN.value,
    Role.REVIEWER.value,
    Role.CONTRIBUTOR.value,
}

CYCLE_WITH_FOUNDATION_SELECT = """
    SELECT cycle.*,
           COALESCE(
             NULLIF(TRIM(attachment.original_filename), ''),
             NULLIF(TRIM(foundation.label), '')
           ) AS evidence_label,
           foundation.label AS evidence_node_label,
           attachment.original_filename AS evidence_document_title,
           foundation.source_kind AS evidence_source_kind,
           foundation.source_sha256 AS evidence_source_sha256,
           COALESCE(
             NULLIF(TRIM(outcome_attachment.original_filename), ''),
             NULLIF(TRIM(outcome_foundation.label), '')
           ) AS outcome_evidence_label,
           outcome_foundation.label AS outcome_evidence_node_label,
           outcome_attachment.original_filename AS outcome_evidence_document_title,
           outcome_foundation.source_kind AS outcome_evidence_source_kind,
           outcome_foundation.source_sha256 AS outcome_evidence_source_sha256
    FROM pilot_decision_cycles cycle
    LEFT JOIN pilot_evidence_graph_nodes foundation
      ON foundation.id=cycle.evidence_node_id
     AND foundation.organization_id=cycle.organization_id
     AND foundation.mission_code=cycle.mission_code
    LEFT JOIN mi_mission_attachments attachment
      ON attachment.id=foundation.attachment_id
     AND attachment.organization_id=cycle.organization_id
     AND attachment.mission_code=cycle.mission_code
    LEFT JOIN pilot_evidence_graph_nodes outcome_foundation
      ON outcome_foundation.id=cycle.outcome_evidence_node_id
     AND outcome_foundation.organization_id=cycle.organization_id
     AND outcome_foundation.mission_code=cycle.mission_code
    LEFT JOIN mi_mission_attachments outcome_attachment
      ON outcome_attachment.id=outcome_foundation.attachment_id
     AND outcome_attachment.organization_id=cycle.organization_id
     AND outcome_attachment.mission_code=cycle.mission_code
"""


class DecisionCycleCreate(BaseModel):
    mission_code: str = Field(min_length=1, max_length=80)
    decision: str = Field(min_length=2, max_length=5000)
    action: str | None = Field(default=None, max_length=5000)
    owner: str | None = Field(default=None, max_length=200)
    due_date: date | None = None
    expected_outcome: str | None = Field(default=None, max_length=5000)
    evidence_node_id: str = Field(min_length=8, max_length=64)
    action_started_at: date | None = None


class DecisionCycleUpdate(BaseModel):
    action: str | None = Field(default=None, max_length=5000)
    owner: str | None = Field(default=None, max_length=200)
    due_date: date | None = None
    status: str | None = Field(default=None, pattern="^(proposed|committed|in_progress|completed|abandoned)$")
    expected_outcome: str | None = Field(default=None, max_length=5000)
    actual_outcome: str | None = Field(default=None, max_length=8000)
    learning: str | None = Field(default=None, max_length=8000)
    action_started_at: date | None = None
    actual_outcome_at: date | None = None
    outcome_evidence_node_id: str | None = Field(default=None, min_length=8, max_length=64)


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


def _require_writer(membership: Membership) -> None:
    if membership.role not in WRITER_ROLES:
        raise HTTPException(status_code=403, detail="A sua função permite consultar, mas não alterar decisões.")


def _validate_operational_state(values: dict) -> None:
    state = values.get("status") or "proposed"
    if state in {"committed", "in_progress", "completed"}:
        if not str(values.get("evidence_node_id") or "").strip():
            raise HTTPException(status_code=409, detail="Associe evidência que fundamente a decisão.")
        if not str(values.get("action") or "").strip():
            raise HTTPException(status_code=409, detail="Defina a ação antes de avançar a decisão.")
        if not str(values.get("expected_outcome") or "").strip():
            raise HTTPException(status_code=409, detail="Defina o resultado esperado antes de avançar a decisão.")
    if state in {"in_progress", "completed"}:
        if not str(values.get("owner") or "").strip():
            raise HTTPException(status_code=409, detail="Identifique o responsável antes de iniciar a execução.")
        if values.get("due_date") is None:
            raise HTTPException(status_code=409, detail="Defina o prazo antes de iniciar a execução.")
        if values.get("action_started_at") is None:
            raise HTTPException(status_code=409, detail="Registe a data real de início da ação antes de iniciar a execução.")
    if state == "completed":
        if not str(values.get("actual_outcome") or "").strip():
            raise HTTPException(status_code=409, detail="Registe o resultado observado antes de concluir a decisão.")
        if not str(values.get("learning") or "").strip():
            raise HTTPException(status_code=409, detail="Registe a aprendizagem antes de concluir a decisão.")
        if values.get("actual_outcome_at") is None:
            raise HTTPException(status_code=409, detail="Registe a data em que o resultado foi observado.")
        if not str(values.get("outcome_evidence_node_id") or "").strip():
            raise HTTPException(status_code=409, detail="Associe evidência própria ao resultado observado.")
        if values.get("outcome_evidence_node_id") == values.get("evidence_node_id"):
            raise HTTPException(
                status_code=409,
                detail="A evidência do resultado tem de ser distinta da evidência que fundamentou a decisão.",
            )
        action_started = str(values.get("action_started_at"))
        outcome_at = str(values.get("actual_outcome_at"))
        if outcome_at < action_started:
            raise HTTPException(status_code=409, detail="O resultado observado não pode anteceder o início real da ação.")
        if outcome_at > date.today().isoformat():
            raise HTTPException(status_code=409, detail="Uma previsão futura não pode ser registada como resultado observado.")


def _ensure_schema(db: Session) -> None:
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS pilot_decision_cycles (
            id VARCHAR(64) PRIMARY KEY,
            organization_id VARCHAR(64) NOT NULL,
            mission_code VARCHAR(80) NOT NULL,
            decision TEXT NOT NULL,
            action TEXT NULL,
            owner VARCHAR(200) NULL,
            due_date DATE NULL,
            status VARCHAR(40) NOT NULL DEFAULT 'proposed',
            expected_outcome TEXT NULL,
            actual_outcome TEXT NULL,
            learning TEXT NULL,
            evidence_node_id VARCHAR(64) NULL,
            action_started_at DATE NULL,
            actual_outcome_at DATE NULL,
            outcome_evidence_node_id VARCHAR(64) NULL,
            mission_revision INTEGER NULL,
            mission_content_hash VARCHAR(64) NULL,
            mission_governance_hash VARCHAR(64) NULL,
            matrix_revision INTEGER NULL,
            matrix_content_hash VARCHAR(64) NULL,
            business_case_revision INTEGER NULL,
            business_case_content_hash VARCHAR(64) NULL,
            validation_revision INTEGER NULL,
            validation_content_hash VARCHAR(64) NULL,
            decision_node_id VARCHAR(64) NULL,
            action_node_id VARCHAR(64) NULL,
            outcome_node_id VARCHAR(64) NULL,
            learning_node_id VARCHAR(64) NULL,
            created_by_user_id VARCHAR(64) NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_pilot_decision_cycles_org_mission
        ON pilot_decision_cycles (organization_id, mission_code, created_at)
    """))
    columns = {item["name"] for item in inspect(db.get_bind()).get_columns("pilot_decision_cycles")}
    additions = {
        "action_started_at": "DATE NULL",
        "actual_outcome_at": "DATE NULL",
        "outcome_evidence_node_id": "VARCHAR(64) NULL",
        "mission_revision": "INTEGER NULL",
        "mission_content_hash": "VARCHAR(64) NULL",
        "mission_governance_hash": "VARCHAR(64) NULL",
        "matrix_revision": "INTEGER NULL",
        "matrix_content_hash": "VARCHAR(64) NULL",
        "business_case_revision": "INTEGER NULL",
        "business_case_content_hash": "VARCHAR(64) NULL",
        "validation_revision": "INTEGER NULL",
        "validation_content_hash": "VARCHAR(64) NULL",
        "decision_node_id": "VARCHAR(64) NULL",
        "action_node_id": "VARCHAR(64) NULL",
        "outcome_node_id": "VARCHAR(64) NULL",
        "learning_node_id": "VARCHAR(64) NULL",
    }
    for column, definition in additions.items():
        if column not in columns:
            db.execute(text(f"ALTER TABLE pilot_decision_cycles ADD COLUMN {column} {definition}"))


def _dependency_snapshot(db: Session, mission: CanonicalMission) -> dict:
    """Pin the reviewed module revisions on which the decision is based."""

    from app.pilot_mission_state import mission_governance_hash

    snapshot = {
        "mission_revision": int(mission.revision),
        "mission_content_hash": mission.content_hash,
        "mission_governance_hash": mission_governance_hash(mission),
        "matrix_revision": None,
        "matrix_content_hash": None,
        "business_case_revision": None,
        "business_case_content_hash": None,
        "validation_revision": None,
        "validation_content_hash": None,
    }
    inspector = inspect(db.get_bind())
    params = {"org": mission.organization_id, "mission": mission.id}
    if inspector.has_table("pilot_alternative_matrices"):
        row = db.execute(
            text(
                """
                SELECT revision, content_hash FROM pilot_alternative_matrices
                WHERE organization_id=:org AND mission_id=:mission
                ORDER BY revision DESC LIMIT 1
                """
            ),
            params,
        ).mappings().first()
        if row:
            snapshot["matrix_revision"] = int(row["revision"])
            snapshot["matrix_content_hash"] = row["content_hash"]
    if inspector.has_table("pilot_business_cases"):
        row = db.execute(
            text(
                """
                SELECT revision, content_hash FROM pilot_business_cases
                WHERE organization_id=:org AND mission_id=:mission
                """
            ),
            params,
        ).mappings().first()
        if row:
            snapshot["business_case_revision"] = int(row["revision"])
            snapshot["business_case_content_hash"] = row["content_hash"]
    if inspector.has_table("pilot_validation_protocols"):
        row = db.execute(
            text(
                """
                SELECT revision, content_hash FROM pilot_validation_protocols
                WHERE organization_id=:org AND mission_id=:mission
                """
            ),
            params,
        ).mappings().first()
        if row:
            snapshot["validation_revision"] = int(row["revision"])
            snapshot["validation_content_hash"] = row["content_hash"]
    return snapshot


def _assert_governed_decision_foundation(db: Session, mission: CanonicalMission) -> None:
    """Do not commit a decision over missing or human-unreviewed inputs."""

    from app.pilot_mission_state import build_mission_state

    state = build_mission_state(
        db,
        organization_id=mission.organization_id,
        mission_id=mission.id,
        mission_code=mission.code,
    )
    modules = {item["key"]: item for item in state["modules"]}
    blockers: list[str] = []
    for key in ("mission", "documents", "evidence", "comparison", "economics", "validation"):
        item = modules[key]
        if item["applicability"] == "not_applicable":
            continue
        if item["applicability"] == "required" and not item.get("content_hash"):
            blockers.append(f"{item['label']} em falta")
        if (
            key in {"comparison", "economics", "validation"}
            and item.get("content_hash")
            and item.get("review", {}).get("status") != "current"
        ):
            blockers.append(f"{item['label']} sem revisão humana atual")
    upstream_modules = {"mission", "documents", "evidence", "comparison", "economics", "validation"}
    critical = [
        item["title"]
        for item in state["conflicts"]
        if item["severity"] == "critical"
        and upstream_modules.intersection(item.get("modules") or [])
    ]
    blockers.extend(critical)
    blockers = list(dict.fromkeys(blockers))
    if blockers:
        raise HTTPException(
            status_code=409,
            detail=(
                "A decisão não pode ser comprometida sobre um estado incompleto: "
                + "; ".join(blockers)
                + "."
            ),
        )


def _mark_outcome_evidence(
    db: Session,
    *,
    organization_id: str,
    mission_id: str,
    evidence_node_id: str,
    cycle_id: str,
    user_id: str,
) -> None:
    row = db.execute(
        text(
            """
            SELECT provenance_json FROM pilot_evidence_graph_nodes
            WHERE id=:node AND organization_id=:org AND mission_id=:mission
            """
        ),
        {"node": evidence_node_id, "org": organization_id, "mission": mission_id},
    ).mappings().one()
    try:
        provenance = json.loads(row["provenance_json"] or "{}")
    except (TypeError, ValueError):
        provenance = {}
    provenance.update(
        governance_role="outcome_evidence",
        outcome_for_cycle_id=cycle_id,
        human_selected=True,
        selected_by_user_id=user_id,
        selected_at=datetime.now(timezone.utc).isoformat(),
    )
    db.execute(
        text(
            """
            UPDATE pilot_evidence_graph_nodes
            SET provenance_json=:provenance, updated_at=CURRENT_TIMESTAMP
            WHERE id=:node AND organization_id=:org AND mission_id=:mission
            """
        ),
        {
            "node": evidence_node_id,
            "org": organization_id,
            "mission": mission_id,
            "provenance": json.dumps(provenance, ensure_ascii=False, sort_keys=True),
        },
    )


def _row(row) -> dict:
    return {
        "id": row["id"], "mission_code": row["mission_code"], "decision": row["decision"],
        "action": row["action"], "owner": row["owner"],
        "due_date": as_iso(row["due_date"]),
        "status": row["status"], "expected_outcome": row["expected_outcome"],
        "actual_outcome": row["actual_outcome"], "learning": row["learning"],
        "action_started_at": as_iso(row.get("action_started_at")),
        "actual_outcome_at": as_iso(row.get("actual_outcome_at")),
        "evidence_node_id": row["evidence_node_id"],
        "evidence_label": row.get("evidence_label"),
        "evidence_node_label": row.get("evidence_node_label"),
        "evidence_document_title": row.get("evidence_document_title"),
        "evidence_source_kind": row.get("evidence_source_kind"),
        "evidence_source_sha256": row.get("evidence_source_sha256"),
        "outcome_evidence_node_id": row.get("outcome_evidence_node_id"),
        "outcome_evidence_label": row.get("outcome_evidence_label"),
        "outcome_evidence_node_label": row.get("outcome_evidence_node_label"),
        "outcome_evidence_document_title": row.get("outcome_evidence_document_title"),
        "outcome_evidence_source_kind": row.get("outcome_evidence_source_kind"),
        "outcome_evidence_source_sha256": row.get("outcome_evidence_source_sha256"),
        "decision_snapshot": {
            "mission_revision": row.get("mission_revision"),
            "mission_content_hash": row.get("mission_content_hash"),
            "mission_governance_hash": row.get("mission_governance_hash"),
            "matrix_revision": row.get("matrix_revision"),
            "matrix_content_hash": row.get("matrix_content_hash"),
            "business_case_revision": row.get("business_case_revision"),
            "business_case_content_hash": row.get("business_case_content_hash"),
            "validation_revision": row.get("validation_revision"),
            "validation_content_hash": row.get("validation_content_hash"),
        },
        "graph_nodes": {
            "decision_node_id": row.get("decision_node_id"),
            "action_node_id": row.get("action_node_id"),
            "outcome_node_id": row.get("outcome_node_id"),
            "learning_node_id": row.get("learning_node_id"),
        },
        "created_at": as_iso(row["created_at"]),
        "updated_at": as_iso(row["updated_at"]),
    }


@router.get("/missions/{mission_code}")
def list_cycles(mission_code: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    membership = _membership(db, user.id); _ensure_schema(db); _ensure_graph_schema(db)
    rows = db.execute(text(CYCLE_WITH_FOUNDATION_SELECT + " WHERE cycle.organization_id=:org AND cycle.mission_code=:mission ORDER BY cycle.created_at DESC"), {"org": membership.organization_id, "mission": mission_code}).mappings().all()
    db.commit(); return [_row(r) for r in rows]


@router.post("", status_code=201)
def create_cycle(payload: DecisionCycleCreate, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    membership = _membership(db, user.id); _require_writer(membership); _ensure_schema(db); _ensure_graph_schema(db); cycle_id = str(uuid4())
    mission = db.query(CanonicalMission).filter(
        CanonicalMission.organization_id == membership.organization_id,
        CanonicalMission.code == payload.mission_code,
    ).one_or_none()
    if mission is None: raise HTTPException(status_code=404, detail="A missão indicada não existe neste workspace.")
    foundation = db.execute(text("""
        SELECT id FROM pilot_evidence_graph_nodes
        WHERE id=:node AND organization_id=:org AND mission_id=:mission
          AND node_type='evidence'
          AND status NOT IN ('rejected', 'superseded')
    """), {
        "node": payload.evidence_node_id,
        "org": membership.organization_id,
        "mission": mission.id,
    }).scalar_one_or_none()
    if foundation is None:
        raise HTTPException(status_code=422, detail="Escolha uma evidência da própria missão como fundamento.")
    dependency = _dependency_snapshot(db, mission)
    db.execute(text("""INSERT INTO pilot_decision_cycles
        (id, organization_id, mission_code, decision, action, owner, due_date,
         status, expected_outcome, evidence_node_id, action_started_at,
         mission_revision, mission_content_hash, mission_governance_hash, matrix_revision,
         matrix_content_hash, business_case_revision, business_case_content_hash,
         validation_revision, validation_content_hash, created_by_user_id)
        VALUES (:id,:org,:mission,:decision,:action,:owner,:due,'proposed',
                :expected,:node,:action_started_at,:mission_revision,
                :mission_content_hash,:mission_governance_hash,:matrix_revision,:matrix_content_hash,
                :business_case_revision,:business_case_content_hash,
                :validation_revision,:validation_content_hash,:user)"""), {
        "id": cycle_id, "org": membership.organization_id, "mission": payload.mission_code,
        "decision": payload.decision, "action": payload.action, "owner": payload.owner,
        "due": payload.due_date, "expected": payload.expected_outcome,
        "node": payload.evidence_node_id, "action_started_at": payload.action_started_at,
        "user": user.id, **dependency,
    })
    record_audit(
        db,
        action="pilot.decision_cycle.created",
        resource_type="decision_cycle",
        resource_id=cycle_id,
        organization_id=membership.organization_id,
        user_id=user.id,
        payload={
            "mission_code": mission.code,
            "status": "proposed",
            "evidence_node_id": payload.evidence_node_id,
            "mission_revision": dependency["mission_revision"],
        },
    )
    db.commit(); row = db.execute(text(CYCLE_WITH_FOUNDATION_SELECT + " WHERE cycle.id=:id"), {"id": cycle_id}).mappings().one(); return _row(row)


@router.patch("/{cycle_id}")
def update_cycle(cycle_id: str, payload: DecisionCycleUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    membership = _membership(db, user.id); _require_writer(membership); _ensure_schema(db); _ensure_graph_schema(db)
    current = db.execute(text(CYCLE_WITH_FOUNDATION_SELECT + " WHERE cycle.id=:id AND cycle.organization_id=:org"), {"id": cycle_id, "org": membership.organization_id}).mappings().first()
    if current is None: raise HTTPException(status_code=404, detail="Ciclo de decisão não encontrado.")
    values = payload.model_dump(exclude_unset=True)
    if not values: return _row(current)
    candidate = dict(current)
    candidate.update(values)
    target_status = str(candidate.get("status") or current["status"])
    allowed_transitions = {
        "proposed": {"proposed", "committed", "abandoned"},
        "committed": {"committed", "in_progress", "abandoned"},
        "in_progress": {"in_progress", "completed", "abandoned"},
        "completed": {"completed"},
        "abandoned": {"abandoned"},
    }
    if target_status not in allowed_transitions.get(str(current["status"]), set()):
        raise HTTPException(
            status_code=409,
            detail=(
                "Respeite a sequência governada: proposta → compromisso → execução → conclusão."
            ),
        )
    mission = db.query(CanonicalMission).filter(
        CanonicalMission.organization_id == membership.organization_id,
        CanonicalMission.code == current["mission_code"],
    ).one()
    outcome_evidence_id = str(candidate.get("outcome_evidence_node_id") or "").strip()
    if outcome_evidence_id:
        outcome_foundation = db.execute(text("""
            SELECT id FROM pilot_evidence_graph_nodes
            WHERE id=:node AND organization_id=:org AND mission_id=:mission
              AND node_type='evidence'
              AND status NOT IN ('rejected', 'superseded')
        """), {
            "node": outcome_evidence_id,
            "org": membership.organization_id,
            "mission": mission.id,
        }).scalar_one_or_none()
        if outcome_foundation is None:
            raise HTTPException(status_code=422, detail="Escolha uma evidência ativa da própria missão para comprovar o resultado.")
    _validate_operational_state(candidate)
    if target_status == "completed" and values.get("status") == "completed":
        _mark_outcome_evidence(
            db,
            organization_id=membership.organization_id,
            mission_id=mission.id,
            evidence_node_id=outcome_evidence_id,
            cycle_id=cycle_id,
            user_id=user.id,
        )
    allowed = {
        "action", "owner", "due_date", "status", "expected_outcome",
        "actual_outcome", "learning", "action_started_at",
        "actual_outcome_at", "outcome_evidence_node_id",
    }; parts=[]; params={"id": cycle_id, "org": membership.organization_id}
    for key,value in values.items():
        if key in allowed: parts.append(f"{key}=:{key}"); params[key]=value
    entering_governed_execution = (
        values.get("status") in {"committed", "in_progress", "completed"}
        and current["status"] == "proposed"
    )
    if entering_governed_execution:
        _assert_governed_decision_foundation(db, mission)
        dependency = _dependency_snapshot(db, mission)
        for key, value in dependency.items():
            parts.append(f"{key}=:{key}")
            params[key] = value
    parts.append("updated_at=CURRENT_TIMESTAMP")
    db.execute(text(f"UPDATE pilot_decision_cycles SET {', '.join(parts)} WHERE id=:id AND organization_id=:org"), params)
    if values.get("status") in {"committed", "in_progress", "completed"}:
        from app.pilot_mission_state import record_module_review

        record_module_review(
            db,
            organization_id=membership.organization_id,
            mission_id=mission.id,
            mission_code=mission.code,
            module_key="decision",
            module_revision=None,
            module_content_hash=None,
            rationale=(
                "Decisão comprometida por uma pessoa sobre as revisões governadas registadas."
                if values.get("status") == "committed"
                else "Execução iniciada por uma pessoa com responsável, prazo e data real explícitos."
                if values.get("status") == "in_progress"
                else "Ciclo concluído por uma pessoa com ação, cronologia, resultado e evidência explícitos."
            ),
            user_id=user.id,
        )
    record_audit(
        db,
        action="pilot.decision_cycle.updated",
        resource_type="decision_cycle",
        resource_id=cycle_id,
        organization_id=membership.organization_id,
        user_id=user.id,
        payload={
            "mission_code": mission.code,
            "previous_status": current["status"],
            "status": target_status,
            "changed_fields": sorted(values),
            "outcome_evidence_node_id": outcome_evidence_id or None,
        },
    )
    db.commit(); row = db.execute(text(CYCLE_WITH_FOUNDATION_SELECT + " WHERE cycle.id=:id"), {"id": cycle_id}).mappings().one(); return _row(row)


@router.post("/{cycle_id}/materialize-learning", status_code=201)
def materialize_learning(cycle_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Convert an observed completed decision cycle into reviewable graph lineage.

    Outcome is treated as observed human-entered evidence of consequence; the learning remains
    proposed until a human explicitly accepts/verifies it in the Evidence Graph. Only then can
    the existing learning-lineage publisher make it reusable across missions.
    """
    membership = _membership(db, user.id); _require_writer(membership); _ensure_schema(db); _ensure_graph_schema(db)
    cycle = db.execute(text("SELECT * FROM pilot_decision_cycles WHERE id=:id AND organization_id=:org"), {"id": cycle_id, "org": membership.organization_id}).mappings().first()
    if cycle is None: raise HTTPException(status_code=404, detail="Ciclo de decisão não encontrado.")
    if cycle["status"] != "completed": raise HTTPException(status_code=409, detail="Conclua a decisão antes de transformar o resultado em aprendizagem.")
    if not cycle["evidence_node_id"]: raise HTTPException(status_code=409, detail="Associe evidência que fundamente a decisão antes de consolidar aprendizagem.")
    if not cycle.get("outcome_evidence_node_id"): raise HTTPException(status_code=409, detail="Associe evidência que comprove o resultado antes de consolidar aprendizagem.")
    if cycle.get("outcome_evidence_node_id") == cycle.get("evidence_node_id"): raise HTTPException(status_code=409, detail="A evidência do resultado tem de ser distinta da evidência que fundamentou a decisão.")
    if not cycle.get("action_started_at") or not cycle.get("actual_outcome_at"): raise HTTPException(status_code=409, detail="Registe a cronologia real da ação e do resultado antes de consolidar aprendizagem.")
    if not (cycle["actual_outcome"] or "").strip(): raise HTTPException(status_code=409, detail="Registe o resultado observado antes de materializar a aprendizagem.")
    if not (cycle["learning"] or "").strip(): raise HTTPException(status_code=409, detail="Registe a aprendizagem antes de a enviar para revisão.")
    mission = _graph_mission(db, membership.organization_id, cycle["mission_code"])
    foundation_exists = db.execute(text("""
        SELECT id FROM pilot_evidence_graph_nodes
        WHERE id=:node AND organization_id=:org AND mission_id=:mission
          AND node_type='evidence'
          AND status NOT IN ('rejected', 'superseded')
    """), {
        "node": cycle["evidence_node_id"],
        "org": membership.organization_id,
        "mission": mission.id,
    }).scalar_one_or_none()
    if foundation_exists is None: raise HTTPException(status_code=409, detail="A evidência de fundamento já não está disponível nesta missão.")
    outcome_foundation_exists = db.execute(text("""
        SELECT id FROM pilot_evidence_graph_nodes
        WHERE id=:node AND organization_id=:org AND mission_id=:mission
          AND node_type='evidence'
          AND status NOT IN ('rejected', 'superseded')
    """), {
        "node": cycle["outcome_evidence_node_id"],
        "org": membership.organization_id,
        "mission": mission.id,
    }).scalar_one_or_none()
    if outcome_foundation_exists is None: raise HTTPException(status_code=409, detail="A evidência do resultado já não está disponível nesta missão.")
    provenance={
        "source":"decision_cycle",
        "cycle_id":cycle_id,
        "human_entered":True,
        "expected_outcome":cycle["expected_outcome"],
        "owner":cycle["owner"],
        "due_date":as_iso(cycle["due_date"]),
        "action_started_at":as_iso(cycle["action_started_at"]),
        "actual_outcome_at":as_iso(cycle["actual_outcome_at"]),
        "decision_snapshot":{
            "mission_revision":cycle.get("mission_revision"),
            "mission_content_hash":cycle.get("mission_content_hash"),
            "mission_governance_hash":cycle.get("mission_governance_hash"),
            "matrix_revision":cycle.get("matrix_revision"),
            "matrix_content_hash":cycle.get("matrix_content_hash"),
            "business_case_revision":cycle.get("business_case_revision"),
            "business_case_content_hash":cycle.get("business_case_content_hash"),
            "validation_revision":cycle.get("validation_revision"),
            "validation_content_hash":cycle.get("validation_content_hash"),
        },
    }
    foundation_id = cycle["evidence_node_id"]
    outcome_foundation_id = cycle["outcome_evidence_node_id"]
    decision_title = normalize_generated_title(cycle["decision"] or "Decisão")
    decision_id = _upsert_node(db, organization_id=membership.organization_id, mission=mission, node_type="decision", label=decision_title[:300], body=cycle["decision"] or "", status="accepted", confidence=None, source_kind="decision_cycle", source_id=f"decision:{cycle_id}", attachment_id=None, char_start=None, char_end=None, source_sha256=None, provenance={**provenance,"role":"committed_decision","foundation_node_id":foundation_id}, user_id=user.id)
    action_id = _upsert_node(db, organization_id=membership.organization_id, mission=mission, node_type="action", label=f"Ação · {decision_title[:260]}", body=cycle["action"] or "", status="accepted", confidence=None, source_kind="decision_cycle", source_id=f"action:{cycle_id}", attachment_id=None, char_start=None, char_end=None, source_sha256=None, provenance={**provenance,"role":"executed_action"}, user_id=user.id)
    outcome_id = _upsert_node(db, organization_id=membership.organization_id, mission=mission, node_type="outcome", label=f"Resultado observado · {decision_title[:240]}", body=cycle["actual_outcome"] or "", status="verified", confidence=None, source_kind="decision_cycle", source_id=f"outcome:{cycle_id}", attachment_id=None, char_start=None, char_end=None, source_sha256=None, provenance={**provenance,"role":"observed_outcome","outcome_evidence_node_id":outcome_foundation_id}, user_id=user.id)
    learning_id = _upsert_node(db, organization_id=membership.organization_id, mission=mission, node_type="learning", label=f"Aprendizagem · {decision_title[:250]}", body=cycle["learning"] or "", status="proposed", confidence=None, source_kind="decision_cycle", source_id=f"learning:{cycle_id}", attachment_id=None, char_start=None, char_end=None, source_sha256=None, provenance={**provenance,"role":"learning_candidate","human_review_required":True}, user_id=user.id)
    _upsert_edge(db, organization_id=membership.organization_id, mission=mission, from_node_id=foundation_id, to_node_id=decision_id, edge_type="informs", provenance={"cycle_id":cycle_id,"explicit":True,"meaning":"human_selected_decision_foundation"}, user_id=user.id)
    _upsert_edge(db, organization_id=membership.organization_id, mission=mission, from_node_id=decision_id, to_node_id=action_id, edge_type="leads_to", provenance={"cycle_id":cycle_id,"explicit":True,"meaning":"decision_authorizes_action"}, user_id=user.id)
    _upsert_edge(db, organization_id=membership.organization_id, mission=mission, from_node_id=action_id, to_node_id=outcome_id, edge_type="leads_to", provenance={"cycle_id":cycle_id,"explicit":True,"meaning":"action_precedes_observed_outcome"}, user_id=user.id)
    _upsert_edge(db, organization_id=membership.organization_id, mission=mission, from_node_id=outcome_foundation_id, to_node_id=outcome_id, edge_type="validates", provenance={"cycle_id":cycle_id,"explicit":True,"meaning":"human_selected_outcome_evidence"}, user_id=user.id)
    _upsert_edge(db, organization_id=membership.organization_id, mission=mission, from_node_id=outcome_id, to_node_id=learning_id, edge_type="informs", provenance={"cycle_id":cycle_id,"explicit":True,"meaning":"observed_outcome_supports_learning_candidate"}, user_id=user.id)
    db.execute(text("""
        UPDATE pilot_decision_cycles SET
            decision_node_id=:decision, action_node_id=:action,
            outcome_node_id=:outcome, learning_node_id=:learning,
            updated_at=CURRENT_TIMESTAMP
        WHERE id=:cycle AND organization_id=:org
    """), {
        "decision": decision_id,
        "action": action_id,
        "outcome": outcome_id,
        "learning": learning_id,
        "cycle": cycle_id,
        "org": membership.organization_id,
    })
    record_audit(
        db,
        action="pilot.decision_cycle.lineage_materialized",
        resource_type="decision_cycle",
        resource_id=cycle_id,
        organization_id=membership.organization_id,
        user_id=user.id,
        payload={
            "mission_code": mission.code,
            "decision_node_id": decision_id,
            "action_node_id": action_id,
            "outcome_node_id": outcome_id,
            "learning_node_id": learning_id,
            "outcome_evidence_node_id": outcome_foundation_id,
        },
    )
    db.commit()
    return {"cycle_id":cycle_id,"mission_code":mission.code,"decision_node_id":decision_id,"action_node_id":action_id,"outcome_node_id":outcome_id,"learning_node_id":learning_id,"learning_status":"proposed","publish_ready":False,"next_step":"Rever e aceitar/verificar a aprendizagem no Evidence Graph antes de a publicar na memória organizacional."}
