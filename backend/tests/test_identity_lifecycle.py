from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.atlas_platform import auth_delivery, identity
from app.atlas_platform.database import Base, SessionLocal, engine
from app.atlas_platform.models import PasswordResetToken, User, UserInvitation
from app.main import app


Base.metadata.create_all(bind=engine)
client = TestClient(app)


def test_managed_email_delivery_requires_https_and_transport_security(
    monkeypatch,
) -> None:
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "identity-staging")
    monkeypatch.setenv("SRIS_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SRIS_SMTP_FROM_EMAIL", "access@example.com")
    monkeypatch.setenv("SRIS_SMTP_SECURITY", "none")
    monkeypatch.setenv("SRIS_PUBLIC_BASE_URL", "http://sris.example.com")
    assert auth_delivery.smtp_configuration() is None

    monkeypatch.setenv("SRIS_SMTP_SECURITY", "starttls")
    monkeypatch.setenv("SRIS_PUBLIC_BASE_URL", "https://sris.example.com")
    assert auth_delivery.smtp_configuration() is not None


def _owner() -> tuple[dict[str, str], str, str]:
    suffix = uuid4().hex[:10]
    email = f"identity-owner-{suffix}@example.com"
    password = "owner-password-123"
    registered = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "full_name": "Identity Owner",
            "password": password,
        },
    )
    assert registered.status_code == 201, registered.text
    logged_in = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert logged_in.status_code == 200, logged_in.text
    headers = {
        "Authorization": f"Bearer {logged_in.json()['access_token']}"
    }
    organization = client.post(
        "/api/organizations",
        headers=headers,
        json={
            "name": f"Identity Lab {suffix}",
            "slug": f"identity-lab-{suffix}",
        },
    )
    assert organization.status_code == 201, organization.text
    return headers, organization.json()["id"], email


def _capture_auth_links(monkeypatch) -> list[tuple[str, str]]:
    captured: list[tuple[str, str]] = []
    monkeypatch.setattr(identity, "auth_email_delivery_ready", lambda: True)

    def build_link(flow: str, raw_token: str) -> str:
        captured.append((flow, raw_token))
        return f"https://sris.example/account.html#{flow}={raw_token}"

    monkeypatch.setattr(identity, "build_auth_link", build_link)
    monkeypatch.setattr(
        identity,
        "send_transactional_email",
        lambda **_: None,
    )
    return captured


def test_owner_invites_new_user_and_invitation_is_single_use(monkeypatch) -> None:
    captured = _capture_auth_links(monkeypatch)
    headers, organization_id, _ = _owner()
    suffix = uuid4().hex[:10]
    invited_email = f"new-user-{suffix}@example.com"

    invited = client.post(
        f"/api/organizations/{organization_id}/invitations",
        headers=headers,
        json={
            "email": invited_email,
            "full_name": "New Contributor",
            "role": "contributor",
        },
    )
    assert invited.status_code == 201, invited.text
    assert captured and captured[-1][0] == "invite"
    invitation_token = captured[-1][1]

    public_details = client.post(
        "/api/auth/invitations/inspect",
        json={"token": invitation_token},
    )
    assert public_details.status_code == 200, public_details.text
    assert public_details.json()["email"] == invited_email
    assert public_details.json()["existing_account"] is False

    accepted = client.post(
        "/api/auth/invitations/accept",
        json={
            "token": invitation_token,
            "password": "new-user-password-123",
            "full_name": "New Contributor",
        },
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["organization_id"] == organization_id
    assert accepted.json()["refresh_token"]
    invited_headers = {
        "Authorization": f"Bearer {accepted.json()['access_token']}"
    }
    me = client.get("/api/auth/me", headers=invited_headers)
    assert me.status_code == 200, me.text
    assert me.json()["email"] == invited_email
    own_membership = client.get(
        f"/api/organizations/{organization_id}/membership",
        headers=invited_headers,
    )
    assert own_membership.status_code == 200, own_membership.text
    assert own_membership.json()["role"] == "contributor"

    memberships = client.get(
        f"/api/organizations/{organization_id}/memberships",
        headers=headers,
    )
    assert memberships.status_code == 200, memberships.text
    contributor = next(
        item for item in memberships.json() if item["email"] == invited_email
    )
    assert contributor["role"] == "contributor"

    changed = client.patch(
        f"/api/organizations/{organization_id}/memberships/{contributor['id']}",
        headers=headers,
        json={"role": "observer"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["role"] == "observer"
    assert client.get(
        f"/api/organizations/{organization_id}/membership",
        headers=invited_headers,
    ).json()["role"] == "observer"

    removed = client.delete(
        f"/api/organizations/{organization_id}/memberships/{contributor['id']}",
        headers=headers,
    )
    assert removed.status_code == 204, removed.text
    assert client.get(
        f"/api/organizations/{organization_id}/membership",
        headers=invited_headers,
    ).status_code == 403

    replay = client.post(
        "/api/auth/invitations/accept",
        json={
            "token": invitation_token,
            "password": "replacement-password-456",
        },
    )
    assert replay.status_code == 404


def test_existing_user_must_confirm_password_to_accept_second_org_invite(
    monkeypatch,
) -> None:
    captured = _capture_auth_links(monkeypatch)
    first_headers, _, existing_email = _owner()
    second_headers, second_organization_id, _ = _owner()

    invited = client.post(
        f"/api/organizations/{second_organization_id}/invitations",
        headers=second_headers,
        json={
            "email": existing_email,
            "full_name": "Existing Owner",
            "role": "observer",
        },
    )
    assert invited.status_code == 201, invited.text
    invitation_token = captured[-1][1]
    details = client.post(
        "/api/auth/invitations/inspect",
        json={"token": invitation_token},
    )
    assert details.status_code == 200
    assert details.json()["existing_account"] is True

    rejected = client.post(
        "/api/auth/invitations/accept",
        json={
            "token": invitation_token,
            "password": "wrong-password-123",
        },
    )
    assert rejected.status_code == 401

    accepted = client.post(
        "/api/auth/invitations/accept",
        json={
            "token": invitation_token,
            "password": "owner-password-123",
        },
    )
    assert accepted.status_code == 200, accepted.text
    assert client.get("/api/auth/me", headers=first_headers).status_code == 200


def test_invitation_resend_rotates_secret_and_revocation_closes_link(
    monkeypatch,
) -> None:
    captured = _capture_auth_links(monkeypatch)
    headers, organization_id, _ = _owner()
    invited_email = f"rotate-{uuid4().hex[:10]}@example.com"
    payload = {
        "email": invited_email,
        "full_name": "Rotating Invite",
        "role": "observer",
    }
    invited = client.post(
        f"/api/organizations/{organization_id}/invitations",
        headers=headers,
        json=payload,
    )
    assert invited.status_code == 201, invited.text
    invitation_id = invited.json()["id"]
    original_token = captured[-1][1]

    with SessionLocal() as db:
        stored = db.get(UserInvitation, invitation_id)
        assert stored is not None
        assert stored.token_hash != original_token
        assert len(stored.token_hash) == 64

    duplicate = client.post(
        f"/api/organizations/{organization_id}/invitations",
        headers=headers,
        json=payload,
    )
    assert duplicate.status_code == 409

    resent = client.post(
        f"/api/organizations/{organization_id}/invitations/{invitation_id}/resend",
        headers=headers,
    )
    assert resent.status_code == 200, resent.text
    replacement_token = captured[-1][1]
    assert replacement_token != original_token
    assert client.post(
        "/api/auth/invitations/inspect",
        json={"token": original_token},
    ).status_code == 404
    assert client.post(
        "/api/auth/invitations/inspect",
        json={"token": replacement_token},
    ).status_code == 200

    revoked = client.delete(
        f"/api/organizations/{organization_id}/invitations/{invitation_id}",
        headers=headers,
    )
    assert revoked.status_code == 204, revoked.text
    assert client.post(
        "/api/auth/invitations/inspect",
        json={"token": replacement_token},
    ).status_code == 404


def test_password_reset_is_generic_single_use_and_revokes_sessions(
    monkeypatch,
) -> None:
    captured = _capture_auth_links(monkeypatch)
    headers, _, email = _owner()
    active_session = client.post(
        "/api/auth/login",
        json={"email": email, "password": "owner-password-123"},
    )
    assert active_session.status_code == 200, active_session.text
    refresh_token = active_session.json()["refresh_token"]

    unknown = client.post(
        "/api/auth/password-reset/request",
        json={"email": f"unknown-{uuid4().hex}@example.com"},
    )
    assert unknown.status_code == 202
    assert unknown.json()["status"] == "accepted"
    assert captured == []

    requested = client.post(
        "/api/auth/password-reset/request",
        json={"email": email},
    )
    assert requested.status_code == 202, requested.text
    assert captured and captured[-1][0] == "reset"
    reset_token = captured[-1][1]
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).one()
        stored_reset = (
            db.query(PasswordResetToken)
            .filter(PasswordResetToken.user_id == user.id)
            .order_by(PasswordResetToken.requested_at.desc())
            .first()
        )
        assert stored_reset is not None
        assert stored_reset.token_hash != reset_token
        assert len(stored_reset.token_hash) == 64

    confirmed = client.post(
        "/api/auth/password-reset/confirm",
        json={
            "token": reset_token,
            "new_password": "reset-password-456",
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json() == {"status": "password_updated"}

    # Changing the password increments auth_version, invalidating earlier JWTs.
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token},
    ).status_code == 401
    assert client.post(
        "/api/auth/login",
        json={"email": email, "password": "owner-password-123"},
    ).status_code == 401
    assert client.post(
        "/api/auth/login",
        json={"email": email, "password": "reset-password-456"},
    ).status_code == 200

    replay = client.post(
        "/api/auth/password-reset/confirm",
        json={
            "token": reset_token,
            "new_password": "another-password-789",
        },
    )
    assert replay.status_code == 400


def test_admin_cannot_invite_another_admin(monkeypatch) -> None:
    captured = _capture_auth_links(monkeypatch)
    owner_headers, organization_id, _ = _owner()
    admin_email = f"admin-{uuid4().hex[:10]}@example.com"
    invited = client.post(
        f"/api/organizations/{organization_id}/invitations",
        headers=owner_headers,
        json={
            "email": admin_email,
            "full_name": "Organization Admin",
            "role": "admin",
        },
    )
    assert invited.status_code == 201, invited.text
    accepted = client.post(
        "/api/auth/invitations/accept",
        json={
            "token": captured[-1][1],
            "password": "admin-password-123",
        },
    )
    admin_headers = {
        "Authorization": f"Bearer {accepted.json()['access_token']}"
    }

    forbidden = client.post(
        f"/api/organizations/{organization_id}/invitations",
        headers=admin_headers,
        json={
            "email": f"peer-{uuid4().hex[:10]}@example.com",
            "full_name": "Peer Admin",
            "role": "admin",
        },
    )
    assert forbidden.status_code == 403


def test_identity_frontend_exposes_invite_and_recovery_flows() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    login = (repo_root / "frontend" / "atlas-os" / "index.html").read_text(
        encoding="utf-8"
    )
    account = (
        repo_root / "frontend" / "atlas-os" / "account.html"
    ).read_text(encoding="utf-8")
    users = (repo_root / "frontend" / "atlas-os" / "users.html").read_text(
        encoding="utf-8"
    )

    assert "/account.html?mode=forgot" in login
    assert 'id="usersLink"' in login
    assert "/api/auth/password-reset/request" in account
    assert "/api/auth/password-reset/confirm" in account
    assert "/api/auth/invitations/accept" in account
    assert "/invitations" in users
    assert "/memberships" in users

    account_response = client.get("/account.html")
    users_response = client.get("/users.html")
    assert account_response.status_code == 200
    assert users_response.status_code == 200
    assert "frame-ancestors 'none'" in account_response.headers[
        "content-security-policy"
    ]
