from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .auth import require_org_role
from .database import get_db
from .models import Membership, Role
from .workflow_models import Workflow
from .workflow_schemas import (
    RepositoryProposalRead,
    ReviewPayload,
    WorkflowCreate,
    WorkflowRead,
)
from .workflow_service import WorkflowService


router = APIRouter(prefix="/api/organizations/{organization_id}/workflows", tags=["workflows"])

service = WorkflowService(
    Path(os.getenv("ATLAS_REPOSITORY_ROOT", ".")).resolve()
)


@router.post("", response_model=WorkflowRead, status_code=201)
def create_workflow(
    organization_id: str,
    payload: WorkflowCreate,
    membership: Membership = Depends(
        require_org_role(
            Role.OWNER.value,
            Role.ADMIN.value,
            Role.REVIEWER.value,
            Role.CONTRIBUTOR.value,
        )
    ),
    db: Session = Depends(get_db),
) -> Workflow:
    return service.create(
        db,
        organization_id=organization_id,
        user_id=membership.user_id,
        title=payload.title,
        source_name=payload.source_name,
        source_type=payload.source_type,
        content=payload.content,
    )


@router.get("", response_model=list[WorkflowRead])
def list_workflows(
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
) -> list[Workflow]:
    return (
        db.query(Workflow)
        .filter(Workflow.organization_id == organization_id)
        .order_by(Workflow.updated_at.desc())
        .all()
    )


def _workflow_or_404(db: Session, workflow_id: str, organization_id: str) -> Workflow:
    workflow = (
        db.query(Workflow)
        .filter(
            Workflow.id == workflow_id,
            Workflow.organization_id == organization_id,
        )
        .one_or_none()
    )
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@router.get("/{workflow_id}", response_model=WorkflowRead)
def get_workflow(
    organization_id: str,
    workflow_id: str,
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
) -> Workflow:
    return _workflow_or_404(db, workflow_id, organization_id)


@router.post("/{workflow_id}/review", response_model=WorkflowRead)
def review_workflow(
    organization_id: str,
    workflow_id: str,
    payload: ReviewPayload,
    membership: Membership = Depends(
        require_org_role(
            Role.OWNER.value,
            Role.ADMIN.value,
            Role.REVIEWER.value,
        )
    ),
    db: Session = Depends(get_db),
) -> Workflow:
    workflow = _workflow_or_404(db, workflow_id, organization_id)
    try:
        return service.review(
            db,
            workflow=workflow,
            approvals=payload.approvals,
            comment=payload.comment,
            user_id=membership.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{workflow_id}/materialize", response_model=WorkflowRead)
def materialize_workflow(
    organization_id: str,
    workflow_id: str,
    membership: Membership = Depends(
        require_org_role(
            Role.OWNER.value,
            Role.ADMIN.value,
            Role.REVIEWER.value,
        )
    ),
    db: Session = Depends(get_db),
) -> Workflow:
    workflow = _workflow_or_404(db, workflow_id, organization_id)
    try:
        return service.materialize(
            db,
            workflow=workflow,
            user_id=membership.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get(
    "/{workflow_id}/repository-proposal",
    response_model=RepositoryProposalRead,
)
def repository_proposal(
    organization_id: str,
    workflow_id: str,
    _: Membership = Depends(
        require_org_role(
            Role.OWNER.value,
            Role.ADMIN.value,
            Role.REVIEWER.value,
        )
    ),
    db: Session = Depends(get_db),
) -> dict:
    workflow = _workflow_or_404(db, workflow_id, organization_id)
    try:
        return service.proposal(workflow)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
