from __future__ import annotations

import os
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.atlas_platform.auth_delivery import auth_email_delivery_ready
from app.atlas_platform.database import get_db
from app.pilot_platform import (
    PROFILE_CATALOG_VERSION,
    PROGRAM_SOURCES,
    SECTOR_PROFILES,
)

router = APIRouter(prefix="/api/pilot", tags=["pilot-capabilities"])

PILOT_BUILD = "20260902-workspace-continuity-v36"

USER_MOMENTS = [
    "context",
    "evidence",
    "decision",
    "measurement",
    "memory",
]

CANONICAL_RECORDS = [
    "observation",
    "evidence",
    "hypothesis",
    "alternative",
    "decision",
    "action",
    "outcome",
    "learning",
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


def _password_reset_delivery() -> str:
    if auth_email_delivery_ready():
        return "email"
    if _flag("SRIS_PILOT_SHOW_RESET_LINK", False):
        return "pilot-link"
    return "configuration-required"


@router.get("/capabilities")
def pilot_capabilities() -> dict:
    """Public, non-sensitive description of the active Pilot surface."""

    return {
        "build": PILOT_BUILD,
        "product": "SRIS Pilot & Mission Intelligence",
        "site_urls": [
            "https://www.sris.io/",
            "https://sris-mission-intelligence.up.railway.app/",
        ],
        "architecture": "universal_core_configurable_profiles",
        "public_signup": _flag("SRIS_PUBLIC_SIGNUP_ENABLED", True),
        "password_reset": True,
        "password_reset_delivery": _password_reset_delivery(),
        "transactional_email_ready": auth_email_delivery_ready(),
        "invitations_enabled": auth_email_delivery_ready(),
        "workspace_profile_endpoint": "/api/pilot/profile",
        "explicit_workspace_selection": True,
        "workspace_continuity_resolution": "requested_then_persistent_mission_activity",
        "pilot_portfolio": True,
        "pilot_charter": True,
        "pilot_data_readiness": True,
        "pilot_scorecard": True,
        "pilot_outcome_report": True,
        "pilot_scale_recommendation": True,
        "pilot_value_case": True,
        "pilot_collaboration": True,
        "pilot_collaboration_roles": True,
        "pilot_report_suite": True,
        "direct_pilot_to_mission_creation": True,
        "configurable_sector_profiles": list(SECTOR_PROFILES),
        "profile_catalog_version": PROFILE_CATALOG_VERSION,
        "profile_count": len(SECTOR_PROFILES),
        "program_sources": list(PROGRAM_SOURCES),
        "hospitality_templates": [
            "hospitality_resource_efficiency",
            "hospitality_operational_intelligence",
        ],
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
        "user_moments": USER_MOMENTS,
        "canonical_records": CANONICAL_RECORDS,
        "canonical_mission_chain": CANONICAL_RECORDS,
        "transversal_epistemic_conditions": TRANSVERSAL_EPISTEMIC_CONDITIONS,
        "tourism_advance_profile": True,
        "hospitality_open_innovation_profile": True,
        "baseline_and_result_comparison": True,
        "hybrid_retrieval": True,
        "assistance_configured": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "assistance_enabled": _flag("SRIS_AI_ENABLED", False),
    }


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _migration_heads() -> list[str]:
    configuration = Config(str(PROJECT_ROOT / "alembic.ini"))
    return sorted(ScriptDirectory.from_config(configuration).get_heads())


@router.get("/build")
def pilot_build() -> dict[str, str]:
    return {
        "build": PILOT_BUILD,
        "product": "SRIS Pilot & Mission Intelligence",
        "branch": os.getenv("RAILWAY_GIT_BRANCH", "local"),
        "commit_sha": os.getenv("RAILWAY_GIT_COMMIT_SHA", "local"),
    }


@router.get("/release-state")
def pilot_release_state(db: Session = Depends(get_db)) -> dict:
    database_revisions = list(
        db.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num"))
        .scalars()
        .all()
    )
    return {
        "build": PILOT_BUILD,
        "service": os.getenv("RAILWAY_SERVICE_NAME", "local"),
        "environment": os.getenv("RAILWAY_ENVIRONMENT_NAME", "local"),
        "branch": os.getenv("RAILWAY_GIT_BRANCH", "local"),
        "commit_sha": os.getenv("RAILWAY_GIT_COMMIT_SHA", "local"),
        "database_revisions": database_revisions,
        "migration_heads": _migration_heads(),
        "database_at_head": sorted(database_revisions) == _migration_heads(),
        "profile_catalog_version": PROFILE_CATALOG_VERSION,
        "profile_count": len(SECTOR_PROFILES),
        "profile_keys": list(SECTOR_PROFILES),
        "program_source_keys": list(PROGRAM_SOURCES),
    }
