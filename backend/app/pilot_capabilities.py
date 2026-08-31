from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.atlas_platform.auth_delivery import auth_email_delivery_ready
from app.atlas_platform.database import get_db
from app.atlas_platform.models import PasswordResetToken, UserInvitation

router = APIRouter(prefix="/api/pilot", tags=["pilot-capabilities"])

PILOT_BUILD = "20260831-interactive-provenance-demo-v36"

CANONICAL_MISSION_CHAIN = [
    "context",
    "observation",
    "evidence",
    "hypothesis",
    "alternatives",
    "decision",
    "action",
    "measurement",
    "outcome",
    "learning",
    "memory",
]

TRANSVERSAL_EPISTEMIC_CONDITIONS = [
    "assumptions",
    "constraints",
    "gaps",
    "uncertainty",
    "provenance",
    "confidence",
]


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _transactional_email_status(db: Session) -> str:
    """Report proven delivery, rather than configuration presence.

    A provider key and sender address only prove that a transport was
    configured.  The Pilot must not describe email as operational until the
    most recent real delivery attempt succeeded.
    """

    if not auth_email_delivery_ready():
        return "not-configured"

    try:
        latest_reset = (
            db.query(PasswordResetToken)
            .filter(PasswordResetToken.delivery_status.in_(("sent", "failed")))
            .order_by(PasswordResetToken.requested_at.desc())
            .first()
        )
        latest_invitation = (
            db.query(UserInvitation)
            .filter(
                UserInvitation.delivery_attempts > 0,
                UserInvitation.delivery_status.in_(("sent", "failed")),
            )
            .order_by(UserInvitation.created_at.desc())
            .first()
        )
    except SQLAlchemyError:
        # Capability discovery must fail closed during first boot or before
        # migrations: configured credentials are never treated as proof.
        return "configured-unverified"
    attempts = []
    if latest_reset is not None:
        attempts.append(
            (_as_utc(latest_reset.requested_at), latest_reset.delivery_status)
        )
    if latest_invitation is not None:
        attempts.append(
            (_as_utc(latest_invitation.created_at), latest_invitation.delivery_status)
        )
    if not attempts:
        return "configured-unverified"
    return "operational" if max(attempts)[1] == "sent" else "delivery-failed"


def _password_reset_delivery(email_configured: bool) -> str:
    if email_configured:
        return "email"
    if _flag("SRIS_PILOT_SHOW_RESET_LINK", False):
        return "pilot-link"
    return "configuration-required"


@router.get("/capabilities")
def pilot_capabilities(db: Session = Depends(get_db)) -> dict:
    """Public, non-sensitive description of the Pilot surface.

    Provider names, model aliases, balances and organization state are
    intentionally excluded. They are implementation details, not product
    capabilities.
    """

    email_configured = auth_email_delivery_ready()
    email_status = _transactional_email_status(db)
    email_operational = email_status == "operational"
    return {
        "build": PILOT_BUILD,
        "public_signup": _flag("SRIS_PUBLIC_SIGNUP_ENABLED", True),
        "password_reset": True,
        "password_reset_delivery": _password_reset_delivery(email_configured),
        "transactional_email_status": email_status,
        "transactional_email_configured": email_configured,
        "transactional_email_ready": email_operational,
        # A previous provider failure must not create a permanent deadlock: once
        # the transport is configured, an administrator needs to be able to
        # retry a failed invitation and thereby establish fresh delivery proof.
        "invitations_enabled": email_configured,
        "workspace_profile_endpoint": "/api/pilot/profile",
        "mission_intelligence": True,
        "document_intelligence": True,
        "persistent_dialogue": True,
        "sub_missions": True,
        "evidence_graph": True,
        "provenance": True,
        "organizational_memory": True,
        "measurable_validation": True,
        "alternative_comparison_matrix": True,
        "live_business_case": True,
        "scenario_financial_analysis": True,
        "human_financial_material_resource_tracking": True,
        "post_mission_lifecycle_costs": True,
        "governed_mission_state": True,
        "cross_module_dependencies": True,
        "cross_module_conflict_detection": True,
        "human_governed_ai_context": True,
        "ai_end_to_end_mission_drafts": True,
        "granular_human_proposal_validation": True,
        "canonical_mission_chain": CANONICAL_MISSION_CHAIN,
        "transversal_epistemic_conditions": TRANSVERSAL_EPISTEMIC_CONDITIONS,
        "tourism_advance_profile": True,
        "baseline_and_result_comparison": True,
        "hybrid_retrieval": True,
        "assistance_configured": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "assistance_enabled": _flag("SRIS_AI_ENABLED", False),
    }


@router.get("/build")
def pilot_build() -> dict[str, str]:
    return {"build": PILOT_BUILD, "product": "SRIS Mission Intelligence Pilot V1"}
