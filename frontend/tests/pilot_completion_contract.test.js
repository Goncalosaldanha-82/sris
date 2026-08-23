import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const here=path.dirname(fileURLToPath(import.meta.url));
const pilot=path.resolve(here,'../pilot-v1');
const read=name=>fs.readFileSync(path.join(pilot,name),'utf8');
const index=read('index.html');
const experience=read('mission-experience-v1.js');

test('Pilot completion layer is loaded by the decision-first application',()=>{
  assert.match(index,/mission-experience-v1\.js/);
  assert.match(experience,/20260823-product-core-v1/);
});

test('Mission documents are first-class and support visible multi-file upload',()=>{
  for(const marker of [
    'sris-upload-zone',
    'Selecionar documentos',
    'multiple accept=',
    'dragenter',
    'mission-intelligence/missions',
    'attachments',
  ]) assert.match(experience,new RegExp(marker));
});

test('Mission and section exports are available without exposing provider details',()=>{
  for(const marker of [
    'Guardar relatório em PDF',
    'Descarregar missão',
    'Exportar secção atual',
    'text/markdown',
    'window.print',
  ]) assert.match(experience,new RegExp(marker));
  assert.doesNotMatch(experience,/gpt-5\.6-terra/);
});

test('Navigation and institutional brand are operational rather than decorative',()=>{
  assert.match(experience,/sris-site-mark/);
  assert.match(experience,/Abrir ou fechar navegação/);
  assert.match(experience,/sris-sidebar-collapsed/);
  assert.match(experience,/MISSION INTELLIGENCE/);
});

test('Assisted analysis is enabled only after runtime confirmation',()=>{
  assert.match(experience,/Análise assistida disponível/);
  assert.match(experience,/Análise assistida ainda não disponível/);
  assert.match(experience,/api\/pilot\/capabilities/);
  assert.match(experience,/buttons\.forEach\(b=>\{b\.disabled=!available/);
});
