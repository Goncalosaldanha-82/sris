"""Platform approval inbox, separate from customer workspace administration."""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from .access_notifications import AccessNotification, approver_recipients, enqueue, notifications_enabled, now_utc, sweep
from .audit import record_audit
from .commercial_access import AccessRejectRequest, _load_request_for_review, list_access_requests, require_platform_approver
from .commercial_access_models import AccessRequest
from .database import get_db
from .models import User

LOGGER = logging.getLogger("sris.access_inbox")
FRONTEND = Path(__file__).resolve().parents[3] / "frontend" / "pilot-v1"


@contextlib.asynccontextmanager
async def inbox_lifespan(_app):
    async def worker():
        first = True
        while True:
            try:
                result = await asyncio.to_thread(sweep)
                if first or result["enqueued"] or result["provider_accepted"] or result["failed"]:
                    LOGGER.warning("SRIS_ACCESS_INBOX %s", result)
                first = False
            except Exception as exc:
                LOGGER.error("SRIS_ACCESS_INBOX worker_error=%s", type(exc).__name__)
            await asyncio.sleep(30)
    task = asyncio.create_task(worker()) if notifications_enabled() else None
    try:
        yield
    finally:
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


router = APIRouter(tags=["access-inbox"], lifespan=inbox_lifespan)


@router.get("/admin/access-requests", include_in_schema=False)
def inbox_page():
    # Public shell only. Every data read and decision requires an authenticated
    # SRIS platform approver. A mail scanner following this GET grants no access.
    html = (FRONTEND / "access-inbox.html").read_text(encoding="utf-8")
    digest = hashlib.sha256((FRONTEND / "access-inbox.js").read_bytes()).hexdigest()[:16]
    return HTMLResponse(html.replace("__ACCESS_INBOX_VERSION__", digest), headers={
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "X-Robots-Tag": "noindex, nofollow",
    })


def _counts(db: Session) -> dict:
    counts = dict(db.query(AccessRequest.status, func.count(AccessRequest.id)).group_by(AccessRequest.status).all())
    return {"pending": int(counts.get("pending", 0)), "approved": int(counts.get("approved", 0)),
            "rejected": int(counts.get("rejected", 0)), "total": sum(counts.values())}


@router.get("/api/admin/access-requests/summary")
def summary(approver: User = Depends(require_platform_approver), db: Session = Depends(get_db)):
    return {"counts": _counts(db), "actor_email": approver.email,
            "notification_recipients": approver_recipients(db), "notifications_enabled": notifications_enabled()}


@router.get("/api/admin/access-requests/inbox")
def inbox(request_status: str | None = Query(default="pending", alias="status"),
          approver: User = Depends(require_platform_approver), db: Session = Depends(get_db)):
    if request_status not in {"pending", "approved", "rejected", "cancelled", "all", None}:
        raise HTTPException(422, "Estado de pedido inválido.")
    result = list_access_requests(request_status=None if request_status == "all" else request_status,
                                  _approver=approver, db=db)
    ids = [r["id"] for r in result["requests"]]
    notices = db.query(AccessNotification).filter(AccessNotification.request_id.in_(ids)).all() if ids else []
    by_request: dict[str, list] = {}
    for n in notices:
        by_request.setdefault(n.request_id, []).append({"kind": n.kind, "status": n.status,
            "recipient": n.recipient, "attempts": n.attempts, "error_code": n.error_code,
            "accepted_at": n.accepted_at.isoformat() if n.accepted_at else None})
    for row in result["requests"]:
        row["notifications"] = by_request.get(row["id"], [])
    result.update(summary(approver=approver, db=db))
    return result


class RefusalRequest(AccessRejectRequest):
    response_message: str = Field(default="", max_length=2000)


@router.post("/api/admin/access-requests/{request_id}/reject")
def refuse(request_id: str, payload: RefusalRequest,
           approver: User = Depends(require_platform_approver), db: Session = Depends(get_db)):
    item = _load_request_for_review(db, request_id)
    if item.status != "pending":
        raise HTTPException(409, "Este pedido já foi decidido.")
    item.status = "rejected"
    item.reviewed_at = now_utc()
    item.reviewed_by_user_id = approver.id
    item.decision_note = payload.decision_note
    # Decision and outgoing response are persisted in the same transaction.
    enqueue(db, item, item.email, "request_rejected", payload.response_message)
    record_audit(db, action="access.request_rejected", resource_type="access_request",
        resource_id=item.id, user_id=approver.id, payload={"status": "rejected", "response_queued": True})
    db.commit()
    return {"status": "rejected", "response_status": "queued"}


@router.post("/api/admin/access-requests/{request_id}/retry-notification")
def retry_notification(request_id: str, approver: User = Depends(require_platform_approver),
                       db: Session = Depends(get_db)):
    item = _load_request_for_review(db, request_id)
    rows = db.query(AccessNotification).filter(AccessNotification.request_id == request_id,
        AccessNotification.status == "failed").with_for_update().all()
    for row in rows:
        row.status = "queued"
        row.attempts = 0
        row.next_attempt_at = now_utc()
        row.error_code = None
    if item.status == "pending":
        for email in approver_recipients(db):
            enqueue(db, item, email, "admin_new")
    record_audit(db, action="access.notification_retry", resource_type="access_request",
                 resource_id=item.id, user_id=approver.id, payload={"reset_failed": len(rows)})
    db.commit()
    return {"status": "queued", "reset_failed": len(rows)}
