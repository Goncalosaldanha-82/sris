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

# The platform test imports the application at module load time, so its pilot
# flags must be set before that import rather than inherited accidentally from
# another test process or a developer shell.
platform_test = ROOT / "backend" / "tests" / "test_pilot_platform.py"
source = platform_test.read_text(encoding="utf-8")
if 'os.environ.setdefault("SRIS_PILOT_MODE", "true")' not in source:
    source = source.replace(
        "from __future__ import annotations\n\nfrom uuid import uuid4\n\nfrom fastapi.testclient import TestClient\n",
        "from __future__ import annotations\n\nimport os\nfrom uuid import uuid4\n\n"
        "os.environ.setdefault(\"SRIS_PILOT_MODE\", \"true\")\n"
        "os.environ.setdefault(\"SRIS_PUBLIC_SIGNUP_ENABLED\", \"true\")\n\n"
        "from fastapi.testclient import TestClient\n",
        1,
    )
    platform_test.write_text(source, encoding="utf-8")
    print("updated backend/tests/test_pilot_platform.py pilot flags")

# Tenant labels contain spaces for readability; email local-parts must not.
tenant_test = ROOT / "backend" / "tests" / "test_pilot_tenant_isolation.py"
source = tenant_test.read_text(encoding="utf-8")
old_email = '"email": f"{prefix}-{marker}@example.com",'
new_email = '"email": f"{prefix.lower().replace(\' \', \'-\')}-{marker}@example.com",'
if old_email in source:
    source = source.replace(old_email, new_email, 1)
    tenant_test.write_text(source, encoding="utf-8")
    print("updated backend/tests/test_pilot_tenant_isolation.py tenant email")
