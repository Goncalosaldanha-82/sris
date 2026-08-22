from __future__ import annotations

import os

from fastapi import APIRouter

router = APIRouter(prefix="/api/pilot", tags=["pilot-capabilities"])

PILOT_BUILD = "20260822-r15-product-reset"


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _model() -> str:
    return os.getenv("SRIS_OPENAI_MODEL", "gpt-5.6-terra").strip() or "gpt-5.6-terra"


@router.get("/capabilities")
def pilot_capabilities() -> dict:
    """Public, non-sensitive description of the Pilot surface.

    The entry page uses this endpoint before authentication. It must therefore
    expose only product availability flags and never provider credentials,
    organization identifiers or account state.
    """

    return {
        "build": PILOT_BUILD,
        "public_signup": _flag("SRIS_PUBLIC_SIGNUP_ENABLED", True),
        "workspace_profile_endpoint": "/api/pilot/profile",
        "mission_intelligence": True,
        "document_intelligence": True,
        "persistent_dialogue": True,
        "sub_missions": True,
        "evidence_graph": True,
        "provenance": True,
        "organizational_memory": True,
        "hybrid_retrieval": True,
        "ai_configured": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "ai_enabled": _flag("SRIS_AI_ENABLED", False),
        "ai_model": _model(),
    }


@router.get("/build")
def pilot_build() -> dict[str, str]:
    return {"build": PILOT_BUILD, "product": "SRIS Mission Intelligence Pilot V1"}
