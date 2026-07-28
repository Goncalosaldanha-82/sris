from fastapi.encoders import jsonable_encoder
from app.models.models import AuditLog

def record_audit(db, organization_id, actor_user_id, action, resource_type, resource_id=None, before=None, after=None, request_id=None, ip_address=None):
    row=AuditLog(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        before=jsonable_encoder(before) if before is not None else None,
        after=jsonable_encoder(after) if after is not None else None,
        request_id=request_id,
        ip_address=ip_address,
    )
    db.add(row)
    return row
