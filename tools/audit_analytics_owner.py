"""Read-only staging check: count permitted identities without exposing PII."""
import json
import os
from sqlalchemy import text
from app.analytics_access import can_read_internal_analytics, configured_analytics_owner
from app.atlas_platform.database import SessionLocal
from app.atlas_platform.models import Membership, User

with SessionLocal() as db:
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SET TRANSACTION READ ONLY"))
        db.execute(text("SET LOCAL statement_timeout='10s'"))
    active=db.query(User).filter(User.is_active.is_(True)).all()
    permitted=[u.id for u in active if can_read_internal_analytics(u,db)]
    privileged={m.user_id for m in db.query(Membership).filter(Membership.role.in_(["owner","admin"])).all()}
    report={"policy_configured":configured_analytics_owner() is not None,
        "allowed_active_accounts":len(permitted),
        "other_active_workspace_administrators_denied":sum(u.id in privileged and u.id not in permitted for u in active),
        "read_only":True,"account_data_emitted":False}
    db.rollback()
print("SRIS_ANALYTICS_OWNER_AUDIT",json.dumps(report,sort_keys=True))
if not report["policy_configured"] or report["allowed_active_accounts"] != 1:
    raise SystemExit("Analytics requires exactly one active, explicitly configured platform proprietor.")
