from __future__ import annotations

import json

from sqlalchemy.orm import Session

from .models import AuditEvent


def record_audit(
    db: Session,
    *,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    organization_id: str | None = None,
    user_id: str | None = None,
    payload: dict | None = None,
) -> None:
    db.add(
        AuditEvent(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            organization_id=organization_id,
            user_id=user_id,
            payload_json=json.dumps(payload or {}, ensure_ascii=False),
        )
    )
