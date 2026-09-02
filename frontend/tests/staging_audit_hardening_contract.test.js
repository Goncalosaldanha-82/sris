import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const read=(path)=>fs.readFileSync(new URL(`../../${path}`,import.meta.url),'utf8');

test('entry copy follows the runtime signup gate and reset uses one route family',()=>{
  const auth=read('frontend/pilot-v1/auth.js');
  const home=read('frontend/pilot-v1/home.html');
  assert.match(auth,/function loginSubtitle\(\)/);
  assert.match(auth,/acesso de novas organizações é feito por convite/);
  assert.match(auth,/\/api\/auth\/password-reset\/request/);
  assert.match(auth,/\/api\/auth\/password-reset\/confirm/);
  assert.doesNotMatch(auth,/\/api\/pilot\/password-reset\/confirm/);
  assert.match(home,/Entre no seu workspace para continuar\./);
});

test('account and mission controls use the active build and accessible names',()=>{
  const account=read('frontend/pilot-v1/account.html');
  const index=read('frontend/pilot-v1/index.html');
  assert.match(account,/pilot\.css\?v=__PILOT_BUILD__/);
  assert.match(account,/sris-logo-compact-dark\.svg\?v=__PILOT_BUILD__/);
  assert.doesNotMatch(account,/20260828-brand-system-v30/);
  assert.match(index,/id="mission-search"[^>]+aria-label="Pesquisar missões"/);
  assert.match(index,/id="mission-file"[^>]+aria-label="Selecionar documentos da missão"/);
});

test('empty mission-dependent areas explain their own prerequisite',()=>{
  const app=read('frontend/pilot-v1/app.js');
  for(const phrase of [
    'Selecione ou crie uma missão para estruturar a evidência.',
    'Selecione ou crie uma missão para definir a baseline e medir o impacto.',
    'Selecione ou crie uma missão para abrir o Business Case Vivo.',
    'Selecione ou crie uma missão para rever e preservar aprendizagem.',
  ])assert.ok(app.includes(phrase),phrase);
});

test('entry contrast override is explicit',()=>{
  const css=read('frontend/pilot-v1/pilot.css');
  assert.match(css,/#auth-subtitle,#trial-copy\{color:#5f7068\}/);
});
