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
const css=read('pilot.css');
const loaded={
  app:read('app.js'),
  auth:read('auth.js'),
  workspace:read('mission-workspace-v2.js'),
  graph:read('evidence-graph.js'),
  validation:read('validation-protocol.js'),
  learning:read('learning-lineage.js'),
  decision:read('decision-cycle-v1.js'),
  admin:read('admin-accounts.js'),
};

test('the Pilot has one explicit browser composition',()=>{
  for(const [name,source] of Object.entries(loaded)){
    assert.doesNotThrow(()=>new Function(source),`${name} must parse`);
    assert.doesNotMatch(source,/new MutationObserver\s*\(/,`${name} must not rewrite the DOM through a broad observer`);
    assert.doesNotMatch(source,/window\.fetch\s*=/,`${name} must not replace global fetch`);
    assert.doesNotMatch(source,/\b(?:prompt|alert|confirm)\s*\(/,`${name} must use governed in-product forms`);
  }
  assert.equal((home.match(/rel="stylesheet"/g)||[]).length,1);
  assert.equal((index.match(/rel="stylesheet"/g)||[]).length,1);
  assert.match(home,/pilot\.css\?v=__PILOT_BUILD__/);
  for(const asset of ['app.js','mission-workspace-v2.js','evidence-graph.js','validation-protocol.js','learning-lineage.js','decision-cycle-v1.js','admin-accounts.js']){
    assert.equal((index.match(new RegExp(asset.replace('.','\\.'),'g'))||[]).length,1);
  }
  for(const obsolete of ['pilot-integration-v3.js','mission-experience-v1.js','release-hardening-v2.js','decision-workbench-v1.js','intelligence-v2.js']){
    assert.doesNotMatch(index,new RegExp(obsolete.replaceAll('.','\\.')));
  }
});

test('Mission Workspace remains the product centre and assistance is secondary',()=>{
  assert.match(index,/O que precisa de atenção agora\./);
  assert.match(index,/Retomar trabalho/);
  assert.match(index,/FILA DE ATENÇÃO/);
  assert.match(index,/Análise assistida, não centro do produto\./);
  assert.match(index,/Humana obrigatória/i);
  assert.doesNotMatch(index,/data-section="billing"|Créditos e planos|gpt-5\.6-terra/);
  assert.doesNotMatch(loaded.workspace,/model_or_system|embedding_model|credit_eur/);
  for(const marker of ['Eficiência de recursos','Problema operacional','Investimento ou alteração','Critério de sucesso']){
    assert.match(index,new RegExp(marker));
  }
});

test('entry page uses the valid institutional sunrise and survives the iPhone keyboard',()=>{
  assert.match(home,/class="auth-photo"/);
  assert.match(home,/territory-sunrise\.webp\?v=__PILOT_BUILD__/);
  assert.match(home,/PILOTO V1 · VALIDAÇÃO OPERACIONAL/);
  assert.match(home,/id="login-submit"/);
  assert.match(css,/\.keyboard-open \.auth-visual\{display:none\}/);
  assert.match(css,/env\(safe-area-inset-bottom\)/);
  assert.match(css,/font-size:16px/);
  assert.match(loaded.auth,/visualViewport/);
  assert.match(loaded.auth,/scrollIntoView/);
  assert.match(loaded.auth,/location\.assign\('\/app'\)/);
});

test('sessions refresh once before protected work is abandoned',()=>{
  assert.match(loaded.app,/async function renewSession/);
  assert.match(loaded.app,/\/api\/auth\/refresh/);
  assert.match(loaded.app,/response\.status===401&&retryAuth&&refreshToken\(\)/);
  assert.match(loaded.app,/return rawApi\(path,\{\.\.\.options,retryAuth:false\}\)/);
  for(const name of ['workspace','graph','validation','learning','decision','admin']){
    assert.match(loaded[name],/window\.SRISApi\?\.request/);
  }
});

test('documents and auditable report exports are canonical actions',()=>{
  assert.match(index,/id="mission-file" multiple/);
  assert.match(index,/id="upload-drop-zone"/);
  assert.match(index,/id="attachment-extraction-panel"/);
  assert.match(index,/data-report="print"/);
  assert.match(index,/data-report="html"/);
  assert.match(index,/data-report="json"/);
  assert.match(index,/data-report="md"/);
  assert.match(loaded.app,/async function uploadFiles/);
  assert.match(loaded.app,/async function loadAttachmentExtraction/);
  assert.match(loaded.app,/document-evidence/);
  assert.match(loaded.app,/EXTRAÇÃO DOCUMENTAL · SEM IA/);
  assert.match(loaded.app,/data-download-attachment/);
  assert.match(loaded.app,/function completeReportHtml/);
  assert.match(loaded.app,/function exportReport/);
  assert.match(loaded.app,/async function reportSnapshot/);
  assert.match(loaded.app,/crypto\.subtle\.digest/);
});

test('canonical transverse objects retain human provenance',()=>{
  for(const id of ['mission-assumptions','mission-constraints','mission-success'])assert.match(index,new RegExp(`id="${id}"`));
  assert.match(loaded.app,/createGraphNode\(mission\.code,'assumption'/);
  assert.match(loaded.app,/createGraphNode\(mission\.code,'constraint'/);
  assert.match(loaded.app,/source:'mission_onboarding'/);
  assert.match(loaded.graph,/value="gap"/);
  assert.match(loaded.graph,/value="alternative"/);
});

test('learning reuse is reviewed in-product and shows active inherited context',()=>{
  assert.match(loaded.learning,/data-review-form/);
  assert.match(loaded.learning,/active-context/);
  assert.match(loaded.learning,/Aprendizagem já revista neste contexto/);
  assert.match(loaded.learning,/sris:learning-reviewed/);
});
