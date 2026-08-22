from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from app.atlas_platform.auth import current_user
from app.atlas_platform.database import get_db
from app.atlas_platform.models import AuditEvent, Membership, Organization, Role, User

router = APIRouter(prefix="/api/pilot", tags=["pilot-operations"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _env_int(name: str, default: int, minimum: int = 1, maximum: int = 100000) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def _membership(db: Session, user_id: str) -> Membership:
    membership = (
        db.query(Membership)
        .filter(Membership.user_id == user_id)
        .order_by(Membership.created_at.asc())
        .first()
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="O utilizador não pertence a um workspace.")
    return membership


def _require_admin(db: Session, user: User) -> Membership:
    membership = _membership(db, user.id)
    if membership.role not in {Role.OWNER.value, Role.ADMIN.value}:
        raise HTTPException(status_code=403, detail="Apenas proprietários ou administradores podem gerir contas.")
    return membership


def _audit(
    db: Session,
    *,
    organization_id: str | None,
    user_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    payload: dict,
) -> None:
    db.add(
        AuditEvent(
            id=str(uuid4()),
            organization_id=organization_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            payload_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
        )
    )


class AccountStateRequest(BaseModel):
    is_active: bool


class AccountRoleRequest(BaseModel):
    role: str


@router.get("/ops/status")
def ops_status(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _membership(db, user.id)
    org_id = membership.organization_id
    return {
        "status": "ok",
        "timestamp": _utcnow().isoformat(),
        "service": os.getenv("RAILWAY_SERVICE_NAME", "local"),
        "environment": os.getenv("RAILWAY_ENVIRONMENT_NAME", os.getenv("ATLAS_ENV", "unknown")),
        "organization_id": org_id,
        "members": db.query(Membership).filter(Membership.organization_id == org_id).count(),
        "active_members": (
            db.query(User)
            .join(Membership, Membership.user_id == User.id)
            .filter(Membership.organization_id == org_id, User.is_active.is_(True))
            .count()
        ),
        "audit_events": db.query(AuditEvent).filter(AuditEvent.organization_id == org_id).count(),
        "ai_configured": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "ai_enabled": os.getenv("SRIS_AI_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"},
        "rate_limit_scope": "process-local-pilot",
    }


@router.get("/admin/accounts")
def list_accounts(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    admin_membership = _require_admin(db, user)
    rows = (
        db.query(User, Membership)
        .join(Membership, Membership.user_id == User.id)
        .filter(Membership.organization_id == admin_membership.organization_id)
        .order_by(User.created_at.asc())
        .all()
    )
    return {
        "organization_id": admin_membership.organization_id,
        "accounts": [
            {
                "id": account.id,
                "email": account.email,
                "full_name": account.full_name,
                "is_active": account.is_active,
                "role": membership.role,
                "last_login_at": account.last_login_at.isoformat() if account.last_login_at else None,
                "created_at": account.created_at.isoformat() if account.created_at else None,
            }
            for account, membership in rows
        ],
    }


@router.patch("/admin/accounts/{account_id}/state")
def set_account_state(
    account_id: str,
    payload: AccountStateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    admin_membership = _require_admin(db, user)
    target_membership = (
        db.query(Membership)
        .filter(
            Membership.user_id == account_id,
            Membership.organization_id == admin_membership.organization_id,
        )
        .one_or_none()
    )
    target = db.get(User, account_id)
    if target is None or target_membership is None:
        raise HTTPException(status_code=404, detail="Conta não encontrada neste workspace.")
    if target.id == user.id and not payload.is_active:
        raise HTTPException(status_code=409, detail="Não pode desativar a sua própria conta durante a sessão ativa.")

    before = target.is_active
    target.is_active = payload.is_active
    if before != payload.is_active:
        target.auth_version = int(target.auth_version or 1) + 1
    _audit(
        db,
        organization_id=admin_membership.organization_id,
        user_id=user.id,
        action="pilot.account.state_changed",
        resource_type="user",
        resource_id=target.id,
        payload={"before": before, "after": payload.is_active},
    )
    db.commit()
    return {"status": "updated", "account_id": target.id, "is_active": target.is_active}


@router.patch("/admin/accounts/{account_id}/role")
def set_account_role(
    account_id: str,
    payload: AccountRoleRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    admin_membership = _require_admin(db, user)
    allowed = {Role.ADMIN.value, Role.REVIEWER.value, Role.CONTRIBUTOR.value, Role.OBSERVER.value}
    if payload.role not in allowed:
        raise HTTPException(status_code=422, detail="Função inválida para administração do piloto.")

    target_membership = (
        db.query(Membership)
        .filter(
            Membership.user_id == account_id,
            Membership.organization_id == admin_membership.organization_id,
        )
        .one_or_none()
    )
    target = db.get(User, account_id)
    if target is None or target_membership is None:
        raise HTTPException(status_code=404, detail="Conta não encontrada neste workspace.")
    if target_membership.role == Role.OWNER.value:
        raise HTTPException(status_code=409, detail="A função de proprietário não pode ser alterada por este endpoint.")

    before = target_membership.role
    target_membership.role = payload.role
    _audit(
        db,
        organization_id=admin_membership.organization_id,
        user_id=user.id,
        action="pilot.account.role_changed",
        resource_type="membership",
        resource_id=target_membership.id,
        payload={"account_id": target.id, "before": before, "after": payload.role},
    )
    db.commit()
    return {"status": "updated", "account_id": target.id, "role": target_membership.role}


class PilotRateLimitMiddleware(BaseHTTPMiddleware):
    """Pilot-grade abuse control for sensitive public and AI endpoints.

    This limiter is intentionally process-local: it protects the current one-replica
    Pilot deployment without adding an external dependency. Before horizontal scale,
    replace the storage with a shared Redis-compatible backend.
    """

    _lock = threading.Lock()
    _buckets: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        rule = self._rule(request)
        if rule is None:
            return await call_next(request)

        limit, window_seconds, namespace = rule
        forwarded = request.headers.get("x-forwarded-for", "")
        client_ip = forwarded.split(",", 1)[0].strip() or (request.client.host if request.client else "unknown")
        key = f"{namespace}:{client_ip}"
        now = time.monotonic()

        with self._lock:
            bucket = self._buckets[key]
            cutoff = now - window_seconds
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, int(window_seconds - (now - bucket[0])))
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Demasiados pedidos. Tente novamente dentro de momentos."},
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": "0",
                    },
                )
            bucket.append(now)
            remaining = max(0, limit - len(bucket))

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response

    @staticmethod
    def _rule(request: Request) -> tuple[int, int, str] | None:
        if request.method not in {"POST", "PUT", "PATCH"}:
            return None
        path = request.url.path
        if path == "/api/pilot/register":
            return (_env_int("SRIS_RATE_LIMIT_SIGNUP_PER_15M", 8), 900, "signup")
        if path == "/api/pilot/password-reset/request":
            return (_env_int("SRIS_RATE_LIMIT_PASSWORD_RESET_PER_15M", 6), 900, "password-reset")
        if path.startswith("/api/pilot/ai") or path.startswith("/api/pilot/intelligence"):
            return (_env_int("SRIS_RATE_LIMIT_AI_PER_MINUTE", 20), 60, "ai")
        return None
