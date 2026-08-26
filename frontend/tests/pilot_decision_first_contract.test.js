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
  comparison:read('alternative-matrix-v1.js'),
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
  for(const asset of ['app.js','mission-workspace-v2.js','evidence-graph.js','alternative-matrix-v1.js','validation-protocol.js','learning-lineage.js','decision-cycle-v1.js','admin-accounts.js']){
    assert.equal((index.match(new RegExp(asset.replace('.','\\.'),'g'))||[]).length,1);
  }
  for(const obsolete of ['pilot-integration-v3.js','mission-experience-v1.js','release-hardening-v2.js','decision-workbench-v1.js','intelligence-v2.js']){
    assert.doesNotMatch(index,new RegExp(obsolete.replaceAll('.','\\.')));
  }
});

test('alternative comparison is multicriteria, persistent and decision-neutral',()=>{
  for(const marker of ['Eficácia','Custo','Risco','Reversibilidade','Experiência do hóspede','Robustez da evidência']){
    assert.match(loaded.comparison,new RegExp(marker));
  }
  assert.match(index,/data-open-mission-tab="comparison"/);
  assert.match(loaded.comparison,/20–100 pontos/);
  assert.match(loaded.comparison,/data-acm-live-total/);
  assert.match(loaded.comparison,/Guardar nova revisão/);
  assert.match(loaded.comparison,/Confirmar revisão humana/);
  assert.match(loaded.comparison,/Nenhuma alternativa é selecionada automaticamente/);
  assert.match(loaded.comparison,/sris:alternative-matrix-updated/);
  assert.match(loaded.comparison,/Duplicado exato detetado/);
  assert.match(loaded.comparison,/Retirar duplicado/);
  assert.match(loaded.comparison,/if \(addingAlternative\) return/);
  assert.match(loaded.comparison,/alternative_change\?\.created/);
  assert.match(loaded.comparison,/\/alternatives\/\$\{encodeURIComponent\(alternativeId\)\}\/duplicate/);
});

test('decision foundation uses the human document title instead of a technical UUID',()=>{
  assert.match(loaded.decision,/const foundationLabel=row\.evidence_label/);
  assert.match(loaded.decision,/summaryField\('Fundamento',foundationLabel/);
  assert.doesNotMatch(loaded.decision,/summaryField\('Fundamento',row\.evidence_node_id\?`Evidência/);
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

test('evidence relations confirm persistence where the user creates them',()=>{
  for(const marker of ['id="eg-edge-preview"','id="eg-edge-swap"','id="eg-edge-submit"','id="eg-edge-status"','id="eg-relations"','id="eg-relations-count"']){
    assert.match(loaded.graph,new RegExp(marker));
  }
  assert.match(loaded.graph,/primeiro objeto \+ relação \+ segundo objeto/);
  assert.match(loaded.graph,/é condicionado\/a por/);
  assert.match(loaded.graph,/Exemplo: “Hipótese é condicionada por Restrição”/);
  assert.match(loaded.graph,/Possível direção invertida/);
  assert.match(loaded.graph,/data-edge-reverse/);
  assert.match(loaded.graph,/data-edge-delete/);
  assert.match(loaded.graph,/data-edge-confirm/);
  assert.match(loaded.graph,/data-edge-cancel/);
  assert.match(loaded.graph,/Confirmar inversão/);
  assert.match(loaded.graph,/Confirmar eliminação/);
  assert.match(loaded.graph,/method:'DELETE'/);
  assert.match(loaded.graph,/\/reverse/);
  assert.match(loaded.graph,/operação ficará registada na auditoria/);
  assert.match(loaded.graph,/A guardar e a confirmar a relação no servidor/);
  assert.match(loaded.graph,/Relação criada e confirmada/);
  assert.match(loaded.graph,/Relação já existente e confirmada/);
  assert.match(loaded.graph,/O servidor não devolveu a relação no grafo persistente/);
  assert.match(loaded.graph,/from_node_id===from&&edge\.to_node_id===to&&edge\.edge_type===edgeType/);
});

test('learning reuse is reviewed in-product and shows active inherited context',()=>{
  assert.match(loaded.learning,/data-review-form/);
  assert.match(loaded.learning,/active-context/);
  assert.match(loaded.learning,/Revisão de aplicabilidade nesta missão/);
  assert.match(loaded.learning,/sris:mission-opened/);
  assert.match(loaded.learning,/loadSequence/);
  assert.match(loaded.learning,/code!==missionCode\(\)/);
  assert.doesNotMatch(loaded.learning,/Aprendizagem já revista neste contexto/);
  assert.match(loaded.learning,/apenas aprendizagens publicadas por outras missões/);
  assert.match(loaded.learning,/evitar reutilização circular/);
  assert.match(loaded.learning,/sris:learning-reviewed/);
  assert.match(loaded.learning,/Reutilizar nesta missão/);
  assert.match(loaded.learning,/Revalidar antes de reutilizar/);
  assert.match(loaded.learning,/Não aplicável a esta missão/);
  assert.match(loaded.learning,/canonicamente válida/);
  assert.match(loaded.learning,/data-applicability/);
  assert.match(loaded.learning,/Que diferenças existem entre os contextos\?/);
  assert.match(loaded.learning,/pointerup.*ensureMobileEditorFocus/);
  assert.match(loaded.learning,/pointer-events:auto!important/);
  assert.match(loaded.learning,/enterkeyhint="next"/);
  assert.match(loaded.learning,/enterkeyhint="done"/);
  assert.doesNotMatch(loaded.learning,/O que mudou no contexto\?/);
  assert.doesNotMatch(loaded.learning,/data-disposition/);
});
