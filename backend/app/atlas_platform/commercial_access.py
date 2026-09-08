from __future__ import annotations

import os
import re
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from .audit import record_audit
from .auth import current_user
from .auth_delivery import auth_email_delivery_ready
from .commercial_access_models import (
    ACCESS_REQUEST_APPROVED,
    ACCESS_REQUEST_PENDING,
    ACCESS_REQUEST_REJECTED,
    COMMERCIAL_PLANS,
    ENTITLEMENT_ACTIVE,
    ENTITLEMENT_GRANDFATHERED,
    AccessRequest,
    CommercialEntitlement,
    entitlement_payload,
    get_entitlement,
    utcnow,
)
from .database import get_db
from .identity import (
    _bounded_env_int,
    _invitation_read,
    _new_token,
    _send_invitation_email,
    _token_hash,
)
from .models import Membership, Organization, Role, User, UserInvitation


router = APIRouter(tags=["commercial-access"])

GENERIC_ACCESS_REQUEST_MESSAGE = (
    "Pedido recebido. O acesso é analisado pelo SRIS. Se for aprovado, "
    "receberá um convite pessoal e de utilização única por email."
)
ALLOWED_ASSIGNMENT_ROLES = {
    Role.OWNER.value,
    Role.ADMIN.value,
    Role.REVIEWER.value,
    Role.CONTRIBUTOR.value,
    Role.OBSERVER.value,
}


class AccessRequestCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    organization_name: str = Field(min_length=2, max_length=200)


class AccessApprovalRequest(BaseModel):
    organization_id: str | None = Field(default=None, max_length=36)
    workspace_name: str | None = Field(default=None, min_length=2, max_length=200)
    role: str = Field(default=Role.OWNER.value, max_length=30)
    plan_code: str = Field(default="pilot", max_length=64)
    entitlement_days: int = Field(default=90, ge=1, le=3650)
    commercial_reference: str | None = Field(default=None, max_length=200)
    decision_note: str | None = Field(default=None, max_length=2000)


class AccessRejectRequest(BaseModel):
    decision_note: str | None = Field(default=None, max_length=2000)


class EntitlementRenewRequest(BaseModel):
    term_days: int = Field(default=365, ge=1, le=3650)
    plan_code: str | None = Field(default=None, max_length=64)
    commercial_reference: str | None = Field(default=None, max_length=200)


def _normalise_email(value: str) -> str:
    return value.strip().lower()


def _platform_approver_emails() -> set[str]:
    values: set[str] = set()
    for name in ("SRIS_ACCESS_APPROVER_EMAILS", "SRIS_PLATFORM_ADMIN_EMAILS"):
        raw = os.getenv(name, "")
        values.update(
            item.strip().lower()
            for item in raw.split(",")
            if item.strip()
        )
    return values


def require_platform_approver(user: User = Depends(current_user)) -> User:
    allowed = _platform_approver_emails()
    if not allowed or user.email.strip().lower() not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "platform_approval_required",
                "message": "Esta operação exige aprovação de plataforma SRIS.",
            },
        )
    return user


def _validate_plan(value: str) -> str:
    plan = value.strip().lower()
    if plan not in COMMERCIAL_PLANS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "unsupported_commercial_plan",
                "message": "O plano comercial indicado não é reconhecido.",
            },
        )
    return plan


def _validate_role(value: str) -> str:
    role = value.strip().lower()
    if role not in ALLOWED_ASSIGNMENT_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "unsupported_workspace_role",
                "message": "A função indicada não pode ser atribuída neste fluxo.",
            },
        )
    return role


def _slug_base(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower().strip()).strip("-")
    return (cleaned or "workspace")[:100]


def _unique_slug(db: Session, name: str) -> str:
    base = _slug_base(name)
    candidate = base
    index = 2
    while db.query(Organization).filter(Organization.slug == candidate).first():
        suffix = f"-{index}"
        candidate = f"{base[:120-len(suffix)]}{suffix}"
        index += 1
    return candidate


def _request_payload(item: AccessRequest) -> dict:
    invitation = None
    return {
        "id": item.id,
        "email": item.email,
        "full_name": item.full_name,
        "organization_name": item.organization_name,
        "status": item.status,
        "plan_code": item.plan_code,
        "entitlement_days": item.entitlement_days,
        "organization_id": item.organization_id,
        "invitation_id": item.invitation_id,
        "decision_note": item.decision_note,
        "requested_at": item.requested_at.isoformat() if item.requested_at else None,
        "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
        "invitation": invitation,
    }


def _load_request_for_review(db: Session, request_id: str) -> AccessRequest:
    item = (
        db.query(AccessRequest)
        .filter(AccessRequest.id == request_id)
        .with_for_update()
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="O pedido de acesso não existe.")
    return item


def _get_or_create_entitlement(
    db: Session,
    *,
    organization_id: str,
    plan_code: str,
    entitlement_days: int,
    commercial_reference: str | None,
    approver_user_id: str,
) -> CommercialEntitlement:
    now = utcnow()
    existing = get_entitlement(db, organization_id)
    if existing is not None:
        # Existing workspaces may already have explicit commercial terms or a
        # migration-created grandfathered right. Approval must never shorten it.
        if existing.status == ENTITLEMENT_GRANDFATHERED:
            return existing
        current_expiry = existing.expires_at
        if current_expiry is not None and current_expiry.tzinfo is None:
            current_expiry = current_expiry.replace(tzinfo=now.tzinfo)
        if current_expiry is None or current_expiry < now + timedelta(days=entitlement_days):
            existing.expires_at = now + timedelta(days=entitlement_days)
        existing.plan_code = plan_code
        existing.status = ENTITLEMENT_ACTIVE
        existing.commercial_reference = commercial_reference or existing.commercial_reference
        existing.approved_by_user_id = approver_user_id
        existing.updated_at = now
        return existing

    entitlement = CommercialEntitlement(
        organization_id=organization_id,
        plan_code=plan_code,
        status=ENTITLEMENT_ACTIVE,
        starts_at=now,
        expires_at=now + timedelta(days=entitlement_days),
        commercial_reference=commercial_reference,
        approved_by_user_id=approver_user_id,
        renewal_count=0,
    )
    db.add(entitlement)
    db.flush()
    return entitlement


@router.post("/api/access-requests", status_code=status.HTTP_202_ACCEPTED)
def create_access_request(
    payload: AccessRequestCreate,
    db: Session = Depends(get_db),
) -> dict:
    email = _normalise_email(str(payload.email))
    pending = (
        db.query(AccessRequest)
        .filter(
            AccessRequest.email == email,
            AccessRequest.status == ACCESS_REQUEST_PENDING,
        )
        .order_by(AccessRequest.requested_at.desc())
        .first()
    )
    if pending is None:
        item = AccessRequest(
            email=email,
            full_name=payload.full_name.strip(),
            organization_name=payload.organization_name.strip(),
            status=ACCESS_REQUEST_PENDING,
        )
        db.add(item)
        db.flush()
        record_audit(
            db,
            action="access.requested",
            resource_type="access_request",
            resource_id=item.id,
            payload={"status": ACCESS_REQUEST_PENDING},
        )
        db.commit()
    # Deliberately non-enumerating: the same response is returned for an
    # existing pending request and a newly created request.
    return {"status": "accepted", "message": GENERIC_ACCESS_REQUEST_MESSAGE}


@router.get("/api/admin/access-requests")
def list_access_requests(
    request_status: str | None = Query(default=None, alias="status"),
    _approver: User = Depends(require_platform_approver),
    db: Session = Depends(get_db),
) -> dict:
    query = db.query(AccessRequest)
    if request_status:
        query = query.filter(AccessRequest.status == request_status.strip().lower())
    items = query.order_by(AccessRequest.requested_at.desc()).limit(200).all()
    result = []
    for item in items:
        row = _request_payload(item)
        if item.invitation_id:
            invitation = db.get(UserInvitation, item.invitation_id)
            if invitation is not None:
                row["invitation"] = _invitation_read(invitation)
        if item.organization_id:
            organization = db.get(Organization, item.organization_id)
            row["workspace"] = (
                {"id": organization.id, "name": organization.name, "slug": organization.slug}
                if organization is not None
                else None
            )
            row["entitlement"] = entitlement_payload(
                get_entitlement(db, item.organization_id)
            )
        result.append(row)
    return {"requests": result, "count": len(result)}


@router.post("/api/admin/access-requests/{request_id}/approve")
def approve_access_request(
    request_id: str,
    payload: AccessApprovalRequest,
    background_tasks: BackgroundTasks,
    approver: User = Depends(require_platform_approver),
    db: Session = Depends(get_db),
) -> dict:
    if not auth_email_delivery_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "auth_email_not_ready",
                "message": "O email transacional tem de estar operacional antes de aprovar novos acessos.",
            },
        )

    item = _load_request_for_review(db, request_id)
    if item.status != ACCESS_REQUEST_PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este pedido já foi decidido.",
        )

    plan_code = _validate_plan(payload.plan_code)
    role = _validate_role(payload.role)
    now = utcnow()

    if payload.organization_id:
        organization = db.get(Organization, payload.organization_id)
        if organization is None:
            raise HTTPException(status_code=404, detail="O workspace indicado não existe.")
    else:
        workspace_name = (payload.workspace_name or item.organization_name).strip()
        organization = Organization(
            name=workspace_name,
            slug=_unique_slug(db, workspace_name),
        )
        db.add(organization)
        db.flush()

    existing_user = db.query(User).filter(User.email == item.email).one_or_none()
    if existing_user is not None:
        membership = (
            db.query(Membership)
            .filter(
                Membership.organization_id == organization.id,
                Membership.user_id == existing_user.id,
            )
            .one_or_none()
        )
        if membership is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Esta pessoa já pertence ao workspace atribuído.",
            )

    active_invitation = (
        db.query(UserInvitation)
        .filter(
            UserInvitation.organization_id == organization.id,
            UserInvitation.email == item.email,
            UserInvitation.accepted_at.is_(None),
            UserInvitation.revoked_at.is_(None),
        )
        .order_by(UserInvitation.created_at.desc())
        .first()
    )
    if active_invitation is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um convite pendente para esta pessoa neste workspace.",
        )

    entitlement = _get_or_create_entitlement(
        db,
        organization_id=organization.id,
        plan_code=plan_code,
        entitlement_days=payload.entitlement_days,
        commercial_reference=payload.commercial_reference,
        approver_user_id=approver.id,
    )

    raw_token = _new_token()
    invitation = UserInvitation(
        organization_id=organization.id,
        email=item.email,
        full_name=item.full_name,
        role=role,
        token_hash=_token_hash("invite", raw_token),
        invited_by_user_id=approver.id,
        expires_at=now
        + timedelta(
            hours=_bounded_env_int(
                "SRIS_INVITATION_TTL_HOURS", 72, 1, 24 * 14
            )
        ),
        delivery_status="pending",
    )
    db.add(invitation)
    db.flush()

    item.status = ACCESS_REQUEST_APPROVED
    item.reviewed_at = now
    item.reviewed_by_user_id = approver.id
    item.organization_id = organization.id
    item.invitation_id = invitation.id
    item.plan_code = plan_code
    item.entitlement_days = payload.entitlement_days
    item.decision_note = payload.decision_note

    record_audit(
        db,
        action="access.request_approved",
        resource_type="access_request",
        resource_id=item.id,
        organization_id=organization.id,
        user_id=approver.id,
        payload={
            "plan_code": plan_code,
            "entitlement_days": payload.entitlement_days,
            "role": role,
        },
    )
    record_audit(
        db,
        action="commercial.entitlement_created",
        resource_type="commercial_entitlement",
        resource_id=entitlement.id,
        organization_id=organization.id,
        user_id=approver.id,
        payload={
            "plan_code": entitlement.plan_code,
            "expires_at": entitlement.expires_at.isoformat()
            if entitlement.expires_at
            else None,
        },
    )
    record_audit(
        db,
        action="user.invited",
        resource_type="user_invitation",
        resource_id=invitation.id,
        organization_id=organization.id,
        user_id=approver.id,
        payload={"email": item.email, "role": role, "source": "access_request"},
    )
    db.commit()
    db.refresh(item)
    db.refresh(entitlement)
    db.refresh(invitation)
    background_tasks.add_task(_send_invitation_email, invitation.id, raw_token)

    return {
        "request": _request_payload(item),
        "workspace": {
            "id": organization.id,
            "name": organization.name,
            "slug": organization.slug,
        },
        "entitlement": entitlement_payload(entitlement),
        "invitation": _invitation_read(invitation),
    }


@router.post("/api/admin/access-requests/{request_id}/reject")
def reject_access_request(
    request_id: str,
    payload: AccessRejectRequest,
    approver: User = Depends(require_platform_approver),
    db: Session = Depends(get_db),
) -> dict:
    item = _load_request_for_review(db, request_id)
    if item.status != ACCESS_REQUEST_PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este pedido já foi decidido.",
        )
    item.status = ACCESS_REQUEST_REJECTED
    item.reviewed_at = utcnow()
    item.reviewed_by_user_id = approver.id
    item.decision_note = payload.decision_note
    record_audit(
        db,
        action="access.request_rejected",
        resource_type="access_request",
        resource_id=item.id,
        user_id=approver.id,
        payload={"status": ACCESS_REQUEST_REJECTED},
    )
    db.commit()
    db.refresh(item)
    return {"request": _request_payload(item)}


@router.post("/api/admin/access-requests/{request_id}/resend-invitation")
def resend_access_invitation(
    request_id: str,
    background_tasks: BackgroundTasks,
    approver: User = Depends(require_platform_approver),
    db: Session = Depends(get_db),
) -> dict:
    if not auth_email_delivery_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="O email transacional não está configurado.",
        )
    item = _load_request_for_review(db, request_id)
    if item.status != ACCESS_REQUEST_APPROVED or not item.invitation_id:
        raise HTTPException(status_code=409, detail="Este pedido não tem um convite aprovado.")
    invitation = db.get(UserInvitation, item.invitation_id)
    if invitation is None or invitation.accepted_at is not None:
        raise HTTPException(status_code=409, detail="O convite já não pode ser reenviado.")

    raw_token = _new_token()
    invitation.token_hash = _token_hash("invite", raw_token)
    invitation.revoked_at = None
    invitation.expires_at = utcnow() + timedelta(
        hours=_bounded_env_int("SRIS_INVITATION_TTL_HOURS", 72, 1, 24 * 14)
    )
    invitation.delivery_status = "pending"
    record_audit(
        db,
        action="user.invitation_resent",
        resource_type="user_invitation",
        resource_id=invitation.id,
        organization_id=invitation.organization_id,
        user_id=approver.id,
        payload={"email": invitation.email, "role": invitation.role, "source": "access_request"},
    )
    db.commit()
    db.refresh(invitation)
    background_tasks.add_task(_send_invitation_email, invitation.id, raw_token)
    return {"invitation": _invitation_read(invitation)}


@router.get("/api/organizations/{organization_id}/commercial-entitlement")
def read_commercial_entitlement(
    organization_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = (
        db.query(Membership)
        .filter(
            Membership.organization_id == organization_id,
            Membership.user_id == user.id,
        )
        .one_or_none()
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="Sem acesso a este workspace.")
    return entitlement_payload(get_entitlement(db, organization_id))


@router.post("/api/admin/organizations/{organization_id}/commercial-entitlement/renew")
def renew_commercial_entitlement(
    organization_id: str,
    payload: EntitlementRenewRequest,
    approver: User = Depends(require_platform_approver),
    db: Session = Depends(get_db),
) -> dict:
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="O workspace indicado não existe.")
    entitlement = get_entitlement(db, organization_id)
    if entitlement is None:
        raise HTTPException(
            status_code=404,
            detail="Este workspace ainda não tem entitlement comercial.",
        )

    now = utcnow()
    plan_code = (
        _validate_plan(payload.plan_code)
        if payload.plan_code is not None
        else entitlement.plan_code
    )
    current_expiry = entitlement.expires_at
    base = now
    if current_expiry is not None:
        current_expiry = (
            current_expiry.replace(tzinfo=now.tzinfo)
            if current_expiry.tzinfo is None
            else current_expiry
        )
        if current_expiry > now:
            base = current_expiry

    entitlement.status = ENTITLEMENT_ACTIVE
    entitlement.plan_code = plan_code
    entitlement.starts_at = entitlement.starts_at or now
    entitlement.expires_at = base + timedelta(days=payload.term_days)
    entitlement.commercial_reference = (
        payload.commercial_reference
        if payload.commercial_reference is not None
        else entitlement.commercial_reference
    )
    entitlement.approved_by_user_id = approver.id
    entitlement.renewal_count = int(entitlement.renewal_count or 0) + 1
    entitlement.updated_at = now
    record_audit(
        db,
        action="commercial.entitlement_renewed",
        resource_type="commercial_entitlement",
        resource_id=entitlement.id,
        organization_id=organization_id,
        user_id=approver.id,
        payload={
            "plan_code": plan_code,
            "term_days": payload.term_days,
            "expires_at": entitlement.expires_at.isoformat(),
            "renewal_count": entitlement.renewal_count,
        },
    )
    db.commit()
    db.refresh(entitlement)
    return {
        "workspace": {"id": organization.id, "name": organization.name},
        "entitlement": entitlement_payload(entitlement),
    }
