import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const html=fs.readFileSync('frontend/pilot-v1/demonstracao.html','utf8');
const css=fs.readFileSync('frontend/pilot-v1/demonstracao.css','utf8');
const js=fs.readFileSync('frontend/pilot-v1/demonstracao.js','utf8');
const main=fs.readFileSync('backend/app/main.py','utf8');
const api=fs.readFileSync('backend/app/mission_intelligence/api.py','utf8');
const data=fs.readFileSync('backend/app/mission_intelligence/fictional_demo.py','utf8');

test('public Tourism Advance demonstration remains a first-class read-only route',()=>{
  assert.match(main,/@app\.get\("\/demonstracao"/);
  assert.ok(main.indexOf('@app.get("/demonstracao"')<main.indexOf('app.mount("/", StaticFiles'));
  assert.match(html,/Demonstração pública · Todos os dados, entidades, pessoas, locais e resultados apresentados são fictícios/);
  assert.match(html,/ALOJAMENTO · SUSTENTABILIDADE · EFICIÊNCIA DE RECURSOS/);
  assert.match(html,/\/demonstracao\.css/);
  assert.match(html,/\/demonstracao\.js/);
  assert.match(css,/\.fictional-banner/);
});

test('the demonstration uses an isolated fictional catalog and public API',()=>{
  assert.match(api,/from \.fictional_demo import fictional_demo_catalog, fictional_demo_mission/);
  assert.match(api,/@public_router\.get\("\/demo\/fictional\/missions"\)/);
  assert.match(js,/\/api\/mission-intelligence\/demo\/fictional\/missions/);
  assert.match(data,/"DEMO-TA-001"/);
  assert.match(data,/Hotel Horizonte Verde \(unidade fictícia\)/);
  assert.match(data,/Caso exclusivamente demonstrativo/);
  assert.match(data,/resultados são fictícios/);
});
