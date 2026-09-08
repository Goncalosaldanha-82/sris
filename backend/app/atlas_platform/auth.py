from __future__ import annotations

import re

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .commercial_access_models import enforce_active_entitlement
from .database import get_db
from .models import Membership, User
from .security import decode_access_token


bearer = HTTPBearer(auto_error=False)


def _commercial_gate_exempt(path: str) -> bool:
    if path.startswith("/api/auth/"):
        return True
    if path == "/api/pilot/profile":
        return True
    if path.startswith("/api/admin/access-requests"):
        return True
    if path.startswith("/api/admin/organizations/") and "/commercial-entitlement" in path:
        return True
    if path.startswith("/api/organizations/") and path.endswith("/commercial-entitlement"):
        return True
    return False


def _request_organization_id(request: Request, db: Session, user_id: str) -> str | None:
    path_match = re.match(r"^/api/(?:admin/)?organizations/([^/]+)", request.url.path)
    if path_match:
        return path_match.group(1)

    requested = request.headers.get("x-sris-organization", "").strip()
    if requested:
        membership = (
            db.query(Membership)
            .filter(
                Membership.user_id == user_id,
                Membership.organization_id == requested,
            )
            .one_or_none()
        )
        if membership is not None:
            return requested

    membership = (
        db.query(Membership)
        .filter(Membership.user_id == user_id)
        .order_by(Membership.created_at.asc())
        .first()
    )
    return membership.organization_id if membership is not None else None


def current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = payload["sub"]
        auth_version = int(payload["ver"])
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active or user.auth_version != auth_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive or unknown user")

    if not _commercial_gate_exempt(request.url.path):
        organization_id = _request_organization_id(request, db, user.id)
        if organization_id is not None:
            enforce_active_entitlement(db, organization_id)
    return user


def require_org_role(*allowed_roles: str):
    def dependency(
        organization_id: str,
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> Membership:
        membership = (
            db.query(Membership)
            .filter(
                Membership.user_id == user.id,
                Membership.organization_id == organization_id,
            )
            .one_or_none()
        )
        if membership is None or membership.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        enforce_active_entitlement(db, organization_id)
        return membership

    return dependency
