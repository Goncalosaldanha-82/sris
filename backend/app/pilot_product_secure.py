from __future__ import annotations

import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.atlas_platform.auth import current_user
from app.atlas_platform.database import get_db
from app.atlas_platform.models import User
from app.pilot_product import (
    PilotPasswordResetRequest,
    PilotTopupRequest,
    _ensure_pilot_schema,
    _flag,
    _hash_token,
    _pilot_runtime,
    _utcnow,
    pilot_test_topup as legacy_test_topup,
    router as legacy_router,
)


# Reuse the mature Pilot product routes, replacing only operations whose public
# behavior must be safer or less commercially prominent during validation.
# The public capability description is served by pilot_capabilities.py.
router = APIRouter(tags=["pilot-product"])
_replaced = {
    ("/api/pilot/capabilities", "GET"),
    ("/api/pilot/password-reset/request", "POST"),
    ("/api/pilot/credits/test-topup", "POST"),
}
for route in legacy_router.routes:
    methods = set(getattr(route, "methods", set()) or set())
    if any((route.path, method) in _replaced for method in methods):
        continue
    router.routes.append(route)


def _public_base_url() -> str:
    return os.getenv("SRIS_PUBLIC_BASE_URL", "").strip().rstrip("/")


def _sender_email() -> str:
    return os.getenv("SRIS_EMAIL_FROM", "").strip()


def _email_provider() -> str | None:
    if not _public_base_url() or not _sender_email():
        return None
    if os.getenv("RESEND_API_KEY", "").strip():
        return "resend"
    if os.getenv("BREVO_API_KEY", "").strip():
        return "brevo"
    return None


def _password_reset_delivery() -> str:
    if _email_provider():
        return "email"
    if _pilot_runtime() and _flag("SRIS_PILOT_SHOW_RESET_LINK", False):
        return "pilot-link"
    return "configuration-required"


def _reset_link(raw_token: str) -> str:
    token = urllib.parse.quote(raw_token, safe="")
    return f"{_public_base_url()}/?reset_token={token}"


def _send_resend(to_email: str, subject: str, text_body: str, html_body: str) -> None:
    payload = json.dumps(
        {
            "from": _sender_email(),
            "to": [to_email],
            "subject": subject,
            "text": text_body,
            "html": html_body,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {os.environ['RESEND_API_KEY'].strip()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status >= 300:
            raise RuntimeError(f"Resend returned HTTP {response.status}")


def _send_brevo(to_email: str, subject: str, text_body: str, html_body: str) -> None:
    payload = json.dumps(
        {
            "sender": {
                "name": os.getenv("SRIS_EMAIL_FROM_NAME", "SRIS Mission Intelligence"),
                "email": _sender_email(),
            },
            "to": [{"email": to_email}],
            "subject": subject,
            "textContent": text_body,
            "htmlContent": html_body,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=payload,
        headers={
            "api-key": os.environ["BREVO_API_KEY"].strip(),
            "Content-Type": "application/json",
            "accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status >= 300:
            raise RuntimeError(f"Brevo returned HTTP {response.status}")


def _send_password_reset_email(to_email: str, raw_token: str) -> None:
    provider = _email_provider()
    if provider is None:
        raise RuntimeError("Transactional email is not configured")
    link = _reset_link(raw_token)
    subject = "Recuperar acesso ao SRIS"
    text_body = (
        "Foi pedido um novo acesso ao seu workspace SRIS.\n\n"
        f"Defina uma nova palavra-passe através deste endereço:\n{link}\n\n"
        "O endereço é válido durante 30 minutos e só pode ser utilizado uma vez. "
        "Se não fez este pedido, ignore esta mensagem."
    )
    html_body = f"""
    <div style="font-family:Arial,sans-serif;line-height:1.6;color:#0d201a;max-width:620px;margin:auto">
      <div style="font-size:13px;letter-spacing:.12em;color:#2f6d59;font-weight:700">SRIS · MISSION INTELLIGENCE</div>
      <h1 style="font-family:Georgia,serif;font-weight:500;font-size:34px">Recuperar acesso</h1>
      <p>Foi pedido um novo acesso ao seu workspace SRIS.</p>
      <p><a href="{link}" style="display:inline-block;background:#103d32;color:#fff;text-decoration:none;padding:13px 18px;border-radius:10px;font-weight:700">Definir nova palavra-passe</a></p>
      <p style="color:#66756e">Este endereço é válido durante 30 minutos e só pode ser utilizado uma vez. Se não fez este pedido, ignore esta mensagem.</p>
    </div>
    """
    if provider == "resend":
        _send_resend(to_email, subject, text_body, html_body)
    else:
        _send_brevo(to_email, subject, text_body, html_body)


@router.post("/api/pilot/password-reset/request")
def pilot_password_reset_request(
    payload: PilotPasswordResetRequest,
    db: Session = Depends(get_db),
) -> dict:
    _ensure_pilot_schema(db)
    email = str(payload.email).strip().lower()
    delivery = _password_reset_delivery()
    response: dict = {
        "status": "accepted",
        "delivery": delivery,
        "message": "Se a conta existir, receberá instruções para recuperar o acesso.",
    }

    user = db.query(User).filter(User.email == email, User.is_active.is_(True)).one_or_none()
    if user is None:
        db.commit()
        return response

    db.execute(
        text(
            "UPDATE pilot_password_reset_tokens "
            "SET used_at=now() WHERE user_id=:uid AND used_at IS NULL"
        ),
        {"uid": user.id},
    )
    raw_token = secrets.token_urlsafe(48)
    db.execute(
        text(
            """
            INSERT INTO pilot_password_reset_tokens
            (id, user_id, token_hash, expires_at)
            VALUES (:id, :uid, :token_hash, :expires_at)
            """
        ),
        {
            "id": str(uuid4()),
            "uid": user.id,
            "token_hash": _hash_token(raw_token),
            "expires_at": _utcnow() + timedelta(minutes=30),
        },
    )
    db.commit()

    if delivery == "email":
        try:
            _send_password_reset_email(user.email, raw_token)
        except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError, KeyError) as exc:
            # Keep the response neutral to avoid account enumeration. The
            # failure remains visible in Railway logs for operational action.
            print(f"SRIS transactional email failed: {type(exc).__name__}: {exc}")
    elif delivery == "pilot-link":
        response["reset_token"] = raw_token
        response["expires_minutes"] = 30

    return response


@router.post("/api/pilot/credits/test-topup")
def pilot_test_topup(
    payload: PilotTopupRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not _flag("SRIS_BILLING_TEST_MODE", False):
        raise HTTPException(
            status_code=403,
            detail="Os carregamentos de teste estão desativados durante a validação operacional.",
        )
    return legacy_test_topup(payload=payload, user=user, db=db)
