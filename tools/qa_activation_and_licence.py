"""Full application routes; isolated SQLite and mocked email only."""
import os
import re
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

for name in list(os.environ):
    if name.startswith("RAILWAY_"):
        os.environ.pop(name)
os.environ.update(ATLAS_ENV="test", ATLAS_DATABASE_URL="sqlite+pysqlite:///:memory:",
    ATLAS_JWT_SECRET="isolated-activation-test-secret-at-least-32-bytes",
    SRIS_ACCESS_NOTIFICATIONS_ENABLED="false", SRIS_COMMERCIAL_ENTITLEMENT_ENFORCEMENT="true")
from fastapi.testclient import TestClient
from app.main import app
from app.atlas_platform import invitation_activation as module
from app.atlas_platform.auth_delivery import AuthDeliveryError
from app.atlas_platform.database import Base, engine, SessionLocal
from app.atlas_platform.models import User, Organization, Membership, UserInvitation, utcnow
from app.atlas_platform.commercial_access_models import CommercialEntitlement
from app.atlas_platform.identity import _token_hash, _as_utc
from app.atlas_platform.security import hash_password, verify_password, create_access_token

Base.metadata.create_all(engine)
client = TestClient(app)
passed = 0
old_password = "old-password-for-isolated-test"
new_password = "new-password-for-isolated-test"


def check(value, label):
    global passed
    assert value, label
    passed += 1
    print("SRIS_ACTIVATION_QA PASS", label)


with SessionLocal() as db:
    operator = User(email="operator@example.com", full_name="QA Operator", password_hash=hash_password(old_password))
    db.add(operator); db.commit(); operator_id = operator.id
os.environ["SRIS_ACCESS_APPROVER_EMAILS"] = "operator@example.com"


def fixture(existing=True):
    key = uuid4().hex
    with SessionLocal() as db:
        org = Organization(name="QA Workspace", slug="qa-"+key)
        db.add(org); db.flush()
        user = User(email=key+"@example.com", full_name="QA Applicant", password_hash=hash_password(old_password)) if existing else None
        if user: db.add(user); db.flush()
        token = "isolated-invitation-"+key
        invitation = UserInvitation(organization_id=org.id, email=key+"@example.com", full_name="QA Applicant", role="owner",
            token_hash=_token_hash("invite", token), invited_by_user_id=operator_id, expires_at=utcnow()+timedelta(hours=72), delivery_status="sent")
        entitlement = CommercialEntitlement(organization_id=org.id, plan_code="pilot", status="active", starts_at=utcnow(), expires_at=utcnow()+timedelta(days=90))
        db.add_all([invitation, entitlement]); db.commit()
        return {"token":token,"invitation":invitation.id,"org":org.id,"user":user.id if user else None,
            "expiry":_as_utc(entitlement.expires_at),"entitlement":entitlement.id}


def proof(f):
    sent=[]
    with patch.object(module,"send_transactional_email",side_effect=lambda **kw:sent.append(kw)):
        response=client.post("/api/auth/invitations/activation/send-code",json={"token":f["token"]})
    assert response.status_code==200, response.text
    return response.json()["proof_id"], re.search(r"\b[0-9]{8}\b",sent[0]["text_body"]).group(), sent


def complete(f, **kwargs):
    return client.post("/api/auth/invitations/activation/complete",json={"token":f["token"],"password":new_password,**kwargs})


f=fixture()
view=client.post("/api/auth/invitations/activation/inspect",json={"token":f["token"]})
check(view.status_code==200 and view.json()["mailbox_confirmation_required"],"existing user is offered password creation with mailbox proof")
check(view.json()["commercial_access"]["expires_at"] and not view.json()["commercial_access"]["automatic_renewal"],"invitation exposes finite terms, not automatic renewal")
check(complete(f).status_code==400,"invitation alone cannot replace an existing password")
id,code,sent=proof(f)
with SessionLocal() as db:
    row=db.get(module.ActivationProof,id)
    check(row.code_hash!=code and len(row.code_hash)==64,"code is stored only as a purpose-bound hash")
    check(verify_password(old_password,db.get(User,f["user"]).password_hash),"sending code does not change the password")
check(client.post("/api/auth/invitations/activation/send-code",json={"token":f["token"]}).status_code==429,"per-account send cooldown is enforced")
bad_code="00000000" if code!="00000000" else "99999999"
check(complete(f,proof_id=id,code=bad_code).status_code==400,"incorrect code cannot activate the account")
with SessionLocal() as db: check(db.get(module.ActivationProof,id).attempts==1,"failed confirmation attempt persists")
other=fixture()
check(complete(other,proof_id=id,code=code).status_code==400,"proof cannot be used on another account or invitation")
old_token=create_access_token(user_id=f["user"],auth_version=1)
accepted=complete(f,proof_id=id,code=code)
check(accepted.status_code==200, "correct code and chosen password activate existing account")
with SessionLocal() as db:
    user=db.get(User,f["user"])
    check(verify_password(new_password,user.password_hash) and not verify_password(old_password,user.password_hash),"new credential replaces old credential")
    check(user.auth_version==2 and db.get(module.ActivationProof,id).used_at is not None,"old sessions invalidated and proof consumed")
    check(db.query(Membership).filter_by(user_id=user.id,organization_id=f["org"]).count()==1,"workspace membership created exactly once")
    check(_as_utc(db.get(CommercialEntitlement,f["entitlement"]).expires_at)==f["expiry"],"activation never extends the commercial deadline")
check(complete(f,proof_id=id,code=code).status_code==404,"accepted invitation cannot be replayed")
check(client.get(f'/api/organizations/{f["org"]}/invitations',headers={"Authorization":"Bearer "+old_token}).status_code==401,"previous access token is rejected")
headers={"Authorization":"Bearer "+accepted.json()["access_token"]}
check(client.get(f'/api/organizations/{f["org"]}/invitations',headers=headers).status_code==200,"new credential accesses active licensed workspace")
with SessionLocal() as db:
    db.get(CommercialEntitlement,f["entitlement"]).expires_at=utcnow()-timedelta(seconds=1); db.commit()
blocked=client.get(f'/api/organizations/{f["org"]}/invitations',headers=headers)
check(blocked.status_code==403 and blocked.json()["detail"]["code"]=="commercial_entitlement_expired","licence expiry blocks backend despite valid login token")
check(client.get(f'/api/organizations/{f["org"]}/commercial-entitlement',headers=headers).status_code==200,"expired customer can still inspect licence state")
check(client.post(f'/api/admin/organizations/{f["org"]}/commercial-entitlement/renew',headers=headers,json={"term_days":30}).status_code==403,"customer owner cannot renew own commercial grant")
with SessionLocal() as db:
    check(db.get(User,f["user"]) is not None and db.query(Membership).filter_by(organization_id=f["org"]).count()==1,"expiry preserves account and membership")
operator_token=create_access_token(user_id=operator_id,auth_version=1)
renewed=client.post(f'/api/admin/organizations/{f["org"]}/commercial-entitlement/renew',headers={"Authorization":"Bearer "+operator_token},json={"term_days":30})
check(renewed.status_code==200 and renewed.json()["entitlement"]["status"]=="active","only authorized SRIS renewal restores the licence")
new=fixture(False)
check(complete(new,full_name="QA New Person").status_code==200,"new person creates password without any previous credential")
existing=fixture()
check(client.post("/api/auth/invitations/activation/complete",json={"token":existing["token"],"password":old_password,"use_current_password":True}).status_code==200,"existing password remains an optional safe route")
expired=fixture(); pid,c,_=proof(expired)
with SessionLocal() as db: db.get(module.ActivationProof,pid).expires_at=utcnow()-timedelta(seconds=1); db.commit()
check(complete(expired,proof_id=pid,code=c).status_code==400,"expired code cannot replace credentials")
rotated=fixture(); pid,c,_=proof(rotated)
with SessionLocal() as db: db.get(User,rotated["user"]).auth_version+=1; db.commit()
check(complete(rotated,proof_id=pid,code=c).status_code==400,"credential-version change invalidates pending code")
limited=fixture(); pid,c,_=proof(limited)
for _ in range(5): complete(limited,proof_id=pid,code="00000000" if c!="00000000" else "99999999")
check(complete(limited,proof_id=pid,code=c).status_code==400,"five failed attempts exhaust a code")
failed=fixture()
with patch.object(module,"send_transactional_email",side_effect=AuthDeliveryError("test failure")):
    response=client.post("/api/auth/invitations/activation/send-code",json={"token":failed["token"]})
check(response.status_code==503,"delivery failure is not falsely presented as a sent code")
with SessionLocal() as db: check(verify_password(old_password,db.get(User,failed["user"]).password_hash),"delivery failure preserves the existing credential")
page=client.get('/account.html')
check(page.status_code==200 and 'id="invite-confirm"' in page.text and '/activation-v42.js' in page.text,"live route serves password creation and confirmation fields")
print('SRIS_ACTIVATION_QA_RESULT',{'passed':passed,'failed':0,'database':'isolated SQLite','email':'mocked; no real sends'})
