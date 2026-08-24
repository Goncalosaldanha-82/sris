import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const here=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(here,'../..');
const read=relative=>fs.readFileSync(path.join(root,relative),'utf8');

const backendMain=read('backend/app/main.py');
const css=read('frontend/pilot-v1/emergency-stability-v1.css');

test('production shell excludes the two mutually-rewriting runtime layers',()=>{
  assert.match(backendMain,/DISABLED_RUNTIME_ASSETS/);
  assert.match(backendMain,/"pilot-integration-v3\.js"/);
  assert.match(backendMain,/"mission-experience-v1\.js"/);
  assert.match(backendMain,/def _remove_disabled_runtime_assets/);
  assert.match(backendMain,/_remove_disabled_runtime_assets\(html\)/);
  assert.match(backendMain,/20260824-emergency-stability-v1/);
});

test('emergency identity layer forces the territory image and canonical mark',()=>{
  assert.match(css,/url\('\/sunrise\.svg\?v=20260824-emergency-stability-v1'\)/);
  assert.match(css,/\.auth-page \.auth-visual\.auth-visual-photo/);
  assert.match(css,/\.brand-emblem:before/);
  assert.match(css,/\.brand-emblem:after/);
  assert.match(css,/#overview \.hero-card/);
});

test('emergency stylesheet is injected with an immutable build identifier',()=>{
  assert.match(backendMain,/emergency-stability-v1\.css/);
  assert.match(backendMain,/X-SRIS-Pilot-Build/);
  assert.match(backendMain,/no-store, no-cache, must-revalidate/);
});
