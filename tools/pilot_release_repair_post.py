from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAPABILITIES = ROOT / "backend" / "app" / "pilot_capabilities.py"

text = CAPABILITIES.read_text(encoding="utf-8")

old = '        "pilot_collaboration": True,\n'
new = (
    '        "pilot_collaboration": True,\n'
    '        "pilot_collaboration_roles": True,\n'
)

if '"pilot_collaboration_roles": True' not in text:
    if old not in text:
        raise RuntimeError("Pilot collaboration capability marker not found")
    text = text.replace(old, new, 1)
    CAPABILITIES.write_text(text, encoding="utf-8")
    print("updated backend/app/pilot_capabilities.py")
else:
    print("pilot collaboration capability already aligned")

# email-validator correctly rejects the special-use .test suffix in the
# currently resolved dependency set. Use the standards-reserved example.com
# domain so integration tests exercise registration rather than invalid input.
for relative in (
    "backend/tests/test_pilot_platform.py",
    "backend/tests/test_pilot_value.py",
    "backend/tests/test_pilot_tenant_isolation.py",
):
    path = ROOT / relative
    source = path.read_text(encoding="utf-8")
    updated = source.replace("@example.test", "@example.com")
    if updated != source:
        path.write_text(updated, encoding="utf-8")
        print(f"updated {relative}")
