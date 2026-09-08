"""Isolated integration gate. Never uses the live database or sends real mail."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if "--isolated" not in sys.argv:
    with tempfile.TemporaryDirectory(prefix="sris-inbox-qa-") as folder:
        env = {key: value for key, value in os.environ.items() if key in {"PATH", "HOME", "LANG", "LD_LIBRARY_PATH"}}
        env.update({"PYTHONPATH": str(ROOT / "backend"), "ATLAS_ENV": "testing",
            "ATLAS_DATABASE_URL": "sqlite+pysqlite:///" + folder + "/qa.db",
            "ATLAS_JWT_SECRET": "sris-isolated-inbox-tests-not-a-production-secret",
            "ATLAS_SELF_REGISTRATION_ENABLED": "true", "ATLAS_ORGANIZATION_CREATION_ENABLED": "true",
            "SRIS_COMMERCIAL_ENTITLEMENT_ENFORCEMENT": "false", "SRIS_ACCESS_NOTIFICATIONS_ENABLED": "false",
            "SRIS_ACCESS_APPROVER_EMAILS": "approver@example.com", "SRIS_ACCESS_ADMIN_BASE_URL": "https://testserver",
            "SRIS_PUBLIC_BASE_URL": "https://testserver", "SRIS_EMAIL_PROVIDER": "resend",
            "SRIS_EMAIL_FROM": "notices@example.com", "RESEND_API_KEY": "not-a-real-key",
            "SRIS_RATE_LIMIT_SIGNUP_PER_15M": "100", "SRIS_AI_ENABLED": "false"})
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--isolated"], env=env, cwd=ROOT)
        raise SystemExit(result.returncode)

from datetime import timedelta
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.atlas_platform import access_notifications as notice, commercial_access
from app.atlas_platform.access_notifications import AccessNotification
from app.atlas_platform.commercial_access_models import AccessRequest
from app.atlas_platform.database import Base, SessionLocal, engine
from app.atlas_platform.models import UserInvitation, Organization

assert engine.url.drivername.startswith("sqlite"), "QA must never reach a live DB"
Base.metadata.create_all(engine)
passed = []

def check(condition, label):
    if not condition:
        raise AssertionError(label)
    passed.append(label)
    print("SRIS_ACCESS_QA PASS " + label, flush=True)


def login(client, email):
    password = "isolated-qa-password-12345"
    created = client.post("/api/auth/register", json={"email": email, "full_name": "QA User", "password": password})
    assert created.status_code == 201, created.text
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def create(client, email, org="QA organization"):
    response = client.post("/api/access-requests", json={"email": email, "full_name": "QA Candidate", "organization_name": org})
    assert response.status_code == 202, response.text
    return response.json()


sent = []
with patch.object(notice, "urlopen", side_effect=AssertionError("Network is forbidden in QA")):
    with TestClient(app) as client:
        admin = login(client, "approver@example.com")
        customer = login(client, "customer@example.com")
        create(client, "candidate@example.com", "<script>unsafe</script>")
        create(client, "candidate@example.com")
        with SessionLocal() as db:
            first = db.query(AccessRequest).filter_by(email="candidate@example.com").one()
            first_id = first.id
            check(db.query(AccessRequest).count() == 1, "duplicate submission does not duplicate pending request")
        check(client.get("/api/admin/access-requests/inbox").status_code == 401, "anonymous request cannot read approval inbox")
        check(client.get("/api/admin/access-requests/inbox", headers=customer).status_code == 403, "ordinary customer cannot read platform inbox")
        page = client.get("/admin/access-requests")
        check(page.status_code == 200 and "__ACCESS_INBOX_VERSION__" not in page.text and "candidate@example.com" not in page.text, "public page is a non-private content-fingerprinted shell")
        check("no-store" in page.headers.get("cache-control", ""), "inbox page is never cached")
        before = client.get("/api/admin/access-requests/inbox", headers=admin)
        check(before.status_code == 200 and before.json()["counts"]["pending"] == 1, "approver sees persistent pending request and count")
        with patch.object(notice, "deliver", side_effect=lambda row: sent.append((row.recipient, row.kind, row.payload_json)) or "qa-provider-id"):
            result = notice.sweep(pacing_seconds=0)
            check(result["enqueued"] == 1 and result["provider_accepted"] == 1 and sent[0][0] == "approver@example.com", "existing pending request triggers one notice to verified approver")
            notice.sweep(pacing_seconds=0)
            check(len(sent) == 1, "successful notices are not sent again by periodic recovery")
            content = json.loads(sent[0][2])
            check("&lt;script&gt;" in content["html"] and '<script>' not in content["html"] and '/admin/access-requests' in content["text"], "notification escapes applicant text and links to authenticated inbox")
        with SessionLocal() as db:
            check(db.query(Organization).count() == 0 and db.query(UserInvitation).count() == 0, "notification and inbox reads never approve or create workspace/invitation")
        create(client, "failure@example.com")
        with patch.object(notice, "deliver", side_effect=notice.NoticeDeliveryError("provider_http_429")):
            notice.sweep(pacing_seconds=0)
        with SessionLocal() as db:
            failed = db.query(AccessNotification).filter_by(status="failed").one()
            failure_id = failed.request_id
            check(failed.attempts == 1 and failed.error_code == "provider_http_429", "failed delivery is persistent and visible, not reported as sent")
        check(client.post(f"/api/admin/access-requests/{failure_id}/retry-notification", headers=customer).status_code == 403, "customer cannot trigger admin notification retry")
        retried = client.post(f"/api/admin/access-requests/{failure_id}/retry-notification", headers=admin)
        check(retried.status_code == 200, "approver can queue retry of a failed notice")
        with patch.object(notice, "deliver", return_value="qa-retry-id"):
            check(notice.sweep(pacing_seconds=0)["provider_accepted"] == 1, "queued failed notice can recover without duplicate request")
        refusal = client.post(f"/api/admin/access-requests/{first_id}/reject", headers=admin,
            json={"decision_note": "INTERNAL-DO-NOT-SEND", "response_message": "Resposta explícita ao requerente."})
        check(refusal.status_code == 200 and refusal.json().get("response_status") == "queued", "refusal persists decision and email response atomically through deployed route")
        with SessionLocal() as db:
            reply = db.query(AccessNotification).filter_by(request_id=first_id, kind="request_rejected").one()
            check(reply.recipient == "candidate@example.com" and "INTERNAL-DO-NOT-SEND" not in reply.payload_json and "Resposta explícita" in reply.payload_json, "rejection response excludes internal notes")
        check(client.post(f"/api/admin/access-requests/{first_id}/reject", headers=admin, json={}).status_code == 409, "same request cannot be decided twice")
        captured = []
        with patch.object(commercial_access, "_send_invitation_email", side_effect=lambda *args: captured.append(args)):
            approved = client.post(f"/api/admin/access-requests/{failure_id}/approve", headers=admin,
                json={"workspace_name": "QA assigned workspace", "plan_code": "pilot", "entitlement_days": 90})
        check(approved.status_code == 200 and len(captured) == 1, "existing approval route still creates workspace and schedules invitation only after human decision")
        summary = client.get("/api/admin/access-requests/summary", headers=admin).json()
        check(summary["counts"] == {"pending": 0, "approved": 1, "rejected": 1, "total": 2}, "pending counter and decision history reconcile")
        # Validate Resend adapter and its acknowledgement using a fake transport.
        class Receipt:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return b'{"id":"qa-transport-receipt"}'
        with SessionLocal() as db:
            row = db.query(AccessNotification).first()
            with patch.object(notice, "urlopen", return_value=Receipt()) as transport:
                receipt = notice.deliver(row)
                request = transport.call_args.args[0]
                check(receipt == "qa-transport-receipt" and request.get_header("Idempotency-key") == "access-notice/" + row.id, "transport retains provider receipt and uses stable idempotency key")
print("SRIS_ACCESS_QA_RESULT " + json.dumps({"passed": len(passed), "failed": 0, "database": "isolated SQLite", "email": "mocked; no real sends"}))
