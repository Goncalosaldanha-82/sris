import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const here=path.dirname(fileURLToPath(import.meta.url));
const pilot=path.resolve(here,'../pilot-v1');
const read=name=>fs.readFileSync(path.join(pilot,name),'utf8');

const index=read('index.html');
const integration=read('pilot-integration-v3.js');
const hardening=read('release-hardening-v2.js');

test('release hardening assets parse and are loaded by the Pilot shell',()=>{
  assert.doesNotThrow(()=>new Function(integration));
  assert.doesNotThrow(()=>new Function(hardening));
  assert.match(index,/pilot-integration-v3\.js/);
  assert.match(integration,/release-hardening-v2\.js/);
});

test('navigation and institutional brand are operational rather than decorative',()=>{
  assert.match(hardening,/sris-menu-toggle/);
  assert.match(hardening,/sris-sidebar-open/);
  assert.match(hardening,/aria-expanded/);
  assert.match(hardening,/sris-mark-v2/);
  assert.match(hardening,/Mission Intelligence/);
});

test('mission documents and report downloads are first-class actions',()=>{
  for(const marker of [
    'Carregar documentos',
    'sris-upload-zone',
    'Relatório completo (.pdf)',
    'Relatório completo (.html)',
    'Secção atual (.md)',
    'makePdf',
  ])assert.match(hardening,new RegExp(marker.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));
});

test('assisted analysis reports runtime truth and remains optional',()=>{
  assert.match(hardening,/Análise assistida disponível/);
  assert.match(hardening,/Análise assistida indisponível/);
  assert.match(hardening,/O Mission Workspace continua operacional sem IA/);
  assert.match(hardening,/disabled=!ready/);
});

test('editorial photography is used without replacing the working surface',()=>{
  assert.match(hardening,/url\('\/sunrise\.svg'\)/);
  assert.match(hardening,/Compreender antes de intervir/);
  assert.match(hardening,/nunca preencher lacunas com confiança artificial/);
});
