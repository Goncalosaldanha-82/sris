from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.atlas_platform.auth import require_org_role
from app.atlas_platform.database import get_db
from app.atlas_platform.models import Membership, Role

from .ai import configured_model, is_ai_configured
from .catalog import demo_mission, load_demo_catalog
from .contracts import AIGovernancePolicyUpdate, AnalysisInput, ReviewRequest
from .engine import ENGINE_VERSION
from .governance import governance_view, update_policy, usage_event_view
from .models import AIUsageEvent, CanonicalMission, IntelligenceRun
from .service import analyze_demo, review_run, run_organizational_analysis, run_view

public_router = APIRouter(prefix="/api/mission-intelligence", tags=["Mission Intelligence"])
organization_router = APIRouter(
    prefix="/api/organizations/{organization_id}/mission-intelligence",
    tags=["Mission Intelligence"],
)


@public_router.get("/status")
def capability_status() -> dict:
    return {
        "foundation_version": "1.3",
        "mission_language": "MDL 1.3",
        "engine_version": ENGINE_VERSION,
        "deterministic_analysis": "available",
        "ai_provider": "openai",
        "ai_model": configured_model(),
        "ai_configured": is_ai_configured(),
        "ai_requires_authentication": True,
        "ai_governance_version": "1.0",
        "ai_organization_policy_required": True,
        "human_review_required": True,
    }


@public_router.get("/demo/missions")
def list_demo_missions() -> dict:
    return load_demo_catalog()


@public_router.get("/demo/missions/{mission_code}")
def get_demo_mission(mission_code: str) -> dict:
    mission = demo_mission(mission_code)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return mission


@public_router.post("/demo/missions/{mission_code}/analyze")
def analyze_public_demo(mission_code: str, payload: AnalysisInput) -> dict:
    try:
        return analyze_demo(mission_code, payload, allow_ai=False)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Mission not found") from exc


@organization_router.get("/missions")
def list_canonical_missions(
    organization_id: str,
    _: Membership = Depends(
        require_org_role(
            Role.OWNER.value,
            Role.ADMIN.value,
            Role.REVIEWER.value,
            Role.CONTRIBUTOR.value,
            Role.OBSERVER.value,
        )
    ),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = (
        db.query(CanonicalMission)
        .filter(CanonicalMission.organization_id == organization_id)
        .order_by(CanonicalMission.updated_at.desc())
        .all()
    )
    return [
        {
            "id": row.id,
            "code": row.code,
            "title": row.title,
            "schema_version": row.schema_version,
            "revision": row.revision,
            "content_hash": row.content_hash,
            "lifecycle_state": row.lifecycle_state,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]


@organization_router.post("/demo/{mission_code}/analyze")
def analyze_organizational_demo(
    organization_id: str,
    mission_code: str,
    payload: AnalysisInput,
    membership: Membership = Depends(
        require_org_role(
            Role.OWNER.value,
            Role.ADMIN.value,
            Role.REVIEWER.value,
            Role.CONTRIBUTOR.value,
        )
    ),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return run_organizational_analysis(
            db,
            organization_id=organization_id,
            user_id=membership.user_id,
            user_role=membership.role,
            mission_code=mission_code,
            payload=payload,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Mission not found") from exc


def _run_or_404(db: Session, organization_id: str, run_id: str) -> IntelligenceRun:
    run = (
        db.query(IntelligenceRun)
        .filter(
            IntelligenceRun.id == run_id,
            IntelligenceRun.organization_id == organization_id,
        )
        .one_or_none()
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Intelligence run not found")
    return run


@organization_router.get("/runs/{run_id}")
def get_intelligence_run(
    organization_id: str,
    run_id: str,
    _: Membership = Depends(
        require_org_role(
            Role.OWNER.value,
            Role.ADMIN.value,
            Role.REVIEWER.value,
            Role.CONTRIBUTOR.value,
            Role.OBSERVER.value,
        )
    ),
    db: Session = Depends(get_db),
) -> dict:
    return run_view(_run_or_404(db, organization_id, run_id))


@organization_router.post("/runs/{run_id}/review")
def review_intelligence_run(
    organization_id: str,
    run_id: str,
    payload: ReviewRequest,
    membership: Membership = Depends(
        require_org_role(Role.OWNER.value, Role.ADMIN.value, Role.REVIEWER.value)
    ),
    db: Session = Depends(get_db),
) -> dict:
    run = _run_or_404(db, organization_id, run_id)
    try:
        reviewed = review_run(
            db,
            run=run,
            user_id=membership.user_id,
            decision=payload.decision,
            comment=payload.comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return run_view(reviewed)


@organization_router.get("/ai-governance")
def get_ai_governance(
    organization_id: str,
    _: Membership = Depends(
        require_org_role(Role.OWNER.value, Role.ADMIN.value, Role.REVIEWER.value)
    ),
    db: Session = Depends(get_db),
) -> dict:
    return governance_view(
        db,
        organization_id=organization_id,
        ai_globally_configured=is_ai_configured(),
    )


@organization_router.put("/ai-governance/policy")
def put_ai_governance_policy(
    organization_id: str,
    payload: AIGovernancePolicyUpdate,
    membership: Membership = Depends(
        require_org_role(Role.OWNER.value, Role.ADMIN.value)
    ),
    db: Session = Depends(get_db),
) -> dict:
    update_policy(
        db,
        organization_id=organization_id,
        user_id=membership.user_id,
        payload=payload,
    )
    return governance_view(
        db,
        organization_id=organization_id,
        ai_globally_configured=is_ai_configured(),
    )


@organization_router.get("/ai-governance/events")
def list_ai_usage_events(
    organization_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    _: Membership = Depends(
        require_org_role(Role.OWNER.value, Role.ADMIN.value, Role.REVIEWER.value)
    ),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = (
        db.query(AIUsageEvent)
        .filter(AIUsageEvent.organization_id == organization_id)
        .order_by(AIUsageEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    return [usage_event_view(row) for row in rows]
