import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const here=path.dirname(fileURLToPath(import.meta.url));
const pilot=path.resolve(here,'../pilot-v1');
const source=fs.readFileSync(path.join(pilot,'decision-cycle-v1.js'),'utf8');
const index=fs.readFileSync(path.join(pilot,'index.html'),'utf8');

test('Decision Loop V2 is syntactically valid and cache-busted',()=>{
  assert.doesNotThrow(()=>new Function(source));
  assert.match(source,/20260822-decision-loop-v2/);
  assert.match(index,/decision-cycle-v1\.js\?v=20260822-decision-loop-v2/);
  assert.ok(index.indexOf('decision-cycle-v1.js')<index.indexOf('decision-workbench-v1.js'));
});

test('Decision Loop replaces browser prompts with governed forms',()=>{
  assert.doesNotMatch(source,/\bprompt\s*\(/);
  assert.doesNotMatch(source,/\balert\s*\(/);
  for(const id of ['dc1-create-form','dc1-decision','dc1-action','dc1-owner','dc1-due','dc1-expected']){
    assert.match(source,new RegExp(id));
  }
  assert.match(source,/Defina a ação antes de avançar o estado da decisão/);
  assert.match(source,/Registe o resultado observado antes de concluir a decisão/);
});

test('Decision outcomes remain governed before organizational reuse',()=>{
  assert.match(source,/materialize-learning/);
  assert.match(source,/learning_status|Aprendizagem enviada para revisão humana/);
  assert.match(source,/Aceitar aprendizagem/);
  assert.match(source,/Publicar na memória organizacional/);
  assert.match(source,/revisão humana obrigatória/);
});
