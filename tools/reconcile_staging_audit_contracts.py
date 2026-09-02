from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "backend" / "tests" / "test_pilot_v1_contract.py"
text = PATH.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global text
    if old in text:
        text = text.replace(old, new, 1)
        return
    if new not in text:
        raise RuntimeError(f"{label} marker not found")


import_marker = (
    "from app.atlas_platform.config import Settings, configured_database_url, "
    "validate_security_settings\n"
)
identity_import = "from app.atlas_platform import identity\n"
if identity_import not in text:
    if import_marker not in text:
        raise RuntimeError("Pilot V1 import marker not found")
    text = text.replace(import_marker, identity_import + import_marker, 1)

# The public product now has one hardened identity route family. Reconcile both
# the OpenAPI expectation and the end-to-end journey with that canonical API.
text = text.replace(
    '"/api/pilot/password-reset/request"',
    '"/api/auth/password-reset/request"',
)
text = text.replace(
    '"/api/pilot/password-reset/confirm"',
    '"/api/auth/password-reset/confirm"',
)

journey_marker = '''def test_account_to_persistent_mission_journey(monkeypatch) -> None:
    monkeypatch.setenv("SRIS_PUBLIC_SIGNUP_ENABLED", "true")
    monkeypatch.setenv("SRIS_PILOT_MODE", "true")
    monkeypatch.setenv("SRIS_PILOT_SHOW_RESET_LINK", "true")
'''
journey_replacement = '''def test_account_to_persistent_mission_journey(monkeypatch) -> None:
    monkeypatch.setenv("SRIS_PUBLIC_SIGNUP_ENABLED", "true")
    monkeypatch.setenv("SRIS_PILOT_MODE", "true")
    monkeypatch.setenv("SRIS_PILOT_SHOW_RESET_LINK", "true")
    captured_reset_tokens: list[str] = []
    monkeypatch.setattr(identity, "auth_email_delivery_ready", lambda: True)
    monkeypatch.setattr(
        identity,
        "_send_password_reset_email",
        lambda _reset_id, raw_token: captured_reset_tokens.append(raw_token),
    )
'''
replace_once(journey_marker, journey_replacement, "Pilot journey setup")

reset_assertions = '''    assert reset.status_code == 200, reset.text
    assert reset.json().get("reset_token")
'''
reset_assertions_hardened = '''    assert reset.status_code == 202, reset.text
    assert reset.json()["status"] == "accepted"
    assert captured_reset_tokens
'''
replace_once(
    reset_assertions,
    reset_assertions_hardened,
    "Pilot journey reset assertions",
)
replace_once(
    '            "token": reset.json()["reset_token"],\n',
    '            "token": captured_reset_tokens[-1],\n',
    "Pilot journey captured reset token",
)

PATH.write_text(text, encoding="utf-8")
print("reconciled backend/tests/test_pilot_v1_contract.py")
