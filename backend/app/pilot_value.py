from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.atlas_platform.audit import record_audit
from app.atlas_platform.auth import require_org_role
from app.atlas_platform.database import Base, get_db
from app.atlas_platform.models import Membership, Role, User
from app.pilot_platform import Pilot, _pilot_or_404, _pilot_view


router = APIRouter(
    prefix="/api/organizations/{organization_id}/pilots",
    tags=["Pilot Value, Collaboration & Reports"],
)

READ_ROLES = (
    Role.OWNER.value,
    Role.ADMIN.value,
    Role.REVIEWER.value,
    Role.CONTRIBUTOR.value,
    Role.OBSERVER.value,
)
WRITE_ROLES = (
    Role.OWNER.value,
    Role.ADMIN.value,
    Role.REVIEWER.value,
    Role.CONTRIBUTOR.value,
)
MANAGE_ROLES = (Role.OWNER.value, Role.ADMIN.value)

VALUE_DIMENSIONS = (
    "economic",
    "operational",
    "resource",
    "experience",
    "governance",
    "learning",
)
VALUE_STATUSES = ("expected", "estimated", "observed", "realized")
PILOT_ROLES = (
    "sponsor",
    "pilot_owner",
    "mission_owner",
    "data_owner",
    "operator",
    "reviewer",
    "program_mentor",
    "observer",
)
REPORT_TYPES = (
    "pilot_brief",
    "data_readiness",
    "decision_dossier",
    "progress",
    "outcome",
    "scale_recommendation",
    "full",
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PilotValueItem(Base):
    __tablename__ = "sris_pilot_value_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    pilot_id: Mapped[str] = mapped_column(
        ForeignKey("sris_pilots.id", ondelete="CASCADE"), index=True
    )
    dimension: Mapped[str] = mapped_column(String(40), index=True)
    label: Mapped[str] = mapped_column(String(300))
    value_status: Mapped[str] = mapped_column(String(30), default="expected", index=True)
    numeric_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    unit: Mapped[str] = mapped_column(String(80), default="")
    recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    period: Mapped[str] = mapped_column(String(160), default="")
    baseline_reference: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(Text, default="")
    calculation: Mapped[str] = mapped_column(Text, default="")
    attribution: Mapped[str] = mapped_column(Text, default="")
    limitations: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[str] = mapped_column(String(20), default="not_evaluable")
    owner: Mapped[str] = mapped_column(String(240), default="")
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class PilotCollaborator(Base):
    __tablename__ = "sris_pilot_collaborators"
    __table_args__ = (
        UniqueConstraint(
            "pilot_id",
            "role_key",
            "email",
            name="uq_sris_pilot_collaborator_role_email",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    pilot_id: Mapped[str] = mapped_column(
        ForeignKey("sris_pilots.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    role_key: Mapped[str] = mapped_column(String(40), index=True)
    display_name: Mapped[str] = mapped_column(String(240))
    email: Mapped[str] = mapped_column(String(320), default="")
    organization_name: Mapped[str] = mapped_column(String(300), default="")
    can_edit: Mapped[bool] = mapped_column(Boolean, default=False)
    can_review: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ValueItemCreate(StrictModel):
    dimension: Literal[
        "economic",
        "operational",
        "resource",
        "experience",
        "governance",
        "learning",
    ]
    label: str = Field(min_length=2, max_length=300)
    value_status: Literal["expected", "estimated", "observed", "realized"] = "expected"
    numeric_value: Decimal | None = None
    unit: str = Field(default="", max_length=80)
    recurring: bool = False
    period: str = Field(default="", max_length=160)
    baseline_reference: str = Field(default="", max_length=10000)
    source: str = Field(default="", max_length=10000)
    calculation: str = Field(default="", max_length=10000)
    attribution: str = Field(default="", max_length=10000)
    limitations: str = Field(default="", max_length=10000)
    confidence: Literal["high", "moderate", "low", "not_evaluable"] = "not_evaluable"
    owner: str = Field(default="", max_length=240)

    @model_validator(mode="after")
    def realized_value_requires_proof(self) -> "ValueItemCreate":
        if self.value_status == "realized":
            missing = [
                label
                for label, value in (
                    ("período", self.period),
                    ("baseline", self.baseline_reference),
                    ("fonte", self.source),
                    ("cálculo", self.calculation),
                    ("atribuição", self.attribution),
                )
                if not value.strip()
            ]
            if missing:
                raise ValueError(
                    "Um benefício realizado exige " + ", ".join(missing) + "."
                )
        return self


class ValueItemUpdate(ValueItemCreate):
    pass


class CollaboratorCreate(StrictModel):
    role_key: Literal[
        "sponsor",
        "pilot_owner",
        "mission_owner",
        "data_owner",
        "operator",
        "reviewer",
        "program_mentor",
        "observer",
    ]
    display_name: str = Field(min_length=2, max_length=240)
    email: str = Field(default="", max_length=320)
    organization_name: str = Field(default="", max_length=300)
    user_id: str | None = Field(default=None, min_length=36, max_length=36)
    can_edit: bool = False
    can_review: bool = False
    active: bool = True
    notes: str = Field(default="", max_length=10000)


class CollaboratorUpdate(CollaboratorCreate):
    pass


def _value_view(row: PilotValueItem) -> dict[str, Any]:
    return {
        "id": row.id,
        "dimension": row.dimension,
        "label": row.label,
        "value_status": row.value_status,
        "numeric_value": float(row.numeric_value) if row.numeric_value is not None else None,
        "unit": row.unit,
        "recurring": row.recurring,
        "period": row.period,
        "baseline_reference": row.baseline_reference,
        "source": row.source,
        "calculation": row.calculation,
        "attribution": row.attribution,
        "limitations": row.limitations,
        "confidence": row.confidence,
        "owner": row.owner,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _collaborator_view(row: PilotCollaborator) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "role_key": row.role_key,
        "display_name": row.display_name,
        "email": row.email,
        "organization_name": row.organization_name,
        "can_edit": row.can_edit,
        "can_review": row.can_review,
        "active": row.active,
        "notes": row.notes,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _value_payload(db: Session, pilot: Pilot) -> dict[str, Any]:
    rows = (
        db.query(PilotValueItem)
        .filter(PilotValueItem.pilot_id == pilot.id)
        .order_by(
            PilotValueItem.dimension.asc(),
            PilotValueItem.value_status.asc(),
            PilotValueItem.created_at.asc(),
        )
        .all()
    )
    items = [_value_view(row) for row in rows]
    dimensions: dict[str, dict[str, Any]] = {}
    for dimension in VALUE_DIMENSIONS:
        dimension_rows = [item for item in items if item["dimension"] == dimension]
        dimensions[dimension] = {
            "count": len(dimension_rows),
            "expected": sum(item["value_status"] == "expected" for item in dimension_rows),
            "estimated": sum(item["value_status"] == "estimated" for item in dimension_rows),
            "observed": sum(item["value_status"] == "observed" for item in dimension_rows),
            "realized": sum(item["value_status"] == "realized" for item in dimension_rows),
        }

    monetary: dict[str, float] = {status_name: 0.0 for status_name in VALUE_STATUSES}
    for item in items:
        if item["unit"].upper() == "EUR" and item["numeric_value"] is not None:
            monetary[item["value_status"]] += float(item["numeric_value"])
    monetary = {key: round(value, 2) for key, value in monetary.items()}

    evidence_complete = sum(
        bool(
            item["period"]
            and item["baseline_reference"]
            and item["source"]
            and item["calculation"]
            and item["attribution"]
        )
        for item in items
        if item["value_status"] in {"observed", "realized"}
    )
    observed_or_realized = sum(
        item["value_status"] in {"observed", "realized"} for item in items
    )
    return {
        "pilot_id": pilot.id,
        "items": items,
        "dimensions": dimensions,
        "monetary_eur": monetary,
        "evidence_completeness_pct": round(
            evidence_complete / max(1, observed_or_realized) * 100
        ),
        "integrity_rule": (
            "Expected, estimated, observed and realized value remain separate. "
            "A realized value requires period, baseline, source, calculation and attribution."
        ),
    }


def _collaborators_payload(db: Session, pilot: Pilot) -> dict[str, Any]:
    rows = (
        db.query(PilotCollaborator)
        .filter(PilotCollaborator.pilot_id == pilot.id)
        .order_by(PilotCollaborator.role_key.asc(), PilotCollaborator.created_at.asc())
        .all()
    )
    return {
        "pilot_id": pilot.id,
        "roles": list(PILOT_ROLES),
        "collaborators": [_collaborator_view(row) for row in rows],
    }


def _assert_user_in_organization(
    db: Session,
    *,
    organization_id: str,
    user_id: str | None,
) -> None:
    if not user_id:
        return
    exists = (
        db.query(Membership.id)
        .filter(
            Membership.organization_id == organization_id,
            Membership.user_id == user_id,
        )
        .first()
    )
    if not exists:
        raise HTTPException(
            status_code=422,
            detail="O utilizador indicado não pertence a esta organização.",
        )


@router.get("/{pilot_id}/value-case")
def get_value_case(
    organization_id: str,
    pilot_id: str,
    _: Membership = Depends(require_org_role(*READ_ROLES)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return _value_payload(db, _pilot_or_404(db, organization_id, pilot_id))


@router.post("/{pilot_id}/value-case/items", status_code=status.HTTP_201_CREATED)
def create_value_item(
    organization_id: str,
    pilot_id: str,
    payload: ValueItemCreate,
    membership: Membership = Depends(require_org_role(*WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    pilot = _pilot_or_404(db, organization_id, pilot_id)
    row = PilotValueItem(
        pilot_id=pilot.id,
        created_by_user_id=membership.user_id,
        **payload.model_dump(),
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        action="pilot.value_item_created",
        resource_type="pilot_value_item",
        resource_id=row.id,
        organization_id=organization_id,
        user_id=membership.user_id,
        payload={
            "pilot_id": pilot.id,
            "dimension": row.dimension,
            "value_status": row.value_status,
        },
    )
    db.commit()
    db.refresh(row)
    return _value_view(row)


@router.put("/{pilot_id}/value-case/items/{item_id}")
def update_value_item(
    organization_id: str,
    pilot_id: str,
    item_id: str,
    payload: ValueItemUpdate,
    membership: Membership = Depends(require_org_role(*WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    pilot = _pilot_or_404(db, organization_id, pilot_id)
    row = (
        db.query(PilotValueItem)
        .filter(PilotValueItem.id == item_id, PilotValueItem.pilot_id == pilot.id)
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Elemento de valor não encontrado")
    for field_name, value in payload.model_dump().items():
        setattr(row, field_name, value)
    record_audit(
        db,
        action="pilot.value_item_updated",
        resource_type="pilot_value_item",
        resource_id=row.id,
        organization_id=organization_id,
        user_id=membership.user_id,
        payload={
            "pilot_id": pilot.id,
            "dimension": row.dimension,
            "value_status": row.value_status,
        },
    )
    db.commit()
    db.refresh(row)
    return _value_view(row)


@router.delete(
    "/{pilot_id}/value-case/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_value_item(
    organization_id: str,
    pilot_id: str,
    item_id: str,
    membership: Membership = Depends(require_org_role(*WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Response:
    pilot = _pilot_or_404(db, organization_id, pilot_id)
    row = (
        db.query(PilotValueItem)
        .filter(PilotValueItem.id == item_id, PilotValueItem.pilot_id == pilot.id)
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Elemento de valor não encontrado")
    db.delete(row)
    record_audit(
        db,
        action="pilot.value_item_deleted",
        resource_type="pilot_value_item",
        resource_id=row.id,
        organization_id=organization_id,
        user_id=membership.user_id,
        payload={"pilot_id": pilot.id},
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{pilot_id}/collaborators")
def get_collaborators(
    organization_id: str,
    pilot_id: str,
    _: Membership = Depends(require_org_role(*READ_ROLES)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return _collaborators_payload(db, _pilot_or_404(db, organization_id, pilot_id))


@router.post("/{pilot_id}/collaborators", status_code=status.HTTP_201_CREATED)
def create_collaborator(
    organization_id: str,
    pilot_id: str,
    payload: CollaboratorCreate,
    membership: Membership = Depends(require_org_role(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    pilot = _pilot_or_404(db, organization_id, pilot_id)
    _assert_user_in_organization(
        db,
        organization_id=organization_id,
        user_id=payload.user_id,
    )
    email = payload.email.strip().lower()
    row = PilotCollaborator(
        pilot_id=pilot.id,
        email=email,
        created_by_user_id=membership.user_id,
        **payload.model_dump(exclude={"email"}),
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        action="pilot.collaborator_created",
        resource_type="pilot_collaborator",
        resource_id=row.id,
        organization_id=organization_id,
        user_id=membership.user_id,
        payload={
            "pilot_id": pilot.id,
            "role_key": row.role_key,
            "linked_user": bool(row.user_id),
        },
    )
    db.commit()
    db.refresh(row)
    return _collaborator_view(row)


@router.put("/{pilot_id}/collaborators/{collaborator_id}")
def update_collaborator(
    organization_id: str,
    pilot_id: str,
    collaborator_id: str,
    payload: CollaboratorUpdate,
    membership: Membership = Depends(require_org_role(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    pilot = _pilot_or_404(db, organization_id, pilot_id)
    row = (
        db.query(PilotCollaborator)
        .filter(
            PilotCollaborator.id == collaborator_id,
            PilotCollaborator.pilot_id == pilot.id,
        )
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Colaborador do piloto não encontrado")
    _assert_user_in_organization(
        db,
        organization_id=organization_id,
        user_id=payload.user_id,
    )
    values = payload.model_dump()
    values["email"] = values["email"].strip().lower()
    for field_name, value in values.items():
        setattr(row, field_name, value)
    record_audit(
        db,
        action="pilot.collaborator_updated",
        resource_type="pilot_collaborator",
        resource_id=row.id,
        organization_id=organization_id,
        user_id=membership.user_id,
        payload={"pilot_id": pilot.id, "role_key": row.role_key},
    )
    db.commit()
    db.refresh(row)
    return _collaborator_view(row)


@router.delete(
    "/{pilot_id}/collaborators/{collaborator_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_collaborator(
    organization_id: str,
    pilot_id: str,
    collaborator_id: str,
    membership: Membership = Depends(require_org_role(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
) -> Response:
    pilot = _pilot_or_404(db, organization_id, pilot_id)
    row = (
        db.query(PilotCollaborator)
        .filter(
            PilotCollaborator.id == collaborator_id,
            PilotCollaborator.pilot_id == pilot.id,
        )
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Colaborador do piloto não encontrado")
    db.delete(row)
    record_audit(
        db,
        action="pilot.collaborator_deleted",
        resource_type="pilot_collaborator",
        resource_id=row.id,
        organization_id=organization_id,
        user_id=membership.user_id,
        payload={"pilot_id": pilot.id, "role_key": row.role_key},
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _report_payload(
    db: Session,
    *,
    pilot: Pilot,
    report_type: str,
) -> dict[str, Any]:
    if report_type not in REPORT_TYPES:
        raise HTTPException(status_code=404, detail="Tipo de relatório desconhecido")
    pilot_payload = _pilot_view(db, pilot)
    value_case = _value_payload(db, pilot)
    collaborators = _collaborators_payload(db, pilot)

    common = {
        "schema": f"sris.{report_type}.v1",
        "report_type": report_type,
        "generated_at": utcnow(),
        "pilot": {
            key: pilot_payload[key]
            for key in (
                "id",
                "code",
                "title",
                "sector_profile",
                "template_key",
                "program_source",
                "partner_name",
                "context_name",
                "context_type",
                "location",
                "problem_statement",
                "decision_question",
                "objective",
                "scope",
                "exclusions",
                "start_date",
                "end_date",
                "lifecycle_state",
                "revision",
            )
        },
        "methodological_contract": pilot_payload["methodological_contract"],
    }
    sections = {
        "pilot_brief": {
            "charter": pilot_payload["charter"],
            "governance": collaborators,
            "readiness": pilot_payload["readiness"],
        },
        "data_readiness": {
            "assessment": pilot_payload["data_readiness"],
            "sources": pilot_payload["data_sources"],
            "metrics": pilot_payload["metrics"],
        },
        "decision_dossier": {
            "missions": pilot_payload["missions"],
            "metrics": pilot_payload["metrics"],
            "value_case": value_case,
            "integrity_note": (
                "The mission remains the source of truth for observations, evidence, "
                "hypotheses, alternatives, decisions, actions, outcomes and learning."
            ),
        },
        "progress": {
            "implementation": pilot_payload["implementation"],
            "work_items": pilot_payload["work_items"],
            "readiness": pilot_payload["readiness"],
        },
        "outcome": {
            "metrics": pilot_payload["metrics"],
            "value_case": value_case,
            "limitations_rule": (
                "No impact is attributed without baseline, period, source, "
                "calculation, attribution assessment and limitations."
            ),
        },
        "scale_recommendation": {
            "scale": pilot_payload["scale"],
            "value_case": value_case,
            "readiness": pilot_payload["readiness"],
        },
    }
    if report_type == "full":
        return {
            **common,
            "sections": sections,
            "governance": collaborators,
        }
    return {**common, "content": sections[report_type]}


@router.get("/{pilot_id}/reports")
def list_reports(
    organization_id: str,
    pilot_id: str,
    _: Membership = Depends(require_org_role(*READ_ROLES)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    pilot = _pilot_or_404(db, organization_id, pilot_id)
    return {
        "pilot_id": pilot.id,
        "reports": [
            {
                "type": report_type,
                "endpoint": (
                    f"/api/organizations/{organization_id}/pilots/"
                    f"{pilot.id}/reports/{report_type}"
                ),
            }
            for report_type in REPORT_TYPES
        ],
    }


@router.get("/{pilot_id}/reports/{report_type}")
def get_report(
    organization_id: str,
    pilot_id: str,
    report_type: str,
    _: Membership = Depends(require_org_role(*READ_ROLES)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return _report_payload(
        db,
        pilot=_pilot_or_404(db, organization_id, pilot_id),
        report_type=report_type,
    )
