"""Exclusive platform-owner analytics authorization, independent of tenant roles."""
from __future__ import annotations

import os
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.atlas_platform.models import Membership, User


def configured_analytics_owner() -> tuple[str, str] | None:
    email = os.getenv("SRIS_ANALYTICS_OWNER_EMAIL", "").strip().lower()
    workspace = os.getenv("SRIS_ANALYTICS_OWNER_WORKSPACE_ID", "").strip()
    # Deliberately one identity, not a wildcard, domain or inherited approver list.
    if not email or email.count("@") != 1 or any(c in email for c in ",;*\r\n "):
        return None
    try:
        workspace = str(UUID(workspace))
    except (ValueError, AttributeError):
        return None
    return email, workspace


def can_read_internal_analytics(user: User, db: Session) -> bool:
    configured = configured_analytics_owner()
    if configured is None or not user.is_active:
        return False
    owner_email, owner_workspace = configured
    if user.email.strip().lower() != owner_email:
        return False
    # Query the pinned internal workspace, NEVER the client-selected workspace.
    return db.query(Membership.id).filter(
        Membership.user_id == user.id,
        Membership.organization_id == owner_workspace,
        Membership.role == "owner",
    ).first() is not None


def require_analytics_owner(user: User, db: Session) -> None:
    if not can_read_internal_analytics(user, db):
        raise HTTPException(status_code=403, detail={
            "code": "platform_analytics_owner_required",
            "message": "Os analytics internos estão reservados ao proprietário da plataforma SRIS.",
        })
