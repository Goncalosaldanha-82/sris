from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.atlas_platform.audit import record_audit
from app.atlas_platform.auth import current_user
from app.atlas_platform.database import get_db
from app.atlas_platform.models import Membership, Role, User
from app.evidence_graph import _ensure_schema as _ensure_graph_schema
from app.mission_intelligence.models import CanonicalMission
from app.pilot_serialization import as_iso

router = APIRouter(prefix="/api/pilot/validation", tags=["pilot-validation"])

PROFILE_NONE = "none"
PROFILE_MEASURABLE = "measurable_decision"
PROFILE_TOURISM = "tourism_advance_resource_efficiency"

PROFILE_DEFINITIONS = {
    PROFILE_NONE: {
        "label": "Sem protocolo quantitativo",
        "description": "A missão mantém o percurso decisional sem impor uma comparação numérica.",
        "denominator_required": False,
    },
    PROFILE_MEASURABLE: {
        "label": "Validação mensurável transversal",
        "description": "Compara uma linha de base e um resultado observável com fonte e revisão humana.",
        "denominator_required": False,
    },
    PROFILE_TOURISM: {
        "label": "Tourism Advance · Eficiência de recursos",
        "description": "Normaliza recursos pela atividade real de uma unidade de alojamento antes de avaliar a intervenção.",
        "denominator_required": True,
    },
}

WRITER_ROLES = {
    Role.OWNER.value,
    Role.ADMIN.value,
    Role.REVIEWER.value,
    Role.CONTRIBUTOR.value,
}
REVIEWER_ROLES = {Role.OWNER.value, Role.ADMIN.value, Role.REVIEWER.value}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProtocolUpsert(BaseModel):
    expected_revision: int | None = Field(default=None, ge=1)
    profile: Literal[
        "measurable_decision",
        "tourism_advance_resource_efficiency",
    ]
    subject: str = Field(default="", max_length=500)
    subject_type: str = Field(default="", max_length=200)
    problem_statement: str = Field(default="", max_length=5000)
    indicator_name: str = Field(default="", max_length=300)
    indicator_unit: str = Field(default="", max_length=80)
    desired_direction: Literal["decrease", "increase", "maintain", "target"] = "decrease"
    denominator_name: str = Field(default="", max_length=300)
    denominator_unit: str = Field(default="", max_length=80)
    target_value: Decimal | None = None
    target_description: str = Field(default="", max_length=3000)
    guardrails: str = Field(default="", max_length=5000)
    intervention_description: str = Field(default="", max_length=5000)
    intervention_start_date: date | None = None
    intervention_end_date: date | None = None
    review_date: date | None = None
    attribution_method: str = Field(default="", max_length=5000)

    @model_validator(mode="after")
    def dates_follow_the_operational_sequence(self) -> "ProtocolUpsert":
        if (
            self.intervention_start_date
            and self.intervention_end_date
            and self.intervention_end_date < self.intervention_start_date
        ):
            raise ValueError("A intervenção não pode terminar antes de começar.")
        if self.review_date and self.intervention_start_date and self.review_date < self.intervention_start_date:
            raise ValueError("A revisão do resultado não pode anteceder a intervenção.")
        return self


class MeasurementUpsert(BaseModel):
    expected_revision: int | None = Field(default=None, ge=1)
    period_start: date
    period_end: date
    numerator_value: Decimal
    denominator_value: Decimal | None = Field(default=None, gt=0)
    evidence_node_id: str = Field(min_length=8, max_length=64)
    data_quality: Literal["low", "moderate", "high"] = "moderate"
    notes: str = Field(default="", max_length=5000)

    @model_validator(mode="after")
    def period_is_valid(self) -> "MeasurementUpsert":
        if self.period_end < self.period_start:
            raise ValueError("O período de medição não pode terminar antes de começar.")
        return self


class ValidationReview(BaseModel):
    expected_revision: int | None = Field(default=None, ge=1)
    attribution_confidence: Literal["high", "moderate", "low", "not_evaluable"]
    review_rationale: str = Field(min_length=10, max_length=5000)
    limitations: str = Field(min_length=10, max_length=5000)
    external_factors: str = Field(default="", max_length=5000)
    implementation_deviation: str = Field(default="", max_length=5000)


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
        raise HTTPException(status_code=403, detail="A sua função permite consultar, mas não alterar a validação.")


def _require_reviewer(membership: Membership) -> None:
    if membership.role not in REVIEWER_ROLES:
        raise HTTPException(status_code=403, detail="A revisão de atribuição exige a função de revisor ou administrador.")


def _ensure_schema(db: Session) -> None:
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS pilot_validation_protocols (
                id VARCHAR(64) PRIMARY KEY,
                organization_id VARCHAR(64) NOT NULL,
                mission_id VARCHAR(64) NOT NULL,
                profile VARCHAR(80) NOT NULL,
                subject VARCHAR(500) NOT NULL DEFAULT '',
                subject_type VARCHAR(200) NOT NULL DEFAULT '',
                problem_statement TEXT NOT NULL DEFAULT '',
                indicator_name VARCHAR(300) NOT NULL DEFAULT '',
                indicator_unit VARCHAR(80) NOT NULL DEFAULT '',
                desired_direction VARCHAR(30) NOT NULL DEFAULT 'decrease',
                denominator_name VARCHAR(300) NOT NULL DEFAULT '',
                denominator_unit VARCHAR(80) NOT NULL DEFAULT '',
                target_value NUMERIC(24, 8) NULL,
                target_description TEXT NOT NULL DEFAULT '',
                guardrails TEXT NOT NULL DEFAULT '',
                intervention_description TEXT NOT NULL DEFAULT '',
                intervention_start_date DATE NULL,
                intervention_end_date DATE NULL,
                review_date DATE NULL,
                attribution_method TEXT NOT NULL DEFAULT '',
                attribution_confidence VARCHAR(30) NULL,
                review_rationale TEXT NOT NULL DEFAULT '',
                limitations TEXT NOT NULL DEFAULT '',
                external_factors TEXT NOT NULL DEFAULT '',
                implementation_deviation TEXT NOT NULL DEFAULT '',
                reviewed_by_user_id VARCHAR(64) NULL,
                reviewed_at TIMESTAMP NULL,
                revision INTEGER NOT NULL DEFAULT 1,
                content_hash VARCHAR(64) NOT NULL DEFAULT '',
                created_by_user_id VARCHAR(64) NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (organization_id, mission_id)
            )
            """
        )
    )
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS pilot_validation_measurements (
                id VARCHAR(64) PRIMARY KEY,
                protocol_id VARCHAR(64) NOT NULL,
                organization_id VARCHAR(64) NOT NULL,
                mission_id VARCHAR(64) NOT NULL,
                phase VARCHAR(20) NOT NULL,
                period_start DATE NOT NULL,
                period_end DATE NOT NULL,
                numerator_value NUMERIC(24, 8) NOT NULL,
                denominator_value NUMERIC(24, 8) NULL,
                normalized_value NUMERIC(24, 8) NOT NULL,
                evidence_node_id VARCHAR(64) NOT NULL,
                data_quality VARCHAR(30) NOT NULL DEFAULT 'moderate',
                notes TEXT NOT NULL DEFAULT '',
                created_by_user_id VARCHAR(64) NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (protocol_id, phase)
            )
            """
        )
    )
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS pilot_validation_events (
                id VARCHAR(64) PRIMARY KEY,
                protocol_id VARCHAR(64) NOT NULL,
                organization_id VARCHAR(64) NOT NULL,
                mission_id VARCHAR(64) NOT NULL,
                revision INTEGER NOT NULL,
                event_type VARCHAR(40) NOT NULL,
                snapshot_json TEXT NOT NULL,
                content_hash VARCHAR(64) NOT NULL,
                created_by_user_id VARCHAR(64) NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (protocol_id, revision)
            )
            """
        )
    )
    db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_pilot_validation_org_mission
            ON pilot_validation_protocols (organization_id, mission_id)
            """
        )
    )
    db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_pilot_validation_measurements_mission
            ON pilot_validation_measurements (organization_id, mission_id, phase)
            """
        )
    )
    db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_pilot_validation_events_protocol
            ON pilot_validation_events (protocol_id, revision)
            """
        )
    )


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


def _profile_from_mission(mission: CanonicalMission) -> str:
    try:
        document = json.loads(mission.document_json or "{}")
    except (TypeError, ValueError):
        return PROFILE_NONE
    profile = str((document.get("metadata") or {}).get("validation_profile") or PROFILE_NONE)
    return profile if profile in PROFILE_DEFINITIONS else PROFILE_NONE


def _protocol_row(db: Session, organization_id: str, mission_id: str):
    _ensure_schema(db)
    return db.execute(
        text(
            """
            SELECT * FROM pilot_validation_protocols
            WHERE organization_id=:org AND mission_id=:mission
            """
        ),
        {"org": organization_id, "mission": mission_id},
    ).mappings().first()


def _measurement_rows(db: Session, organization_id: str, mission_id: str) -> dict[str, dict]:
    rows = db.execute(
        text(
            """
            SELECT * FROM pilot_validation_measurements
            WHERE organization_id=:org AND mission_id=:mission
            ORDER BY phase ASC
            """
        ),
        {"org": organization_id, "mission": mission_id},
    ).mappings().all()
    return {str(row["phase"]): _measurement_view(row) for row in rows}


def _number(value) -> float | None:
    if value is None:
        return None
    return float(value)


def _protocol_view(row) -> dict | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "profile": row["profile"],
        "subject": row["subject"],
        "subject_type": row["subject_type"],
        "problem_statement": row["problem_statement"],
        "indicator_name": row["indicator_name"],
        "indicator_unit": row["indicator_unit"],
        "desired_direction": row["desired_direction"],
        "denominator_name": row["denominator_name"],
        "denominator_unit": row["denominator_unit"],
        "target_value": _number(row["target_value"]),
        "target_description": row["target_description"],
        "guardrails": row["guardrails"],
        "intervention_description": row["intervention_description"],
        "intervention_start_date": as_iso(row["intervention_start_date"]),
        "intervention_end_date": as_iso(row["intervention_end_date"]),
        "review_date": as_iso(row["review_date"]),
        "attribution_method": row["attribution_method"],
        "attribution_confidence": row["attribution_confidence"],
        "review_rationale": row["review_rationale"],
        "limitations": row["limitations"],
        "external_factors": row["external_factors"],
        "implementation_deviation": row["implementation_deviation"],
        "reviewed_by_user_id": row["reviewed_by_user_id"],
        "reviewed_at": as_iso(row["reviewed_at"]),
        "revision": int(row["revision"] or 1),
        "content_hash": row["content_hash"],
        "created_at": as_iso(row["created_at"]),
        "updated_at": as_iso(row["updated_at"]),
    }


def _measurement_view(row) -> dict:
    return {
        "id": row["id"],
        "phase": row["phase"],
        "period_start": as_iso(row["period_start"]),
        "period_end": as_iso(row["period_end"]),
        "numerator_value": _number(row["numerator_value"]),
        "denominator_value": _number(row["denominator_value"]),
        "normalized_value": _number(row["normalized_value"]),
        "evidence_node_id": row["evidence_node_id"],
        "data_quality": row["data_quality"],
        "notes": row["notes"],
        "created_at": as_iso(row["created_at"]),
        "updated_at": as_iso(row["updated_at"]),
    }


def _analysis(protocol: dict | None, baseline: dict | None, result: dict | None) -> dict:
    if not protocol:
        return {
            "comparable": False,
            "absolute_change": None,
            "percent_change": None,
            "target_status": "not_configured",
            "normalized_unit": "",
        }
    denominator_required = bool(
        PROFILE_DEFINITIONS.get(protocol["profile"], {}).get("denominator_required")
        or str(protocol.get("denominator_name") or "").strip()
    )
    normalized_unit = str(protocol.get("indicator_unit") or "")
    if denominator_required and protocol.get("denominator_unit"):
        normalized_unit = f"{normalized_unit}/{protocol['denominator_unit']}"
    comparable = bool(
        baseline
        and result
        and baseline.get("normalized_value") is not None
        and result.get("normalized_value") is not None
        and baseline.get("period_end")
        and result.get("period_start")
        and baseline["period_end"] <= result["period_start"]
        and (
            not denominator_required
            or (baseline.get("denominator_value") and result.get("denominator_value"))
        )
    )
    absolute_change = None
    percent_change = None
    target_status = "not_configured"
    if comparable:
        baseline_value = float(baseline["normalized_value"])
        result_value = float(result["normalized_value"])
        absolute_change = result_value - baseline_value
        if baseline_value != 0:
            percent_change = absolute_change / abs(baseline_value) * 100
        target = protocol.get("target_value")
        if target is None:
            target_status = "not_configured"
        else:
            direction = protocol.get("desired_direction")
            tolerance = max(abs(float(target)) * 0.01, 1e-9)
            if direction == "decrease":
                target_status = "met" if result_value <= float(target) else "missed"
            elif direction == "increase":
                target_status = "met" if result_value >= float(target) else "missed"
            else:
                target_status = "met" if abs(result_value - float(target)) <= tolerance else "missed"
    elif baseline or result:
        target_status = "indeterminate"
    return {
        "comparable": comparable,
        "denominator_required": denominator_required,
        "normalized_unit": normalized_unit,
        "baseline_value": baseline.get("normalized_value") if baseline else None,
        "result_value": result.get("normalized_value") if result else None,
        "absolute_change": absolute_change,
        "percent_change": percent_change,
        "target_value": protocol.get("target_value"),
        "target_status": target_status,
        "direction": protocol.get("desired_direction"),
    }


def _validation_checks(
    *,
    required: bool,
    profile: str,
    protocol: dict | None,
    baseline: dict | None,
    result: dict | None,
    analysis: dict,
) -> list[dict]:
    if not required:
        return []
    denominator_required = bool(
        PROFILE_DEFINITIONS.get(profile, {}).get("denominator_required")
        or (protocol and str(protocol.get("denominator_name") or "").strip())
    )
    scope_ready = bool(
        protocol
        and str(protocol.get("subject") or "").strip()
        and str(protocol.get("problem_statement") or "").strip()
    )
    indicator_ready = bool(
        protocol
        and str(protocol.get("indicator_name") or "").strip()
        and str(protocol.get("indicator_unit") or "").strip()
        and (not denominator_required or (
            str(protocol.get("denominator_name") or "").strip()
            and str(protocol.get("denominator_unit") or "").strip()
        ))
    )
    baseline_ready = bool(
        baseline
        and baseline.get("evidence_node_id")
        and baseline.get("period_start")
        and baseline.get("period_end")
        and baseline.get("normalized_value") is not None
        and (not denominator_required or baseline.get("denominator_value"))
    )
    intervention_ready = bool(
        protocol
        and str(protocol.get("intervention_description") or "").strip()
        and protocol.get("intervention_start_date")
        and protocol.get("review_date")
        and protocol.get("target_value") is not None
        and str(protocol.get("target_description") or "").strip()
    )
    result_ready = bool(
        result
        and result.get("evidence_node_id")
        and result.get("period_start")
        and result.get("period_end")
        and result.get("normalized_value") is not None
        and (not denominator_required or result.get("denominator_value"))
    )
    target_evaluated = bool(
        analysis.get("comparable")
        and analysis.get("target_status") in {"met", "missed"}
    )
    review_ready = bool(
        protocol
        and protocol.get("reviewed_at")
        and protocol.get("attribution_confidence")
        and str(protocol.get("review_rationale") or "").strip()
        and str(protocol.get("limitations") or "").strip()
    )
    return [
        {"key": "validation_scope", "label": "Unidade, problema e âmbito de validação definidos", "passed": scope_ready, "count": int(scope_ready)},
        {"key": "indicator_defined", "label": "Indicador, unidade e normalização definidos", "passed": indicator_ready, "count": int(indicator_ready)},
        {"key": "baseline_comparable", "label": "Baseline quantitativa ligada à evidência", "passed": baseline_ready, "count": int(baseline_ready)},
        {"key": "intervention_defined", "label": "Intervenção, meta e data de revisão definidas", "passed": intervention_ready, "count": int(intervention_ready)},
        {"key": "result_comparable", "label": "Resultado comparável ligado à evidência", "passed": bool(result_ready and analysis.get("comparable")), "count": int(bool(result_ready and analysis.get("comparable")))},
        {"key": "target_evaluated", "label": "Resultado comparado deterministicamente com a meta", "passed": target_evaluated, "count": int(target_evaluated)},
        {"key": "attribution_reviewed", "label": "Atribuição, limitações e fatores externos revistos", "passed": review_ready, "count": int(review_ready)},
    ]


def validation_readiness(
    db: Session,
    *,
    organization_id: str,
    mission_id: str,
) -> dict:
    _ensure_schema(db)
    mission = (
        db.query(CanonicalMission)
        .filter(
            CanonicalMission.organization_id == organization_id,
            CanonicalMission.id == mission_id,
        )
        .one_or_none()
    )
    if mission is None:
        return {"required": False, "profile": PROFILE_NONE, "ready": True, "checks": []}
    row = _protocol_row(db, organization_id, mission_id)
    protocol = _protocol_view(row)
    profile = str(protocol.get("profile") if protocol else _profile_from_mission(mission))
    required = profile != PROFILE_NONE or protocol is not None
    measurements = _measurement_rows(db, organization_id, mission_id) if protocol else {}
    baseline = measurements.get("baseline")
    result = measurements.get("result")
    analysis = _analysis(protocol, baseline, result)
    checks = _validation_checks(
        required=required,
        profile=profile,
        protocol=protocol,
        baseline=baseline,
        result=result,
        analysis=analysis,
    )
    completed = sum(1 for check in checks if check["passed"])
    return {
        "required": required,
        "profile": profile,
        "profile_label": PROFILE_DEFINITIONS.get(profile, PROFILE_DEFINITIONS[PROFILE_NONE])["label"],
        "ready": not required or completed == len(checks),
        "completed_checks": completed,
        "total_checks": len(checks),
        "progress_percent": 100 if not checks else round(completed / len(checks) * 100),
        "checks": checks,
        "blocking_keys": [check["key"] for check in checks if not check["passed"]],
        "analysis": analysis,
    }


def _history(db: Session, protocol_id: str) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT revision, event_type, content_hash, created_by_user_id, created_at
            FROM pilot_validation_events
            WHERE protocol_id=:protocol
            ORDER BY revision DESC
            LIMIT 50
            """
        ),
        {"protocol": protocol_id},
    ).mappings().all()
    return [
        {
            "revision": int(row["revision"]),
            "event_type": row["event_type"],
            "content_hash": row["content_hash"],
            "created_by_user_id": row["created_by_user_id"],
            "created_at": as_iso(row["created_at"]),
        }
        for row in rows
    ]


def _aggregate(
    db: Session,
    *,
    organization_id: str,
    mission: CanonicalMission,
    include_history: bool = True,
) -> dict:
    row = _protocol_row(db, organization_id, mission.id)
    protocol = _protocol_view(row)
    profile = str(protocol.get("profile") if protocol else _profile_from_mission(mission))
    measurements = _measurement_rows(db, organization_id, mission.id) if protocol else {}
    baseline = measurements.get("baseline")
    result = measurements.get("result")
    analysis = _analysis(protocol, baseline, result)
    readiness = validation_readiness(
        db,
        organization_id=organization_id,
        mission_id=mission.id,
    )
    aggregate = {
        "schema": "sris.validation.protocol.v1",
        "mission_id": mission.id,
        "mission_code": mission.code,
        "required": readiness["required"],
        "profile": profile,
        "profile_definition": PROFILE_DEFINITIONS.get(profile, PROFILE_DEFINITIONS[PROFILE_NONE]),
        "protocol": protocol,
        "baseline": baseline,
        "result": result,
        "analysis": analysis,
        "readiness": readiness,
    }
    if include_history and protocol:
        aggregate["history"] = _history(db, protocol["id"])
    return aggregate


def _snapshot_hash(snapshot: dict) -> str:
    payload = json.loads(json.dumps(snapshot, ensure_ascii=False, default=str))
    payload.pop("history", None)
    if payload.get("protocol"):
        payload["protocol"].pop("content_hash", None)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _record_snapshot(
    db: Session,
    *,
    organization_id: str,
    mission: CanonicalMission,
    protocol_id: str,
    event_type: str,
    user_id: str,
) -> str:
    snapshot = _aggregate(
        db,
        organization_id=organization_id,
        mission=mission,
        include_history=False,
    )
    protocol = snapshot["protocol"] or {}
    revision = int(protocol.get("revision") or 1)
    digest = _snapshot_hash(snapshot)
    db.execute(
        text(
            """
            UPDATE pilot_validation_protocols
            SET content_hash=:hash, updated_at=CURRENT_TIMESTAMP
            WHERE id=:id AND organization_id=:org
            """
        ),
        {"hash": digest, "id": protocol_id, "org": organization_id},
    )
    db.execute(
        text(
            """
            INSERT INTO pilot_validation_events
                (id, protocol_id, organization_id, mission_id, revision, event_type,
                 snapshot_json, content_hash, created_by_user_id)
            VALUES
                (:id, :protocol, :org, :mission, :revision, :event, :snapshot, :hash, :user)
            """
        ),
        {
            "id": str(uuid4()),
            "protocol": protocol_id,
            "org": organization_id,
            "mission": mission.id,
            "revision": revision,
            "event": event_type,
            "snapshot": json.dumps(snapshot, ensure_ascii=False, sort_keys=True, default=str),
            "hash": digest,
            "user": user_id,
        },
    )
    record_audit(
        db,
        action=f"pilot.validation.{event_type}",
        resource_type="validation_protocol",
        resource_id=protocol_id,
        organization_id=organization_id,
        user_id=user_id,
        payload={
            "mission_code": mission.code,
            "revision": revision,
            "content_hash": digest,
        },
    )
    return digest


def _assert_revision(row, expected_revision: int | None) -> None:
    if row is None or expected_revision is None:
        return
    current = int(row["revision"] or 1)
    if current != expected_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "validation_revision_conflict",
                "message": "O protocolo foi alterado. Atualize a missão antes de repetir a operação.",
                "current_revision": current,
            },
        )


def seed_validation_protocol(
    db: Session,
    *,
    organization_id: str,
    mission: CanonicalMission,
    profile: str,
    user_id: str,
) -> None:
    if profile not in {PROFILE_MEASURABLE, PROFILE_TOURISM}:
        return
    _ensure_schema(db)
    existing = _protocol_row(db, organization_id, mission.id)
    if existing is not None:
        return
    try:
        document = json.loads(mission.document_json or "{}")
    except (TypeError, ValueError):
        document = {}
    question = str(document.get("central_question") or "")
    defaults = {
        "subject_type": "Unidade de alojamento" if profile == PROFILE_TOURISM else "Unidade de análise",
        "indicator_name": "Consumo de água" if profile == PROFILE_TOURISM else "",
        "indicator_unit": "m³" if profile == PROFILE_TOURISM else "",
        "denominator_name": "Quartos-noite ocupados" if profile == PROFILE_TOURISM else "",
        "denominator_unit": "quarto-noite ocupado" if profile == PROFILE_TOURISM else "",
        "guardrails": (
            "Experiência do hóspede; custo operacional; continuidade da operação; "
            "ausência de transferência material do consumo para outro recurso."
            if profile == PROFILE_TOURISM
            else ""
        ),
        "attribution_method": (
            "Comparação antes/depois normalizada pela atividade real, com variáveis externas, "
            "alterações de operação e limitações explicitamente revistas."
            if profile == PROFILE_TOURISM
            else "Comparação entre baseline e resultado observado, com limitações explícitas."
        ),
    }
    protocol_id = str(uuid4())
    db.execute(
        text(
            """
            INSERT INTO pilot_validation_protocols
                (id, organization_id, mission_id, profile, subject_type, problem_statement,
                 indicator_name, indicator_unit, denominator_name, denominator_unit,
                 guardrails, attribution_method, revision, created_by_user_id)
            VALUES
                (:id, :org, :mission, :profile, :subject_type, :problem,
                 :indicator, :unit, :denominator, :denominator_unit,
                 :guardrails, :method, 1, :user)
            """
        ),
        {
            "id": protocol_id,
            "org": organization_id,
            "mission": mission.id,
            "profile": profile,
            "subject_type": defaults["subject_type"],
            "problem": question,
            "indicator": defaults["indicator_name"],
            "unit": defaults["indicator_unit"],
            "denominator": defaults["denominator_name"],
            "denominator_unit": defaults["denominator_unit"],
            "guardrails": defaults["guardrails"],
            "method": defaults["attribution_method"],
            "user": user_id,
        },
    )
    _record_snapshot(
        db,
        organization_id=organization_id,
        mission=mission,
        protocol_id=protocol_id,
        event_type="protocol_seeded",
        user_id=user_id,
    )


def _evidence_exists(
    db: Session,
    *,
    organization_id: str,
    mission_id: str,
    evidence_node_id: str,
) -> bool:
    _ensure_graph_schema(db)
    value = db.execute(
        text(
            """
            SELECT id FROM pilot_evidence_graph_nodes
            WHERE id=:node AND organization_id=:org AND mission_id=:mission
              AND node_type='evidence'
              AND status NOT IN ('rejected', 'superseded')
            """
        ),
        {"node": evidence_node_id, "org": organization_id, "mission": mission_id},
    ).scalar_one_or_none()
    return value is not None


@router.get("/profiles")
def validation_profiles() -> dict:
    return {"profiles": PROFILE_DEFINITIONS}


@router.get("/missions/{mission_code}")
def get_validation(
    mission_code: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _membership(db, user.id)
    mission = _mission(db, membership.organization_id, mission_code)
    result = _aggregate(db, organization_id=membership.organization_id, mission=mission)
    db.commit()
    return result


@router.put("/missions/{mission_code}/protocol")
def upsert_protocol(
    mission_code: str,
    payload: ProtocolUpsert,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _membership(db, user.id)
    _require_writer(membership)
    mission = _mission(db, membership.organization_id, mission_code)
    row = _protocol_row(db, membership.organization_id, mission.id)
    _assert_revision(row, payload.expected_revision)
    if row is not None:
        measurement_count = int(
            db.execute(
                text("SELECT COUNT(*) FROM pilot_validation_measurements WHERE protocol_id=:protocol"),
                {"protocol": row["id"]},
            ).scalar()
            or 0
        )
        locked_fields = (
            "profile",
            "indicator_name",
            "indicator_unit",
            "denominator_name",
            "denominator_unit",
        )
        contract_changed = any(
            str(row[field] or "").strip() != str(getattr(payload, field) or "").strip()
            for field in locked_fields
        )
        if measurement_count and contract_changed:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "validation_measurement_contract_locked",
                    "message": (
                        "O indicador ou a regra de normalização já tem medições. "
                        "Preserve este protocolo e crie uma nova missão para alterar a base de comparação."
                    ),
                },
            )
    values = payload.model_dump(exclude={"expected_revision"})
    params = {
        **values,
        "target_value": _number(values["target_value"]),
        "org": membership.organization_id,
        "mission": mission.id,
        "user": user.id,
    }
    if row is None:
        protocol_id = str(uuid4())
        params["id"] = protocol_id
        db.execute(
            text(
                """
                INSERT INTO pilot_validation_protocols
                    (id, organization_id, mission_id, profile, subject, subject_type,
                     problem_statement, indicator_name, indicator_unit, desired_direction,
                     denominator_name, denominator_unit, target_value, target_description,
                     guardrails, intervention_description, intervention_start_date,
                     intervention_end_date, review_date, attribution_method, revision,
                     created_by_user_id)
                VALUES
                    (:id, :org, :mission, :profile, :subject, :subject_type,
                     :problem_statement, :indicator_name, :indicator_unit, :desired_direction,
                     :denominator_name, :denominator_unit, :target_value, :target_description,
                     :guardrails, :intervention_description, :intervention_start_date,
                     :intervention_end_date, :review_date, :attribution_method, 1, :user)
                """
            ),
            params,
        )
        event_type = "protocol_created"
    else:
        protocol_id = str(row["id"])
        params["id"] = protocol_id
        db.execute(
            text(
                """
                UPDATE pilot_validation_protocols SET
                    profile=:profile, subject=:subject, subject_type=:subject_type,
                    problem_statement=:problem_statement, indicator_name=:indicator_name,
                    indicator_unit=:indicator_unit, desired_direction=:desired_direction,
                    denominator_name=:denominator_name, denominator_unit=:denominator_unit,
                    target_value=:target_value, target_description=:target_description,
                    guardrails=:guardrails, intervention_description=:intervention_description,
                    intervention_start_date=:intervention_start_date,
                    intervention_end_date=:intervention_end_date, review_date=:review_date,
                    attribution_method=:attribution_method,
                    reviewed_by_user_id=NULL, reviewed_at=NULL,
                    attribution_confidence=NULL, review_rationale='', limitations='',
                    external_factors='', implementation_deviation='',
                    revision=revision+1,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=:id AND organization_id=:org
                """
            ),
            params,
        )
        event_type = "protocol_updated"
    _record_snapshot(
        db,
        organization_id=membership.organization_id,
        mission=mission,
        protocol_id=protocol_id,
        event_type=event_type,
        user_id=user.id,
    )
    db.commit()
    return _aggregate(db, organization_id=membership.organization_id, mission=mission)


@router.put("/missions/{mission_code}/measurements/{phase}")
def upsert_measurement(
    mission_code: str,
    phase: Literal["baseline", "result"],
    payload: MeasurementUpsert,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _membership(db, user.id)
    _require_writer(membership)
    mission = _mission(db, membership.organization_id, mission_code)
    protocol_row = _protocol_row(db, membership.organization_id, mission.id)
    if protocol_row is None:
        raise HTTPException(status_code=409, detail="Configure primeiro o protocolo de validação da missão.")
    _assert_revision(protocol_row, payload.expected_revision)
    protocol = _protocol_view(protocol_row) or {}
    denominator_required = bool(
        PROFILE_DEFINITIONS.get(protocol.get("profile"), {}).get("denominator_required")
        or str(protocol.get("denominator_name") or "").strip()
    )
    if denominator_required and payload.denominator_value is None:
        raise HTTPException(status_code=422, detail="Esta missão exige o valor da atividade usado na normalização.")
    if not _evidence_exists(
        db,
        organization_id=membership.organization_id,
        mission_id=mission.id,
        evidence_node_id=payload.evidence_node_id,
    ):
        raise HTTPException(status_code=422, detail="Associe uma evidência válida da própria missão à medição.")
    normalized = payload.numerator_value
    if payload.denominator_value is not None:
        normalized = payload.numerator_value / payload.denominator_value
    current = db.execute(
        text(
            """
            SELECT id FROM pilot_validation_measurements
            WHERE protocol_id=:protocol AND phase=:phase
            """
        ),
        {"protocol": protocol_row["id"], "phase": phase},
    ).scalar_one_or_none()
    params = {
        "id": current or str(uuid4()),
        "protocol": protocol_row["id"],
        "org": membership.organization_id,
        "mission": mission.id,
        "phase": phase,
        "period_start": payload.period_start,
        "period_end": payload.period_end,
        "numerator": _number(payload.numerator_value),
        "denominator": _number(payload.denominator_value),
        "normalized": _number(normalized),
        "evidence": payload.evidence_node_id,
        "quality": payload.data_quality,
        "notes": payload.notes,
        "user": user.id,
    }
    if current:
        db.execute(
            text(
                """
                UPDATE pilot_validation_measurements SET
                    period_start=:period_start, period_end=:period_end,
                    numerator_value=:numerator, denominator_value=:denominator,
                    normalized_value=:normalized, evidence_node_id=:evidence,
                    data_quality=:quality, notes=:notes, updated_at=CURRENT_TIMESTAMP
                WHERE id=:id AND organization_id=:org
                """
            ),
            params,
        )
    else:
        db.execute(
            text(
                """
                INSERT INTO pilot_validation_measurements
                    (id, protocol_id, organization_id, mission_id, phase, period_start,
                     period_end, numerator_value, denominator_value, normalized_value,
                     evidence_node_id, data_quality, notes, created_by_user_id)
                VALUES
                    (:id, :protocol, :org, :mission, :phase, :period_start,
                     :period_end, :numerator, :denominator, :normalized,
                     :evidence, :quality, :notes, :user)
                """
            ),
            params,
        )
    db.execute(
        text(
            """
            UPDATE pilot_validation_protocols
            SET revision=revision+1, reviewed_by_user_id=NULL, reviewed_at=NULL,
                attribution_confidence=NULL, review_rationale='', limitations='',
                external_factors='', implementation_deviation='',
                updated_at=CURRENT_TIMESTAMP
            WHERE id=:id AND organization_id=:org
            """
        ),
        {"id": protocol_row["id"], "org": membership.organization_id},
    )
    _record_snapshot(
        db,
        organization_id=membership.organization_id,
        mission=mission,
        protocol_id=str(protocol_row["id"]),
        event_type=f"{phase}_recorded",
        user_id=user.id,
    )
    db.commit()
    return _aggregate(db, organization_id=membership.organization_id, mission=mission)


@router.post("/missions/{mission_code}/review")
def review_validation(
    mission_code: str,
    payload: ValidationReview,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _membership(db, user.id)
    _require_reviewer(membership)
    mission = _mission(db, membership.organization_id, mission_code)
    protocol_row = _protocol_row(db, membership.organization_id, mission.id)
    if protocol_row is None:
        raise HTTPException(status_code=409, detail="Configure primeiro o protocolo de validação.")
    _assert_revision(protocol_row, payload.expected_revision)
    measurements = _measurement_rows(db, membership.organization_id, mission.id)
    if not measurements.get("baseline") or not measurements.get("result"):
        raise HTTPException(status_code=409, detail="Registe a baseline e o resultado antes da revisão de atribuição.")
    protocol = _protocol_view(protocol_row) or {}
    analysis = _analysis(protocol, measurements.get("baseline"), measurements.get("result"))
    if not analysis.get("comparable"):
        raise HTTPException(
            status_code=409,
            detail="A baseline e o resultado ainda não formam uma comparação temporal e metodologicamente válida.",
        )
    db.execute(
        text(
            """
            UPDATE pilot_validation_protocols SET
                attribution_confidence=:confidence, review_rationale=:rationale,
                limitations=:limitations, external_factors=:external,
                implementation_deviation=:deviation, reviewed_by_user_id=:user,
                reviewed_at=CURRENT_TIMESTAMP, revision=revision+1,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=:id AND organization_id=:org
            """
        ),
        {
            "confidence": payload.attribution_confidence,
            "rationale": payload.review_rationale,
            "limitations": payload.limitations,
            "external": payload.external_factors,
            "deviation": payload.implementation_deviation,
            "user": user.id,
            "id": protocol_row["id"],
            "org": membership.organization_id,
        },
    )
    _record_snapshot(
        db,
        organization_id=membership.organization_id,
        mission=mission,
        protocol_id=str(protocol_row["id"]),
        event_type="attribution_reviewed",
        user_id=user.id,
    )
    from app.pilot_mission_state import record_module_review

    record_module_review(
        db,
        organization_id=membership.organization_id,
        mission_id=mission.id,
        mission_code=mission.code,
        module_key="validation",
        module_revision=None,
        module_content_hash=None,
        rationale=payload.review_rationale.strip(),
        user_id=user.id,
    )
    db.commit()
    return _aggregate(db, organization_id=membership.organization_id, mission=mission)
