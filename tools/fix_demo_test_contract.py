from pathlib import Path

path = Path('frontend/tests/public_demonstration_contract.test.js')
path.write_text(
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
  assert.ok(html.includes('Demonstração pública · Todos os dados, entidades, pessoas, locais e resultados apresentados são fictícios'));
  assert.ok(html.includes('ALOJAMENTO · SUSTENTABILIDADE · EFICIÊNCIA DE RECURSOS'));
  assert.ok(html.includes('/demonstracao.css'));
  assert.ok(html.includes('/demonstracao.js'));
  assert.match(css,/\\.fictional-banner/);
  assert.ok(html.includes('Voltar ao site SRIS'));
  assert.ok(html.includes('https://sris.io/'));
  assert.ok(html.includes('https://sris.io/#contacto'));
  assert.ok(html.includes('Entrar na aplicação'));
  assert.ok(html.includes('https://app.sris.io/'));
  assert.ok(!html.includes('https://www.sris.io/'));
  assert.ok(!html.includes('https://sris-mission-intelligence.up.railway.app/#contacto'));
});

test('the demonstration uses an isolated fictional catalog and the measured-mission scope',()=>{
  assert.ok(api.includes('from .fictional_demo import fictional_demo_catalog, fictional_demo_mission'));
  assert.ok(api.includes('@public_router.get(\"/demo/fictional/missions\")'));
  assert.ok(js.includes('/api/mission-intelligence/demo/fictional/missions'));
  assert.ok(data.includes('\"DEMO-TA-001\"'));
  assert.ok(data.includes('Hotel Horizonte Verde (unidade fictícia)'));
  assert.ok(data.includes('Caso exclusivamente demonstrativo'));
  assert.ok(data.includes('resultados são fictícios'));
  assert.ok(data.includes('Piloto de medição de oito semanas, dentro do acompanhamento de 90 dias'));
  assert.ok(data.includes('dentro do piloto SRIS de 90 dias'));
  assert.ok(data.includes('Não incluída no benefício projetado'));
  assert.ok(data.includes('Três de cerca de seis incidentes anuais estimados × 1 400 € de receita sob risco'));
  assert.ok(js.includes('pilot.duration_context'));
});
""",
    encoding='utf-8',
)
print('demonstration contract rewritten with literal URL assertions')
