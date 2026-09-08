from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "backend" / "tests" / "test_pilot_v1_contract.py"
text = PATH.read_text(encoding="utf-8")

# The product now has one canonical identity route family. Keep the broad
# operational contract aligned without weakening the secure public response.
text = text.replace(
    '"/api/pilot/password-reset/request"',
    '"/api/auth/password-reset/request"',
)
text = text.replace(
    '"/api/pilot/password-reset/confirm"',
    '"/api/auth/password-reset/confirm"',
)

identity_import = "from app.atlas_platform import identity\n"
config_import = (
    "from app.atlas_platform.config import Settings, configured_database_url, "
    "validate_security_settings\n"
)
if identity_import not in text:
    if config_import not in text:
        raise RuntimeError("Could not locate the Pilot V1 import block")
    text = text.replace(config_import, identity_import + config_import, 1)

journey_start = text.find("def test_account_to_persistent_mission_journey(monkeypatch) -> None:")
if journey_start < 0:
    raise RuntimeError("Could not locate the persistent mission journey")
journey_end = text.find("\ndef ", journey_start + 5)
if journey_end < 0:
    journey_end = len(text)
journey = text[journey_start:journey_end]

capture_block = '''    captured_reset_tokens: list[str] = []
    monkeypatch.setattr(identity, "auth_email_delivery_ready", lambda: True)
    monkeypatch.setattr(
        identity,
        "_send_password_reset_email",
        lambda _reset_id, raw_token: captured_reset_tokens.append(raw_token),
    )
'''
if "captured_reset_tokens: list[str]" not in journey:
    setup_pattern = re.compile(
        r'(    monkeypatch\.setenv\("SRIS_PILOT_SHOW_RESET_LINK", "true"\)\n)'
    )
    journey, count = setup_pattern.subn(r"\1" + capture_block, journey, count=1)
    if count != 1:
        raise RuntimeError("Could not add secure reset-token capture to the journey")

# Accept the canonical enumeration-resistant response and obtain the one-time
# raw token exclusively through the mocked delivery channel used by the test.
journey = re.sub(
    r"    assert (reset(?:_start)?)\.status_code == 200, \1\.text\n",
    r"    assert \1.status_code == 202, \1.text\n",
    journey,
    count=1,
)
journey = re.sub(
    r"    assert (reset(?:_start)?)\.json\(\)\.get\(\"reset_token\"\)\n",
    "    assert captured_reset_tokens\n",
    journey,
    count=1,
)
journey = re.sub(
    r'(reset(?:_start)?)\.json\(\)\[\"reset_token\"\]',
    "captured_reset_tokens[-1]",
    journey,
)

if '"/api/auth/password-reset/request"' not in journey:
    raise RuntimeError("The journey does not use the canonical reset request route")
if '"/api/auth/password-reset/confirm"' not in journey:
    raise RuntimeError("The journey does not use the canonical reset confirm route")
if "assert captured_reset_tokens" not in journey:
    raise RuntimeError("The journey still lacks delivery-channel token capture")
if "reset_token\"]" in journey or "reset_token')" in journey:
    raise RuntimeError("The journey still expects token disclosure in the public response")

text = text[:journey_start] + journey + text[journey_end:]
PATH.write_text(text, encoding="utf-8")
print("reconciled backend/tests/test_pilot_v1_contract.py with canonical identity")
