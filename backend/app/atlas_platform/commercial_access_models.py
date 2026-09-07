from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from .database import Base


ACCESS_REQUEST_PENDING = "pending"
ACCESS_REQUEST_APPROVED = "approved"
ACCESS_REQUEST_REJECTED = "rejected"
ACCESS_REQUEST_CANCELLED = "cancelled"

ENTITLEMENT_ACTIVE = "active"
ENTITLEMENT_GRANDFATHERED = "grandfathered"
ENTITLEMENT_EXPIRED = "expired"
ENTITLEMENT_SUSPENDED = "suspended"
ENTITLEMENT_CANCELLED = "cancelled"

COMMERCIAL_PLANS = {"pilot", "professional", "organization"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def managed_runtime() -> bool:
    return any(
        os.getenv(name)
        for name in (
            "RAILWAY_ENVIRONMENT_ID",
            "RAILWAY_PROJECT_ID",
            "RAILWAY_SERVICE_ID",
        )
    )


def commercial_gate_enforced() -> bool:
    return _flag(
        "SRIS_COMMERCIAL_ENTITLEMENT_ENFORCEMENT",
        managed_runtime(),
    )


class AccessRequest(Base):
    """Pre-auth request for a governed SRIS workspace access decision."""

    __tablename__ = "sris_access_requests"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    email: Mapped[str] = mapped_column(String(320), index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    organization_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(
        String(32), default=ACCESS_REQUEST_PENDING, index=True
    )
    plan_code: Mapped[str] = mapped_column(String(64), default="pilot")
    entitlement_days: Mapped[int] = mapped_column(Integer, default=90)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    invitation_id: Mapped[str | None] = mapped_column(
        ForeignKey("user_invitations.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CommercialEntitlement(Base):
    """Commercial right to use one SRIS workspace, separate from identity."""

    __tablename__ = "sris_commercial_entitlements"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    plan_code: Mapped[str] = mapped_column(String(64), default="pilot")
    status: Mapped[str] = mapped_column(
        String(32), default=ENTITLEMENT_ACTIVE, index=True
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    commercial_reference: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    approved_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    renewal_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


def effective_entitlement_status(
    entitlement: CommercialEntitlement,
    *,
    now: datetime | None = None,
) -> str:
    if entitlement.status == ENTITLEMENT_GRANDFATHERED:
        return ENTITLEMENT_ACTIVE
    if entitlement.status != ENTITLEMENT_ACTIVE:
        return entitlement.status
    current = now or utcnow()
    expires_at = _as_utc(entitlement.expires_at)
    if expires_at is not None and expires_at <= current:
        return ENTITLEMENT_EXPIRED
    return ENTITLEMENT_ACTIVE


def entitlement_payload(
    entitlement: CommercialEntitlement | None,
    *,
    enforcement: bool | None = None,
) -> dict:
    if entitlement is None:
        return {
            "present": False,
            "status": "missing",
            "lifecycle_status": "missing",
            "plan_code": None,
            "starts_at": None,
            "expires_at": None,
            "renewal_count": 0,
            "enforced": commercial_gate_enforced()
            if enforcement is None
            else enforcement,
        }
    effective = effective_entitlement_status(entitlement)
    return {
        "present": True,
        "status": effective,
        "lifecycle_status": entitlement.status,
        "plan_code": entitlement.plan_code,
        "starts_at": _as_utc(entitlement.starts_at).isoformat()
        if entitlement.starts_at
        else None,
        "expires_at": _as_utc(entitlement.expires_at).isoformat()
        if entitlement.expires_at
        else None,
        "commercial_reference": entitlement.commercial_reference,
        "renewal_count": int(entitlement.renewal_count or 0),
        "enforced": commercial_gate_enforced()
        if enforcement is None
        else enforcement,
    }


def get_entitlement(
    db: Session,
    organization_id: str,
) -> CommercialEntitlement | None:
    return (
        db.query(CommercialEntitlement)
        .filter(CommercialEntitlement.organization_id == organization_id)
        .one_or_none()
    )


def enforce_active_entitlement(
    db: Session,
    organization_id: str,
) -> CommercialEntitlement | None:
    """Fail closed in managed environments; preserve data and identity on expiry."""

    if not commercial_gate_enforced():
        return get_entitlement(db, organization_id)

    entitlement = get_entitlement(db, organization_id)
    if entitlement is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "commercial_entitlement_missing",
                "message": "Este workspace não tem um entitlement comercial ativo.",
            },
        )

    effective = effective_entitlement_status(entitlement)
    if effective != ENTITLEMENT_ACTIVE:
        message = {
            ENTITLEMENT_EXPIRED: "O entitlement comercial deste workspace expirou. Renove o acesso para continuar.",
            ENTITLEMENT_SUSPENDED: "O entitlement comercial deste workspace está suspenso.",
            ENTITLEMENT_CANCELLED: "O entitlement comercial deste workspace foi cancelado.",
        }.get(effective, "O entitlement comercial deste workspace não está ativo.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": f"commercial_entitlement_{effective}",
                "message": message,
                "plan_code": entitlement.plan_code,
                "expires_at": _as_utc(entitlement.expires_at).isoformat()
                if entitlement.expires_at
                else None,
            },
        )
    return entitlement
