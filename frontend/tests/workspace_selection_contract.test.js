const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..', '..');
const read = relative => fs.readFileSync(path.join(root, relative), 'utf8');

test('workspace selection is explicit, persistent and request-scoped', () => {
  const html = read('frontend/pilot-v1/index.html');
  const app = read('frontend/pilot-v1/app.js');
  const database = read('backend/app/atlas_platform/database.py');
  const main = read('backend/app/main.py');
  const product = read('backend/app/pilot_product.py');

  assert.match(html, /id="workspace-selector"/);
  assert.match(html, /espaço selecionado/);
  assert.match(app, /X-SRIS-Organization/);
  assert.match(app, /sris_workspace_selection/);
  assert.match(app, /organization_id=\$\{encodeURIComponent\(preferred\)\}/);
  assert.match(database, /class WorkspaceAwareQuery/);
  assert.match(database, /Membership\.organization_id == organization_id/);
  assert.match(main, /request\.headers\.get\("x-sris-organization"\)/);
  assert.match(product, /selected_by/);
  assert.match(product, /mission_activity/);
  assert.match(product, /"workspaces"/);
});
