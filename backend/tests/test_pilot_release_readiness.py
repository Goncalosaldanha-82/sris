from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app import pilot_release_readiness as readiness_module
from app.atlas_platform.database import Base, SessionLocal, engine
from app.atlas_platform.models import AuditEvent, PilotReleaseAcceptance
from app.main import app


Base.metadata.create_all(bind=engine)
client = TestClient(app)


def _owner() -> tuple[dict[str, str], str]:
    suffix = uuid4().hex[:10]
    email = f"release-owner-{suffix}@example.com"
    password = "release-owner-password-123"
    registered = client.post(
        "/api/auth/register",
        json={"email": email, "full_name": "Release Owner", "password": password},
    )
    assert registered.status_code == 201, registered.text
    login = client.post("/api/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    organization = client.post(
        "/api/organizations",
        headers=headers,
        json={"name": f"Release Lab {suffix}", "slug": f"release-lab-{suffix}"},
    )
    assert organization.status_code == 201, organization.text
    return headers, organization.json()["id"]


def _automatic_checks(_db, _organization_id):
    return {
        "email_configured": (True, "Servidor configurado."),
        "ai_operational": (True, "Resposta real registada."),
        "owner_password_rotated": (True, "Rotação auditada."),
        "real_mission_completed": (True, "MIS-REAL — missão completa"),
    }


def test_release_gate_requires_evidence_and_is_build_scoped(monkeypatch) -> None:
    monkeypatch.setattr(readiness_module, "_automatic_checks", _automatic_checks)
    headers, organization_id = _owner()
    path = f"/api/pilot/release-readiness?organization_id={organization_id}"
    initial = client.get(path, headers=headers)
    assert initial.status_code == 200, initial.text
    assert initial.json()["passed_count"] == 4
    assert initial.json()["total_count"] == 10
    assert initial.json()["ready_for_external_test"] is False

    missing_evidence = client.put(
        f"/api/pilot/release-readiness/checks/exports_accepted?organization_id={organization_id}",
        headers=headers,
        json={"accepted": True, "evidence": "curto"},
    )
    assert missing_evidence.status_code == 422

    accepted = client.put(
        f"/api/pilot/release-readiness/checks/exports_accepted?organization_id={organization_id}",
        headers=headers,
        json={
            "accepted": True,
            "evidence": "Firefox e Chrome: nome, download e conteúdo confirmados.",
        },
    )
    assert accepted.status_code == 200, accepted.text
    export_check = next(
        check for check in accepted.json()["checks"] if check["key"] == "exports_accepted"
    )
    assert export_check["passed"] is True
    assert export_check["source"] == "human_acceptance"

    premature_freeze = client.put(
        f"/api/pilot/release-readiness/checks/regression_accepted?organization_id={organization_id}",
        headers=headers,
        json={"accepted": True, "evidence": "Regressão integral executada sem falhas."},
    )
    assert premature_freeze.status_code == 409

    with SessionLocal() as db:
        row = (
            db.query(PilotReleaseAcceptance)
            .filter(PilotReleaseAcceptance.organization_id == organization_id)
            .one()
        )
        assert row.check_key == "exports_accepted"
        assert row.build == readiness_module.PILOT_BUILD
        audit = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.organization_id == organization_id,
                AuditEvent.action == "pilot.release_acceptance_recorded",
            )
            .one()
        )
        assert audit.resource_id == "exports_accepted"
