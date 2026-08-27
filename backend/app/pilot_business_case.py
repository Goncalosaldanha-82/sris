from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.atlas_platform.audit import record_audit
from app.atlas_platform.auth import current_user
from app.atlas_platform.database import get_db
from app.atlas_platform.models import Membership, Role, User
from app.evidence_graph import (
    _ensure_schema as _ensure_graph_schema,
    _membership,
    _mission,
    _require_mission_mutable,
)
from app.pilot_serialization import as_iso


router = APIRouter(
    prefix="/api/pilot/business-cases",
    tags=["pilot-live-business-case"],
)

WRITER_ROLES = {
    Role.OWNER.value,
    Role.ADMIN.value,
    Role.REVIEWER.value,
    Role.CONTRIBUTOR.value,
}
REVIEWER_ROLES = {Role.OWNER.value, Role.ADMIN.value, Role.REVIEWER.value}

CaseKind = Literal["commercial", "public_value", "cost_effectiveness", "hybrid"]
ItemKind = Literal[
    "monetary_cost",
    "monetary_benefit",
    "non_monetary_benefit",
    "human_resource",
    "material_resource",
    "equipment_resource",
    "financial_resource",
]
FinancialTreatment = Literal["cost", "benefit", "none"]
ItemPhase = Literal["planning", "execution", "post_mission"]
Recurrence = Literal["one_off", "monthly", "quarterly", "annual"]
Confidence = Literal["low", "moderate", "high"]
AmountBasis = Literal["total", "per_unit"]
OperationalStatus = Literal["planned", "committed", "active", "completed", "blocked"]

RESOURCE_KINDS = {
    "human_resource",
    "material_resource",
    "equipment_resource",
    "financial_resource",
}
RECURRENCE_INTERVALS = {"one_off": 0, "monthly": 1, "quarterly": 3, "annual": 12}
CONFIDENCE_POINTS = {"low": 35.0, "moderate": 65.0, "high": 90.0}

CASE_KIND_DEFINITIONS = {
    "commercial": {
        "label": "Retorno comercial",
        "description": "Receita, poupança, margem, benefício líquido e retorno financeiro.",
        "profit_applicable": True,
    },
    "public_value": {
        "label": "Valor público, social ou ambiental",
        "description": "Custos monetários e resultados não monetizados permanecem separados.",
        "profit_applicable": False,
    },
    "cost_effectiveness": {
        "label": "Custo-eficácia",
        "description": "Compara o custo total com uma unidade de resultado observável.",
        "profit_applicable": False,
    },
    "hybrid": {
        "label": "Valor híbrido",
        "description": "Combina retorno financeiro com resultados públicos, sociais ou ambientais.",
        "profit_applicable": True,
    },
}

ITEM_KIND_DEFINITIONS = {
    "monetary_cost": "Custo monetário",
    "monetary_benefit": "Benefício monetário",
    "non_monetary_benefit": "Benefício não monetizado",
    "human_resource": "Recurso humano",
    "material_resource": "Material ou consumível",
    "equipment_resource": "Equipamento ou capacidade",
    "financial_resource": "Financiamento disponível",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sql_values(values: dict) -> dict:
    """Keep raw SQL parameters portable across PostgreSQL and SQLite."""
    return {
        key: float(value) if isinstance(value, Decimal) else value
        for key, value in values.items()
    }


class BusinessCaseUpsert(BaseModel):
    expected_revision: int | None = Field(default=None, ge=0)
    case_kind: CaseKind = "hybrid"
    currency: str = Field(default="EUR", pattern=r"^[A-Z]{3}$")
    horizon_months: int = Field(default=60, ge=1, le=600)
    discount_rate_pct: Decimal = Field(default=Decimal("8"), ge=0, le=100)
    decision_context: str = Field(default="", max_length=5000)
    baseline: str = Field(default="", max_length=5000)
    counterfactual: str = Field(default="", max_length=5000)
    planned_start_date: date | None = None
    planned_end_date: date | None = None
    forecast_end_date: date | None = None
    actual_start_date: date | None = None
    actual_end_date: date | None = None
    outcome_name: str = Field(default="", max_length=300)
    outcome_unit: str = Field(default="", max_length=80)
    planned_outcome_quantity: Decimal | None = Field(default=None, ge=0)
    actual_outcome_quantity: Decimal | None = Field(default=None, ge=0)
    notes: str = Field(default="", max_length=8000)

    @model_validator(mode="after")
    def validate_dates(self) -> "BusinessCaseUpsert":
        if self.planned_start_date and self.planned_end_date and self.planned_end_date < self.planned_start_date:
            raise ValueError("A conclusão prevista não pode anteceder o início previsto.")
        if self.actual_start_date and self.actual_end_date and self.actual_end_date < self.actual_start_date:
            raise ValueError("A conclusão real não pode anteceder o início real.")
        return self


class LineItemCreate(BaseModel):
    expected_revision: int | None = Field(default=None, ge=1)
    kind: ItemKind
    financial_treatment: FinancialTreatment
    category: str = Field(default="", max_length=120)
    label: str = Field(min_length=2, max_length=300)
    description: str = Field(default="", max_length=5000)
    phase: ItemPhase = "execution"
    unit: str = Field(default="", max_length=80)
    amount_basis: AmountBasis = "total"
    planned_quantity: Decimal | None = Field(default=None, ge=0)
    actual_quantity: Decimal | None = Field(default=None, ge=0)
    conservative_amount: Decimal | None = Field(default=None, ge=0)
    base_amount: Decimal | None = Field(default=None, ge=0)
    favorable_amount: Decimal | None = Field(default=None, ge=0)
    committed_amount: Decimal | None = Field(default=None, ge=0)
    realized_amount: Decimal | None = Field(default=None, ge=0)
    forecast_amount: Decimal | None = Field(default=None, ge=0)
    start_month: int = Field(default=0, ge=0, le=599)
    end_month: int | None = Field(default=None, ge=0, le=599)
    recurrence: Recurrence = "one_off"
    source_label: str = Field(default="", max_length=500)
    evidence_node_id: str | None = Field(default=None, min_length=8, max_length=64)
    alternative_node_id: str | None = Field(default=None, min_length=8, max_length=64)
    responsible: str = Field(default="", max_length=300)
    operational_status: OperationalStatus = "planned"
    blocker: str = Field(default="", max_length=3000)
    assumption: str = Field(default="", max_length=3000)
    confidence: Confidence = "moderate"
    include_in_totals: bool = True

    @model_validator(mode="after")
    def validate_semantics(self) -> "LineItemCreate":
        self.label = " ".join(self.label.split())
        self.category = " ".join(self.category.split())
        if self.end_month is not None and self.end_month < self.start_month:
            raise ValueError("O mês final não pode anteceder o mês inicial.")
        forced = {
            "monetary_cost": "cost",
            "monetary_benefit": "benefit",
            "non_monetary_benefit": "none",
            "financial_resource": "none",
        }
        expected = forced.get(self.kind)
        if expected and self.financial_treatment != expected:
            raise ValueError("O tratamento financeiro não corresponde ao tipo de registo.")
        if self.financial_treatment != "none" and all(
            value is None
            for value in (
                self.conservative_amount,
                self.base_amount,
                self.favorable_amount,
                self.committed_amount,
                self.realized_amount,
                self.forecast_amount,
            )
        ):
            raise ValueError("Registe pelo menos um valor monetário para esta linha.")
        if self.kind == "non_monetary_benefit" and self.planned_quantity is None and self.actual_quantity is None:
            raise ValueError("Registe uma quantidade prevista ou realizada para o benefício não monetizado.")
        if self.amount_basis == "per_unit" and self.planned_quantity is None:
            raise ValueError("Um valor por unidade exige uma quantidade prevista.")
        if self.operational_status == "blocked" and not self.blocker.strip():
            raise ValueError("Indique o bloqueio que impede este custo, benefício ou recurso.")
        return self


class LineItemUpdate(BaseModel):
    expected_revision: int | None = Field(default=None, ge=1)
    kind: ItemKind | None = None
    financial_treatment: FinancialTreatment | None = None
    category: str | None = Field(default=None, max_length=120)
    label: str | None = Field(default=None, min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    phase: ItemPhase | None = None
    unit: str | None = Field(default=None, max_length=80)
    amount_basis: AmountBasis | None = None
    planned_quantity: Decimal | None = Field(default=None, ge=0)
    actual_quantity: Decimal | None = Field(default=None, ge=0)
    conservative_amount: Decimal | None = Field(default=None, ge=0)
    base_amount: Decimal | None = Field(default=None, ge=0)
    favorable_amount: Decimal | None = Field(default=None, ge=0)
    committed_amount: Decimal | None = Field(default=None, ge=0)
    realized_amount: Decimal | None = Field(default=None, ge=0)
    forecast_amount: Decimal | None = Field(default=None, ge=0)
    start_month: int | None = Field(default=None, ge=0, le=599)
    end_month: int | None = Field(default=None, ge=0, le=599)
    recurrence: Recurrence | None = None
    source_label: str | None = Field(default=None, max_length=500)
    evidence_node_id: str | None = Field(default=None, min_length=8, max_length=64)
    alternative_node_id: str | None = Field(default=None, min_length=8, max_length=64)
    responsible: str | None = Field(default=None, max_length=300)
    operational_status: OperationalStatus | None = None
    blocker: str | None = Field(default=None, max_length=3000)
    assumption: str | None = Field(default=None, max_length=3000)
    confidence: Confidence | None = None
    include_in_totals: bool | None = None


class BusinessCaseReview(BaseModel):
    expected_revision: int = Field(ge=1)
    rationale: str = Field(min_length=5, max_length=5000)


def _require_membership(db: Session, user_id: str) -> Membership:
    membership = _membership(db, user_id)
    if membership is None:
        raise HTTPException(status_code=403, detail="A conta não tem um workspace associado.")
    return membership


def _require_writer(membership: Membership) -> None:
    if membership.role not in WRITER_ROLES:
        raise HTTPException(status_code=403, detail="A sua função permite consultar, mas não alterar o business case.")


def _require_reviewer(membership: Membership) -> None:
    if membership.role not in REVIEWER_ROLES:
        raise HTTPException(status_code=403, detail="A revisão económica exige a função de revisor ou administrador.")


def _ensure_schema(db: Session) -> None:
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS pilot_business_cases (
            id VARCHAR(64) PRIMARY KEY,
            organization_id VARCHAR(64) NOT NULL,
            mission_id VARCHAR(64) NOT NULL,
            mission_code VARCHAR(80) NOT NULL,
            case_kind VARCHAR(40) NOT NULL DEFAULT 'hybrid',
            currency VARCHAR(3) NOT NULL DEFAULT 'EUR',
            horizon_months INTEGER NOT NULL DEFAULT 60,
            discount_rate_pct NUMERIC(12,6) NOT NULL DEFAULT 8,
            decision_context TEXT NOT NULL DEFAULT '',
            baseline TEXT NOT NULL DEFAULT '',
            counterfactual TEXT NOT NULL DEFAULT '',
            planned_start_date DATE NULL,
            planned_end_date DATE NULL,
            forecast_end_date DATE NULL,
            actual_start_date DATE NULL,
            actual_end_date DATE NULL,
            outcome_name VARCHAR(300) NOT NULL DEFAULT '',
            outcome_unit VARCHAR(80) NOT NULL DEFAULT '',
            planned_outcome_quantity NUMERIC(24,8) NULL,
            actual_outcome_quantity NUMERIC(24,8) NULL,
            notes TEXT NOT NULL DEFAULT '',
            status VARCHAR(30) NOT NULL DEFAULT 'active',
            revision INTEGER NOT NULL DEFAULT 0,
            content_hash VARCHAR(64) NOT NULL DEFAULT '',
            review_rationale TEXT NOT NULL DEFAULT '',
            reviewed_by_user_id VARCHAR(64) NULL,
            reviewed_at TIMESTAMP NULL,
            created_by_user_id VARCHAR(64) NULL,
            updated_by_user_id VARCHAR(64) NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (organization_id, mission_id)
        )
    """))
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_pilot_business_case_org_mission
        ON pilot_business_cases (organization_id, mission_id)
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS pilot_business_case_items (
            id VARCHAR(64) PRIMARY KEY,
            business_case_id VARCHAR(64) NOT NULL,
            organization_id VARCHAR(64) NOT NULL,
            mission_id VARCHAR(64) NOT NULL,
            mission_code VARCHAR(80) NOT NULL,
            kind VARCHAR(40) NOT NULL,
            financial_treatment VARCHAR(20) NOT NULL,
            category VARCHAR(120) NOT NULL DEFAULT '',
            label VARCHAR(300) NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            phase VARCHAR(30) NOT NULL DEFAULT 'execution',
            unit VARCHAR(80) NOT NULL DEFAULT '',
            amount_basis VARCHAR(20) NOT NULL DEFAULT 'total',
            planned_quantity NUMERIC(24,8) NULL,
            actual_quantity NUMERIC(24,8) NULL,
            conservative_amount NUMERIC(24,8) NULL,
            base_amount NUMERIC(24,8) NULL,
            favorable_amount NUMERIC(24,8) NULL,
            committed_amount NUMERIC(24,8) NULL,
            realized_amount NUMERIC(24,8) NULL,
            forecast_amount NUMERIC(24,8) NULL,
            start_month INTEGER NOT NULL DEFAULT 0,
            end_month INTEGER NULL,
            recurrence VARCHAR(20) NOT NULL DEFAULT 'one_off',
            source_label VARCHAR(500) NOT NULL DEFAULT '',
            evidence_node_id VARCHAR(64) NULL,
            alternative_node_id VARCHAR(64) NULL,
            responsible VARCHAR(300) NOT NULL DEFAULT '',
            operational_status VARCHAR(20) NOT NULL DEFAULT 'planned',
            blocker TEXT NOT NULL DEFAULT '',
            assumption TEXT NOT NULL DEFAULT '',
            confidence VARCHAR(20) NOT NULL DEFAULT 'moderate',
            include_in_totals BOOLEAN NOT NULL DEFAULT TRUE,
            created_by_user_id VARCHAR(64) NULL,
            updated_by_user_id VARCHAR(64) NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            retired_at TIMESTAMP NULL
        )
    """))
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_pilot_business_case_items_case
        ON pilot_business_case_items
           (business_case_id, alternative_node_id, kind, phase, retired_at)
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS pilot_business_case_events (
            id VARCHAR(64) PRIMARY KEY,
            business_case_id VARCHAR(64) NOT NULL,
            organization_id VARCHAR(64) NOT NULL,
            mission_id VARCHAR(64) NOT NULL,
            revision INTEGER NOT NULL,
            event_type VARCHAR(50) NOT NULL,
            snapshot_json TEXT NOT NULL,
            content_hash VARCHAR(64) NOT NULL,
            created_by_user_id VARCHAR(64) NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (business_case_id, revision)
        )
    """))
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_pilot_business_case_events_case
        ON pilot_business_case_events (business_case_id, revision)
    """))


def _decimal(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _number(value) -> float | None:
    if value is None:
        return None
    return round(float(_decimal(value)), 8)


def _case_row(db: Session, *, organization_id: str, mission_id: str):
    return db.execute(
        text("""
            SELECT * FROM pilot_business_cases
            WHERE organization_id=:org AND mission_id=:mission
        """),
        {"org": organization_id, "mission": mission_id},
    ).mappings().first()


def _active_item_rows(db: Session, case_id: str) -> list:
    return db.execute(
        text("""
            SELECT item.*, evidence.label AS evidence_label,
                   evidence.status AS evidence_status,
                   attachment.original_filename AS evidence_document_title,
                   alternative.label AS alternative_label,
                   alternative.body AS alternative_body
            FROM pilot_business_case_items item
            LEFT JOIN pilot_evidence_graph_nodes evidence
              ON evidence.id=item.evidence_node_id
             AND evidence.organization_id=item.organization_id
             AND evidence.mission_id=item.mission_id
            LEFT JOIN mi_mission_attachments attachment
              ON attachment.id=evidence.attachment_id
             AND attachment.organization_id=item.organization_id
             AND attachment.mission_id=item.mission_id
            LEFT JOIN pilot_evidence_graph_nodes alternative
              ON alternative.id=item.alternative_node_id
             AND alternative.organization_id=item.organization_id
             AND alternative.mission_id=item.mission_id
             AND alternative.node_type='alternative'
            WHERE item.business_case_id=:case_id AND item.retired_at IS NULL
            ORDER BY item.phase ASC, item.created_at ASC, item.label ASC
        """),
        {"case_id": case_id},
    ).mappings().all()


def _default_case(mission) -> dict:
    return {
        "id": None,
        "mission_id": mission.id,
        "mission_code": mission.code,
        "case_kind": "hybrid",
        "currency": "EUR",
        "horizon_months": 60,
        "discount_rate_pct": 8.0,
        "decision_context": "",
        "baseline": "",
        "counterfactual": "",
        "planned_start_date": None,
        "planned_end_date": None,
        "forecast_end_date": None,
        "actual_start_date": None,
        "actual_end_date": None,
        "outcome_name": "",
        "outcome_unit": "",
        "planned_outcome_quantity": None,
        "actual_outcome_quantity": None,
        "notes": "",
        "status": "not_started",
        "revision": 0,
        "content_hash": "",
        "review_rationale": "",
        "reviewed_at": None,
        "created_at": None,
        "updated_at": None,
    }


def _case_dict(row) -> dict:
    return {
        "id": row["id"],
        "mission_id": row["mission_id"],
        "mission_code": row["mission_code"],
        "case_kind": row["case_kind"],
        "currency": row["currency"],
        "horizon_months": int(row["horizon_months"]),
        "discount_rate_pct": _number(row["discount_rate_pct"]),
        "decision_context": row["decision_context"] or "",
        "baseline": row["baseline"] or "",
        "counterfactual": row["counterfactual"] or "",
        "planned_start_date": as_iso(row["planned_start_date"]),
        "planned_end_date": as_iso(row["planned_end_date"]),
        "forecast_end_date": as_iso(row["forecast_end_date"]),
        "actual_start_date": as_iso(row["actual_start_date"]),
        "actual_end_date": as_iso(row["actual_end_date"]),
        "outcome_name": row["outcome_name"] or "",
        "outcome_unit": row["outcome_unit"] or "",
        "planned_outcome_quantity": _number(row["planned_outcome_quantity"]),
        "actual_outcome_quantity": _number(row["actual_outcome_quantity"]),
        "notes": row["notes"] or "",
        "status": row["status"],
        "revision": int(row["revision"]),
        "content_hash": row["content_hash"] or "",
        "review_rationale": row["review_rationale"] or "",
        "reviewed_at": as_iso(row["reviewed_at"]),
        "created_at": as_iso(row["created_at"]),
        "updated_at": as_iso(row["updated_at"]),
    }


def _item_dict(row) -> dict:
    return {
        "id": row["id"],
        "business_case_id": row["business_case_id"],
        "kind": row["kind"],
        "financial_treatment": row["financial_treatment"],
        "category": row["category"] or "",
        "label": row["label"],
        "description": row["description"] or "",
        "phase": row["phase"],
        "unit": row["unit"] or "",
        "amount_basis": row["amount_basis"],
        "planned_quantity": _number(row["planned_quantity"]),
        "actual_quantity": _number(row["actual_quantity"]),
        "conservative_amount": _number(row["conservative_amount"]),
        "base_amount": _number(row["base_amount"]),
        "favorable_amount": _number(row["favorable_amount"]),
        "committed_amount": _number(row["committed_amount"]),
        "realized_amount": _number(row["realized_amount"]),
        "forecast_amount": _number(row["forecast_amount"]),
        "start_month": int(row["start_month"] or 0),
        "end_month": int(row["end_month"]) if row["end_month"] is not None else None,
        "recurrence": row["recurrence"],
        "source_label": row["source_label"] or "",
        "evidence_node_id": row["evidence_node_id"],
        "evidence_label": row.get("evidence_document_title") or row.get("evidence_label"),
        "evidence_status": row.get("evidence_status"),
        "alternative_node_id": row["alternative_node_id"],
        "alternative_label": row.get("alternative_label"),
        "alternative_body": row.get("alternative_body"),
        "responsible": row["responsible"] or "",
        "operational_status": row["operational_status"],
        "blocker": row["blocker"] or "",
        "assumption": row["assumption"] or "",
        "confidence": row["confidence"],
        "include_in_totals": bool(row["include_in_totals"]),
        "created_at": as_iso(row["created_at"]),
        "updated_at": as_iso(row["updated_at"]),
    }


def _occurrence_months(item: dict, horizon_months: int) -> list[int]:
    if horizon_months <= 0:
        return []
    start = max(0, int(item.get("start_month") or 0))
    if start >= horizon_months:
        return []
    recurrence = str(item.get("recurrence") or "one_off")
    interval = RECURRENCE_INTERVALS.get(recurrence, 0)
    if interval == 0:
        return [start]
    raw_end = item.get("end_month")
    end = horizon_months - 1 if raw_end is None else min(int(raw_end), horizon_months - 1)
    return list(range(start, end + 1, interval))


def _scenario_unit_amount(item: dict, scenario: str) -> float:
    base = float(item.get("base_amount") or 0)
    if scenario == "conservative" and item.get("conservative_amount") is not None:
        amount = float(item["conservative_amount"])
    elif scenario == "favorable" and item.get("favorable_amount") is not None:
        amount = float(item["favorable_amount"])
    else:
        amount = base
    if item.get("amount_basis") == "per_unit":
        amount *= float(item.get("planned_quantity") or 0)
    return amount


def _payback_month(cashflows: list[float], total_cost: float, total_benefit: float) -> int | None:
    if total_cost <= 0 or total_benefit <= 0:
        return None
    cumulative = 0.0
    for month, value in enumerate(cashflows):
        cumulative += value
        if cumulative >= -0.000001:
            return month
    return None


def _npv(cashflows: list[float], annual_rate_pct: float) -> float:
    annual_rate = max(0.0, annual_rate_pct) / 100
    return round(
        sum(value / ((1 + annual_rate) ** (month / 12)) for month, value in enumerate(cashflows)),
        2,
    )


def _scenario_summary(items: list[dict], *, scenario: str, horizon: int, discount_rate: float) -> dict:
    cashflows = [0.0 for _ in range(horizon)]
    total_cost = 0.0
    gross_benefit = 0.0
    for item in items:
        if not item.get("include_in_totals") or item.get("financial_treatment") == "none":
            continue
        months = _occurrence_months(item, horizon)
        amount = _scenario_unit_amount(item, scenario)
        total = amount * len(months)
        direction = -1 if item["financial_treatment"] == "cost" else 1
        if direction < 0:
            total_cost += total
        else:
            gross_benefit += total
        for month in months:
            cashflows[month] += direction * amount
    net = gross_benefit - total_cost
    roi = (net / total_cost * 100) if total_cost > 0 else None
    payback = _payback_month(cashflows, total_cost, gross_benefit)
    return {
        "scenario": scenario,
        "total_cost": round(total_cost, 2),
        "gross_benefit": round(gross_benefit, 2),
        "net_benefit": round(net, 2),
        "roi_pct": round(roi, 2) if roi is not None else None,
        "payback_months": payback,
        "break_even_gap": round(max(total_cost - gross_benefit, 0), 2),
        "npv": _npv(cashflows, discount_rate),
    }


def _forecast_item_total(item: dict, horizon: int) -> float:
    raw_amount = (
        item.get("forecast_amount")
        if item.get("forecast_amount") is not None
        else item.get("base_amount")
    )
    unit_amount = float(raw_amount or 0)
    if item.get("amount_basis") == "per_unit":
        unit_amount *= float(item.get("planned_quantity") or 0)
    projected = unit_amount * len(_occurrence_months(item, horizon))
    live_floor = float(item.get("realized_amount") or 0) + float(
        item.get("committed_amount") or 0
    )
    return max(projected, live_floor)


def _funding_item_total(item: dict, horizon: int) -> float:
    """Funding stages describe the same envelope, not additive expenditure."""

    raw_amount = (
        item.get("forecast_amount")
        if item.get("forecast_amount") is not None
        else item.get("base_amount")
    )
    unit_amount = float(raw_amount or 0)
    if item.get("amount_basis") == "per_unit":
        unit_amount *= float(item.get("planned_quantity") or 0)
    projected = unit_amount * len(_occurrence_months(item, horizon))
    return max(
        projected,
        float(item.get("committed_amount") or 0),
        float(item.get("realized_amount") or 0),
    )


def _forecast_summary(items: list[dict], *, horizon: int, discount_rate: float) -> dict:
    cashflows = [0.0 for _ in range(horizon)]
    total_cost = 0.0
    gross_benefit = 0.0
    for item in items:
        if not item.get("include_in_totals") or item.get("financial_treatment") == "none":
            continue
        months = _occurrence_months(item, horizon)
        unit_amount = float(item.get("forecast_amount") if item.get("forecast_amount") is not None else item.get("base_amount") or 0)
        if item.get("amount_basis") == "per_unit":
            unit_amount *= float(item.get("planned_quantity") or 0)
        total = _forecast_item_total(item, horizon)
        direction = -1 if item["financial_treatment"] == "cost" else 1
        if direction < 0:
            total_cost += total
        else:
            gross_benefit += total
        if months:
            for month in months:
                cashflows[month] += direction * unit_amount
            residual = total - unit_amount * len(months)
            if residual > 0:
                cashflows[months[-1]] += direction * residual
    net = gross_benefit - total_cost
    return {
        "total_cost": round(total_cost, 2),
        "gross_benefit": round(gross_benefit, 2),
        "net_benefit": round(net, 2),
        "roi_pct": round(net / total_cost * 100, 2) if total_cost > 0 else None,
        "payback_months": _payback_month(cashflows, total_cost, gross_benefit),
        "npv": _npv(cashflows, discount_rate),
    }


def _date_value(raw) -> date | None:
    if isinstance(raw, date):
        return raw
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def _live_metrics(case: dict, items: list[dict]) -> dict:
    horizon = int(case.get("horizon_months") or 60)
    discount_rate = float(case.get("discount_rate_pct") or 0)
    scenarios = {
        name: _scenario_summary(items, scenario=name, horizon=horizon, discount_rate=discount_rate)
        for name in ("conservative", "base", "favorable")
    }
    forecast = _forecast_summary(items, horizon=horizon, discount_rate=discount_rate)
    committed_cost = sum(
        float(item.get("committed_amount") or 0)
        for item in items
        if item.get("include_in_totals") and item.get("financial_treatment") == "cost"
    )
    realized_cost = sum(
        float(item.get("realized_amount") or 0)
        for item in items
        if item.get("include_in_totals") and item.get("financial_treatment") == "cost"
    )
    committed_benefit = sum(
        float(item.get("committed_amount") or 0)
        for item in items
        if item.get("include_in_totals") and item.get("financial_treatment") == "benefit"
    )
    realized_benefit = sum(
        float(item.get("realized_amount") or 0)
        for item in items
        if item.get("include_in_totals") and item.get("financial_treatment") == "benefit"
    )
    evidence_linked_realized_benefit = sum(
        float(item.get("realized_amount") or 0)
        for item in items
        if item.get("include_in_totals")
        and item.get("financial_treatment") == "benefit"
        and item.get("evidence_node_id")
    )
    reviewed_evidence_realized_benefit = sum(
        float(item.get("realized_amount") or 0)
        for item in items
        if item.get("include_in_totals")
        and item.get("financial_treatment") == "benefit"
        and item.get("evidence_node_id")
        and item.get("evidence_status") in {"accepted", "verified"}
    )
    verified_realized_benefit = sum(
        float(item.get("realized_amount") or 0)
        for item in items
        if item.get("include_in_totals")
        and item.get("financial_treatment") == "benefit"
        and item.get("evidence_node_id")
        and item.get("evidence_status") == "verified"
    )
    funding = sum(
        _funding_item_total(item, horizon)
        for item in items
        if item.get("kind") == "financial_resource"
    )
    planned_hours = 0.0
    actual_hours = 0.0
    for item in items:
        if item.get("kind") != "human_resource":
            continue
        unit = str(item.get("unit") or "").strip().casefold()
        if unit in {"hora", "horas", "h", "hour", "hours"}:
            planned_hours += float(item.get("planned_quantity") or 0) * max(1, len(_occurrence_months(item, horizon)))
            actual_hours += float(item.get("actual_quantity") or 0)
    annual_post_burden = 0.0
    for item in items:
        if not item.get("include_in_totals") or item.get("financial_treatment") != "cost" or item.get("phase") != "post_mission":
            continue
        amount = float(item.get("forecast_amount") if item.get("forecast_amount") is not None else item.get("base_amount") or 0)
        if item.get("amount_basis") == "per_unit":
            amount *= float(item.get("planned_quantity") or 0)
        multiplier = {"monthly": 12, "quarterly": 4, "annual": 1}.get(str(item.get("recurrence")), 0)
        annual_post_burden += amount * multiplier
    base = scenarios["base"]
    expected_cost = float(base["total_cost"])
    expected_benefit = float(base["gross_benefit"])
    actual_net = realized_benefit - realized_cost
    actual_roi = actual_net / realized_cost * 100 if realized_cost > 0 else None
    planned_outcome = case.get("planned_outcome_quantity")
    actual_outcome = case.get("actual_outcome_quantity")
    planned_start = _date_value(case.get("planned_start_date"))
    planned_end = _date_value(case.get("planned_end_date"))
    forecast_end = _date_value(case.get("forecast_end_date"))
    actual_start = _date_value(case.get("actual_start_date"))
    actual_end = _date_value(case.get("actual_end_date"))
    planned_duration = (planned_end - planned_start).days if planned_start and planned_end else None
    actual_duration = (actual_end - actual_start).days if actual_start and actual_end else None
    schedule_variance = (forecast_end - planned_end).days if forecast_end and planned_end else None
    profit_applicable = bool(CASE_KIND_DEFINITIONS.get(case.get("case_kind"), {}).get("profit_applicable"))
    forecast_margin = forecast["net_benefit"] / forecast["gross_benefit"] * 100 if forecast["gross_benefit"] > 0 else None
    return {
        "currency": case.get("currency") or "EUR",
        "horizon_months": horizon,
        "budget_base": round(expected_cost, 2),
        "committed_cost": round(committed_cost, 2),
        "realized_cost": round(realized_cost, 2),
        "remaining_cost": round(max(float(forecast["total_cost"]) - committed_cost - realized_cost, 0), 2),
        "forecast_cost_at_completion": forecast["total_cost"],
        "cost_variance": round(float(forecast["total_cost"]) - expected_cost, 2),
        "cost_variance_pct": round((float(forecast["total_cost"]) - expected_cost) / expected_cost * 100, 2) if expected_cost > 0 else None,
        "expected_gross_benefit": round(expected_benefit, 2),
        "committed_benefit": round(committed_benefit, 2),
        "realized_benefit": round(realized_benefit, 2),
        "evidence_linked_realized_benefit": round(evidence_linked_realized_benefit, 2),
        "reviewed_evidence_realized_benefit": round(reviewed_evidence_realized_benefit, 2),
        "verified_realized_benefit": round(verified_realized_benefit, 2),
        "unverified_realized_benefit": round(max(realized_benefit - verified_realized_benefit, 0), 2),
        "forecast_gross_benefit": forecast["gross_benefit"],
        "forecast_net_benefit": forecast["net_benefit"],
        "realized_net_benefit": round(actual_net, 2),
        "forecast_roi_pct": forecast["roi_pct"],
        "realized_roi_pct": round(actual_roi, 2) if actual_roi is not None else None,
        "forecast_payback_months": forecast["payback_months"],
        "forecast_npv": forecast["npv"],
        "break_even_required_benefit": base["total_cost"],
        "break_even_gap": base["break_even_gap"],
        "profit_applicable": profit_applicable,
        "forecast_profit": forecast["net_benefit"] if profit_applicable else None,
        "forecast_margin_pct": round(forecast_margin, 2) if profit_applicable and forecast_margin is not None else None,
        "planned_human_hours": round(planned_hours, 2),
        "actual_human_hours": round(actual_hours, 2),
        "annual_post_mission_burden": round(annual_post_burden, 2),
        "funding_available": round(funding, 2),
        "funding_gap": round(max(float(forecast["total_cost"]) - funding, 0), 2),
        "blocked_resource_count": sum(
            1 for item in items
            if item.get("kind") in RESOURCE_KINDS and item.get("operational_status") == "blocked"
        ),
        "planned_outcome_quantity": planned_outcome,
        "actual_outcome_quantity": actual_outcome,
        "cost_per_planned_outcome": round(float(forecast["total_cost"]) / float(planned_outcome), 4) if planned_outcome not in (None, 0) else None,
        "cost_per_actual_outcome": round(realized_cost / float(actual_outcome), 4) if actual_outcome not in (None, 0) else None,
        "planned_duration_days": planned_duration,
        "actual_duration_days": actual_duration,
        "schedule_variance_days": schedule_variance,
        "schedule_variance_pct": (
            round(schedule_variance / planned_duration * 100, 2)
            if schedule_variance is not None and planned_duration not in (None, 0)
            else None
        ),
        "scenarios": scenarios,
    }


def _metric_states(case: dict, items: list[dict]) -> dict[str, str]:
    """Distinguish a calculated zero from a dimension with no source records."""

    known = "observed_or_estimated"
    partial = "partial_observed_or_estimated"
    unknown = "unknown_not_zero"

    def coverage(rows: list[dict], predicate) -> str:
        if not rows:
            return unknown
        covered = sum(1 for row in rows if predicate(row))
        if covered == 0:
            return unknown
        return known if covered == len(rows) else partial

    def combine(*states: str) -> str:
        if any(state == unknown for state in states):
            return unknown
        if any(state == partial for state in states):
            return partial
        return known

    def amount_declared(item: dict, *fields: str) -> bool:
        return any(item.get(field) is not None for field in fields)

    def forecast_declared(item: dict) -> bool:
        return amount_declared(
            item,
            "forecast_amount",
            "base_amount",
            "committed_amount",
            "realized_amount",
        )

    included_costs = [
        item for item in items
        if item.get("include_in_totals") and item.get("financial_treatment") == "cost"
    ]
    included_benefits = [
        item for item in items
        if item.get("include_in_totals") and item.get("financial_treatment") == "benefit"
    ]
    resources = [item for item in items if item.get("kind") in RESOURCE_KINDS]
    human_hour_lines = [
        item for item in items
        if item.get("kind") == "human_resource"
        and str(item.get("unit") or "").strip().casefold()
        in {"hora", "horas", "h", "hour", "hours"}
    ]
    funding_lines = [item for item in items if item.get("kind") == "financial_resource"]
    post_mission_costs = [
        item for item in included_costs if item.get("phase") == "post_mission"
    ]
    schedule_known = bool(
        case.get("planned_start_date")
        and case.get("planned_end_date")
        and (case.get("forecast_end_date") or case.get("actual_end_date"))
    )
    outcome_known = bool(
        case.get("planned_outcome_quantity") is not None
        or case.get("actual_outcome_quantity") is not None
    )
    budget_state = coverage(included_costs, lambda item: item.get("base_amount") is not None)
    committed_cost_state = coverage(
        included_costs, lambda item: item.get("committed_amount") is not None
    )
    realized_cost_state = coverage(
        included_costs, lambda item: item.get("realized_amount") is not None
    )
    forecast_cost_state = coverage(included_costs, forecast_declared)
    expected_benefit_state = coverage(
        included_benefits, lambda item: item.get("base_amount") is not None
    )
    committed_benefit_state = coverage(
        included_benefits, lambda item: item.get("committed_amount") is not None
    )
    realized_benefit_state = coverage(
        included_benefits, lambda item: item.get("realized_amount") is not None
    )
    forecast_benefit_state = coverage(included_benefits, forecast_declared)
    forecast_financial_state = combine(
        forecast_cost_state,
        forecast_benefit_state,
    )
    realized_financial_state = combine(
        realized_cost_state,
        realized_benefit_state,
    )
    planned_hours_state = coverage(
        human_hour_lines, lambda item: item.get("planned_quantity") is not None
    )
    actual_hours_state = coverage(
        human_hour_lines, lambda item: item.get("actual_quantity") is not None
    )
    funding_state = coverage(funding_lines, forecast_declared)
    post_mission_state = coverage(
        post_mission_costs,
        lambda item: amount_declared(item, "forecast_amount", "base_amount"),
    )
    planned_outcome_state = known if case.get("planned_outcome_quantity") is not None else unknown
    actual_outcome_state = known if case.get("actual_outcome_quantity") is not None else unknown
    chosen_cost_per_outcome_state = (
        combine(realized_cost_state, actual_outcome_state)
        if case.get("actual_outcome_quantity") is not None
        else combine(forecast_cost_state, planned_outcome_state)
    )
    scenario_states: dict[str, str] = {}
    for scenario in ("conservative", "base", "favorable"):
        field = f"{scenario}_amount"
        cost_state = coverage(
            included_costs,
            lambda item, field=field: item.get(field) is not None
            or (scenario != "base" and item.get("base_amount") is not None),
        )
        benefit_state = coverage(
            included_benefits,
            lambda item, field=field: item.get(field) is not None
            or (scenario != "base" and item.get("base_amount") is not None),
        )
        financial_state = combine(cost_state, benefit_state)
        scenario_states.update(
            {
                f"scenario_{scenario}_costs": cost_state,
                f"scenario_{scenario}_benefits": benefit_state,
                f"scenario_{scenario}_financial": financial_state,
            }
        )
    return {
        "any_lines": known if items else unknown,
        "financial": forecast_financial_state,
        "costs": known if included_costs else unknown,
        "benefits": known if included_benefits else unknown,
        "resources": known if resources else unknown,
        "human_hours": (
            known
            if planned_hours_state == known and actual_hours_state == known
            else unknown
            if planned_hours_state == unknown and actual_hours_state == unknown
            else partial
        ),
        "planned_human_hours": planned_hours_state,
        "actual_human_hours": actual_hours_state,
        "budget_base": budget_state,
        "committed_cost": committed_cost_state,
        "realized_cost": realized_cost_state,
        "forecast_cost": forecast_cost_state,
        "cost_variance": combine(budget_state, forecast_cost_state),
        "expected_benefit": expected_benefit_state,
        "committed_benefit": committed_benefit_state,
        "realized_benefit": realized_benefit_state,
        "evidence_linked_realized_benefit": coverage(
            included_benefits,
            lambda item: item.get("realized_amount") is not None
            and bool(item.get("evidence_node_id")),
        ),
        "reviewed_evidence_realized_benefit": coverage(
            included_benefits,
            lambda item: item.get("realized_amount") is not None
            and bool(item.get("evidence_node_id"))
            and item.get("evidence_status") in {"accepted", "verified"},
        ),
        "verified_realized_benefit": coverage(
            included_benefits,
            lambda item: item.get("realized_amount") is not None
            and bool(item.get("evidence_node_id"))
            and item.get("evidence_status") == "verified",
        ),
        "realized_financial": realized_financial_state,
        "forecast_benefit": forecast_benefit_state,
        "forecast_financial": forecast_financial_state,
        "remaining_cost": combine(
            forecast_cost_state,
            committed_cost_state,
            realized_cost_state,
        ),
        "break_even_required_benefit": scenario_states["scenario_base_costs"],
        "break_even_gap": scenario_states["scenario_base_financial"],
        "forecast_profit": forecast_financial_state,
        "forecast_margin": forecast_financial_state,
        "funding": funding_state,
        "funding_gap": combine(funding_state, forecast_cost_state),
        "post_mission_costs": post_mission_state,
        "schedule": known if schedule_known else unknown,
        "outcome": known if outcome_known else unknown,
        "planned_outcome": planned_outcome_state,
        "actual_outcome": actual_outcome_state,
        "cost_per_planned_outcome": combine(forecast_cost_state, planned_outcome_state),
        "cost_per_actual_outcome": combine(realized_cost_state, actual_outcome_state),
        "cost_per_outcome": chosen_cost_per_outcome_state,
        **scenario_states,
    }


def _resource_summary(items: list[dict], horizon: int) -> dict:
    human = [item for item in items if item.get("kind") == "human_resource"]
    materials = [item for item in items if item.get("kind") == "material_resource"]
    equipment = [item for item in items if item.get("kind") == "equipment_resource"]
    funding = [item for item in items if item.get("kind") == "financial_resource"]
    planned_hours = 0.0
    actual_hours = 0.0
    for item in human:
        unit = str(item.get("unit") or "").strip().casefold()
        if unit in {"hora", "horas", "h", "hour", "hours"}:
            planned_hours += float(item.get("planned_quantity") or 0) * max(
                1, len(_occurrence_months(item, horizon))
            )
            actual_hours += float(item.get("actual_quantity") or 0)
    return {
        "human_roles": len(human),
        "planned_human_hours": round(planned_hours, 2),
        "actual_human_hours": round(actual_hours, 2),
        "material_lines": len(materials),
        "equipment_lines": len(equipment),
        "funding_lines": len(funding),
        "blocked_lines": sum(
            1 for item in human + materials + equipment + funding
            if item.get("operational_status") == "blocked"
        ),
        "labels": [
            item["label"]
            for item in human + materials + equipment + funding
            if str(item.get("label") or "").strip()
        ][:12],
    }


def _quality(case: dict, items: list[dict]) -> dict:
    monetary = [
        item
        for item in items
        if item.get("include_in_totals") and item.get("financial_treatment") in {"cost", "benefit"}
    ]
    if not monetary:
        return {
            "state": "not_evaluable",
            "monetary_line_count": 0,
            "evidence_linked_count": 0,
            "source_declared_count": 0,
            "scenario_explicit_count": 0,
            "actual_value_count": 0,
            "evidence_coverage_pct": None,
            "source_coverage_pct": None,
            "confidence_score": None,
            "overall_score": None,
            "overall_label": "not_evaluable",
            "case_reviewed": case.get("status") == "reviewed",
        }
    evidence_count = sum(1 for item in monetary if item.get("evidence_node_id"))
    source_count = sum(1 for item in monetary if item.get("source_label") or item.get("evidence_node_id"))
    confidence_score = (
        sum(CONFIDENCE_POINTS.get(str(item.get("confidence")), 0) for item in monetary) / len(monetary)
        if monetary
        else 0
    )
    evidence_coverage = evidence_count / len(monetary) * 100 if monetary else 0
    source_coverage = source_count / len(monetary) * 100 if monetary else 0
    scenario_explicit = sum(
        1
        for item in monetary
        if item.get("conservative_amount") is not None and item.get("favorable_amount") is not None
    )
    actuals = sum(1 for item in monetary if item.get("realized_amount") is not None)
    overall = round(
        confidence_score * 0.45
        + evidence_coverage * 0.25
        + source_coverage * 0.20
        + (scenario_explicit / len(monetary) * 100 if monetary else 0) * 0.10,
        1,
    )
    label = "high" if overall >= 80 else "moderate" if overall >= 50 else "low"
    return {
        "state": "assessed",
        "monetary_line_count": len(monetary),
        "evidence_linked_count": evidence_count,
        "source_declared_count": source_count,
        "scenario_explicit_count": scenario_explicit,
        "actual_value_count": actuals,
        "evidence_coverage_pct": round(evidence_coverage, 1),
        "source_coverage_pct": round(source_coverage, 1),
        "confidence_score": round(confidence_score, 1),
        "overall_score": overall,
        "overall_label": label,
        "case_reviewed": case.get("status") == "reviewed",
    }


def _readiness(case: dict, items: list[dict]) -> dict:
    cost_items = [item for item in items if item.get("include_in_totals") and item.get("financial_treatment") == "cost"]
    benefit_items = [item for item in items if item.get("include_in_totals") and item.get("financial_treatment") == "benefit"]
    non_monetary = [item for item in items if item.get("kind") == "non_monetary_benefit"]
    resources = [item for item in items if item.get("kind") in RESOURCE_KINDS]
    monetary = cost_items + benefit_items
    checks = [
        {
            "key": "economic_context",
            "label": "Âmbito económico e decisão definidos",
            "passed": bool(str(case.get("decision_context") or "").strip()),
            "blocking": True,
        },
        {
            "key": "baseline_counterfactual",
            "label": "Situação de partida e custo de não agir explícitos",
            "passed": bool(str(case.get("baseline") or "").strip() and str(case.get("counterfactual") or "").strip()),
            "blocking": True,
        },
        {
            "key": "costs_defined",
            "label": "Custo do ciclo de vida estruturado",
            "passed": bool(cost_items),
            "blocking": True,
        },
        {
            "key": "value_defined",
            "label": "Benefício ou unidade de resultado estruturada",
            "passed": bool(benefit_items or non_monetary or case.get("planned_outcome_quantity") is not None),
            "blocking": True,
        },
        {
            "key": "resources_defined",
            "label": "Pessoas, financiamento ou materiais identificados",
            "passed": bool(resources),
            "blocking": True,
        },
        {
            "key": "sources_declared",
            "label": "Origem declarada para cada valor monetário",
            "passed": bool(monetary) and all(item.get("source_label") or item.get("evidence_node_id") for item in monetary),
            "blocking": True,
        },
        {
            "key": "scenarios_explicit",
            "label": "Cenários conservador e favorável explicitados",
            "passed": bool(monetary) and all(
                item.get("conservative_amount") is not None and item.get("favorable_amount") is not None
                for item in monetary
            ),
            "blocking": False,
        },
        {
            "key": "evidence_linked",
            "label": "Valores monetários ligados a evidência da missão",
            "passed": bool(monetary) and all(item.get("evidence_node_id") for item in monetary),
            "blocking": False,
        },
    ]
    blocking = [check["key"] for check in checks if check["blocking"] and not check["passed"]]
    completed = sum(1 for check in checks if check["passed"])
    return {
        "ready_for_review": not blocking,
        "reviewed": case.get("status") == "reviewed",
        "completed_checks": completed,
        "total_checks": len(checks),
        "progress_percent": round(completed / len(checks) * 100),
        "blocking_keys": blocking,
        "checks": checks,
    }


def _warnings(case: dict, items: list[dict], metrics: dict, quality: dict, readiness: dict) -> list[dict]:
    warnings: list[dict] = []
    if not case.get("id"):
        return [{
            "code": "case_not_started",
            "severity": "info",
            "message": "Configure o horizonte e a lógica de valor antes de registar custos e recursos.",
        }]
    if not any(item.get("financial_treatment") == "cost" and item.get("include_in_totals") for item in items):
        warnings.append({"code": "no_cost", "severity": "high", "message": "Não existe qualquer custo incluído no cálculo."})
    has_cost = float(metrics.get("forecast_cost_at_completion") or 0) > 0
    if not any(item.get("financial_treatment") == "benefit" and item.get("include_in_totals") for item in items):
        roi_note = (
            "O ROI financeiro reflete apenas os custos monetários registados; "
            "benefícios públicos ou não monetizados permanecem fora desse indicador."
            if has_cost
            else "O ROI financeiro ainda não é calculável porque também não existe um custo positivo incluído."
        )
        warnings.append({
            "code": "no_monetary_benefit",
            "severity": "medium",
            "message": f"Não existe benefício monetário. {roi_note}",
        })
    if not any(item.get("kind") in RESOURCE_KINDS for item in items):
        warnings.append({"code": "no_resources", "severity": "high", "message": "Ainda não foram identificados recursos humanos, financeiros ou materiais."})
    if quality["monetary_line_count"] and quality["source_coverage_pct"] < 100:
        warnings.append({"code": "source_gap", "severity": "high", "message": "Há valores monetários sem origem declarada; os indicadores não devem ser usados como prova."})
    if quality["monetary_line_count"] and quality["evidence_coverage_pct"] < 100:
        warnings.append({"code": "evidence_gap", "severity": "medium", "message": "Nem todos os valores estão ligados a evidência documental da missão."})
    if quality["scenario_explicit_count"] < quality["monetary_line_count"] and quality["monetary_line_count"]:
        warnings.append({"code": "scenario_fallback", "severity": "medium", "message": "Algumas linhas reutilizam o valor base nos cenários conservador ou favorável."})
    planned_hours_declared = any(
        item.get("kind") == "human_resource"
        and str(item.get("unit") or "").strip().casefold()
        in {"hora", "horas", "h", "hour", "hours"}
        and item.get("planned_quantity") is not None
        for item in items
    )
    if not planned_hours_declared and any(item.get("kind") == "human_resource" for item in items):
        warnings.append({"code": "hours_missing", "severity": "medium", "message": "Existem recursos humanos, mas o esforço planeado não está registado em horas."})
    blocked = [
        item for item in items
        if item.get("kind") in RESOURCE_KINDS and item.get("operational_status") == "blocked"
    ]
    if blocked:
        warnings.append({
            "code": "blocked_resources",
            "severity": "high",
            "message": f"{len(blocked)} recurso(s) estão bloqueados e podem alterar custo, prazo ou benefício.",
        })
    outside_horizon = [item for item in items if int(item.get("start_month") or 0) >= int(case.get("horizon_months") or 0)]
    if outside_horizon:
        warnings.append({"code": "outside_horizon", "severity": "high", "message": f"{len(outside_horizon)} linha(s) começam fora do horizonte e não entram nos cálculos."})
    if case.get("status") == "reviewed" and readiness["blocking_keys"]:
        warnings.append({"code": "review_invalidated", "severity": "high", "message": "A revisão guardada já não satisfaz os requisitos mínimos atuais."})
    if metrics["forecast_roi_pct"] is None:
        warnings.append({"code": "roi_not_calculable", "severity": "info", "message": "ROI não calculável: falta um custo monetário positivo incluído no cálculo."})
    return warnings


def _display_number(value: float | int | None, digits: int = 0) -> str:
    if value is None:
        return "não calculável"
    rendered = f"{float(value):,.{digits}f}"
    return rendered.replace(",", " ").replace(".", ",")


def _display_money(value: float | int | None, currency: str) -> str:
    if value is None:
        return "não calculável"
    amount = _display_number(value, 0)
    return f"{amount} €" if currency == "EUR" else f"{amount} {currency}"


def _executive_conclusion(
    case: dict,
    metrics: dict,
    metric_states: dict[str, str],
) -> str:
    if not case.get("id"):
        return "O business case vivo ainda não foi iniciado nesta missão."
    currency = str(metrics.get("currency") or case.get("currency") or "EUR")
    statements: list[str] = []

    def state_sentence(sentence: str, *keys: str) -> str:
        partial = any(
            metric_states.get(key) == "partial_observed_or_estimated"
            for key in keys
        )
        if not partial:
            return sentence
        return "Com dados parciais, " + sentence[:1].lower() + sentence[1:]

    hours = float(metrics.get("actual_human_hours") or 0)
    realized_cost = float(metrics.get("realized_cost") or 0)
    actual_hours_known = metric_states["actual_human_hours"] != "unknown_not_zero"
    realized_cost_known = metric_states["realized_cost"] != "unknown_not_zero"
    if hours > 0 and actual_hours_known and realized_cost_known:
        statements.append(
            state_sentence(
                "A missão registou "
                f"{_display_number(hours, 1)} horas de trabalho e "
                f"{_display_money(realized_cost, currency)} de custo realizado.",
                "actual_human_hours",
                "realized_cost",
            )
        )
    elif hours > 0 and actual_hours_known:
        statements.append(
            state_sentence(
                f"A missão registou {_display_number(hours, 1)} horas de trabalho; "
                "o custo monetário continua por determinar.",
                "actual_human_hours",
            )
        )
    elif realized_cost > 0:
        statements.append(
            state_sentence(
                f"A missão registou {_display_money(realized_cost, currency)} de custo realizado.",
                "realized_cost",
            )
        )
    forecast_cost = metrics.get("forecast_cost_at_completion")
    variance_pct = metrics.get("cost_variance_pct")
    if (
        forecast_cost is not None
        and metric_states["forecast_cost"] != "unknown_not_zero"
    ):
        if variance_pct is None or abs(float(variance_pct)) < 0.005:
            variance = "em linha com o orçamento base"
        elif float(variance_pct) < 0:
            variance = f"{_display_number(abs(float(variance_pct)), 1)}% abaixo do orçamento base"
        else:
            variance = f"{_display_number(float(variance_pct), 1)}% acima do orçamento base"
        statements.append(
            state_sentence(
                f"O custo previsto à conclusão é {_display_money(forecast_cost, currency)}, {variance}.",
                "forecast_cost",
                "cost_variance",
            )
        )
    evidence_linked = float(metrics.get("evidence_linked_realized_benefit") or 0)
    reviewed_evidence = float(metrics.get("reviewed_evidence_realized_benefit") or 0)
    verified = float(metrics.get("verified_realized_benefit") or 0)
    realized = float(metrics.get("realized_benefit") or 0)
    if verified > 0 and metric_states["verified_realized_benefit"] != "unknown_not_zero":
        statements.append(
            state_sentence(
                f"O benefício realizado com evidência verificada é {_display_money(verified, currency)}.",
                "verified_realized_benefit",
            )
        )
    elif (
        reviewed_evidence > 0
        and metric_states["reviewed_evidence_realized_benefit"]
        != "unknown_not_zero"
    ):
        statements.append(
            state_sentence(
                f"O benefício realizado com evidência revista é {_display_money(reviewed_evidence, currency)}.",
                "reviewed_evidence_realized_benefit",
            )
        )
    elif (
        evidence_linked > 0
        and metric_states["evidence_linked_realized_benefit"]
        != "unknown_not_zero"
    ):
        statements.append(
            state_sentence(
                f"Foram registados {_display_money(evidence_linked, currency)} de benefício realizado com fonte ligada, ainda por rever.",
                "evidence_linked_realized_benefit",
            )
        )
    elif realized > 0 and metric_states["realized_benefit"] != "unknown_not_zero":
        statements.append(
            state_sentence(
                f"Foram registados {_display_money(realized, currency)} de benefício realizado, ainda sem evidência ligada.",
                "realized_benefit",
            )
        )
    projected_net = metrics.get("forecast_net_benefit")
    roi = metrics.get("forecast_roi_pct")
    payback = metrics.get("forecast_payback_months")
    if (
        projected_net is not None
        and metric_states["forecast_financial"] != "unknown_not_zero"
    ):
        return_part = f"O benefício líquido projetado é {_display_money(projected_net, currency)}"
        if roi is not None:
            return_part += f", com ROI de {_display_number(roi, 1)}%"
        if payback is not None:
            return_part += f" e recuperação no mês {_display_number(payback, 0)}"
        elif roi is not None and float(roi) <= 0:
            return_part += " e sem recuperação dentro do horizonte analisado"
        statements.append(state_sentence(return_part + ".", "forecast_financial"))
    annual_burden = float(metrics.get("annual_post_mission_burden") or 0)
    if annual_burden > 0 and metric_states["post_mission_costs"] != "unknown_not_zero":
        statements.append(
            state_sentence(
                f"Após a missão, permanece um encargo anual de {_display_money(annual_burden, currency)}.",
                "post_mission_costs",
            )
        )
    return " ".join(statements) or "O modelo existe, mas ainda não contém valores suficientes para uma conclusão económica."


def _canonical_json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _record_revision(
    db: Session,
    *,
    case_id: str,
    organization_id: str,
    mission_id: str,
    event_type: str,
    user_id: str,
) -> None:
    current = db.execute(
        text("SELECT revision FROM pilot_business_cases WHERE id=:id AND organization_id=:org"),
        {"id": case_id, "org": organization_id},
    ).mappings().one()
    revision = int(current["revision"] or 0) + 1
    db.execute(
        text("""
            UPDATE pilot_business_cases
            SET revision=:revision, updated_at=CURRENT_TIMESTAMP
            WHERE id=:id AND organization_id=:org
        """),
        {"revision": revision, "id": case_id, "org": organization_id},
    )
    row = db.execute(text("SELECT * FROM pilot_business_cases WHERE id=:id"), {"id": case_id}).mappings().one()
    items = [_item_dict(item) for item in _active_item_rows(db, case_id)]
    case_snapshot = _case_dict(row)
    case_snapshot.pop("content_hash", None)
    snapshot = {
        "schema": "sris.pilot.live-business-case.v1",
        "case": case_snapshot,
        "items": sorted(items, key=lambda item: item["id"]),
    }
    raw = _canonical_json(snapshot)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    db.execute(
        text("UPDATE pilot_business_cases SET content_hash=:digest WHERE id=:id"),
        {"digest": digest, "id": case_id},
    )
    db.execute(
        text("""
            INSERT INTO pilot_business_case_events
                (id, business_case_id, organization_id, mission_id, revision,
                 event_type, snapshot_json, content_hash, created_by_user_id)
            VALUES
                (:id, :case_id, :org, :mission, :revision,
                 :event_type, :snapshot, :digest, :user)
        """),
        {
            "id": str(uuid4()),
            "case_id": case_id,
            "org": organization_id,
            "mission": mission_id,
            "revision": revision,
            "event_type": event_type,
            "snapshot": raw,
            "digest": digest,
            "user": user_id,
        },
    )


def _history(db: Session, case_id: str) -> list[dict]:
    rows = db.execute(
        text("""
            SELECT revision, event_type, content_hash, created_at
            FROM pilot_business_case_events
            WHERE business_case_id=:case_id
            ORDER BY revision DESC LIMIT 50
        """),
        {"case_id": case_id},
    ).mappings().all()
    return [
        {
            "revision": int(row["revision"]),
            "event_type": row["event_type"],
            "content_hash": row["content_hash"],
            "created_at": as_iso(row["created_at"]),
        }
        for row in rows
    ]


def _integrity_verified(db: Session, case: dict) -> bool:
    if not case.get("id") or not case.get("content_hash"):
        return False
    row = db.execute(
        text("""
            SELECT snapshot_json, content_hash FROM pilot_business_case_events
            WHERE business_case_id=:case_id AND revision=:revision
        """),
        {"case_id": case["id"], "revision": case["revision"]},
    ).mappings().first()
    if row is None:
        return False
    computed = hashlib.sha256(str(row["snapshot_json"]).encode("utf-8")).hexdigest()
    return computed == row["content_hash"] == case["content_hash"]


def _evidence_options(db: Session, *, organization_id: str, mission_id: str) -> list[dict]:
    rows = db.execute(
        text("""
            SELECT node.id, node.label, node.status, node.source_kind, node.source_sha256,
                   attachment.original_filename AS document_title
            FROM pilot_evidence_graph_nodes node
            LEFT JOIN mi_mission_attachments attachment
              ON attachment.id=node.attachment_id
             AND attachment.organization_id=node.organization_id
             AND attachment.mission_id=node.mission_id
            WHERE node.organization_id=:org AND node.mission_id=:mission
              AND node.node_type='evidence'
              AND node.status NOT IN ('rejected', 'superseded')
            ORDER BY node.created_at ASC, node.label ASC
        """),
        {"org": organization_id, "mission": mission_id},
    ).mappings().all()
    return [
        {
            "id": row["id"],
            "label": row["document_title"] or row["label"],
            "status": row["status"],
            "source_kind": row["source_kind"],
            "source_sha256": row["source_sha256"],
        }
        for row in rows
    ]


def _alternative_options(db: Session, *, organization_id: str, mission_id: str) -> list[dict]:
    rows = db.execute(
        text("""
            SELECT id, label, body, status
            FROM pilot_evidence_graph_nodes
            WHERE organization_id=:org AND mission_id=:mission
              AND node_type='alternative'
              AND status NOT IN ('rejected', 'superseded')
            ORDER BY created_at ASC, label ASC, id ASC
        """),
        {"org": organization_id, "mission": mission_id},
    ).mappings().all()
    return [
        {
            "id": row["id"],
            "label": row["label"],
            "body": row["body"] or "",
            "status": row["status"],
        }
        for row in rows
    ]


def _alternative_profile(case: dict, alternative: dict, items: list[dict]) -> dict:
    horizon = int(case.get("horizon_months") or 60)
    metrics = _live_metrics(case, items)
    quality = _quality(case, items)
    cost_items = [
        item for item in items
        if item.get("include_in_totals") and item.get("financial_treatment") == "cost"
    ]
    value_items = [
        item for item in items
        if item.get("include_in_totals")
        and (
            item.get("financial_treatment") == "benefit"
            or item.get("kind") == "non_monetary_benefit"
        )
    ]
    resource_items = [item for item in items if item.get("kind") in RESOURCE_KINDS]
    metric_states = _metric_states(case, items)
    cost_modelled = metric_states["scenario_base_costs"] == "observed_or_estimated"
    value_modelled = (
        metric_states["scenario_base_benefits"] == "observed_or_estimated"
        or any(item.get("kind") == "non_monetary_benefit" for item in value_items)
    )
    base = metrics["scenarios"]["base"]
    return {
        "alternative_node_id": alternative["id"],
        "alternative_label": alternative["label"],
        "alternative_body": alternative.get("body") or "",
        "line_count": len(items),
        "metrics_state": "observed_or_estimated" if items else "unknown_not_zero",
        "metric_states": metric_states,
        "complete": bool(cost_modelled and value_modelled and resource_items),
        "gaps": [
            label
            for present, label in (
                (cost_modelled, "custo total base"),
                (value_modelled, "benefício ou resultado base"),
                (resource_items, "recursos necessários"),
            )
            if not present
        ],
        "total_cost": base["total_cost"],
        "probable_gross_benefit": base["gross_benefit"],
        "probable_net_benefit": base["net_benefit"],
        "roi_pct": base["roi_pct"],
        "payback_months": base["payback_months"],
        "npv": base["npv"],
        "annual_post_mission_burden": metrics["annual_post_mission_burden"],
        "cost_per_planned_outcome": metrics["cost_per_planned_outcome"],
        "resources": _resource_summary(items, horizon),
        "quality": quality,
    }


def _alternative_comparison(
    case: dict,
    all_items: list[dict],
    alternatives: list[dict],
) -> dict:
    profiles = [
        _alternative_profile(
            case,
            alternative,
            [
                item
                for item in all_items
                if item.get("alternative_node_id") == alternative["id"]
            ],
        )
        for alternative in alternatives
    ]
    return {
        "configured": bool(case.get("id")),
        "business_case_revision": int(case.get("revision") or 0),
        "business_case_content_hash": case.get("content_hash") or "",
        "currency": case.get("currency") or "EUR",
        "horizon_months": int(case.get("horizon_months") or 60),
        "profile_count": sum(1 for profile in profiles if profile["line_count"] > 0),
        "complete_profile_count": sum(1 for profile in profiles if profile["complete"]),
        "profiles": profiles,
        "calculation_policy": (
            "Alternative-specific lines are excluded from mission totals and compared "
            "independently under the same horizon and discount rate."
        ),
    }


def alternative_economic_comparison(
    db: Session,
    *,
    organization_id: str,
    mission_id: str,
) -> dict:
    """Expose live alternative economics without coupling them to a matrix score."""

    _ensure_schema(db)
    alternatives = _alternative_options(
        db,
        organization_id=organization_id,
        mission_id=mission_id,
    )
    row = _case_row(db, organization_id=organization_id, mission_id=mission_id)
    if row is None:
        empty_case = {
            "id": None,
            "revision": 0,
            "content_hash": "",
            "currency": "EUR",
            "horizon_months": 60,
            "discount_rate_pct": 8.0,
            "case_kind": "hybrid",
            "planned_outcome_quantity": None,
            "actual_outcome_quantity": None,
        }
        return _alternative_comparison(empty_case, [], alternatives)
    case = _case_dict(row)
    all_items = [_item_dict(item) for item in _active_item_rows(db, case["id"])]
    return _alternative_comparison(case, all_items, alternatives)


def _governed_prefill(db: Session, mission) -> dict:
    """Offer traceable proposals; never persist inferred economics automatically."""

    document = json.loads(mission.document_json or "{}")
    metadata = document.get("metadata") or {}
    protocol = None
    measurements: dict[str, dict] = {}
    inspector = inspect(db.get_bind())
    if inspector.has_table("pilot_validation_protocols"):
        protocol = db.execute(
            text(
                """
                SELECT * FROM pilot_validation_protocols
                WHERE organization_id=:org AND mission_id=:mission
                """
            ),
            {"org": mission.organization_id, "mission": mission.id},
        ).mappings().first()
    if inspector.has_table("pilot_validation_measurements"):
        rows = db.execute(
            text(
                """
                SELECT * FROM pilot_validation_measurements
                WHERE organization_id=:org AND mission_id=:mission
                """
            ),
            {"org": mission.organization_id, "mission": mission.id},
        ).mappings().all()
        measurements = {str(row["phase"]): dict(row) for row in rows}
    result = measurements.get("result") or {}
    return {
        "human_confirmation_required": True,
        "canonical_mutation": "none_until_user_saves",
        "message": (
            "Propostas derivadas do contexto e da medição já governados. "
            "Confirme, corrija ou rejeite cada campo antes de guardar."
        ),
        "fields": {
            "decision_context": {
                "value": document.get("central_question") or "",
                "source_ids": [f"MISSION:{mission.id}"],
            },
            "baseline": {
                "value": (protocol or {}).get("problem_statement") or document.get("context") or "",
                "source_ids": [
                    f"PROTOCOL:{protocol['id']}" if protocol else f"MISSION:{mission.id}"
                ],
            },
            "planned_start_date": {
                "value": as_iso((protocol or {}).get("intervention_start_date")),
                "source_ids": [f"PROTOCOL:{protocol['id']}"] if protocol else [],
            },
            "planned_end_date": {
                "value": as_iso((protocol or {}).get("intervention_end_date")),
                "source_ids": [f"PROTOCOL:{protocol['id']}"] if protocol else [],
            },
            "outcome_name": {
                "value": (protocol or {}).get("indicator_name") or "",
                "source_ids": [f"PROTOCOL:{protocol['id']}"] if protocol else [],
            },
            "outcome_unit": {
                "value": (protocol or {}).get("indicator_unit") or "",
                "source_ids": [f"PROTOCOL:{protocol['id']}"] if protocol else [],
            },
            "planned_outcome_quantity": {
                "value": _number((protocol or {}).get("target_value")),
                "source_ids": [f"PROTOCOL:{protocol['id']}"] if protocol else [],
            },
            "actual_outcome_quantity": {
                "value": _number(result.get("normalized_value")),
                "source_ids": [f"MEASURE:{result['id']}"] if result else [],
            },
        },
        "unresolved_fields": ["counterfactual", "discount_rate_pct", "economic_line_items"],
        "mission_horizon": metadata.get("horizon") or "",
    }


def _response(db: Session, *, organization_id: str, mission) -> dict:
    row = _case_row(db, organization_id=organization_id, mission_id=mission.id)
    case = _case_dict(row) if row is not None else _default_case(mission)
    items = [_item_dict(item) for item in _active_item_rows(db, case["id"])] if case.get("id") else []
    mission_items = [item for item in items if not item.get("alternative_node_id")]
    alternatives = _alternative_options(
        db,
        organization_id=organization_id,
        mission_id=mission.id,
    )
    metrics = _live_metrics(case, mission_items)
    metric_states = _metric_states(case, mission_items)
    quality = _quality(case, mission_items)
    readiness = _readiness(case, mission_items)
    return {
        "schema": "sris.pilot.live-business-case.v1",
        "calculation_policy": "deterministic_server_side_no_ai",
        "case": case,
        "items": items,
        "mission_item_count": len(mission_items),
        "alternative_item_count": len(items) - len(mission_items),
        "metrics": metrics,
        "quality": quality,
        "readiness": readiness,
        "warnings": _warnings(case, mission_items, metrics, quality, readiness),
        "executive_conclusion": _executive_conclusion(case, metrics, metric_states),
        "evidence": _evidence_options(db, organization_id=organization_id, mission_id=mission.id),
        "alternatives": alternatives,
        "alternative_comparison": _alternative_comparison(case, items, alternatives),
        "history": _history(db, case["id"]) if case.get("id") else [],
        "integrity_verified": _integrity_verified(db, case),
        # Creating the foundation does not assert that every economic value is
        # zero.  Until at least one mission-level line exists, the calculated
        # zeroes are placeholders and must be rendered as unknown.
        "metrics_state": metric_states["any_lines"],
        "metric_states": metric_states,
        "governed_prefill": _governed_prefill(db, mission),
        "definitions": {
            "case_kinds": CASE_KIND_DEFINITIONS,
            "item_kinds": ITEM_KIND_DEFINITIONS,
            "financial_treatments": {
                "cost": "Inclui no custo total",
                "benefit": "Inclui no benefício monetário",
                "none": "Quantifica sem monetizar",
            },
            "phases": {
                "planning": "Planeamento",
                "execution": "Execução",
                "post_mission": "Após a missão",
            },
            "recurrence": {
                "one_off": "Única",
                "monthly": "Mensal",
                "quarterly": "Trimestral",
                "annual": "Anual",
            },
            "operational_status": {
                "planned": "Planeado",
                "committed": "Comprometido",
                "active": "Em curso",
                "completed": "Concluído",
                "blocked": "Bloqueado",
            },
            "confidence": {
                "low": "Baixa",
                "moderate": "Moderada",
                "high": "Alta",
            },
            "metric_states": {
                "unknown_not_zero": "Por determinar — ausência de dados não significa zero",
                "partial_observed_or_estimated": "Parcial — apenas parte das linhas tem valor declarado",
                "observed_or_estimated": "Apurado — existe estimativa ou observação para todas as linhas aplicáveis",
            },
        },
    }


def _check_revision(case_row, expected_revision: int | None) -> None:
    if expected_revision is not None and int(case_row["revision"]) != expected_revision:
        raise HTTPException(
            status_code=409,
            detail="O business case foi atualizado por outra ação. Recarregue a missão antes de guardar.",
        )


def _reset_review(db: Session, case_id: str, user_id: str) -> None:
    db.execute(
        text("""
            UPDATE pilot_business_cases
            SET status='active', review_rationale='', reviewed_by_user_id=NULL,
                reviewed_at=NULL, updated_by_user_id=:user, updated_at=CURRENT_TIMESTAMP
            WHERE id=:id
        """),
        {"id": case_id, "user": user_id},
    )


def _validate_evidence(
    db: Session,
    *,
    evidence_node_id: str | None,
    organization_id: str,
    mission_id: str,
) -> None:
    if not evidence_node_id:
        return
    found = db.execute(
        text("""
            SELECT id FROM pilot_evidence_graph_nodes
            WHERE id=:id AND organization_id=:org AND mission_id=:mission
              AND node_type='evidence' AND status NOT IN ('rejected', 'superseded')
        """),
        {"id": evidence_node_id, "org": organization_id, "mission": mission_id},
    ).scalar_one_or_none()
    if found is None:
        raise HTTPException(status_code=422, detail="Escolha uma evidência ativa da própria missão.")


def _validate_alternative(
    db: Session,
    *,
    alternative_node_id: str | None,
    organization_id: str,
    mission_id: str,
) -> None:
    if not alternative_node_id:
        return
    found = db.execute(
        text("""
            SELECT id FROM pilot_evidence_graph_nodes
            WHERE id=:id AND organization_id=:org AND mission_id=:mission
              AND node_type='alternative' AND status NOT IN ('rejected', 'superseded')
        """),
        {"id": alternative_node_id, "org": organization_id, "mission": mission_id},
    ).scalar_one_or_none()
    if found is None:
        raise HTTPException(status_code=422, detail="Escolha uma alternativa ativa da própria missão.")


def business_case_readiness(
    db: Session,
    *,
    organization_id: str,
    mission_id: str,
    mission_code: str,
) -> dict:
    _ensure_schema(db)
    row = _case_row(db, organization_id=organization_id, mission_id=mission_id)
    if row is None:
        return {"required": False, "checks": [], "passed": False, "count": 0}
    case = _case_dict(row)
    items = [
        _item_dict(item)
        for item in _active_item_rows(db, case["id"])
        if not item["alternative_node_id"]
    ]
    readiness = _readiness(case, items)
    checks = [
        {
            "key": "business_case_structured",
            "label": "Business case económico e recursos estruturados",
            "passed": readiness["ready_for_review"],
            "count": len(items),
        },
        {
            "key": "business_case_reviewed",
            "label": "Business case revisto após a última alteração",
            "passed": case["status"] == "reviewed",
            "count": 1 if case["status"] == "reviewed" else 0,
        },
    ]
    return {
        "required": True,
        "checks": checks,
        "passed": all(check["passed"] for check in checks),
        "count": sum(1 for check in checks if check["passed"]),
        "mission_code": mission_code,
    }


@router.get("/missions/{mission_code}")
def get_business_case(
    mission_code: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _require_membership(db, user.id)
    _ensure_graph_schema(db)
    _ensure_schema(db)
    mission = _mission(db, membership.organization_id, mission_code)
    response = _response(db, organization_id=membership.organization_id, mission=mission)
    db.commit()
    return response


@router.put("/missions/{mission_code}")
def upsert_business_case(
    mission_code: str,
    payload: BusinessCaseUpsert,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _require_membership(db, user.id)
    _require_writer(membership)
    _ensure_graph_schema(db)
    _ensure_schema(db)
    mission = _mission(db, membership.organization_id, mission_code)
    _require_mission_mutable(mission)
    current = _case_row(db, organization_id=membership.organization_id, mission_id=mission.id)
    values = _sql_values(payload.model_dump(exclude={"expected_revision"}))
    if current is None:
        if payload.expected_revision not in (None, 0):
            raise HTTPException(status_code=409, detail="O business case ainda não existe nesta missão.")
        case_id = str(uuid4())
        db.execute(
            text("""
                INSERT INTO pilot_business_cases
                    (id, organization_id, mission_id, mission_code, case_kind, currency,
                     horizon_months, discount_rate_pct, decision_context, baseline,
                     counterfactual, planned_start_date, planned_end_date, forecast_end_date,
                     actual_start_date, actual_end_date, outcome_name, outcome_unit,
                     planned_outcome_quantity, actual_outcome_quantity, notes, status,
                     created_by_user_id, updated_by_user_id)
                VALUES
                    (:id, :org, :mission, :code, :case_kind, :currency,
                     :horizon_months, :discount_rate_pct, :decision_context, :baseline,
                     :counterfactual, :planned_start_date, :planned_end_date, :forecast_end_date,
                     :actual_start_date, :actual_end_date, :outcome_name, :outcome_unit,
                     :planned_outcome_quantity, :actual_outcome_quantity, :notes, 'active',
                     :user, :user)
            """),
            {
                "id": case_id,
                "org": membership.organization_id,
                "mission": mission.id,
                "code": mission.code,
                "user": user.id,
                **values,
            },
        )
        event_type = "case_created"
    else:
        _check_revision(current, payload.expected_revision)
        case_id = current["id"]
        allowed = tuple(values)
        assignments = ", ".join(f"{key}=:{key}" for key in allowed)
        db.execute(
            text(f"""
                UPDATE pilot_business_cases
                SET {assignments}, status='active', review_rationale='',
                    reviewed_by_user_id=NULL, reviewed_at=NULL,
                    updated_by_user_id=:user, updated_at=CURRENT_TIMESTAMP
                WHERE id=:id AND organization_id=:org
            """),
            {"id": case_id, "org": membership.organization_id, "user": user.id, **values},
        )
        event_type = "case_updated"
    _record_revision(
        db,
        case_id=case_id,
        organization_id=membership.organization_id,
        mission_id=mission.id,
        event_type=event_type,
        user_id=user.id,
    )
    record_audit(
        db,
        action=f"pilot.business_case.{event_type}",
        resource_type="business_case",
        resource_id=case_id,
        organization_id=membership.organization_id,
        user_id=user.id,
        payload={"mission_code": mission.code, "case_kind": payload.case_kind},
    )
    db.commit()
    return _response(db, organization_id=membership.organization_id, mission=mission)


@router.post("/missions/{mission_code}/items", status_code=201)
def create_line_item(
    mission_code: str,
    payload: LineItemCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _require_membership(db, user.id)
    _require_writer(membership)
    _ensure_graph_schema(db)
    _ensure_schema(db)
    mission = _mission(db, membership.organization_id, mission_code)
    _require_mission_mutable(mission)
    case = _case_row(db, organization_id=membership.organization_id, mission_id=mission.id)
    if case is None:
        raise HTTPException(status_code=409, detail="Guarde primeiro a configuração do business case.")
    _check_revision(case, payload.expected_revision)
    _validate_evidence(
        db,
        evidence_node_id=payload.evidence_node_id,
        organization_id=membership.organization_id,
        mission_id=mission.id,
    )
    _validate_alternative(
        db,
        alternative_node_id=payload.alternative_node_id,
        organization_id=membership.organization_id,
        mission_id=mission.id,
    )
    item_id = str(uuid4())
    values = _sql_values(payload.model_dump(exclude={"expected_revision"}))
    db.execute(
        text("""
            INSERT INTO pilot_business_case_items
                (id, business_case_id, organization_id, mission_id, mission_code,
                 kind, financial_treatment, category, label, description, phase, unit,
                 amount_basis, planned_quantity, actual_quantity, conservative_amount, base_amount,
                 favorable_amount, committed_amount, realized_amount, forecast_amount,
                 start_month, end_month, recurrence, source_label, evidence_node_id,
                 alternative_node_id, responsible, operational_status, blocker,
                 assumption, confidence, include_in_totals,
                 created_by_user_id, updated_by_user_id)
            VALUES
                (:id, :case_id, :org, :mission, :code,
                 :kind, :financial_treatment, :category, :label, :description, :phase, :unit,
                 :amount_basis, :planned_quantity, :actual_quantity, :conservative_amount, :base_amount,
                 :favorable_amount, :committed_amount, :realized_amount, :forecast_amount,
                 :start_month, :end_month, :recurrence, :source_label, :evidence_node_id,
                 :alternative_node_id, :responsible, :operational_status, :blocker,
                 :assumption, :confidence, :include_in_totals,
                 :user, :user)
        """),
        {
            "id": item_id,
            "case_id": case["id"],
            "org": membership.organization_id,
            "mission": mission.id,
            "code": mission.code,
            "user": user.id,
            **values,
        },
    )
    _reset_review(db, case["id"], user.id)
    _record_revision(
        db,
        case_id=case["id"],
        organization_id=membership.organization_id,
        mission_id=mission.id,
        event_type="item_created",
        user_id=user.id,
    )
    record_audit(
        db,
        action="pilot.business_case.item_created",
        resource_type="business_case_item",
        resource_id=item_id,
        organization_id=membership.organization_id,
        user_id=user.id,
        payload={"mission_code": mission.code, "kind": payload.kind, "label": payload.label},
    )
    db.commit()
    response = _response(db, organization_id=membership.organization_id, mission=mission)
    response["item_change"] = {"created": True, "item_id": item_id}
    return response


def _line_candidate(current: dict, values: dict) -> LineItemCreate:
    source = {
        key: current.get(key)
        for key in (
            "kind",
            "financial_treatment",
            "category",
            "label",
            "description",
            "phase",
            "unit",
            "amount_basis",
            "planned_quantity",
            "actual_quantity",
            "conservative_amount",
            "base_amount",
            "favorable_amount",
            "committed_amount",
            "realized_amount",
            "forecast_amount",
            "start_month",
            "end_month",
            "recurrence",
            "source_label",
            "evidence_node_id",
            "alternative_node_id",
            "responsible",
            "operational_status",
            "blocker",
            "assumption",
            "confidence",
            "include_in_totals",
        )
    }
    source.update(values)
    return LineItemCreate.model_validate(source)


@router.patch("/missions/{mission_code}/items/{item_id}")
def update_line_item(
    mission_code: str,
    item_id: str,
    payload: LineItemUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _require_membership(db, user.id)
    _require_writer(membership)
    _ensure_graph_schema(db)
    _ensure_schema(db)
    mission = _mission(db, membership.organization_id, mission_code)
    _require_mission_mutable(mission)
    case = _case_row(db, organization_id=membership.organization_id, mission_id=mission.id)
    if case is None:
        raise HTTPException(status_code=404, detail="O business case ainda não existe.")
    _check_revision(case, payload.expected_revision)
    row = db.execute(
        text("""
            SELECT * FROM pilot_business_case_items
            WHERE id=:id AND business_case_id=:case_id AND organization_id=:org
              AND mission_id=:mission AND retired_at IS NULL
        """),
        {"id": item_id, "case_id": case["id"], "org": membership.organization_id, "mission": mission.id},
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="A linha económica indicada não existe nesta missão.")
    updates = payload.model_dump(exclude_unset=True, exclude={"expected_revision"})
    if not updates:
        return _response(db, organization_id=membership.organization_id, mission=mission)
    current = _item_dict(row)
    candidate = _line_candidate(current, updates)
    normalized = _sql_values(candidate.model_dump(exclude={"expected_revision"}))
    _validate_evidence(
        db,
        evidence_node_id=candidate.evidence_node_id,
        organization_id=membership.organization_id,
        mission_id=mission.id,
    )
    _validate_alternative(
        db,
        alternative_node_id=candidate.alternative_node_id,
        organization_id=membership.organization_id,
        mission_id=mission.id,
    )
    assignments = ", ".join(f"{key}=:{key}" for key in normalized)
    db.execute(
        text(f"""
            UPDATE pilot_business_case_items
            SET {assignments}, updated_by_user_id=:user, updated_at=CURRENT_TIMESTAMP
            WHERE id=:id AND business_case_id=:case_id
        """),
        {"id": item_id, "case_id": case["id"], "user": user.id, **normalized},
    )
    _reset_review(db, case["id"], user.id)
    _record_revision(
        db,
        case_id=case["id"],
        organization_id=membership.organization_id,
        mission_id=mission.id,
        event_type="item_updated",
        user_id=user.id,
    )
    record_audit(
        db,
        action="pilot.business_case.item_updated",
        resource_type="business_case_item",
        resource_id=item_id,
        organization_id=membership.organization_id,
        user_id=user.id,
        payload={"mission_code": mission.code, "changed_fields": sorted(updates)},
    )
    db.commit()
    response = _response(db, organization_id=membership.organization_id, mission=mission)
    response["item_change"] = {"updated": True, "item_id": item_id}
    return response


@router.delete("/missions/{mission_code}/items/{item_id}")
def retire_line_item(
    mission_code: str,
    item_id: str,
    expected_revision: int = Query(ge=1),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _require_membership(db, user.id)
    _require_writer(membership)
    _ensure_graph_schema(db)
    _ensure_schema(db)
    mission = _mission(db, membership.organization_id, mission_code)
    _require_mission_mutable(mission)
    case = _case_row(db, organization_id=membership.organization_id, mission_id=mission.id)
    if case is None:
        raise HTTPException(status_code=404, detail="O business case ainda não existe.")
    _check_revision(case, expected_revision)
    row = db.execute(
        text("""
            SELECT id, label, kind FROM pilot_business_case_items
            WHERE id=:id AND business_case_id=:case_id AND organization_id=:org
              AND mission_id=:mission AND retired_at IS NULL
        """),
        {"id": item_id, "case_id": case["id"], "org": membership.organization_id, "mission": mission.id},
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="A linha económica indicada não existe nesta missão.")
    db.execute(
        text("""
            UPDATE pilot_business_case_items
            SET retired_at=CURRENT_TIMESTAMP, updated_by_user_id=:user,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=:id
        """),
        {"id": item_id, "user": user.id},
    )
    _reset_review(db, case["id"], user.id)
    _record_revision(
        db,
        case_id=case["id"],
        organization_id=membership.organization_id,
        mission_id=mission.id,
        event_type="item_retired",
        user_id=user.id,
    )
    record_audit(
        db,
        action="pilot.business_case.item_retired",
        resource_type="business_case_item",
        resource_id=item_id,
        organization_id=membership.organization_id,
        user_id=user.id,
        payload={"mission_code": mission.code, "label": row["label"], "kind": row["kind"]},
    )
    db.commit()
    response = _response(db, organization_id=membership.organization_id, mission=mission)
    response["item_change"] = {"retired": True, "item_id": item_id}
    return response


@router.post("/missions/{mission_code}/review")
def review_business_case(
    mission_code: str,
    payload: BusinessCaseReview,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _require_membership(db, user.id)
    _require_reviewer(membership)
    _ensure_graph_schema(db)
    _ensure_schema(db)
    mission = _mission(db, membership.organization_id, mission_code)
    _require_mission_mutable(mission)
    case_row = _case_row(db, organization_id=membership.organization_id, mission_id=mission.id)
    if case_row is None:
        raise HTTPException(status_code=404, detail="O business case ainda não existe.")
    _check_revision(case_row, payload.expected_revision)
    case = _case_dict(case_row)
    items = [_item_dict(item) for item in _active_item_rows(db, case["id"])]
    readiness = _readiness(case, items)
    if readiness["blocking_keys"]:
        labels = [
            check["label"]
            for check in readiness["checks"]
            if check["key"] in readiness["blocking_keys"]
        ]
        raise HTTPException(
            status_code=409,
            detail="Complete antes da revisão: " + "; ".join(labels) + ".",
        )
    db.execute(
        text("""
            UPDATE pilot_business_cases
            SET status='reviewed', review_rationale=:rationale,
                reviewed_by_user_id=:user, reviewed_at=:reviewed_at,
                updated_by_user_id=:user, updated_at=CURRENT_TIMESTAMP
            WHERE id=:id AND organization_id=:org
        """),
        {
            "id": case["id"],
            "org": membership.organization_id,
            "rationale": payload.rationale.strip(),
            "user": user.id,
            "reviewed_at": _utcnow(),
        },
    )
    _record_revision(
        db,
        case_id=case["id"],
        organization_id=membership.organization_id,
        mission_id=mission.id,
        event_type="case_reviewed",
        user_id=user.id,
    )
    record_audit(
        db,
        action="pilot.business_case.reviewed",
        resource_type="business_case",
        resource_id=case["id"],
        organization_id=membership.organization_id,
        user_id=user.id,
        payload={"mission_code": mission.code, "rationale": payload.rationale.strip()},
    )
    from app.pilot_mission_state import record_module_review

    record_module_review(
        db,
        organization_id=membership.organization_id,
        mission_id=mission.id,
        mission_code=mission.code,
        module_key="economics",
        module_revision=None,
        module_content_hash=None,
        rationale=payload.rationale.strip(),
        user_id=user.id,
    )
    db.commit()
    return _response(db, organization_id=membership.organization_id, mission=mission)
