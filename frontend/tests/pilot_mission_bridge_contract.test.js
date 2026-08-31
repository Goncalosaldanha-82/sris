import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const here=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(here,'../..');
const read=relative=>fs.readFileSync(path.join(root,relative),'utf8');
const bridge=read('frontend/pilot-v1/pilot-mission-bridge-v1.js');
const server=read('backend/app/main.py');

test('pilot can create a mission without leaving an unlinked orphan',()=>{
  assert.match(bridge,/data-create-pilot-mission/);
  assert.match(bridge,/sris_pending_pilot_mission_link/);
  assert.match(bridge,/previousMissionId/);
  assert.match(bridge,/submitted:true/);
  assert.match(bridge,/link_role:'primary'/);
  assert.match(bridge,/Missão criada e ligada automaticamente/);
});

test('mission form is prefilled from the governed pilot contract',()=>{
  for(const field of ['#mission-title','#mission-objective','#mission-question','#mission-context','#mission-assumptions','#mission-constraints']){
    assert.match(bridge,new RegExp(field.replace('#','\\#')));
  }
  assert.match(bridge,/current\.charter\?\.success_definition/);
  assert.match(bridge,/current\.charter\?\.suspension_conditions/);
  assert.match(bridge,/Origem do piloto/);
});

test('bridge is bounded, session-scoped and does not patch global browser functions',()=>{
  assert.match(bridge,/30\*60\*1000/);
  assert.match(bridge,/sessionStorage/);
  assert.doesNotMatch(bridge,/MutationObserver/);
  assert.doesNotMatch(bridge,/window\.fetch\s*=/);
  assert.doesNotMatch(bridge,/\bprompt\s*\(/);
  assert.doesNotMatch(bridge,/\bconfirm\s*\(/);
  assert.doesNotMatch(bridge,/\balert\s*\(/);
});

test('integrated server loads the bridge after the pilot workspace',()=>{
  assert.match(server,/pilot-platform-v1\.js/);
  assert.match(server,/pilot-value-v1\.js/);
  assert.match(server,/pilot-mission-bridge-v1\.js/);
});
