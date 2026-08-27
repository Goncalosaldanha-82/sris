import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const here=path.dirname(fileURLToPath(import.meta.url));
const pilot=path.resolve(here,'../pilot-v1');
const source=fs.readFileSync(path.join(pilot,'decision-cycle-v1.js'),'utf8');
const index=fs.readFileSync(path.join(pilot,'index.html'),'utf8');

test('Decision Loop is syntactically valid and follows the Pilot build token',()=>{
  assert.doesNotThrow(()=>new Function(source));
  assert.match(source,/20260827-governed-context-and-memory-v26/);
  assert.match(index,/decision-cycle-v1\.js\?v=__PILOT_BUILD__/);
  assert.doesNotMatch(index,/decision-workbench-v1\.js/);
  assert.doesNotMatch(source,/new MutationObserver\s*\(/);
  assert.match(source,/sris:evidence-graph-updated/);
  assert.match(source,/sris:mission-opened/);
  assert.match(source,/sris:decision-cycles-updated/);
});

test('Decision Loop uses governed forms instead of browser prompts',()=>{
  assert.doesNotMatch(source,/\bprompt\s*\(/);
  assert.doesNotMatch(source,/\balert\s*\(/);
  for(const id of ['dc1-create-form','dc1-decision','dc1-action','dc1-owner','dc1-due','dc1-expected'])assert.match(source,new RegExp(id));
  assert.match(source,/Fundamento da decisão/);
  assert.match(source,/loadEvidenceOptions/);
  assert.match(source,/Selecione a evidência que fundamenta a decisão/);
  assert.match(source,/Defina a ação antes de avançar o estado da decisão/);
  assert.match(source,/Registe o resultado observado antes de concluir a decisão/);
  assert.match(source,/evidência que fundamenta a decisão tem de ser aceite ou verificada/);
  assert.match(source,/evidência do resultado tem de ser aceite ou verificada/);
});

test('outcomes remain reviewed before organizational reuse',()=>{
  assert.match(source,/materialize-learning/);
  assert.match(source,/Aprendizagem enviada para revisão humana/);
  assert.match(source,/Aceitar aprendizagem/);
  assert.match(source,/Publicar na memória organizacional/);
  assert.match(source,/revisão humana obrigatória/);
});
