from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.atlas_platform.access_inbox import router as access_inbox_router
from app.atlas_platform.auth import current_user
from app.atlas_platform.commercial_access import (
    AccessRequestCreate,
    create_access_request,
    router as commercial_access_router,
)
from app.atlas_platform.commercial_access_models import (
    enforce_active_entitlement,
    entitlement_payload,
    get_entitlement,
)
from app.atlas_platform.database import get_db
from app.atlas_platform.identity import (
    confirm_password_reset as canonical_confirm_password_reset,
    request_password_reset as canonical_request_password_reset,
)
from app.atlas_platform.models import User
from app.atlas_platform.schemas import (
    PasswordResetConfirmRequest,
    PasswordResetConfirmResponse,
    PasswordResetStartRequest,
    PasswordResetStartResponse,
)
from app.pilot_product import (
    PilotAIRequest,
    PilotTopupRequest,
    _flag,
    _membership_for_user,
    pilot_ai_ask as legacy_ai_ask,
    pilot_profile as legacy_profile,
    pilot_test_topup as legacy_test_topup,
    router as legacy_router,
)


router = APIRouter(tags=["pilot-product"])
_access_request_lock = threading.Lock()
_access_request_buckets: dict[str, deque[float]] = defaultdict(deque)


def _limit_access_request(request: Request) -> None:
    try:
        limit = int(os.getenv("SRIS_RATE_LIMIT_SIGNUP_PER_15M", "8"))
    except ValueError:
        limit = 8
    limit = max(1, min(1000, limit))
    forwarded = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded.split(",", 1)[0].strip() or (request.client.host if request.client else "unknown")
    now = time.monotonic()
    cutoff = now - 900
    with _access_request_lock:
        bucket = _access_request_buckets[client_ip]
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Demasiados pedidos. Tente novamente dentro de momentos.",
            )
        bucket.append(now)


_replaced = {
    ("/api/pilot/capabilities", "GET"),
    ("/api/pilot/register", "POST"),
    ("/api/pilot/profile", "GET"),
    ("/api/pilot/ai/ask", "POST"),
    ("/api/pilot/password-reset/request", "POST"),
    ("/api/pilot/password-reset/confirm", "POST"),
    ("/api/pilot/credits/test-topup", "POST"),
}
for route in legacy_router.routes:
    methods = set(getattr(route, "methods", set()) or set())
    if any((route.path, method) in _replaced for method in methods):
        continue
    router.routes.append(route)


@router.post("/api/access-requests", status_code=status.HTTP_202_ACCEPTED)
def governed_access_request(
    payload: AccessRequestCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    _limit_access_request(request)
    return create_access_request(payload=payload, db=db)


@router.post(
    "/api/pilot/register",
    status_code=status.HTTP_202_ACCEPTED,
    include_in_schema=False,
    deprecated=True,
)
def legacy_register_alias(
    payload: AccessRequestCreate,
    db: Session = Depends(get_db),
) -> dict:
    return create_access_request(payload=payload, db=db)


@router.get("/api/pilot/profile")
def pilot_profile(
    organization_id: str | None = Query(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    profile = legacy_profile(
        organization_id=organization_id,
        user=user,
        db=db,
    )
    for workspace in profile.get("workspaces", []):
        workspace["commercial_access"] = entitlement_payload(
            get_entitlement(db, workspace["id"])
        )
    organization = profile.get("organization") or {}
    selected_id = organization.get("id")
    profile["commercial_access"] = entitlement_payload(
        get_entitlement(db, selected_id)
    ) if selected_id else entitlement_payload(None)
    return profile


@router.post("/api/pilot/ai/ask")
def pilot_ai_ask(
    payload: PilotAIRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _membership_for_user(db, user.id)
    if membership is None:
        raise HTTPException(
            status_code=403,
            detail="A conta não tem um workspace associado.",
        )
    enforce_active_entitlement(db, membership.organization_id)
    return legacy_ai_ask(payload=payload, user=user, db=db)


@router.post(
    "/api/pilot/password-reset/request",
    response_model=PasswordResetStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
    include_in_schema=False,
    deprecated=True,
)
def legacy_password_reset_request_alias(
    payload: PasswordResetStartRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> PasswordResetStartResponse:
    return canonical_request_password_reset(
        payload=payload,
        background_tasks=background_tasks,
        db=db,
    )


@router.post(
    "/api/pilot/password-reset/confirm",
    response_model=PasswordResetConfirmResponse,
    include_in_schema=False,
    deprecated=True,
)
def legacy_password_reset_confirm_alias(
    payload: PasswordResetConfirmRequest,
    db: Session = Depends(get_db),
) -> PasswordResetConfirmResponse:
    return canonical_confirm_password_reset(payload=payload, db=db)


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
    membership = _membership_for_user(db, user.id)
    if membership is None:
        raise HTTPException(status_code=403, detail="Sem workspace associado.")
    enforce_active_entitlement(db, membership.organization_id)
    return legacy_test_topup(payload=payload, user=user, db=db)


for commercial_route in commercial_access_router.routes:
    if commercial_route.path in {"/api/access-requests", "/api/admin/access-requests/{request_id}/reject"}:
        continue
    router.routes.append(commercial_route)

# include_router also preserves the durable notification worker lifespan.
router.include_router(access_inbox_router)
