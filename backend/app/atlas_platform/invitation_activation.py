"""Invitation activation with an independent mailbox proof for existing accounts.

An invitation alone must never reset an existing account's global credential.
No raw code or password is persisted. Licence terms are not changed here.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import logging
import secrets
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from .audit import record_audit
from .auth_delivery import AuthDeliveryError, send_transactional_email
from .commercial_access_models import entitlement_payload, get_entitlement, enforce_active_entitlement
from .database import Base, get_db
from .identity import _as_utc, _invitation_status, _token_hash, accept_invitation, invitation_details
from .models import PasswordResetToken, User, UserInvitation, utcnow
from .schemas import InvitationAcceptRequest, InvitationInspectRequest
from .security import hash_password

router = APIRouter(tags=["invitation-activation"])
logger = logging.getLogger("sris.invitation_activation")


class ActivationProof(Base):
    __tablename__ = "sris_invitation_activation_proofs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    invitation_id: Mapped[str] = mapped_column(ForeignKey("user_invitations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    invitation_hash: Mapped[str] = mapped_column(String(64))
    code_hash: Mapped[str] = mapped_column(String(64))
    auth_version: Mapped[int] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    delivery_status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ActivationRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class ActivationComplete(ActivationRequest):
    password: str = Field(min_length=12, max_length=200)
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    proof_id: str | None = Field(default=None, max_length=36)
    code: str | None = Field(default=None, pattern=r"^[0-9]{8}$")
    use_current_password: bool = False


def load_invitation(db: Session, token: str) -> UserInvitation:
    invitation = db.query(UserInvitation).filter(
        UserInvitation.token_hash == _token_hash("invite", token)
    ).with_for_update().one_or_none()
    if invitation is None or _invitation_status(invitation) != "pending":
        raise HTTPException(404, "O convite não existe, expirou ou já foi utilizado.")
    return invitation


def code_hash(proof_id: str, invitation_hash: str, code: str) -> str:
    return hashlib.sha256(f"activation\0{proof_id}\0{invitation_hash}\0{code}".encode()).hexdigest()


@router.post("/api/auth/invitations/activation/inspect")
def inspect_activation(payload: ActivationRequest, db: Session = Depends(get_db)) -> dict:
    data = invitation_details(InvitationInspectRequest(token=payload.token), db=db).model_dump(mode="json")
    invitation = load_invitation(db, payload.token)
    terms = entitlement_payload(get_entitlement(db, invitation.organization_id))
    data["commercial_access"] = {k: terms.get(k) for k in (
        "present", "status", "lifecycle_status", "plan_code", "starts_at", "expires_at", "enforced"
    )}
    data["commercial_access"].update({"automatic_renewal": False, "automatic_billing": False})
    data["mailbox_confirmation_required"] = data["existing_account"]
    return data


@router.post("/api/auth/invitations/activation/send-code")
def send_code(payload: ActivationRequest, db: Session = Depends(get_db)) -> dict:
    invitation = load_invitation(db, payload.token)
    enforce_active_entitlement(db, invitation.organization_id)
    user = db.query(User).filter(User.email == invitation.email).with_for_update().one_or_none()
    if user is None:
        return {"status": "not_required", "message": "Pode criar a palavra-passe diretamente."}
    if not user.is_active:
        raise HTTPException(403, "Esta conta está desativada. Contacte o SRIS.")
    now = utcnow()
    recent = db.query(ActivationProof).filter(ActivationProof.user_id == user.id,
        ActivationProof.created_at > now - timedelta(hours=1)).order_by(ActivationProof.created_at.desc()).all()
    if len(recent) >= 5 or (recent and now - _as_utc(recent[0].created_at) < timedelta(seconds=60)):
        raise HTTPException(429, "Aguarde antes de pedir outro código. Máximo de cinco envios por hora.")
    for old in db.query(ActivationProof).filter(ActivationProof.user_id == user.id,
        ActivationProof.used_at.is_(None), ActivationProof.revoked_at.is_(None)).all():
        old.revoked_at = now
    code = f"{secrets.randbelow(100_000_000):08d}"
    proof_id = str(uuid4())
    proof = ActivationProof(id=proof_id, invitation_id=invitation.id, user_id=user.id,
        invitation_hash=invitation.token_hash, code_hash=code_hash(proof_id, invitation.token_hash, code),
        auth_version=user.auth_version, expires_at=min(_as_utc(invitation.expires_at), now + timedelta(minutes=10)))
    db.add(proof)
    db.flush()
    record_audit(db, action="user.invitation_activation_code_requested", resource_type="activation_proof",
        resource_id=proof.id, user_id=user.id, organization_id=invitation.organization_id,
        payload={"expires_minutes": 10})
    # The account/password and membership remain unchanged while the email is sent.
    db.commit()
    try:
        body = (f"O seu código de confirmação SRIS é: {code}\n\n"
                "Introduza-o na página do convite, juntamente com a nova palavra-passe. "
                "É válido durante 10 minutos e só pode ser usado uma vez.\n\n"
                "A nova palavra-passe substitui a anterior nesta conta SRIS e encerra as sessões antigas. "
                "Não altera o prazo comercial do workspace.\n\n"
                "Se não pediu esta alteração, ignore este email. Não partilhe o código.")
        send_transactional_email(recipient=invitation.email,
            subject="SRIS | Código para definir a palavra-passe",
            text_body=body, html_body="<p>" + html.escape(body).replace("\n", "<br>") + "</p>")
        proof.delivery_status = "provider_accepted"
        db.commit()
    except AuthDeliveryError:
        proof.delivery_status = "failed"
        proof.revoked_at = utcnow()
        db.commit()
        logger.warning("SRIS_ACTIVATION_CODE delivery=failed")
        raise HTTPException(503, "Não foi possível enviar o código. A palavra-passe não foi alterada. Tente novamente mais tarde.") from None
    return {"status": "provider_accepted", "proof_id": proof.id, "expires_minutes": 10,
        "message": "Código enviado para o email do convite. Consulte a caixa de entrada e introduza-o aqui."}


@router.post("/api/auth/invitations/activation/complete")
def complete_activation(payload: ActivationComplete, db: Session = Depends(get_db)):
    invitation = load_invitation(db, payload.token)
    enforce_active_entitlement(db, invitation.organization_id)
    user = db.query(User).filter(User.email == invitation.email).with_for_update().one_or_none()
    if user is not None and not payload.use_current_password:
        proof = db.query(ActivationProof).filter(ActivationProof.id == payload.proof_id).with_for_update().one_or_none()
        now = utcnow()
        if (not user.is_active or proof is None or proof.user_id != user.id
            or proof.invitation_id != invitation.id or proof.invitation_hash != invitation.token_hash
            or proof.auth_version != user.auth_version or proof.used_at is not None
            or proof.revoked_at is not None or _as_utc(proof.expires_at) <= now
            or proof.delivery_status != "provider_accepted" or proof.attempts >= 5):
            raise HTTPException(400, "Confirme o email com um código válido antes de definir a nova palavra-passe.")
        proof.attempts += 1
        expected = code_hash(proof.id, invitation.token_hash, payload.code or "")
        if not hmac.compare_digest(proof.code_hash, expected):
            db.commit()  # Persist the attempt, but never change the account.
            raise HTTPException(400, "Código incorreto. São permitidas cinco tentativas por código.")
        proof.used_at = now
        user.password_hash = hash_password(payload.password)
        user.auth_version += 1
        for reset in db.query(PasswordResetToken).filter(PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None), PasswordResetToken.revoked_at.is_(None)).all():
            reset.revoked_at = now
        record_audit(db, action="user.password_reset_completed", resource_type="user", resource_id=user.id,
            organization_id=invitation.organization_id, user_id=user.id,
            payload={"sessions_revoked": True, "source": "invitation_mailbox_confirmation"})
        db.flush()
    # Reuse canonical membership, single-use invitation, password verification
    # and session issuance. Its commit atomically persists the password change.
    return accept_invitation(InvitationAcceptRequest(token=payload.token,
        password=payload.password, full_name=payload.full_name), db=db)
