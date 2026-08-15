from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.atlas_platform.auth import require_org_role
from app.atlas_platform.database import get_db
from app.atlas_platform.models import Membership, Role

from .ai import (
    configured_model,
    configured_pilot_organization_id,
    institutional_onboarding_closed,
    is_ai_configured,
    is_ai_organization_authorized,
    is_context_research_configured,
)
from .attachments import (
    MAX_ATTACHMENT_BYTES,
    AttachmentError,
    attachment_content,
    attachment_view,
    create_attachment,
    delete_attachment,
    get_attachment,
    list_attachments,
)
from .catalog import demo_mission, load_demo_catalog
from .contracts import (
    AIGovernancePolicyUpdate,
    AnalysisInput,
    MIInteractionInput,
    MIProposalReviewRequest,
    MissionCreateRequest,
    MissionUpdateRequest,
    ReviewRequest,
)
from .dialogue_service import (
    MIDialogueConflict,
    dialogue_session_view,
    get_dialogue_session,
    list_dialogue_sessions,
    review_dialogue_proposal,
    run_interactive_turn,
)
from .engine import ENGINE_VERSION
from .governance import governance_view, update_policy, usage_event_view
from .interactive import INTERACTIVE_PROMPT_VERSION
from .models import AIUsageEvent, CanonicalMission, IntelligenceRun
from .portfolio import (
    create_mission,
    list_mission_portfolio,
    mission_view,
    update_mission,
)
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
        "portfolio_contract_version": "1.0",
        "mission_hierarchy": "available",
        "institutional_mission_creation": "available",
        "mission_language": "MDL 1.3",
        "engine_version": ENGINE_VERSION,
        "deterministic_analysis": "available",
        "interactive_mission_intelligence": "available",
        "interactive_contract_version": "2.2",
        "mission_attachments": "encrypted_and_model_readable",
        "mission_exports": "client_side_auditable",
        "interactive_prompt_version": INTERACTIVE_PROMPT_VERSION,
        "interactive_state": "locally_persisted",
        "proposal_review": "granular_human_review",
        "canonical_auto_mutation": False,
        "ai_provider": "openai",
        "ai_model": configured_model(),
        "ai_configured": is_ai_configured(),
        "context_research_engine": "installed",
        "context_research_configured": is_context_research_configured(),
        "context_research_requires_authentication": True,
        "context_research_requires_human_review": True,
        "ai_pilot_gate": "single_organization",
        "ai_pilot_organization_configured": (
            configured_pilot_organization_id() is not None
        ),
        "institutional_onboarding_closed": institutional_onboarding_closed(),
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
    return list_mission_portfolio(db, organization_id=organization_id)


@organization_router.post("/missions", status_code=201)
def post_canonical_mission(
    organization_id: str,
    payload: MissionCreateRequest,
    membership: Membership = Depends(
        require_org_role(
            Role.OWNER.value,
            Role.ADMIN.value,
            Role.CONTRIBUTOR.value,
        )
    ),
    db: Session = Depends(get_db),
) -> dict:
    return create_mission(
        db,
        organization_id=organization_id,
        user_id=membership.user_id,
        payload=payload,
    )


@organization_router.get("/missions/{mission_id}")
def get_canonical_mission(
    organization_id: str,
    mission_id: str,
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
    row = (
        db.query(CanonicalMission)
        .filter(
            CanonicalMission.id == mission_id,
            CanonicalMission.organization_id == organization_id,
        )
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return mission_view(db, organization_id=organization_id, row=row)


@organization_router.patch("/missions/{mission_id}")
def patch_canonical_mission(
    organization_id: str,
    mission_id: str,
    payload: MissionUpdateRequest,
    membership: Membership = Depends(
        require_org_role(
            Role.OWNER.value,
            Role.ADMIN.value,
            Role.CONTRIBUTOR.value,
        )
    ),
    db: Session = Depends(get_db),
) -> dict:
    return update_mission(
        db,
        organization_id=organization_id,
        mission_id=mission_id,
        user_id=membership.user_id,
        payload=payload,
    )


def _attachment_error(exc: AttachmentError) -> HTTPException:
    status = 404 if exc.code in {"mission_not_found", "attachment_not_found"} else 422
    return HTTPException(
        status_code=status,
        detail={"code": exc.code, "message": exc.message},
    )


@organization_router.post("/missions/{mission_code}/attachments", status_code=201)
async def upload_mission_attachment(
    organization_id: str,
    mission_code: str,
    file: UploadFile = File(...),
    dialogue_session_id: str | None = Form(default=None),
    question_id: str | None = Form(default=None),
    membership: Membership = Depends(
        require_org_role(Role.OWNER.value, Role.ADMIN.value, Role.REVIEWER.value)
    ),
    db: Session = Depends(get_db),
) -> dict:
    content = await file.read(MAX_ATTACHMENT_BYTES + 1)
    try:
        row = create_attachment(
            db,
            organization_id=organization_id,
            mission_code=mission_code,
            user_id=membership.user_id,
            filename=file.filename or "anexo",
            declared_media_type=file.content_type,
            content=content,
            dialogue_session_id=dialogue_session_id,
            question_id=question_id,
        )
    except AttachmentError as exc:
        raise _attachment_error(exc) from exc
    return attachment_view(row)


@organization_router.get("/missions/{mission_code}/attachments")
def get_mission_attachments(
    organization_id: str,
    mission_code: str,
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
    return [
        attachment_view(row)
        for row in list_attachments(
            db,
            organization_id=organization_id,
            mission_code=mission_code,
        )
    ]


@organization_router.get("/missions/{mission_code}/attachments/{attachment_id}/download")
def download_mission_attachment(
    organization_id: str,
    mission_code: str,
    attachment_id: str,
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
) -> Response:
    row = get_attachment(
        db,
        organization_id=organization_id,
        mission_code=mission_code,
        attachment_id=attachment_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    try:
        content = attachment_content(row)
    except AttachmentError as exc:
        raise _attachment_error(exc) from exc
    return Response(
        content=content,
        media_type=row.media_type,
        headers={
            "Content-Disposition": (
                "attachment; filename*=UTF-8''" + quote(row.original_filename, safe="")
            )
        },
    )


@organization_router.delete(
    "/missions/{mission_code}/attachments/{attachment_id}",
    status_code=204,
)
def remove_mission_attachment(
    organization_id: str,
    mission_code: str,
    attachment_id: str,
    membership: Membership = Depends(
        require_org_role(Role.OWNER.value, Role.ADMIN.value, Role.REVIEWER.value)
    ),
    db: Session = Depends(get_db),
) -> Response:
    row = get_attachment(
        db,
        organization_id=organization_id,
        mission_code=mission_code,
        attachment_id=attachment_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    try:
        delete_attachment(db, row=row, user_id=membership.user_id)
    except AttachmentError as exc:
        raise _attachment_error(exc) from exc
    return Response(status_code=204)


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


@organization_router.post("/missions/{mission_code}/analyze")
def analyze_organizational_mission(
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


@organization_router.post("/demo/{mission_code}/interact")
def interact_with_organizational_demo(
    organization_id: str,
    mission_code: str,
    payload: MIInteractionInput,
    membership: Membership = Depends(
        require_org_role(
            Role.OWNER.value,
            Role.ADMIN.value,
            Role.REVIEWER.value,
        )
    ),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return run_interactive_turn(
            db,
            organization_id=organization_id,
            user_id=membership.user_id,
            user_role=membership.role,
            mission_code=mission_code,
            payload=payload,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Mission not found") from exc
    except MIDialogueConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except AttachmentError as exc:
        raise _attachment_error(exc) from exc


@organization_router.post("/missions/{mission_code}/interact")
def interact_with_organizational_mission(
    organization_id: str,
    mission_code: str,
    payload: MIInteractionInput,
    membership: Membership = Depends(
        require_org_role(
            Role.OWNER.value,
            Role.ADMIN.value,
            Role.REVIEWER.value,
        )
    ),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return run_interactive_turn(
            db,
            organization_id=organization_id,
            user_id=membership.user_id,
            user_role=membership.role,
            mission_code=mission_code,
            payload=payload,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Mission not found") from exc
    except MIDialogueConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except AttachmentError as exc:
        raise _attachment_error(exc) from exc


@organization_router.get("/dialogues")
def get_dialogue_sessions(
    organization_id: str,
    mission_code: str | None = Query(default=None, max_length=80),
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
    return list_dialogue_sessions(
        db,
        organization_id=organization_id,
        mission_code=mission_code,
    )


@organization_router.get("/dialogues/{session_id}")
def get_dialogue(
    organization_id: str,
    session_id: str,
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
    session = get_dialogue_session(
        db,
        organization_id=organization_id,
        session_id=session_id,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Dialogue session not found")
    return dialogue_session_view(session)


@organization_router.put(
    "/dialogues/{session_id}/turns/{turn_id}/proposals/{proposal_id}/review"
)
def put_dialogue_proposal_review(
    organization_id: str,
    session_id: str,
    turn_id: str,
    proposal_id: str,
    payload: MIProposalReviewRequest,
    membership: Membership = Depends(
        require_org_role(Role.OWNER.value, Role.ADMIN.value, Role.REVIEWER.value)
    ),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return review_dialogue_proposal(
            db,
            organization_id=organization_id,
            session_id=session_id,
            turn_id=turn_id,
            proposal_id=proposal_id,
            user_id=membership.user_id,
            payload=payload,
        )
    except MIDialogueConflict as exc:
        raise HTTPException(
            status_code=404 if exc.code.endswith("not_found") else 409,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


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
        ai_organization_authorized=is_ai_organization_authorized(organization_id),
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
    if payload.enabled and not is_ai_organization_authorized(organization_id):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "organization_not_authorized",
                "message": "This organization is not authorized for the AI pilot",
            },
        )
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
        ai_organization_authorized=is_ai_organization_authorized(organization_id),
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
