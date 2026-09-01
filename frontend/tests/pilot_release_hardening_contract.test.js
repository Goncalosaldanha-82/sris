import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const here=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(here,'../..');
const read=relative=>fs.readFileSync(path.join(root,relative),'utf8');
const index=read('frontend/pilot-v1/index.html');
const home=read('frontend/pilot-v1/home.html');
const account=read('frontend/pilot-v1/account.html');
const app=read('frontend/pilot-v1/app.js');
const css=read('frontend/pilot-v1/pilot.css');
const server=read('backend/app/main.py');
const config=read('backend/app/atlas_platform/config.py');
const migrations=read('migrations/env.py');

test('server serves the declared build without hidden asset injection',()=>{
  assert.match(server,/html\.replace\("__PILOT_BUILD__", PILOT_BUILD\)/);
  assert.doesNotMatch(server,/DISABLED_RUNTIME_ASSETS|_inject_stable_runtime|release-hardening-v2/);
  assert.match(server,/X-SRIS-Pilot-Build/);
  assert.match(index,/__PILOT_BUILD__/);
});

test('Railway database resolution is shared and rejects ephemeral SQLite',()=>{
  assert.match(config,/os\.getenv\("ATLAS_DATABASE_URL"/);
  assert.match(config,/os\.getenv\("DATABASE_URL"/);
  assert.match(config,/managed deployments cannot use SQLite/);
  assert.match(migrations,/settings\.database_url/);
  assert.doesNotMatch(migrations,/os\.getenv\("ATLAS_DATABASE_URL"\)/);
});

test('navigation is direct, accessible and closes deterministically',()=>{
  assert.match(index,/id="menu-btn"[^>]+aria-expanded="false"/);
  assert.match(index,/id="sidebar-backdrop"/);
  assert.match(app,/function setMenu\(open\)/);
  assert.match(app,/event\.key==='Escape'/);
  assert.match(app,/setAttribute\('aria-expanded'/);
});

test('runtime truth disables unconfigured assistance without blocking missions',()=>{
  assert.match(app,/function setAssistanceState\(ready\)/);
  assert.match(app,/submit\.disabled=!ready/);
  assert.match(app,/A assistência não está configurada neste serviço/);
  assert.match(index,/id="assistance-unavailable"/);
  assert.match(index,/Continuar no espaço de missão/);
  assert.match(index,/A missão, a evidência, a decisão e a memória permanecem canónicas/);
});

test('external readiness is evidence-backed and the mission chain is canonical',()=>{
  assert.match(index,/id="release-readiness-panel"/);
  assert.match(index,/data-cycle-step="0">Contexto<\/button>/);
  assert.match(index,/data-cycle-step="3">Medição<\/button>/);
  assert.match(index,/data-cycle-step="4">Memória<\/button>/);
  assert.match(index,/Memória → revalidação → novo Contexto/);
  assert.match(index,/Condições transversais de validade/);
  assert.match(index,/id="cycle-prev"/);
  assert.match(index,/id="cycle-next"/);
  assert.match(app,/\/api\/pilot\/release-readiness/);
  assert.match(app,/source==='human_acceptance'/);
  assert.match(app,/evidence\.length<10/);
});

test('mobile mission creation wins the synchronization race and stays actionable',()=>{
  assert.match(app,/const missionSync=section==='mission'&&orgId\(\)/);
  assert.match(app,/await go\('mission'\)/);
  assert.match(app,/dataset\.mode!=='editor'/);
  assert.match(app,/revealMissionWorkspace\(\$\('#mission-editor'\)\)/);
  assert.match(index,/id="primary-mission-cta"/);
  assert.match(index,/id="empty-new-btn"/);
  assert.match(index,/class="mission-path-details"/);
  assert.match(css,/calc\(126px \+ env\(safe-area-inset-bottom\)\)/);
  assert.match(css,/#mission\[data-mode="editor"\] \.mission-rail/);
  assert.match(css,/scroll-snap-type:x mandatory/);
});
test('official SRIS vector identity is consistent across platform surfaces',()=>{
  const pages=home+'\n'+index+'\n'+account;
  assert.match(home,/sris-logo-compact-dark\.svg/);
  assert.match(home,/sris-logo-compact-light\.svg/);
  assert.match(index,/sris-logo-compact-dark\.svg/);
  assert.match(index,/sris-mark-dark\.svg/);
  assert.match(account,/sris-logo-compact-dark\.svg/);
  assert.equal((pages.match(/sris-favicon\.svg/g)||[]).length,3);
  assert.doesNotMatch(pages,/class="brand-emblem/);
  assert.match(css,/\.brand-lockup-image/);
  assert.match(app,/REPORT_BRAND_DATA_URI/);
  for(const asset of ['sris-logo-compact-dark.svg','sris-logo-compact-light.svg','sris-mark-dark.svg','sris-favicon.svg']){
    assert.equal(fs.existsSync(path.join(root,'frontend/pilot-v1',asset)),true);
  }
});

