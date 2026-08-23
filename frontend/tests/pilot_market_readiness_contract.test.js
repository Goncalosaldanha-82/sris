import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const here=path.dirname(fileURLToPath(import.meta.url));
const pilot=path.resolve(here,'../pilot-v1');
const read=name=>fs.readFileSync(path.join(pilot,name),'utf8');
const brand=read('brand-v2.css');
const ops=read('ops-status.js');
const market=read('market-readiness-v2.js');
const report=read('report-export-v1.js');
const visual=read('market-readiness-v2.css');
const mark=read('sris-mark-v2.svg');

test('market-ready modules are loaded by existing Pilot assets',()=>{
  assert.match(brand,/market-readiness-v2\.css/);
  assert.match(ops,/market-readiness-v2\.js/);
  assert.match(ops,/report-export-v1\.js/);
  for(const source of [ops,market,report])assert.doesNotThrow(()=>new Function(source));
});

test('navigation control is functional and accessible',()=>{
  assert.match(market,/aria-expanded/);
  assert.match(market,/nav-open/);
  assert.match(market,/Escape/);
  assert.match(visual,/body\.nav-open \.sidebar/);
  assert.match(visual,/\.nav-scrim/);
});

test('mission documents have a visible upload surface',()=>{
  assert.match(market,/Carregar documento para esta missão/);
  assert.match(market,/mission-file/);
  assert.match(market,/upload-file-btn/);
  assert.match(market,/DataTransfer/);
  assert.match(market,/\.pdf,.doc,.docx,.xls,.xlsx/);
});

test('mission reports and sections can be downloaded',()=>{
  assert.match(report,/Imprimir \/ guardar PDF/);
  assert.match(report,/Descarregar relatório completo/);
  assert.match(report,/Descarregar dados estruturados/);
  assert.match(report,/Descarregar secção atual/);
  assert.match(report,/sris\.mission\.report\.v1/);
});

test('assisted analysis is governed by real readiness state',()=>{
  assert.match(market,/\/api\/pilot\/capabilities/);
  assert.match(market,/\/api\/pilot\/intelligence\/ask/);
  assert.match(market,/provider/);
  assert.match(market,/runtime/);
  assert.match(market,/policy/);
  assert.match(market,/revisão humana/);
});

test('canonical brand and photography are applied',()=>{
  assert.match(mark,/<circle/);
  assert.match(mark,/<path/);
  assert.match(visual,/sris-mark-v2\.svg/);
  assert.match(visual,/sunrise\.svg/);
});
