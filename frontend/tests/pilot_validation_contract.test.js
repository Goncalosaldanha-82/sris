import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import {fileURLToPath} from 'node:url';

const here=path.dirname(fileURLToPath(import.meta.url));
const pilot=path.resolve(here,'../pilot-v1');
const read=name=>fs.readFileSync(path.join(pilot,name),'utf8');
const index=read('index.html');
const app=read('app.js');
const validation=read('validation-protocol.js');
const css=read('pilot.css');

test('measurable validation is an explicit governed mission area',()=>{
  assert.doesNotThrow(()=>new Function(validation));
  assert.match(index,/data-mission-area="validation"/);
  assert.match(index,/data-mission-tab="validation"/);
  assert.match(index,/id="mission-validation-profile"/);
  assert.match(index,/validation-protocol\.js\?v=__PILOT_BUILD__/);
  assert.match(app,/validation_profile:/);
  assert.match(app,/validation_protocol:/);
  assert.match(app,/Baseline → intervenção → resultado/);
  assert.match(css,/Governed measurable validation/);
});

test('Tourism Advance is a specialized profile of a transversal architecture',()=>{
  assert.match(index,/Validação mensurável transversal/);
  assert.match(index,/Tourism Advance · Eficiência de recursos/);
  assert.match(validation,/perfil Tourism Advance é uma configuração especializada desta arquitetura transversal/);
  assert.match(validation,/tourism_advance_resource_efficiency/);
  assert.match(validation,/measurable_decision/);
  assert.match(app,/hospitality_resource_efficiency/);
});

test('baseline and result remain evidence-backed and deterministic',()=>{
  for(const marker of ['Baseline','Resultado','Atividade para normalização','Evidência de origem','Rever a atribuição','Limitações','Fatores externos','CÁLCULO DETERMINÍSTICO · SEM IA']){
    assert.match(validation,new RegExp(marker));
  }
  assert.match(validation,/measurements\/\$\{phase\}/);
  assert.match(validation,/evidence_node_id/);
  assert.match(validation,/expected_revision/);
  assert.match(validation,/content_hash/);
  assert.match(validation,/sris:validation-updated/);
  assert.doesNotMatch(validation,/new MutationObserver\s*\(/);
  assert.doesNotMatch(validation,/window\.fetch\s*=/);
  assert.doesNotMatch(validation,/\b(?:prompt|alert|confirm)\s*\(/);
});
