from __future__ import annotations

import os

from fastapi import APIRouter
from app.atlas_platform.auth_delivery import auth_email_delivery_ready

router = APIRouter(prefix="/api/pilot", tags=["pilot-capabilities"])

PILOT_BUILD = "20260826-learning-title-language-v20"


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _password_reset_delivery() -> str:
    base = os.getenv("SRIS_PUBLIC_BASE_URL", "").strip()
    sender = os.getenv("SRIS_EMAIL_FROM", "").strip()
    provider = bool(os.getenv("RESEND_API_KEY", "").strip() or os.getenv("BREVO_API_KEY", "").strip())
    if base and sender and provider:
        return "email"
    if _flag("SRIS_PILOT_SHOW_RESET_LINK", False):
        return "pilot-link"
    return "configuration-required"


@router.get("/capabilities")
def pilot_capabilities() -> dict:
    """Public, non-sensitive description of the Pilot surface.

    Provider names, model aliases, balances and organization state are
    intentionally excluded. They are implementation details, not product
    capabilities.
    """

    return {
        "build": PILOT_BUILD,
        "public_signup": _flag("SRIS_PUBLIC_SIGNUP_ENABLED", True),
        "password_reset": True,
        "password_reset_delivery": _password_reset_delivery(),
        "transactional_email_ready": auth_email_delivery_ready(),
        "invitations_enabled": auth_email_delivery_ready(),
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
        "tourism_advance_profile": True,
        "baseline_and_result_comparison": True,
        "hybrid_retrieval": True,
        "assistance_configured": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "assistance_enabled": _flag("SRIS_AI_ENABLED", False),
        "billing_mode": "disabled",
    }


@router.get("/build")
def pilot_build() -> dict[str, str]:
    return {"build": PILOT_BUILD, "product": "SRIS Mission Intelligence Pilot V1"}
