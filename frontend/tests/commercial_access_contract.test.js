const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

function read(relativePath){
  return fs.readFileSync(path.join(__dirname, relativePath), 'utf8');
}

test('Create account starts a governed access request instead of collecting a password', () => {
  const html = read('../pilot-v1/home.html');
  const auth = read('../pilot-v1/auth.js');
  assert.match(html, /data-mode="register">Criar conta</);
  assert.match(html, /id="register-submit"[^>]*>Pedir acesso</);
  assert.doesNotMatch(html, /id="reg-password"/);
  assert.match(auth, /\/api\/access-requests/);
  assert.doesNotMatch(auth, /api\('\/api\/pilot\/register'/);
  assert.match(auth, /tab\.disabled=false/);
});

test('Access request keeps a stable form reference across the asynchronous submission', () => {
  const auth = read('../pilot-v1/auth.js');
  assert.match(auth, /const form=e\.currentTarget/);
  assert.match(auth, /form\.reset\(\)/);
  assert.doesNotMatch(auth, /e\.currentTarget\.reset\(\)/);
});

test('Workspace administration stays separate from commercial platform administration', () => {
  const loader = read('../pilot-v1/admin-accounts.js');
  const entitlement = read('../pilot-v1/commercial-entitlement-ui.js');
  const requests = read('../pilot-v1/commercial-requests-ui.js');
  assert.match(loader, /admin-workspace-core\.js/);
  assert.match(loader, /commercial-access-admin\.js/);
  assert.match(entitlement, /commercial-entitlement\/renew/);
  assert.match(entitlement, /Entitlement comercial/);
  assert.match(requests, /\/api\/admin\/access-requests/);
  assert.match(requests, /\/approve/);
  assert.match(requests, /resend-invitation/);
});
