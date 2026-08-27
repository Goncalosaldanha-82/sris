import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const here=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(here,'../..');
const read=relative=>fs.readFileSync(path.join(root,relative),'utf8');

const backendMain=read('backend/app/main.py');
const publicFrontend=read('frontend/atlas-os/index.html');

test('production serves the governed public demonstration frontend',()=>{
  assert.match(backendMain,/FRONTEND_DIR = PROJECT_ROOT \/ "frontend" \/ "atlas-os"/);
  assert.match(backendMain,/20260827-public-demo-v1/);
  assert.match(backendMain,/X-SRIS-Production-Build/);
  assert.match(backendMain,/_production_frontend_html\("index\.html"\)/);
  assert.doesNotMatch(backendMain,/FRONTEND_DIR = PROJECT_ROOT \/ "frontend" \/ "pilot-v1"/);
});

test('public entry preserves the credential-free demonstration boundary',()=>{
  assert.match(publicFrontend,/id="demoButton"/);
  assert.match(publicFrontend,/Abrir demonstração/);
  assert.match(publicFrontend,/sessionStorage\.setItem\("sris_demo","true"\)/);
  assert.match(publicFrontend,/openApp\(\{mode:"demo"\}\)/);
  assert.match(publicFrontend,/A análise por IA não é executada no modo de demonstração/);
});
