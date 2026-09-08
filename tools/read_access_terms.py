"""Read-only licence audit for one explicitly identified staging request."""
import argparse
import json
import os
from uuid import UUID
from sqlalchemy import create_engine, text
from app.atlas_platform.config import configured_database_url

parser = argparse.ArgumentParser()
parser.add_argument('--request-id', required=True, type=UUID)
args = parser.parse_args()
if os.getenv('RAILWAY_SERVICE_ID') != '5adcd02c-c875-499f-bd3b-b4d5ea256258':
    raise SystemExit('This audit is restricted to the Pilot staging service.')
engine = create_engine(configured_database_url(), pool_pre_ping=True)
with engine.connect() as conn:
    tx = conn.begin()
    conn.execute(text('SET TRANSACTION READ ONLY'))
    conn.execute(text("SET LOCAL statement_timeout='10s'"))
    row = conn.execute(text('''SELECT r.id AS request_id, r.status AS request_status,
        r.entitlement_days AS approved_days, r.reviewed_at, r.organization_id,
        e.plan_code, e.status AS licence_status, e.starts_at, e.expires_at,
        i.accepted_at AS invitation_accepted_at,
        EXISTS (SELECT 1 FROM users u JOIN memberships m ON m.user_id=u.id
            WHERE LOWER(u.email)=LOWER(r.email) AND m.organization_id=r.organization_id) AS membership_exists
        FROM sris_access_requests r
        LEFT JOIN sris_commercial_entitlements e ON e.organization_id=r.organization_id
        LEFT JOIN user_invitations i ON i.id=r.invitation_id
        WHERE r.id=:id'''), {'id':str(args.request_id)}).mappings().one_or_none()
    legacy = conn.execute(text('''SELECT COUNT(*) FROM memberships m
        JOIN users u ON u.id=m.user_id
        JOIN sris_access_requests r ON LOWER(r.email)=LOWER(u.email)
        JOIN sris_commercial_entitlements e ON e.organization_id=m.organization_id
        WHERE r.id=:id AND e.status='grandfathered' AND e.expires_at IS NULL'''),
        {'id':str(args.request_id)}).scalar()
    report = dict(row) if row else {'found':False}
    report['other_grandfathered_memberships'] = int(legacy or 0)
    report['enforcement_configured'] = os.getenv('SRIS_COMMERCIAL_ENTITLEMENT_ENFORCEMENT')
    print('SRIS_ACCESS_TERMS_READONLY', json.dumps(report,default=str,sort_keys=True))
    tx.rollback()
