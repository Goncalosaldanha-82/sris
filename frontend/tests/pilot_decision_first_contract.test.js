import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const here=path.dirname(fileURLToPath(import.meta.url));
const pilot=path.resolve(here,'../pilot-v1');
const read=name=>fs.readFileSync(path.join(pilot,name),'utf8');

const index=read('index.html');
const home=read('home.html');
const app=read('app.js');
const auth=read('auth.js');
const integration=read('pilot-integration-v3.js');
const graph=read('evidence-graph.js');

test('decision-first Pilot assets are syntactically valid',()=>{
  for(const [name,source] of Object.entries({app,auth,integration,graph})){
    assert.doesNotThrow(()=>new Function(source),`${name} must parse`);
  }
});

test('Mission Workspace is the product centre and billing is absent',()=>{
  assert.match(index,/SRIS — Espaço de Missão/);
  assert.match(index,/Comece pela decisão\. Preserve a razão\./);
  assert.match(index,/Comece por uma decisão real, não por uma conversa genérica\./);
  assert.match(index,/data-section="mission"/);
  assert.match(index,/data-section="copilot"/);
  assert.doesNotMatch(index,/data-section="billing"/);
  assert.doesNotMatch(index,/id="billing"/);
  assert.doesNotMatch(index,/pilot-operational-v1\.js/);
  assert.doesNotMatch(index,/gpt-5\.6-terra/);
  assert.doesNotMatch(index,/Créditos e planos/);
});

test('empty state offers real mission templates without fake seed data',()=>{
  for(const marker of [
    'Eficiência de recursos',
    'Problema operacional',
    'Investimento ou alteração',
    'Criar missão livre',
  ])assert.match(index,new RegExp(marker));
  assert.match(app,/const missionTemplates=/);
  assert.match(app,/resource:/);
  assert.match(app,/incident:/);
  assert.match(app,/investment:/);
  assert.doesNotMatch(index,/Nascente de Dragos|Penela Vivo 2035|Paisagem Resiliente/);
});

test('canonical transverse objects are created with human provenance',()=>{
  for(const id of ['mission-assumptions','mission-constraints','mission-success']){
    assert.match(index,new RegExp(`id="${id}"`));
  }
  assert.match(app,/createGraphNode\(mission\.code,'assumption'/);
  assert.match(app,/createGraphNode\(mission\.code,'constraint'/);
  assert.match(app,/createGraphNode\(mission\.code,'outcome'/);
  assert.match(app,/source:'mission_onboarding'/);
  assert.match(graph,/value="assumption"/);
  assert.match(graph,/value="constraint"/);
  assert.match(graph,/value="gap"/);
  assert.match(graph,/value="alternative"/);
  assert.match(graph,/value="action"/);
});

test('assistance remains optional and does not expose provider or wallet data',()=>{
  assert.match(index,/Análise assistida, não centro do produto\./);
  assert.match(index,/revisão humana obrigatória/i);
  assert.doesNotMatch(index,/Crédito IA|Último custo|Saldo/);
  assert.doesNotMatch(app,/billing-balance|last-charge|model-name/);
  assert.doesNotMatch(integration,/billing-balance|last-charge|model-name/);
  assert.doesNotMatch(graph,/provenance\.model/);
});

test('entry page uses the real photo element and current validation language',()=>{
  assert.match(home,/class="sunrise-photo"/);
  assert.match(home,/PILOTO V1 · VALIDAÇÃO OPERACIONAL/);
  assert.match(home,/Disciplina antes da assistência/);
  assert.match(home,/nunca preencher lacunas com confiança artificial/);
  assert.doesNotMatch(home,/SEPT 2026/);
  assert.doesNotMatch(home,/Crédito inicial incluído/);
  assert.match(auth,/reset_token/);
  assert.match(auth,/history\.replaceState/);
});
