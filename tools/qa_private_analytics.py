"""Real application authorization routes, isolated database and synthetic identities."""
import os
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

for name in list(os.environ):
    if name.startswith("RAILWAY_"):
        os.environ.pop(name)
os.environ.update(ATLAS_ENV="test", ATLAS_DATABASE_URL="sqlite+pysqlite:///:memory:",
    ATLAS_JWT_SECRET="isolated-private-analytics-test-secret-at-least-32-bytes",
    SRIS_ACCESS_NOTIFICATIONS_ENABLED="false", SRIS_COMMERCIAL_ENTITLEMENT_ENFORCEMENT="true",
    SRIS_ANALYTICS_INGEST_TOKEN="isolated-ingest-only-token")

from fastapi.testclient import TestClient
from sqlalchemy import event
from app.main import app
from app.analytics_access import configured_analytics_owner
from app.atlas_platform.database import Base, engine, SessionLocal
from app.atlas_platform.models import User, Membership, Organization, utcnow
from app.atlas_platform.commercial_access_models import CommercialEntitlement
from app.atlas_platform.security import create_access_token, hash_password
from app.internal_analytics import InternalAnalyticsEvent

Base.metadata.create_all(engine)
client = TestClient(app)
passed = 0

def check(condition, label):
    global passed
    assert condition, label
    passed += 1
    print("SRIS_ANALYTICS_QA PASS", label)


def organization(db, label):
    row = Organization(name=label, slug="qa-"+uuid4().hex)
    db.add(row);db.flush()
    db.add(CommercialEntitlement(organization_id=row.id, plan_code="pilot", status="active",
        starts_at=utcnow(), expires_at=utcnow()+timedelta(days=90)))
    return row.id

with SessionLocal() as db:
    internal_org = organization(db, "Internal SRIS QA")
    tenant_org = organization(db, "Customer QA")
    users = {}
    for name, role, org in [
        ("operator", "owner", internal_org), ("tenant-owner", "owner", tenant_org),
        ("tenant-admin", "admin", tenant_org), ("tenant-member", "contributor", tenant_org),
        ("other-internal-owner", "owner", internal_org), ("same-domain", "owner", tenant_org),
    ]:
        user = User(email=name+"@example.com", full_name="Synthetic QA",
                    password_hash=hash_password("isolated-test-password"), is_active=True)
        db.add(user);db.flush()
        db.add(Membership(user_id=user.id, organization_id=org, role=role))
        users[name] = user.id
    db.add(InternalAnalyticsEvent(event_name="site_view", surface="site", source="private-qa-sentinel"))
    db.commit()

os.environ["SRIS_ANALYTICS_OWNER_EMAIL"] = "operator@example.com"
os.environ["SRIS_ANALYTICS_OWNER_WORKSPACE_ID"] = internal_org
os.environ["SRIS_ACCESS_APPROVER_EMAILS"] = "tenant-owner@example.com"

def headers(name, **extra):
    return {"Authorization": "Bearer "+create_access_token(user_id=users[name],auth_version=1), **extra}

def summary(name, **extra):
    return client.get("/api/internal-analytics/summary?days=30",headers=headers(name, **extra))

response = client.get("/api/internal-analytics/summary")
check(response.status_code==401, "anonymous cannot read analytics")
response = summary("operator")
check(response.status_code==200 and response.json()["views"]["site"]==1, "pinned internal proprietor can read counters")
check("no-store" in response.headers.get("cache-control", ""), "authorized summary is not cached")
for name in ("tenant-owner","tenant-admin","tenant-member","other-internal-owner","same-domain"):
    response = summary(name)
    check(response.status_code==403 and response.json()["detail"]["code"]=="platform_analytics_owner_required",
          name+" is denied despite valid authentication and active licence")
    assert "private-qa-sentinel" not in response.text
response = summary("tenant-owner", **{"X-SRIS-Organization": internal_org, "X-User-Email": "operator@example.com"})
check(response.status_code==403 and "platform_analytics_owner_required" in response.text,
      "forged internal workspace or identity headers do not authorize")

queries=[]
def capture(_conn,_cursor,statement,*_args):
    queries.append(statement.lower())
event.listen(engine,"before_cursor_execute",capture)
summary("tenant-owner")
event.remove(engine,"before_cursor_execute",capture)
check(not any("sris_internal_analytics_events" in sql for sql in queries), "denied request never queries private event table")

for key in ("SRIS_ANALYTICS_OWNER_EMAIL","SRIS_ANALYTICS_OWNER_WORKSPACE_ID"):
    previous=os.environ.pop(key)
    check(summary("operator").status_code==403, "missing "+key+" fails closed")
    os.environ[key]=previous
old=os.environ["SRIS_ANALYTICS_OWNER_EMAIL"]
os.environ["SRIS_ANALYTICS_OWNER_EMAIL"]="*@example.com"
check(configured_analytics_owner() is None and summary("operator").status_code==403, "wildcards do not grant analytics access")
os.environ["SRIS_ANALYTICS_OWNER_EMAIL"]=old
os.environ["SRIS_ANALYTICS_OWNER_WORKSPACE_ID"]=tenant_org
check(summary("operator").status_code==403, "owner email alone without pinned membership is insufficient")
os.environ["SRIS_ANALYTICS_OWNER_WORKSPACE_ID"]=internal_org

with SessionLocal() as db:
    membership=db.query(Membership).filter(Membership.user_id==users["operator"], Membership.organization_id==internal_org).one()
    membership.role="admin";db.commit()
check(summary("operator").status_code==403, "internal ownership withdrawal takes effect without a new login")
with SessionLocal() as db:
    membership=db.query(Membership).filter(Membership.user_id==users["operator"]).one()
    membership.role="owner";db.get(User, users["operator"]).auth_version=2;db.commit()
check(summary("operator").status_code==401, "revoked session does not retain access")
with SessionLocal() as db:
    user=db.get(User, users["operator"]);user.auth_version=1;user.is_active=False;db.commit()
check(summary("operator").status_code==401, "inactive proprietor cannot read analytics")
with SessionLocal() as db:
    db.get(User, users["operator"]).is_active=True;db.commit()

response=client.post("/api/internal-analytics/collect", headers={"X-SRIS-Analytics-Token":"isolated-ingest-only-token"},
    json={"event_name":"demo_view","surface":"demo","source":"qa"})
check(response.status_code==204 and summary("operator").json()["views"]["demo"]==1, "event collection and counters are preserved")
response=client.get("/api/internal-analytics/summary",headers={"X-SRIS-Analytics-Token":"isolated-ingest-only-token"})
check(response.status_code==401, "ingestion token grants no read access")
response=client.post("/api/internal-analytics/collect",headers=headers("tenant-owner"),json={"event_name":"demo_view","surface":"demo"})
check(response.status_code==403, "customer role grants no ingestion privilege")

shell=client.get("/admin/analytics")
check(shell.status_code==200 and "private-qa-sentinel" not in shell.text and 'class="value"' not in shell.text,
      "direct dashboard URL serves only an empty shell without metrics")
check("no-store" in shell.headers.get("cache-control", ""), "private dashboard shell is not cached")
root=Path(__file__).resolve().parents[1]
digest=sha256((root/"frontend/pilot-v1/analytics-ui-v1.js").read_bytes()).hexdigest()[:16]
response=client.get("/app")
check(response.status_code==200 and "analytics-owner-v43-"+digest in response.text,
      "served application fingerprints actual security-corrected JavaScript")
check('id="analytics-nav-group" hidden' in response.text and 'aria-label="Leitura privada de interesse" hidden' in response.text,
      "both analytics surfaces are initially hidden")
script=client.get("/analytics-ui-v1.js")
check("no-store" in script.headers.get("cache-control", "") and "ADMIN_ROLES" not in script.text,
      "served JavaScript does not infer access from tenant role")
print("SRIS_ANALYTICS_QA_RESULT", {"passed":passed,"failed":0,"database":"isolated SQLite","authentication":"real application JWT/RBAC routes; synthetic users"})
