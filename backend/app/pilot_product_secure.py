from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.atlas_platform.auth import current_user
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
    PilotTopupRequest,
    _flag,
    pilot_test_topup as legacy_test_topup,
    router as legacy_router,
)


# Reuse mature Pilot routes while replacing operations whose public behavior is
# governed by the canonical identity lifecycle or disabled during validation.
router = APIRouter(tags=["pilot-product"])
_replaced = {
    ("/api/pilot/capabilities", "GET"),
    ("/api/pilot/password-reset/request", "POST"),
    ("/api/pilot/password-reset/confirm", "POST"),
    ("/api/pilot/credits/test-topup", "POST"),
}
for route in legacy_router.routes:
    methods = set(getattr(route, "methods", set()) or set())
    if any((route.path, method) in _replaced for method in methods):
        continue
    router.routes.append(route)


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
    """Compatibility alias backed by the canonical reset-token store."""

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
    """Compatibility alias backed by the canonical reset-token store."""

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
    return legacy_test_topup(payload=payload, user=user, db=db)
