from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "backend" / "tests" / "test_pilot_v1_contract.py"
text = PATH.read_text(encoding="utf-8")

import_marker = "from app.atlas_platform.config import Settings, configured_database_url, validate_security_settings\n"
identity_import = "from app.atlas_platform import identity\n"
if identity_import not in text:
    if import_marker not in text:
        raise RuntimeError("Pilot V1 import marker not found")
    text = text.replace(import_marker, identity_import + import_marker, 1)

text = text.replace(
    '        "/api/pilot/password-reset/request",\n        "/api/pilot/password-reset/confirm",',
    '        "/api/auth/password-reset/request",\n        "/api/auth/password-reset/confirm",',
    1,
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
if journey_marker in text:
    text = text.replace(journey_marker, journey_replacement, 1)
elif "captured_reset_tokens: list[str]" not in text:
    raise RuntimeError("Pilot journey setup marker not found")

reset_marker = '''    assert reset_start.status_code == 200, reset_start.text
    reset_token = reset_start.json()["reset_token"]
'''
reset_replacement = '''    assert reset_start.status_code == 202, reset_start.text
    assert captured_reset_tokens
    reset_token = captured_reset_tokens[-1]
'''
if reset_marker in text:
    text = text.replace(reset_marker, reset_replacement, 1)
elif "reset_token = captured_reset_tokens[-1]" not in text:
    raise RuntimeError("Pilot journey reset assertion marker not found")

PATH.write_text(text, encoding="utf-8")
print("reconciled backend/tests/test_pilot_v1_contract.py")
