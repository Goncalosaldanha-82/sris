from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one marker, found {count}: {old!r}")
    return text.replace(old, new, 1)


def replace_count(
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


html_path = ROOT / "frontend" / "pilot-v1" / "demonstracao.html"
html = html_path.read_text(encoding="utf-8")
html = replace_count(
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


data_path = ROOT / "backend" / "app" / "mission_intelligence" / "fictional_demo.py"
data = data_path.read_text(encoding="utf-8")
for old, new, label in (
    (
        '"catalog_version": "2026-09-02",',
        '"catalog_version": "2026-09-05",',
        "catalog version",
    ),
    (
        '"note": "Piloto de oito semanas antes de investimento generalizado."',
        '"note": "Piloto de medição de oito semanas, dentro do acompanhamento de 90 dias."',
        "decision-chain duration",
    ),
    (
        '"detail": "Piloto de oito semanas aprovado; não constitui prova de poupança nem decisão de investimento generalizado."',
        '"detail": "Piloto de medição de oito semanas, dentro do acompanhamento de 90 dias, aprovado; não constitui prova de poupança nem decisão de investimento generalizado."',
        "decision-node duration",
    ),
    (
        '"avoidable_operating_loss_basis": "Horas de manutenção, desperdício e indisponibilidade operacional estimados."',
        '"avoidable_operating_loss_basis": "Horas de manutenção, desperdício e indisponibilidade operacional estimados. Não incluída no benefício projetado."',
        "avoidable-loss exclusion",
    ),
    (
        '"duration_weeks": 8,',
        '"duration_weeks": 8,\n                    "duration_context": "dentro do piloto SRIS de 90 dias",',
        "duration context",
    ),
    (
        '"protected_revenue_basis": "Três incidentes evitados × 1 400 € de receita sob risco."',
        '"protected_revenue_basis": "Três de cerca de seis incidentes anuais estimados × 1 400 € de receita sob risco."',
        "protected-revenue basis",
    ),
):
    data = replace_once(data, old, new, label=label)
data_path.write_text(data, encoding="utf-8")


js_path = ROOT / "frontend" / "pilot-v1" / "demonstracao.js"
js = js_path.read_text(encoding="utf-8")
js = replace_once(
    js,
    "${metric('Duração e esforço',`${esc(pilot.duration_weeks)} semanas · ${esc(pilot.internal_hours)} h`)}",
    "${metric('Duração e esforço',`${esc(pilot.duration_weeks)} semanas · ${esc(pilot.internal_hours)} h`,pilot.duration_context)}",
    label="duration rendering",
)
js_path.write_text(js, encoding="utf-8")


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


frontend_test_path = ROOT / "frontend" / "tests" / "public_demonstration_contract.test.js"
frontend_test_path.write_text(
    """import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const html=fs.readFileSync('frontend/pilot-v1/demonstracao.html','utf8');
const css=fs.readFileSync('frontend/pilot-v1/demonstracao.css','utf8');
const js=fs.readFileSync('frontend/pilot-v1/demonstracao.js','utf8');
const main=fs.readFileSync('backend/app/main.py','utf8');
const api=fs.readFileSync('backend/app/mission_intelligence/api.py','utf8');
const data=fs.readFileSync('backend/app/mission_intelligence/fictional_demo.py','utf8');

test('public demonstration remains a first-class read-only route',()=>{
  assert.match(main,/@app\\.get\\(\"\\/demonstracao\"/);
  assert.ok(main.indexOf('@app.get(\"/demonstracao\"')<main.indexOf('app.mount(\"/\", StaticFiles'));
  assert.match(html,/Demonstração pública · Todos os dados, entidades, pessoas, locais e resultados apresentados são fictícios/);
  assert.match(html,/ALOJAMENTO · SUSTENTABILIDADE · EFICIÊNCIA DE RECURSOS/);
  assert.match(html,/\\/demonstracao\\.css/);
  assert.match(html,/\\/demonstracao\\.js/);
  assert.match(css,/\\.fictional-banner/);
  assert.match(html,/Voltar ao site SRIS/);
  assert.match(html,/https:\\/\\/sris\\.io\\//);
  assert.match(html,/https:\\/\\/sris\\.io\\\/#contacto/);
  assert.match(html,/Entrar na aplicação/);
  assert.match(html,/https:\\/\\/app\\.sris\\.io\\//);
});

test('the demonstration uses an isolated fictional catalog and the measured-mission scope',()=>{
  assert.match(api,/from \\.fictional_demo import fictional_demo_catalog, fictional_demo_mission/);
  assert.match(api,/@public_router\\.get\\(\"\\/demo\\/fictional\\/missions\"\\)/);
  assert.match(js,/\\/api\\/mission-intelligence\\/demo\\/fictional\\/missions/);
  assert.match(data,/\"DEMO-TA-001\"/);
  assert.match(data,/Hotel Horizonte Verde \\(unidade fictícia\\)/);
  assert.match(data,/Caso exclusivamente demonstrativo/);
  assert.match(data,/resultados são fictícios/);
  assert.match(data,/Piloto de medição de oito semanas, dentro do acompanhamento de 90 dias/);
  assert.match(data,/dentro do piloto SRIS de 90 dias/);
  assert.match(data,/Não incluída no benefício projetado/);
  assert.match(data,/Três de cerca de seis incidentes anuais estimados × 1 400 € de receita sob risco/);
  assert.match(js,/pilot\\.duration_context/);
});
""",
    encoding="utf-8",
)


backend_test_path = ROOT / "backend" / "tests" / "test_staging_audit_hardening.py"
backend_test = backend_test_path.read_text(encoding="utf-8")
if "def test_public_demo_matches_the_90_day_measured_mission_offer" not in backend_test:
    backend_test += '''\n\ndef test_public_demo_matches_the_90_day_measured_mission_offer() -> None:\n    mission = fictional_demo_catalog()["missions"]["DEMO-TA-001"]\n    decision = mission["situation"]["chain"][4]\n    assert decision["note"] == (\n        "Piloto de medição de oito semanas, dentro do acompanhamento de 90 dias."\n    )\n    business_case = mission["business_case"]\n    assert business_case["pilot"]["duration_context"] == (\n        "dentro do piloto SRIS de 90 dias"\n    )\n    assert business_case["baseline"]["avoidable_operating_loss_basis"].endswith(\n        "Não incluída no benefício projetado."\n    )\n    central = next(\n        item for item in business_case["scenarios"] if item["id"] == "central"\n    )\n    assert central["protected_revenue_basis"] == (\n        "Três de cerca de seis incidentes anuais estimados × 1 400 € "\n        "de receita sob risco."\n    )\n'''
backend_test_path.write_text(backend_test, encoding="utf-8")


for path in (data_path, capabilities_path, backend_test_path):
    compile(path.read_text(encoding="utf-8"), str(path), "exec")

print("demonstration measured-mission release applied")
