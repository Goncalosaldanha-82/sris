from __future__ import annotations

import hashlib
import html
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .audit import record_audit
from .auth import require_org_role
from .auth_delivery import (
    AuthDeliveryError,
    auth_email_delivery_ready,
    build_auth_link,
    send_transactional_email,
)
from .config import environment_flag
from .database import SessionLocal, get_db
from .models import (
    Membership,
    Organization,
    PasswordResetToken,
    Role,
    User,
    UserInvitation,
    utcnow,
)
from .schemas import (
    AuthCapabilitiesRead,
    InvitationAcceptRequest,
    InvitationAcceptResponse,
    InvitationCreate,
    InvitationInspectRequest,
    InvitationPublicRead,
    InvitationRead,
    MembershipRoleUpdate,
    PasswordResetConfirmRequest,
    PasswordResetConfirmResponse,
    PasswordResetStartRequest,
    PasswordResetStartResponse,
)
from .security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)


router = APIRouter(tags=["identity"])
logger = logging.getLogger(__name__)

INVITABLE_BY_OWNER = {
    Role.ADMIN.value,
    Role.REVIEWER.value,
    Role.CONTRIBUTOR.value,
    Role.OBSERVER.value,
}
INVITABLE_BY_ADMIN = {
    Role.REVIEWER.value,
    Role.CONTRIBUTOR.value,
    Role.OBSERVER.value,
}
GENERIC_RESET_MESSAGE = (
    "Se existir uma conta ativa com esse email, receberá instruções para "
    "definir uma nova palavra-passe."
)


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _managed_runtime() -> bool:
    return any(
        os.getenv(name)
        for name in (
            "RAILWAY_ENVIRONMENT_ID",
            "RAILWAY_PROJECT_ID",
            "RAILWAY_SERVICE_ID",
        )
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _token_hash(purpose: str, raw_token: str) -> str:
    return hashlib.sha256(f"{purpose}\0{raw_token}".encode("utf-8")).hexdigest()


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _invitation_status(invitation: UserInvitation) -> str:
    if invitation.accepted_at is not None:
        return "accepted"
    if invitation.revoked_at is not None:
        return "revoked"
    if _as_utc(invitation.expires_at) <= utcnow():
        return "expired"
    return "pending"


def _invitation_read(invitation: UserInvitation) -> InvitationRead:
    return InvitationRead(
        id=invitation.id,
        organization_id=invitation.organization_id,
        email=invitation.email,
        full_name=invitation.full_name,
        role=invitation.role,
        status=_invitation_status(invitation),
        delivery_status=invitation.delivery_status,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
        last_sent_at=invitation.last_sent_at,
    )


def _invalid_invitation() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="O convite não existe ou já não é válido.",
    )


def _first_organization_id(db: Session, user_id: str) -> str | None:
    membership = (
        db.query(Membership)
        .filter(Membership.user_id == user_id)
        .order_by(Membership.created_at.asc())
        .first()
    )
    return membership.organization_id if membership is not None else None


def _send_invitation_email(invitation_id: str, raw_token: str) -> None:
    with SessionLocal() as db:
        invitation = db.get(UserInvitation, invitation_id)
        if invitation is None or _invitation_status(invitation) != "pending":
            return
        organization = db.get(Organization, invitation.organization_id)
        if organization is None:
            invitation.delivery_status = "failed"
            db.commit()
            return

        try:
            activation_url = build_auth_link("invite", raw_token)
            recipient_name = invitation.full_name.strip() or invitation.email
            safe_name = html.escape(recipient_name)
            safe_organization = html.escape(organization.name)
            safe_url = html.escape(activation_url, quote=True)
            send_transactional_email(
                recipient=invitation.email,
                subject=f"Convite para {organization.name} no SRIS",
                text_body=(
                    f"Olá {recipient_name},\n\n"
                    f"Foi convidado para integrar {organization.name} no SRIS "
                    f"com o perfil {invitation.role}.\n\n"
                    f"Ative a conta através deste link:\n{activation_url}\n\n"
                    "O link é pessoal, expira e só pode ser usado uma vez. "
                    "Se não esperava este convite, ignore a mensagem."
                ),
                html_body=(
                    f"<p>Olá {safe_name},</p>"
                    f"<p>Foi convidado para integrar <strong>{safe_organization}</strong> "
                    f"no SRIS com o perfil <strong>{html.escape(invitation.role)}</strong>.</p>"
                    f'<p><a href="{safe_url}">Ativar conta no SRIS</a></p>'
                    "<p>O link é pessoal, expira e só pode ser usado uma vez. "
                    "Se não esperava este convite, ignore a mensagem.</p>"
                ),
            )
            invitation.delivery_status = "sent"
            invitation.last_sent_at = utcnow()
        except AuthDeliveryError:
            invitation.delivery_status = "failed"
            logger.exception("SRIS invitation email delivery failed")
        finally:
            invitation.delivery_attempts += 1
            db.commit()


def _send_password_reset_email(reset_id: str, raw_token: str) -> None:
    with SessionLocal() as db:
        reset = db.get(PasswordResetToken, reset_id)
        if reset is None or reset.used_at is not None or reset.revoked_at is not None:
            return
        if _as_utc(reset.expires_at) <= utcnow():
            return
        user = db.get(User, reset.user_id)
        if user is None or not user.is_active:
            return

        try:
            reset_url = build_auth_link("reset", raw_token)
            safe_name = html.escape(user.full_name.strip() or user.email)
            safe_url = html.escape(reset_url, quote=True)
            send_transactional_email(
                recipient=user.email,
                subject="Recuperar a palavra-passe do SRIS",
                text_body=(
                    f"Olá {user.full_name.strip() or user.email},\n\n"
                    "Foi pedida uma nova palavra-passe para a sua conta SRIS.\n\n"
                    f"Defina-a através deste link:\n{reset_url}\n\n"
                    "O link expira em breve e só pode ser usado uma vez. "
                    "Se não fez este pedido, ignore a mensagem."
                ),
                html_body=(
                    f"<p>Olá {safe_name},</p>"
                    "<p>Foi pedida uma nova palavra-passe para a sua conta SRIS.</p>"
                    f'<p><a href="{safe_url}">Definir nova palavra-passe</a></p>'
                    "<p>O link expira em breve e só pode ser usado uma vez. "
                    "Se não fez este pedido, ignore a mensagem.</p>"
                ),
            )
            reset.delivery_status = "sent"
            reset.sent_at = utcnow()
        except AuthDeliveryError:
            reset.delivery_status = "failed"
            logger.exception("SRIS password-reset email delivery failed")
        finally:
            db.commit()


def _assert_invitable(inviter: Membership, requested_role: str) -> str:
    role = requested_role.strip().lower()
    allowed = (
        INVITABLE_BY_OWNER
        if inviter.role == Role.OWNER.value
        else INVITABLE_BY_ADMIN
    )
    if role not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="O seu perfil não pode atribuir essa função.",
        )
    return role


@router.get("/api/auth/capabilities", response_model=AuthCapabilitiesRead)
def auth_capabilities() -> AuthCapabilitiesRead:
    public_registration = environment_flag(
        "ATLAS_SELF_REGISTRATION_ENABLED",
        default=not _managed_runtime(),
    )
    email_ready = auth_email_delivery_ready()
    return AuthCapabilitiesRead(
        account_creation="invitation_only",
        invitations_enabled=email_ready,
        password_reset_enabled=email_ready,
        public_registration_enabled=public_registration,
    )


@router.post(
    "/api/organizations/{organization_id}/invitations",
    response_model=InvitationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_invitation(
    organization_id: str,
    payload: InvitationCreate,
    background_tasks: BackgroundTasks,
    inviter: Membership = Depends(
        require_org_role(Role.OWNER.value, Role.ADMIN.value)
    ),
    db: Session = Depends(get_db),
) -> InvitationRead:
    if not auth_email_delivery_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="O envio de emails de autenticação ainda não está configurado.",
        )

    email = str(payload.email).strip().lower()
    role = _assert_invitable(inviter, payload.role)
    existing_user = db.query(User).filter(User.email == email).one_or_none()
    if existing_user is not None:
        if not existing_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A conta existe, mas está desativada.",
            )
        existing_membership = (
            db.query(Membership)
            .filter(
                Membership.organization_id == organization_id,
                Membership.user_id == existing_user.id,
            )
            .one_or_none()
        )
        if existing_membership is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Este utilizador já pertence à organização.",
            )

    now = utcnow()
    previous = (
        db.query(UserInvitation)
        .filter(
            UserInvitation.organization_id == organization_id,
            UserInvitation.email == email,
            UserInvitation.accepted_at.is_(None),
            UserInvitation.revoked_at.is_(None),
        )
        .order_by(UserInvitation.created_at.desc())
        .all()
    )
    if any(_as_utc(item.expires_at) > now for item in previous):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um convite pendente para este email.",
        )
    for item in previous:
        item.revoked_at = now

    raw_token = _new_token()
    invitation = UserInvitation(
        organization_id=organization_id,
        email=email,
        full_name=payload.full_name.strip(),
        role=role,
        token_hash=_token_hash("invite", raw_token),
        invited_by_user_id=inviter.user_id,
        expires_at=now
        + timedelta(
            hours=_bounded_env_int(
                "SRIS_INVITATION_TTL_HOURS",
                72,
                1,
                24 * 14,
            )
        ),
        delivery_status="pending",
    )
    db.add(invitation)
    db.flush()
    record_audit(
        db,
        action="user.invited",
        resource_type="user_invitation",
        resource_id=invitation.id,
        organization_id=organization_id,
        user_id=inviter.user_id,
        payload={"email": email, "role": role},
    )
    db.commit()
    db.refresh(invitation)
    background_tasks.add_task(_send_invitation_email, invitation.id, raw_token)
    return _invitation_read(invitation)


@router.get(
    "/api/organizations/{organization_id}/invitations",
    response_model=list[InvitationRead],
)
def list_invitations(
    organization_id: str,
    _: Membership = Depends(
        require_org_role(Role.OWNER.value, Role.ADMIN.value)
    ),
    db: Session = Depends(get_db),
) -> list[InvitationRead]:
    invitations = (
        db.query(UserInvitation)
        .filter(UserInvitation.organization_id == organization_id)
        .order_by(UserInvitation.created_at.desc())
        .all()
    )
    return [_invitation_read(item) for item in invitations]


@router.post(
    "/api/organizations/{organization_id}/invitations/{invitation_id}/resend",
    response_model=InvitationRead,
)
def resend_invitation(
    organization_id: str,
    invitation_id: str,
    background_tasks: BackgroundTasks,
    inviter: Membership = Depends(
        require_org_role(Role.OWNER.value, Role.ADMIN.value)
    ),
    db: Session = Depends(get_db),
) -> InvitationRead:
    if not auth_email_delivery_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="O envio de emails de autenticação ainda não está configurado.",
        )
    invitation = (
        db.query(UserInvitation)
        .filter(
            UserInvitation.id == invitation_id,
            UserInvitation.organization_id == organization_id,
        )
        .one_or_none()
    )
    if invitation is None or invitation.accepted_at is not None:
        raise _invalid_invitation()
    _assert_invitable(inviter, invitation.role)

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
        organization_id=organization_id,
        user_id=inviter.user_id,
        payload={"email": invitation.email, "role": invitation.role},
    )
    db.commit()
    db.refresh(invitation)
    background_tasks.add_task(_send_invitation_email, invitation.id, raw_token)
    return _invitation_read(invitation)


@router.delete(
    "/api/organizations/{organization_id}/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_invitation(
    organization_id: str,
    invitation_id: str,
    inviter: Membership = Depends(
        require_org_role(Role.OWNER.value, Role.ADMIN.value)
    ),
    db: Session = Depends(get_db),
) -> None:
    invitation = (
        db.query(UserInvitation)
        .filter(
            UserInvitation.id == invitation_id,
            UserInvitation.organization_id == organization_id,
        )
        .one_or_none()
    )
    if invitation is None or invitation.accepted_at is not None:
        raise _invalid_invitation()
    _assert_invitable(inviter, invitation.role)
    invitation.revoked_at = utcnow()
    record_audit(
        db,
        action="user.invitation_revoked",
        resource_type="user_invitation",
        resource_id=invitation.id,
        organization_id=organization_id,
        user_id=inviter.user_id,
        payload={"email": invitation.email, "role": invitation.role},
    )
    db.commit()


@router.post(
    "/api/auth/invitations/inspect",
    response_model=InvitationPublicRead,
)
def invitation_details(
    payload: InvitationInspectRequest,
    db: Session = Depends(get_db),
) -> InvitationPublicRead:
    invitation = (
        db.query(UserInvitation)
        .filter(
            UserInvitation.token_hash
            == _token_hash("invite", payload.token)
        )
        .one_or_none()
    )
    if invitation is None or _invitation_status(invitation) != "pending":
        raise _invalid_invitation()
    organization = db.get(Organization, invitation.organization_id)
    if organization is None:
        raise _invalid_invitation()
    existing_account = (
        db.query(User).filter(User.email == invitation.email).first() is not None
    )
    return InvitationPublicRead(
        organization_name=organization.name,
        email=invitation.email,
        full_name=invitation.full_name,
        role=invitation.role,
        expires_at=invitation.expires_at,
        existing_account=existing_account,
    )


@router.post(
    "/api/auth/invitations/accept",
    response_model=InvitationAcceptResponse,
)
def accept_invitation(
    payload: InvitationAcceptRequest,
    db: Session = Depends(get_db),
) -> InvitationAcceptResponse:
    invitation = (
        db.query(UserInvitation)
        .filter(
            UserInvitation.token_hash
            == _token_hash("invite", payload.token)
        )
        .with_for_update()
        .one_or_none()
    )
    if invitation is None or _invitation_status(invitation) != "pending":
        raise _invalid_invitation()

    user = db.query(User).filter(User.email == invitation.email).one_or_none()
    if user is not None:
        if not user.is_active or not verify_password(
            payload.password,
            user.password_hash,
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Não foi possível confirmar a conta existente.",
            )
    else:
        full_name = (payload.full_name or invitation.full_name).strip()
        user = User(
            email=invitation.email,
            full_name=full_name,
            password_hash=hash_password(payload.password),
            is_active=True,
            auth_version=1,
        )
        db.add(user)
        db.flush()

    membership = (
        db.query(Membership)
        .filter(
            Membership.user_id == user.id,
            Membership.organization_id == invitation.organization_id,
        )
        .one_or_none()
    )
    if membership is None:
        membership = Membership(
            user_id=user.id,
            organization_id=invitation.organization_id,
            role=invitation.role,
        )
        db.add(membership)
        db.flush()

    now = utcnow()
    invitation.accepted_at = now
    invitation.accepted_by_user_id = user.id
    record_audit(
        db,
        action="user.invitation_accepted",
        resource_type="membership",
        resource_id=membership.id,
        organization_id=invitation.organization_id,
        user_id=user.id,
        payload={"email": invitation.email, "role": invitation.role},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="O convite já foi aceite ou a associação já existe.",
        ) from exc

    return InvitationAcceptResponse(
        status="account_activated",
        access_token=create_access_token(
            user_id=user.id,
            auth_version=user.auth_version,
        ),
        refresh_token=create_refresh_token(
            user_id=user.id,
            auth_version=user.auth_version,
        ),
        organization_id=invitation.organization_id,
    )


@router.post(
    "/api/auth/password-reset/request",
    response_model=PasswordResetStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_password_reset(
    payload: PasswordResetStartRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> PasswordResetStartResponse:
    # The public response is deliberately identical for unknown users,
    # disabled accounts, throttled requests and unavailable email delivery.
    response = PasswordResetStartResponse(
        status="accepted",
        message=GENERIC_RESET_MESSAGE,
    )
    if not auth_email_delivery_ready():
        return response

    email = str(payload.email).strip().lower()
    user = (
        db.query(User)
        .filter(User.email == email, User.is_active.is_(True))
        .one_or_none()
    )
    if user is None:
        return response

    now = utcnow()
    cooldown = timedelta(
        seconds=_bounded_env_int(
            "SRIS_PASSWORD_RESET_COOLDOWN_SECONDS",
            60,
            30,
            3600,
        )
    )
    latest = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.user_id == user.id)
        .order_by(PasswordResetToken.requested_at.desc())
        .first()
    )
    if latest is not None and now - _as_utc(latest.requested_at) < cooldown:
        return response

    for previous in (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.revoked_at.is_(None),
        )
        .all()
    ):
        previous.revoked_at = now

    raw_token = _new_token()
    reset = PasswordResetToken(
        user_id=user.id,
        token_hash=_token_hash("reset", raw_token),
        expires_at=now
        + timedelta(
            minutes=_bounded_env_int(
                "SRIS_PASSWORD_RESET_TTL_MINUTES",
                30,
                5,
                120,
            )
        ),
        delivery_status="pending",
    )
    db.add(reset)
    db.flush()
    record_audit(
        db,
        action="user.password_reset_requested",
        resource_type="password_reset",
        resource_id=reset.id,
        organization_id=_first_organization_id(db, user.id),
        user_id=user.id,
        payload={"delivery": "email"},
    )
    db.commit()
    background_tasks.add_task(_send_password_reset_email, reset.id, raw_token)
    return response


@router.post(
    "/api/auth/password-reset/confirm",
    response_model=PasswordResetConfirmResponse,
)
def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    db: Session = Depends(get_db),
) -> PasswordResetConfirmResponse:
    reset = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.token_hash
            == _token_hash("reset", payload.token)
        )
        .with_for_update()
        .one_or_none()
    )
    now = utcnow()
    if (
        reset is None
        or reset.used_at is not None
        or reset.revoked_at is not None
        or _as_utc(reset.expires_at) <= now
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O link de recuperação é inválido ou expirou.",
        )

    user = db.get(User, reset.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O link de recuperação é inválido ou expirou.",
        )
    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A nova palavra-passe tem de ser diferente da atual.",
        )

    reset.used_at = now
    user.password_hash = hash_password(payload.new_password)
    user.auth_version += 1
    for other in (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.id != reset.id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.revoked_at.is_(None),
        )
        .all()
    ):
        other.revoked_at = now
    record_audit(
        db,
        action="user.password_reset_completed",
        resource_type="user",
        resource_id=user.id,
        organization_id=_first_organization_id(db, user.id),
        user_id=user.id,
        payload={"sessions_revoked": True},
    )
    db.commit()
    return PasswordResetConfirmResponse(status="password_updated")


@router.patch(
    "/api/organizations/{organization_id}/memberships/{membership_id}",
)
def update_membership_role(
    organization_id: str,
    membership_id: str,
    payload: MembershipRoleUpdate,
    owner: Membership = Depends(require_org_role(Role.OWNER.value)),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    target = (
        db.query(Membership)
        .filter(
            Membership.id == membership_id,
            Membership.organization_id == organization_id,
        )
        .one_or_none()
    )
    if target is None:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado.")
    if target.role == Role.OWNER.value:
        raise HTTPException(
            status_code=409,
            detail="A propriedade da organização exige um fluxo próprio de transferência.",
        )
    requested_role = payload.role.strip().lower()
    if requested_role not in INVITABLE_BY_OWNER:
        raise HTTPException(status_code=400, detail="Perfil inválido.")
    previous_role = target.role
    target.role = requested_role
    record_audit(
        db,
        action="membership.role_changed",
        resource_type="membership",
        resource_id=target.id,
        organization_id=organization_id,
        user_id=owner.user_id,
        payload={"from": previous_role, "to": requested_role},
    )
    db.commit()
    return {"id": target.id, "role": target.role}


@router.delete(
    "/api/organizations/{organization_id}/memberships/{membership_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_membership(
    organization_id: str,
    membership_id: str,
    owner: Membership = Depends(require_org_role(Role.OWNER.value)),
    db: Session = Depends(get_db),
) -> None:
    target = (
        db.query(Membership)
        .filter(
            Membership.id == membership_id,
            Membership.organization_id == organization_id,
        )
        .one_or_none()
    )
    if target is None:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado.")
    if target.role == Role.OWNER.value:
        raise HTTPException(
            status_code=409,
            detail="O proprietário não pode ser removido por este fluxo.",
        )
    target_user_id = target.user_id
    target_role = target.role
    db.delete(target)
    record_audit(
        db,
        action="membership.removed",
        resource_type="membership",
        resource_id=membership_id,
        organization_id=organization_id,
        user_id=owner.user_id,
        payload={"removed_user_id": target_user_id, "role": target_role},
    )
    db.commit()
