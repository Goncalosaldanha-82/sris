"""Read-only verification of one approved request; emits no email or secrets."""
import argparse
import json
import os
from sqlalchemy import text
from app.atlas_platform.database import SessionLocal

parser=argparse.ArgumentParser()
parser.add_argument('--request-id',required=True)
args=parser.parse_args()
if os.getenv('RAILWAY_SERVICE_ID')!='5adcd02c-c875-499f-bd3b-b4d5ea256258' or os.getenv('RAILWAY_ENVIRONMENT_ID')!='625472d4-144c-460a-b152-d1890f1f80db':
    raise SystemExit('Read-only inspection restricted to SRIS staging')
with SessionLocal() as db:
    db.execute(text('SET TRANSACTION READ ONLY'))
    db.execute(text("SET LOCAL statement_timeout='10s'"))
    row=db.execute(text('''SELECT r.status AS request_status, i.delivery_status,
        i.accepted_at IS NOT NULL AS invitation_accepted,
        i.revoked_at IS NOT NULL AS invitation_revoked,
        i.expires_at > CURRENT_TIMESTAMP AS invitation_within_validity,
        u.id IS NOT NULL AS account_exists, u.is_active AS account_active,
        m.id IS NOT NULL AS workspace_membership_exists
        FROM sris_access_requests r JOIN user_invitations i ON i.id=r.invitation_id
        LEFT JOIN users u ON LOWER(u.email)=LOWER(r.email)
        LEFT JOIN memberships m ON m.user_id=u.id AND m.organization_id=r.organization_id
        WHERE r.id=:request_id'''),{'request_id':args.request_id}).mappings().one_or_none()
    print('SRIS_APPROVED_ACCESS_CHECK '+json.dumps(dict(row) if row else {'found':False},sort_keys=True))
    db.rollback()
