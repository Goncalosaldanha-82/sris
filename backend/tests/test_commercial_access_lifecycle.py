from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.atlas_platform import commercial_access
from app.atlas_platform.commercial_access_models import (
    AccessRequest,
    CommercialEntitlement,
    get_entitlement,
    utcnow,
)
from app.atlas_platform.database import Base, SessionLocal, engine
from app.atlas_platform.models import Membership, User, UserInvitation
from app.main import app


Base.metadata.create_all(bind=engine)
client = TestClient(app)


def _register_and_login(email: str, password: str = "approver-password-123") -> dict[str, str]:
    registered = client.post(
        "/api/auth/register",
        json={"email": email, "full_name": "SRIS Approver", "password": password},
    )
    assert registered.status_code == 201, registered.text
    logged = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert logged.status_code == 200, logged.text
    return {"Authorization": f"Bearer {logged.json()['access_token']}"}


def _request(email: str, organization_name: str = "Access Lab") -> None:
    response = client.post(
        "/api/access-requests",
        json={
            "email": email,
            "full_name": "Requested Owner",
            "organization_name": organization_name,
        },
    )
    assert response.status_code == 202, response.text
    assert "convite" in response.json()["message"].lower()


def _request_id(headers: dict[str, str], email: str) -> str:
    listed = client.get("/api/admin/access-requests", headers=headers)
    assert listed.status_code == 200, listed.text
    item = next(row for row in listed.json()["requests"] if row["email"] == email)
    return item["id"]


def test_public_access_request_is_pre_auth_and_non_enumerating(monkeypatch) -> None:
    suffix = uuid4().hex[:10]
    email = f"access-request-{suffix}@example.com"
    _request(email)
    _request(email)

    with SessionLocal() as db:
        assert db.query(User).filter(User.email == email).one_or_none() is None
        requests = db.query(AccessRequest).filter(AccessRequest.email == email).all()
        assert len(requests) == 1
        assert requests[0].status == "pending"


def test_approval_requires_explicit_platform_approver(monkeypatch) -> None:
    suffix = uuid4().hex[:10]
    approver_email = f"not-approver-{suffix}@example.com"
    headers = _register_and_login(approver_email)
    _request(f"candidate-{suffix}@example.com")
    monkeypatch.delenv("SRIS_ACCESS_APPROVER_EMAILS", raising=False)
    monkeypatch.delenv("SRIS_PLATFORM_ADMIN_EMAILS", raising=False)

    response = client.get("/api/admin/access-requests", headers=headers)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "platform_approval_required"


def test_approval_creates_workspace_entitlement_and_single_use_owner_invite(monkeypatch) -> None:
    suffix = uuid4().hex[:10]
    approver_email = f"approver-{suffix}@example.com"
    candidate_email = f"candidate-{suffix}@example.com"
    candidate_password = "candidate-password-123"
    headers = _register_and_login(approver_email)
    monkeypatch.setenv("SRIS_ACCESS_APPROVER_EMAILS", approver_email)
    monkeypatch.setattr(commercial_access, "auth_email_delivery_ready", lambda: True)
    captured: list[tuple[str, str]] = []
    monkeypatch.setattr(
        commercial_access,
        "_send_invitation_email",
        lambda invitation_id, raw_token: captured.append((invitation_id, raw_token)),
    )

    _request(candidate_email, f"Governed Workspace {suffix}")
    request_id = _request_id(headers, candidate_email)
    approved = client.post(
        f"/api/admin/access-requests/{request_id}/approve",
        headers=headers,
        json={"plan_code": "professional", "entitlement_days": 120},
    )
    assert approved.status_code == 200, approved.text
    body = approved.json()
    organization_id = body["workspace"]["id"]
    assert body["entitlement"]["status"] == "active"
    assert body["entitlement"]["plan_code"] == "professional"
    assert body["invitation"]["role"] == "owner"
    assert captured and captured[-1][0] == body["invitation"]["id"]
    raw_token = captured[-1][1]

    with SessionLocal() as db:
        assert db.query(User).filter(User.email == candidate_email).one_or_none() is None
        invitation = db.get(UserInvitation, body["invitation"]["id"])
        assert invitation is not None
        assert invitation.token_hash != raw_token
        entitlement = get_entitlement(db, organization_id)
        assert entitlement is not None
        assert entitlement.plan_code == "professional"

    accepted = client.post(
        "/api/auth/invitations/accept",
        json={
            "token": raw_token,
            "password": candidate_password,
            "full_name": "Requested Owner",
        },
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["organization_id"] == organization_id

    repeated = client.post(
        "/api/auth/invitations/accept",
        json={
            "token": raw_token,
            "password": candidate_password,
            "full_name": "Requested Owner",
        },
    )
    assert repeated.status_code in {400, 404, 409}

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == candidate_email).one()
        membership = (
            db.query(Membership)
            .filter(
                Membership.user_id == user.id,
                Membership.organization_id == organization_id,
            )
            .one()
        )
        assert membership.role == "owner"


def test_expired_entitlement_blocks_workspace_operations_and_renewal_reactivates(monkeypatch) -> None:
    suffix = uuid4().hex[:10]
    approver_email = f"renew-approver-{suffix}@example.com"
    candidate_email = f"renew-candidate-{suffix}@example.com"
    candidate_password = "candidate-password-123"
    headers = _register_and_login(approver_email)
    monkeypatch.setenv("SRIS_ACCESS_APPROVER_EMAILS", approver_email)
    monkeypatch.setenv("SRIS_COMMERCIAL_ENTITLEMENT_ENFORCEMENT", "true")
    monkeypatch.setattr(commercial_access, "auth_email_delivery_ready", lambda: True)
    captured: list[tuple[str, str]] = []
    monkeypatch.setattr(
        commercial_access,
        "_send_invitation_email",
        lambda invitation_id, raw_token: captured.append((invitation_id, raw_token)),
    )

    _request(candidate_email, f"Renewal Workspace {suffix}")
    request_id = _request_id(headers, candidate_email)
    approved = client.post(
        f"/api/admin/access-requests/{request_id}/approve",
        headers=headers,
        json={"plan_code": "pilot", "entitlement_days": 30},
    )
    assert approved.status_code == 200, approved.text
    organization_id = approved.json()["workspace"]["id"]
    raw_token = captured[-1][1]
    accepted = client.post(
        "/api/auth/invitations/accept",
        json={
            "token": raw_token,
            "password": candidate_password,
            "full_name": "Requested Owner",
        },
    )
    assert accepted.status_code == 200, accepted.text
    owner_headers = {"Authorization": f"Bearer {accepted.json()['access_token']}"}

    with SessionLocal() as db:
        entitlement = (
            db.query(CommercialEntitlement)
            .filter(CommercialEntitlement.organization_id == organization_id)
            .one()
        )
        entitlement.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()

    blocked = client.get(
        f"/api/organizations/{organization_id}/invitations",
        headers=owner_headers,
    )
    assert blocked.status_code == 403, blocked.text
    assert blocked.json()["detail"]["code"] == "commercial_entitlement_expired"

    # Expiry does not remove the account, membership or right to inspect the
    # commercial state needed to resolve the access problem.
    state = client.get(
        f"/api/organizations/{organization_id}/commercial-entitlement",
        headers=owner_headers,
    )
    assert state.status_code == 200, state.text
    assert state.json()["status"] == "expired"

    renewed = client.post(
        f"/api/admin/organizations/{organization_id}/commercial-entitlement/renew",
        headers=headers,
        json={"term_days": 365, "plan_code": "professional"},
    )
    assert renewed.status_code == 200, renewed.text
    assert renewed.json()["entitlement"]["status"] == "active"
    assert renewed.json()["entitlement"]["plan_code"] == "professional"
    assert renewed.json()["entitlement"]["renewal_count"] == 1

    restored = client.get(
        f"/api/organizations/{organization_id}/invitations",
        headers=owner_headers,
    )
    assert restored.status_code == 200, restored.text
