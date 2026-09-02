import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const here=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(here,'../..');
const read=relative=>fs.readFileSync(path.join(root,relative),'utf8');
const platform=read('frontend/pilot-v1/pilot-platform-v1.js');
const server=read('backend/app/main.py');
const capabilities=read('backend/app/pilot_capabilities.py');
const domain=read('backend/app/pilot_platform.py');
const migration=read('migrations/versions/20260901_0023_pilot_mission_platform.py');

test('Pilot and Mission Intelligence is an explicit isolated product surface',()=>{
  assert.match(server,/from app\.pilot_platform import router as pilot_platform_router/);
  assert.match(server,/app\.include_router\(pilot_platform_router\)/);
  assert.match(server,/pilot-platform-v1\.js/);
  assert.match(platform,/PILOT & MISSION INTELLIGENCE/);
  assert.match(platform,/data-section='pilots'|data\.section='pilots'|dataset\.section='pilots'/);
  assert.match(platform,/Pilot Charter|PILOT CHARTER/);
  assert.match(platform,/DATA READINESS/);
  assert.match(platform,/PILOT SCORECARD/);
  assert.match(platform,/SCALE RECOMMENDATION/);
});

test('five user moments and eight persistent records stay distinct',()=>{
  for(const moment of ['Contexto','Evidência','Decisão','Medição','Memória'])assert.match(platform,new RegExp(moment));
  for(const record of ['Observação','Evidência','Hipótese','Alternativa','Decisão','Ação','Resultado','Aprendizagem'])assert.match(platform,new RegExp(record));
  assert.match(capabilities,/USER_MOMENTS/);
  assert.match(capabilities,/CANONICAL_RECORDS/);
  assert.match(capabilities,/"canonical_mission_chain": CANONICAL_RECORDS/);
  assert.doesNotMatch(capabilities,/"context",\s*"observation"/);
});

test('sector profiles configure one universal core instead of forking products',()=>{
  assert.match(domain,/universal_core_configurable_profiles/);
  for(const profile of ['cross_sector','hospitality','public_sector','industrial_operations','territorial_lab','research_and_innovation'])assert.match(domain,new RegExp(profile));
  for(const template of ['hospitality_resource_efficiency','hospitality_operational_intelligence','public_service_improvement','investment_validation','research_and_innovation_validation'])assert.match(domain,new RegExp(template));
  assert.match(domain,/PROFILE_CATALOG_VERSION/);
  assert.match(domain,/EXPECTED_PROFILE_KEYS/);
  assert.match(domain,/program_source/);
  assert.match(domain,/tourism_advance/);
  assert.match(platform,/research_and_innovation:'Investigação e inovação'/);
  assert.match(platform,/catalog\.program_sources/);
  assert.match(platform,/programSourceOptions/);
  assert.doesNotMatch(platform,/\.slice\(0,4\)/);
});

test('pilot value remains evidence-backed and does not invent results',()=>{
  assert.match(domain,/baseline_value/);
  assert.match(domain,/current_value/);
  assert.match(domain,/limitations/);
  assert.match(domain,/Nenhum benefício é apresentado como realizado/);
  assert.match(platform,/sem precisão fictícia/);
  assert.match(platform,/Valor sem ficção/);
});

test('platform extension is deterministic and does not replace browser primitives',()=>{
  assert.doesNotMatch(platform,/MutationObserver/);
  assert.doesNotMatch(platform,/window\.fetch\s*=/);
  assert.doesNotMatch(platform,/\bprompt\s*\(/);
  assert.doesNotMatch(platform,/\bconfirm\s*\(/);
  assert.doesNotMatch(platform,/\balert\s*\(/);
  assert.match(platform,/window\.SRISPlatform=/);
});

test('database migration covers pilots, missions, metrics, sources and delivery',()=>{
  for(const table of ['sris_pilots','sris_pilot_missions','sris_pilot_metrics','sris_pilot_data_sources','sris_pilot_work_items'])assert.match(migration,new RegExp(table));
  assert.match(migration,/down_revision[^\n]+20260827_0022/);
});
