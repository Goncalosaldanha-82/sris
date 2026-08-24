import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const here=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(here,'../..');
const read=relative=>fs.readFileSync(path.join(root,relative),'utf8');
const index=read('frontend/pilot-v1/index.html');
const app=read('frontend/pilot-v1/app.js');
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
  assert.match(index,/A missão, a evidência, a decisão e a memória permanecem canónicas/);
});
