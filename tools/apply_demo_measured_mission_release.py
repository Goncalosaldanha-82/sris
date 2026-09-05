from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one marker, found {count}: {old!r}")
    return text.replace(old, new, 1)


def replace_exact_count(
    text: str,
    old: str,
    new: str,
    *,
    expected: int,
    label: str,
) -> str:
    count = text.count(old)
    if count != expected:
        raise RuntimeError(
            f"{label}: expected {expected} markers, found {count}: {old!r}"
        )
    return text.replace(old, new)


# Public demonstration links and canonical domains.
html_path = ROOT / "frontend" / "pilot-v1" / "demonstracao.html"
html = html_path.read_text(encoding="utf-8")
html = replace_exact_count(
    html,
    "https://www.sris.io/",
    "https://sris.io/",
    expected=2,
    label="canonical site links",
)
html = replace_once(
    html,
    '<a href="/">Entrar na aplicação</a>',
    '<a href="https://app.sris.io/">Entrar na aplicação</a>',
    label="application link",
)
html = replace_once(
    html,
    'href="https://sris-mission-intelligence.up.railway.app/#contacto"',
    'href="https://sris.io/#contacto"',
    label="institutional contact link",
)
html_path.write_text(html, encoding="utf-8")

# Live demonstration data and the 90-day / measured-mission distinction.
data_path = ROOT / "backend" / "app" / "mission_intelligence" / "fictional_demo.py"
data = data_path.read_text(encoding="utf-8")
data = replace_once(
    data,
    '"catalog_version": "2026-09-02",',
    '"catalog_version": "2026-09-05",',
    label="catalog version",
)
data = replace_once(
    data,
    '"note": "Piloto de oito semanas antes de investimento generalizado."',
    '"note": "Piloto de medição de oito semanas, dentro do acompanhamento de 90 dias."',
    label="decision-chain duration",
)
data = replace_once(
    data,
    '"detail": "Piloto de oito semanas aprovado; não constitui prova de poupança nem decisão de investimento generalizado."',
    '"detail": "Piloto de medição de oito semanas, dentro do acompanhamento de 90 dias, aprovado; não constitui prova de poupança nem decisão de investimento generalizado."',
    label="decision-node duration",
)
data = replace_once(
    data,
    '"avoidable_operating_loss_basis": "Horas de manutenção, desperdício e indisponibilidade operacional estimados."',
    '"avoidable_operating_loss_basis": "Horas de manutenção, desperdício e indisponibilidade operacional estimados. Não incluída no benefício projetado."',
    label="avoidable-loss exclusion",
)
data = replace_once(
    data,
    '"duration_weeks": 8,',
    '"duration_weeks": 8,\n                    "duration_context": "dentro do piloto SRIS de 90 dias",',
    label="duration context",
)
data = replace_once(
    data,
    '"protected_revenue_basis": "Três incidentes evitados × 1 400 € de receita sob risco."',
    '"protected_revenue_basis": "Três de cerca de seis incidentes anuais estimados × 1 400 € de receita sob risco."',
    label="protected-revenue basis",
)
data_path.write_text(data, encoding="utf-8")

# Render the duration context under the eight-week measurement effort.
js_path = ROOT / "frontend" / "pilot-v1" / "demonstracao.js"
js = js_path.read_text(encoding="utf-8")
js = replace_once(
    js,
    "${metric('Duração e esforço',`${esc(pilot.duration_weeks)} semanas · ${esc(pilot.internal_hours)} h`)}",
    "${metric('Duração e esforço',`${esc(pilot.duration_weeks)} semanas · ${esc(pilot.internal_hours)} h`,pilot.duration_context)}",
    label="duration rendering",
)
js_path.write_text(js, encoding="utf-8")

# Bump the public build so immutable assets cannot reuse the previous version.
capabilities_path = ROOT / "backend" / "app" / "pilot_capabilities.py"
capabilities = capabilities_path.read_text(encoding="utf-8")
capabilities = replace_once(
    capabilities,
    'PILOT_BUILD = "20260902-staging-audit-hardening-v37"',
    'PILOT_BUILD = "20260905-demo-measured-mission-v38"',
    label="pilot build",
)
capabilities = replace_once(
    capabilities,
    '"https://www.sris.io/",',
    '"https://sris.io/",',
    label="canonical site URL",
)
capabilities_path.write_text(capabilities, encoding="utf-8")

# Update the frontend contract so future releases cannot regress the links or scope.
frontend_test_path = ROOT / "frontend" / "tests" / "public_demonstration_contract.test.js"
frontend_test = frontend_test_path.read_text(encoding="utf-8")
frontend_test = replace_once(
    frontend_test,
    "assert.match(html,/https:\\/\\/www\\.sris\\.io\\//);",
    "assert.match(html,/https:\\/\\/sris\\.io\\//);",
    label="canonical-site contract",
)
frontend_test = replace_once(
    frontend_test,
    "assert.match(html,/https:\\/\\/sris-mission-intelligence\\.up\\.railway\\.app\\\/#contacto/);",
    "assert.match(html,/https:\\/\\/sris\\.io\\\/#contacto/);",
    label="contact-link contract",
)
frontend_test = replace_once(
    frontend_test,
    "  assert.match(html,/Entrar na aplicação/);\n",
    "  assert.match(html,/Entrar na aplicação/);\n  assert.match(html,/https:\\/\\/app\\.sris\\.io\\//);\n",
    label="app-link contract",
)
frontend_test = replace_once(
    frontend_test,
    "  assert.match(data,/resultados são fictícios/);\n",
    "  assert.match(data,/resultados são fictícios/);\n"
    "  assert.match(data,/Piloto de medição de oito semanas, dentro do acompanhamento de 90 dias/);\n"
    "  assert.match(data,/dentro do piloto SRIS de 90 dias/);\n"
    "  assert.match(data,/Não incluída no benefício projetado/);\n"
    "  assert.match(data,/Três de cerca de seis incidentes anuais estimados × 1 400 € de receita sob risco/);\n"
    "  assert.match(js,/pilot\\.duration_context/);\n",
    label="demo-content contracts",
)
frontend_test_path.write_text(frontend_test, encoding="utf-8")

# Add an executable backend regression around the exact public values.
backend_test_path = ROOT / "backend" / "tests" / "test_staging_audit_hardening.py"
backend_test = backend_test_path.read_text(encoding="utf-8")
if "def test_public_demo_matches_the_90_day_measured_mission_offer" not in backend_test:
    backend_test += '''\n\ndef test_public_demo_matches_the_90_day_measured_mission_offer() -> None:\n    mission = fictional_demo_catalog()["missions"]["DEMO-TA-001"]\n    decision = mission["situation"]["chain"][4]\n    assert decision["note"] == (\n        "Piloto de medição de oito semanas, dentro do acompanhamento de 90 dias."\n    )\n    business_case = mission["business_case"]\n    assert business_case["pilot"]["duration_context"] == (\n        "dentro do piloto SRIS de 90 dias"\n    )\n    assert business_case["baseline"]["avoidable_operating_loss_basis"].endswith(\n        "Não incluída no benefício projetado."\n    )\n    central = next(\n        item for item in business_case["scenarios"] if item["id"] == "central"\n    )\n    assert central["protected_revenue_basis"] == (\n        "Três de cerca de seis incidentes anuais estimados × 1 400 € "\n        "de receita sob risco."\n    )\n'''
backend_test_path.write_text(backend_test, encoding="utf-8")

# Fail fast on accidental partial replacements.
for path in (html_path, data_path, js_path, capabilities_path):
    compile_source = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        compile(compile_source, str(path), "exec")

print("demonstration measured-mission release applied")
