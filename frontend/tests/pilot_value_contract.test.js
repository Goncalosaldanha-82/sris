import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const here=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(here,'../..');
const read=relative=>fs.readFileSync(path.join(root,relative),'utf8');
const ui=read('frontend/pilot-v1/pilot-value-v1.js');
const server=read('backend/app/main.py');
const domain=read('backend/app/pilot_value.py');
const migration=read('migrations/versions/20260901_0024_pilot_value_collaboration_reports.py');
const capabilities=read('backend/app/pilot_capabilities.py');

test('value, collaboration and reports are part of the integrated app',()=>{
  assert.match(server,/from app\.pilot_value import router as pilot_value_router/);
  assert.match(server,/app\.include_router\(pilot_value_router\)/);
  assert.match(server,/pilot-value-v1\.js/);
  assert.match(ui,/VALOR DO PILOTO/);
  assert.match(ui,/Valor do piloto/);
  assert.match(ui,/EQUIPA DO PILOTO/);
  assert.match(ui,/REPORT SUITE/);
  assert.match(capabilities,/"pilot_value_case": True/);
  assert.match(capabilities,/"pilot_collaboration_roles": True/);
  assert.match(capabilities,/"pilot_report_suite": True/);
});

test('value status is explicit and realized value requires proof',()=>{
  for(const status of ['expected','estimated','observed','realized']){
    assert.match(domain,new RegExp(`"${status}"`));
    assert.match(ui,new RegExp(`${status}:`));
  }
  for(const field of ['period','baseline_reference','source','calculation','attribution']){
    assert.match(domain,new RegExp(field));
  }
  assert.match(domain,/realized_value_requires_proof/);
  assert.match(domain,/Um benefício realizado exige/);
  assert.match(ui,/Um valor realizado exige período, baseline, fonte, cálculo e avaliação de atribuição/);
});

test('pilot roles include internal and external collaborators without transferring formal authority',()=>{
  for(const role of ['sponsor','pilot_owner','mission_owner','data_owner','operator','reviewer','program_mentor','observer']){
    assert.match(domain,new RegExp(`"${role}"`));
    assert.match(ui,new RegExp(`${role}:`));
  }
  assert.match(domain,/O utilizador indicado não pertence a esta organização/);
  assert.match(ui,/limites de autoridade/);
});

test('report suite covers the operational life of a pilot',()=>{
  for(const report of ['pilot_brief','data_readiness','decision_dossier','progress','outcome','scale_recommendation','full']){
    assert.match(domain,new RegExp(`"${report}"`));
    assert.match(ui,new RegExp(`${report}:`));
  }
  assert.match(domain,/No impact is attributed without baseline/);
  assert.match(ui,/Exportar JSON/);
  assert.match(ui,/Ver \/ imprimir/);
});

test('value extension is deterministic and does not override global fetch or DOM observation',()=>{
  assert.doesNotMatch(ui,/MutationObserver/);
  assert.doesNotMatch(ui,/window\.fetch\s*=/);
  assert.doesNotMatch(ui,/\bprompt\s*\(/);
  assert.doesNotMatch(ui,/\bconfirm\s*\(/);
  assert.doesNotMatch(ui,/\balert\s*\(/);
  assert.match(ui,/window\.SRISPilotValue=/);
});

test('migration creates and removes both value and collaboration tables',()=>{
  assert.match(migration,/sris_pilot_value_items/);
  assert.match(migration,/sris_pilot_collaborators/);
  assert.match(migration,/down_revision[^\n]+20260901_0023/);
  assert.match(migration,/drop_table\("sris_pilot_collaborators"\)/);
  assert.match(migration,/drop_table\("sris_pilot_value_items"\)/);
});
