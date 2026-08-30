from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.atlas_platform import auth_delivery, identity
from app.atlas_platform.database import Base, SessionLocal, engine
from app.atlas_platform.models import (
    Membership,
    Organization,
    PasswordResetToken,
    Role,
    User,
    UserInvitation,
)
from app.main import app


Base.metadata.create_all(bind=engine)
client = TestClient(app)


def _clear_delivery_environment(monkeypatch) -> None:
    for name in (
        "SRIS_EMAIL_PROVIDER",
        "SRIS_EMAIL_FROM",
        "RESEND_API_KEY",
        "BREVO_API_KEY",
        "SRIS_SMTP_HOST",
        "SRIS_SMTP_USERNAME",
        "SRIS_SMTP_PASSWORD",
        "SRIS_SMTP_FROM_EMAIL",
    ):
        monkeypatch.delenv(name, raising=False)


def test_managed_email_delivery_requires_https_and_transport_security(
    monkeypatch,
) -> None:
    _clear_delivery_environment(monkeypatch)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "identity-staging")
    monkeypatch.setenv("SRIS_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SRIS_SMTP_FROM_EMAIL", "access@example.com")
    monkeypatch.setenv("SRIS_SMTP_SECURITY", "none")
    monkeypatch.setenv("SRIS_PUBLIC_BASE_URL", "http://sris.example.com")
    assert auth_delivery.smtp_configuration() is None

    monkeypatch.setenv("SRIS_SMTP_SECURITY", "starttls")
    monkeypatch.setenv("SRIS_PUBLIC_BASE_URL", "https://sris.example.com")
    assert auth_delivery.smtp_configuration() is not None


def test_resend_is_a_first_class_fail_closed_identity_transport(monkeypatch) -> None:
    _clear_delivery_environment(monkeypatch)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "identity-staging")
    monkeypatch.setenv("SRIS_EMAIL_PROVIDER", "resend")
    monkeypatch.setenv("SRIS_EMAIL_FROM", "access@example.com")
    monkeypatch.setenv("SRIS_PUBLIC_BASE_URL", "https://sris.example.com")
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    configuration = auth_delivery.auth_delivery_configuration()
    assert configuration is not None
    assert configuration.provider == "resend"
    assert auth_delivery.build_auth_link("reset", "secret").startswith(
        "https://sris.example.com/account.html#reset="
    )

    monkeypatch.setenv("BREVO_API_KEY", "another-test-key")
    monkeypatch.delenv("SRIS_EMAIL_PROVIDER")
    assert auth_delivery.auth_delivery_configuration() is None


def test_resend_delivery_uses_json_api_without_exposing_key(monkeypatch) -> None:
    _clear_delivery_environment(monkeypatch)
    monkeypatch.setenv("SRIS_EMAIL_PROVIDER", "resend")
    monkeypatch.setenv("SRIS_EMAIL_FROM", "access@example.com")
    monkeypatch.setenv("SRIS_PUBLIC_BASE_URL", "https://sris.example.com")
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    captured = {}

    class Response:
        status = 202

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(auth_delivery, "urlopen", fake_urlopen)
    auth_delivery.send_transactional_email(
        recipient="person@example.com",
        subject="Ativar acesso",
        text_body="Texto",
        html_body="<p>Texto</p>",
    )
    request = captured["request"]
    assert request.full_url == "https://api.resend.com/emails"
    assert request.get_header("Authorization") == "Bearer test-key"
    assert b"person@example.com" in request.data


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


def test_exact_email_gate_bootstraps_first_owner_through_normal_reset(
    monkeypatch,
) -> None:
    captured = _capture_auth_links(monkeypatch)
    suffix = uuid4().hex[:10]
    owner_email = f"institutional-owner-{suffix}@example.com"
    organization_slug = f"sris-{suffix}"
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "identity-staging")
    monkeypatch.setenv("ATLAS_SELF_REGISTRATION_ENABLED", "false")
    monkeypatch.setenv("ATLAS_ORGANIZATION_CREATION_ENABLED", "false")
    monkeypatch.setenv("SRIS_ACCESS_ACTIVATION_EMAIL", owner_email)
    monkeypatch.setenv(
        "SRIS_ACCESS_ACTIVATION_ORGANIZATION_SLUG",
        organization_slug,
    )
    monkeypatch.setenv("SRIS_ACCESS_ACTIVATION_ORGANIZATION_NAME", "SRIS")
    monkeypatch.setenv("SRIS_ACCESS_ACTIVATION_FULL_NAME", "Gonçalo Saldanha")

    unrelated_email = f"not-gated-{suffix}@example.com"
    unrelated = client.post(
        "/api/auth/password-reset/request",
        json={"email": unrelated_email},
    )
    assert unrelated.status_code == 202
    with SessionLocal() as db:
        assert db.query(User).filter(User.email == unrelated_email).first() is None

    requested = client.post(
        "/api/auth/password-reset/request",
        json={"email": owner_email},
    )
    assert requested.status_code == 202, requested.text
    assert captured and captured[-1][0] == "reset"
    reset_token = captured[-1][1]

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == owner_email).one()
        organization = (
            db.query(Organization)
            .filter(Organization.slug == organization_slug)
            .one()
        )
        membership = (
            db.query(Membership)
            .filter(
                Membership.user_id == user.id,
                Membership.organization_id == organization.id,
            )
            .one()
        )
        assert user.is_active is True
        assert user.full_name == "Gonçalo Saldanha"
        assert membership.role == Role.OWNER.value

    confirmed = client.post(
        "/api/auth/password-reset/confirm",
        json={
            "token": reset_token,
            "new_password": "institutional-owner-password-456",
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    logged_in = client.post(
        "/api/auth/login",
        json={
            "email": owner_email,
            "password": "institutional-owner-password-456",
        },
    )
    assert logged_in.status_code == 200, logged_in.text


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


def test_observer_cannot_mutate_or_materialize_the_mission_graph(monkeypatch) -> None:
    captured = _capture_auth_links(monkeypatch)
    owner_headers, organization_id, _ = _owner()
    mission = client.post(
        f"/api/organizations/{organization_id}/mission-intelligence/missions",
        headers=owner_headers,
        json={
            "title": "Validar permissões do grafo",
            "objective": "Confirmar que observadores apenas consultam o estado governado.",
            "central_question": "Um observador consegue alterar ou materializar o grafo?",
            "context": "Teste institucional de separação de funções.",
            "mission_kind": "mission",
            "domain": "access_governance",
            "priority": "standard",
            "stakeholders": [],
        },
    )
    assert mission.status_code == 201, mission.text
    code = mission.json()["code"]
    graph_base = f"/api/pilot/evidence-graph/missions/{code}"
    source = client.post(
        f"{graph_base}/nodes",
        headers=owner_headers,
        json={
            "node_type": "evidence",
            "label": "Fonte governada",
            "body": "Registo criado pelo proprietário para validar as permissões.",
            "status": "proposed",
        },
    )
    assert source.status_code == 201, source.text
    proposed_cycle = client.post(
        "/api/pilot/decision-cycles",
        headers=owner_headers,
        json={
            "mission_code": code,
            "decision": "Usar a proposta como fundamento sem a promover automaticamente.",
            "action": "Validar o controlo de revisão factual.",
            "expected_outcome": "O compromisso é recusado enquanto a evidência for apenas proposta.",
            "evidence_node_id": source.json()["id"],
        },
    )
    assert proposed_cycle.status_code == 201, proposed_cycle.text
    blocked_unreviewed_foundation = client.patch(
        f"/api/pilot/decision-cycles/{proposed_cycle.json()['id']}",
        headers=owner_headers,
        json={"status": "committed"},
    )
    assert blocked_unreviewed_foundation.status_code == 409, blocked_unreviewed_foundation.text
    assert "revista humanamente" in blocked_unreviewed_foundation.json()["detail"]
    reviewed_learning = client.post(
        f"{graph_base}/nodes",
        headers=owner_headers,
        json={
            "node_type": "learning",
            "label": "Aprendizagem revista",
            "body": "Uma aprendizagem institucional só pode ser publicada por quem revê.",
            "status": "accepted",
        },
    )
    assert reviewed_learning.status_code == 201, reviewed_learning.text
    blocked_reviewed_rewrite = client.patch(
        f"{graph_base}/nodes/{reviewed_learning.json()['id']}",
        headers=owner_headers,
        json={"body": "Uma revisão aceite não pode ser reescrita no mesmo objeto."},
    )
    assert blocked_reviewed_rewrite.status_code == 409, blocked_reviewed_rewrite.text
    assert (
        blocked_reviewed_rewrite.json()["detail"]["code"]
        == "reviewed_node_version_required"
    )

    contributor_email = f"graph-contributor-{uuid4().hex[:10]}@example.com"
    contributor_invite = client.post(
        f"/api/organizations/{organization_id}/invitations",
        headers=owner_headers,
        json={
            "email": contributor_email,
            "full_name": "Graph Contributor",
            "role": "contributor",
        },
    )
    assert contributor_invite.status_code == 201, contributor_invite.text
    contributor_acceptance = client.post(
        "/api/auth/invitations/accept",
        json={
            "token": captured[-1][1],
            "password": "contributor-password-123",
        },
    )
    assert contributor_acceptance.status_code == 200, contributor_acceptance.text
    contributor_headers = {
        "Authorization": f"Bearer {contributor_acceptance.json()['access_token']}"
    }
    contributor_proposal = client.post(
        f"{graph_base}/nodes",
        headers=contributor_headers,
        json={
            "node_type": "claim",
            "label": "Proposta do colaborador",
            "body": "Um colaborador pode estruturar conteúdo sem o validar.",
            "status": "proposed",
        },
    )
    assert contributor_proposal.status_code == 201, contributor_proposal.text
    forbidden_contributor_review = client.patch(
        f"{graph_base}/nodes/{contributor_proposal.json()['id']}",
        headers=contributor_headers,
        json={"status": "accepted"},
    )
    assert forbidden_contributor_review.status_code == 403, forbidden_contributor_review.text
    assert "revisor" in forbidden_contributor_review.json()["detail"]
    forbidden_preaccepted_create = client.post(
        f"{graph_base}/nodes",
        headers=contributor_headers,
        json={
            "node_type": "claim",
            "label": "Validação indevida",
            "body": "Um objeto novo não pode contornar a revisão humana.",
            "status": "accepted",
        },
    )
    assert forbidden_preaccepted_create.status_code == 403, forbidden_preaccepted_create.text

    observer_email = f"observer-{uuid4().hex[:10]}@example.com"
    invited = client.post(
        f"/api/organizations/{organization_id}/invitations",
        headers=owner_headers,
        json={
            "email": observer_email,
            "full_name": "Graph Observer",
            "role": "observer",
        },
    )
    assert invited.status_code == 201, invited.text
    accepted = client.post(
        "/api/auth/invitations/accept",
        json={
            "token": captured[-1][1],
            "password": "observer-password-123",
        },
    )
    assert accepted.status_code == 200, accepted.text
    observer_headers = {
        "Authorization": f"Bearer {accepted.json()['access_token']}"
    }

    assert client.get(graph_base, headers=observer_headers).status_code == 200
    forbidden_create = client.post(
        f"{graph_base}/nodes",
        headers=observer_headers,
        json={
            "node_type": "claim",
            "label": "Alteração indevida",
            "body": "Este objeto não deve ser criado por um observador.",
        },
    )
    forbidden_update = client.patch(
        f"{graph_base}/nodes/{source.json()['id']}",
        headers=observer_headers,
        json={"status": "accepted"},
    )
    forbidden_sync = client.post(f"{graph_base}/sync", headers=observer_headers)
    for response in (forbidden_create, forbidden_update, forbidden_sync):
        assert response.status_code == 403, response.text
        assert "consultar" in response.json()["detail"]

    candidates = client.get(
        f"/api/pilot/learning/missions/{code}/candidates",
        headers=observer_headers,
    )
    assert candidates.status_code == 200, candidates.text
    forbidden_publish = client.post(
        f"/api/pilot/learning/missions/{code}/publish/{reviewed_learning.json()['id']}",
        headers=observer_headers,
    )
    assert forbidden_publish.status_code == 403, forbidden_publish.text
    assert "revisor" in forbidden_publish.json()["detail"]


def test_identity_frontend_exposes_invite_and_recovery_flows() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    login = (repo_root / "frontend" / "pilot-v1" / "home.html").read_text(
        encoding="utf-8"
    )
    auth = (repo_root / "frontend" / "pilot-v1" / "auth.js").read_text(
        encoding="utf-8"
    )
    account = (
        repo_root / "frontend" / "pilot-v1" / "account.html"
    ).read_text(encoding="utf-8")
    workspace = (repo_root / "frontend" / "pilot-v1" / "index.html").read_text(
        encoding="utf-8"
    )
    administration = (
        repo_root / "frontend" / "pilot-v1" / "admin-accounts.js"
    ).read_text(
        encoding="utf-8"
    )

    assert 'id="forgot-link"' in login
    assert "/api/auth/password-reset/request" in auth
    assert "/api/pilot/password-reset/confirm" in auth
    assert "/api/auth/password-reset/request" in account
    assert "/api/auth/password-reset/confirm" in account
    assert "/api/auth/invitations/accept" in account
    assert "/invitations" in administration
    assert "/admin/accounts" in administration
    assert "/admin-accounts.js" in workspace

    account_response = client.get("/account.html")
    workspace_response = client.get("/app")
    assert account_response.status_code == 200
    assert workspace_response.status_code == 200
    assert "frame-ancestors 'none'" in account_response.headers[
        "content-security-policy"
    ]
