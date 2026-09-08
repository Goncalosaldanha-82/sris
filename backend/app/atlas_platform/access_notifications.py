"""Durable access-request notices. Transport acceptance is not inbox delivery."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import formataddr
from html import escape
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .auth_delivery import auth_delivery_configuration, send_transactional_email
from .commercial_access_models import AccessRequest
from .database import Base, SessionLocal
from .models import User

LOGGER = logging.getLogger("sris.access_inbox")
MAX_ATTEMPTS = 6
RETRY_SECONDS = (60, 300, 900, 3600, 10800, 21600)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def notifications_enabled() -> bool:
    return os.getenv("SRIS_ACCESS_NOTIFICATIONS_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


class AccessNotification(Base):
    __tablename__ = "sris_access_notifications"
    # Stable key makes enqueueing idempotent across submissions and restarts.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("sris_access_requests.id", ondelete="CASCADE"), index=True)
    recipient: Mapped[str] = mapped_column(String(320))
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)


def approver_recipients(db: Session) -> list[str]:
    from .commercial_access import _platform_approver_emails
    allowed = _platform_approver_emails()
    if not allowed:
        return []
    return sorted({u.email.strip().lower() for u in db.query(User).filter(
        func.lower(User.email).in_(allowed), User.is_active.is_(True)
    ).all()})


def admin_url() -> str:
    cfg = auth_delivery_configuration()
    base = os.getenv("SRIS_ACCESS_ADMIN_BASE_URL", "").strip().rstrip("/")
    base = base or (cfg.public_base_url if cfg else "")
    parsed = urlparse(base)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.query or parsed.fragment:
        raise ValueError("access_admin_url_not_configured")
    return base + "/admin/access-requests"


def enqueue(db: Session, item: AccessRequest, recipient: str, kind: str,
            response_message: str = "") -> bool:
    recipient = recipient.strip().lower()
    key = hashlib.sha256(f"{kind}:{item.id}:{recipient}".encode()).hexdigest()
    if db.get(AccessNotification, key) is not None:
        return False
    if kind == "admin_new":
        link = admin_url()
        subject = "SRIS | Novo pedido de acesso"
        body = (f"Novo pedido de acesso SRIS, pendente da sua decisão.\n\n"
                f"Nome: {item.full_name}\nOrganização / projeto: {item.organization_name}\n"
                f"Email: {item.email}\n\nAnalisar, aprovar ou recusar: {link}\n\n"
                "Entre com a sua conta de aprovação SRIS. Abrir este endereço não aprova o pedido. "
                "O requerente só recebe o convite depois da sua aprovação.")
    elif kind == "request_rejected":
        subject = "SRIS | Resposta ao seu pedido de acesso"
        body = (f"Olá {item.full_name},\n\n"
                + (response_message.strip() or "Obrigado pelo seu interesse no SRIS. Após análise, o seu pedido de acesso não foi aprovado nesta fase.")
                + "\n\nEste pedido foi encerrado sem criação de acesso.\nEquipa SRIS")
        link = ""
    else:
        raise ValueError("unsupported_notification_kind")
    html = '<div lang="pt-PT" style="font-family:Arial,sans-serif;line-height:1.6;max-width:640px">'
    html += "<h2>" + escape(subject) + "</h2><p>" + escape(body).replace("\n", "<br>") + "</p>"
    if link:
        html += f'<p><a href="{escape(link, quote=True)}">Abrir pedidos de acesso</a></p>'
    html += "</div>"
    notice = AccessNotification(id=key, request_id=item.id, recipient=recipient, kind=kind,
        status="queued", payload_json=json.dumps({"subject": subject, "text": body, "html": html}, ensure_ascii=False),
        attempts=0, next_attempt_at=now_utc())
    try:
        with db.begin_nested():
            db.add(notice)
            db.flush()
    except IntegrityError:
        return False
    return True


class NoticeDeliveryError(RuntimeError):
    pass


def deliver(notice: AccessNotification) -> str | None:
    """Return the provider message ID; never claim confirmed mailbox delivery."""
    cfg = auth_delivery_configuration()
    if cfg is None:
        raise NoticeDeliveryError("configuration_required")
    data = json.loads(notice.payload_json)
    if cfg.provider != "resend":
        send_transactional_email(recipient=notice.recipient, subject=data["subject"],
                                 text_body=data["text"], html_body=data["html"])
        return None
    payload = {"from": formataddr((cfg.from_name, cfg.from_email)), "to": [notice.recipient],
               "subject": data["subject"], "text": data["text"], "html": data["html"]}
    request = Request("https://api.resend.com/emails", method="POST",
        data=json.dumps(payload, ensure_ascii=False).encode(), headers={
            "Authorization": f"Bearer {os.environ['RESEND_API_KEY'].strip()}",
            "Content-Type": "application/json", "User-Agent": "SRIS-access-inbox/1.0",
            "Idempotency-Key": "access-notice/" + notice.id,
        })
    try:
        with urlopen(request, timeout=cfg.timeout_seconds) as response:
            if not 200 <= response.status < 300:
                raise NoticeDeliveryError(f"provider_http_{response.status}")
            result = json.loads(response.read())
            message_id = str(result.get("id", ""))[:200]
            if not message_id:
                raise NoticeDeliveryError("provider_receipt_missing")
            return message_id
    except HTTPError as exc:
        # Only the machine-readable error name is kept; no raw body, PII or keys.
        name = ""
        try:
            name = re.sub(r"[^a-zA-Z0-9_]", "", str(json.loads(exc.read()).get("name", "")))[:40]
        except Exception:
            pass
        raise NoticeDeliveryError(f"provider_http_{exc.code}" + (":" + name if name else "")) from None
    except (URLError, OSError, ValueError) as exc:
        raise NoticeDeliveryError("provider_transport_" + type(exc).__name__) from None


def process_one(notice_id: str) -> str:
    with SessionLocal() as db:
        row = db.query(AccessNotification).filter(AccessNotification.id == notice_id).with_for_update(skip_locked=True).one_or_none()
        if row is None or row.status not in {"queued", "failed"} or row.attempts >= MAX_ATTEMPTS:
            return "skipped"
        at = now_utc()
        due = row.next_attempt_at
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        if due > at:
            return "skipped"
        item = db.get(AccessRequest, row.request_id)
        permitted = item is not None and (
            (row.kind == "admin_new" and item.status == "pending" and row.recipient in approver_recipients(db))
            or (row.kind == "request_rejected" and item.status == "rejected" and row.recipient == item.email.lower())
        )
        if not permitted:
            row.status = "cancelled"
            db.commit()
            return "cancelled"
        row.attempts += 1
        row.attempted_at = at
        try:
            row.provider_id = deliver(row)
            row.status = "provider_accepted"
            row.accepted_at = now_utc()
            row.error_code = None
        except Exception as exc:
            row.status = "failed"
            row.error_code = str(exc)[:100] if isinstance(exc, NoticeDeliveryError) else type(exc).__name__
            row.next_attempt_at = at + timedelta(seconds=RETRY_SECONDS[row.attempts - 1])
        db.commit()
        LOGGER.warning("SRIS_ACCESS_NOTICE status=%s kind=%s attempts=%s provider_id=%s error=%s",
                       row.status, row.kind, row.attempts, row.provider_id or "-", row.error_code or "-")
        return row.status


def sweep(*, pacing_seconds: float = 1.0) -> dict:
    """Recover pending requests missed by previous builds; never approve any."""
    stats = {"pending": 0, "recipients": 0, "enqueued": 0, "provider_accepted": 0, "failed": 0}
    with SessionLocal() as db:
        recipients = approver_recipients(db)
        stats["recipients"] = len(recipients)
        stats["pending"] = db.query(AccessRequest).filter(AccessRequest.status == "pending").count()
        # Scan only requests missing this recipient's durable notice. Existing
        # accepted/failed records remain evidence, not reasons to enqueue twice.
        for recipient in recipients:
            existing = db.query(AccessNotification.request_id).filter(
                AccessNotification.recipient == recipient, AccessNotification.kind == "admin_new")
            pending = db.query(AccessRequest).filter(AccessRequest.status == "pending",
                ~AccessRequest.id.in_(existing)).order_by(AccessRequest.requested_at.asc()).limit(20).all()
            for item in pending:
                stats["enqueued"] += int(enqueue(db, item, recipient, "admin_new"))
        db.commit()
        jobs = [x.id for x in db.query(AccessNotification).filter(
            AccessNotification.status.in_(["queued", "failed"]), AccessNotification.attempts < MAX_ATTEMPTS,
            AccessNotification.next_attempt_at <= now_utc()).order_by(AccessNotification.created_at.asc()).limit(20).all()]
    for index, notice_id in enumerate(jobs):
        if index and pacing_seconds:
            time.sleep(pacing_seconds)
        result = process_one(notice_id)
        if result in stats:
            stats[result] += 1
    return stats
