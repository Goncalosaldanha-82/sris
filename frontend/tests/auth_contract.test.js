const test = require('node:test');
const assert = require('node:assert/strict');
const { normalizeMe, identityLabel } = require('../assets/contracts.js');

test('normalizes canonical /auth/me response', () => {
  const me = normalizeMe({
    user: { id: 'u1', email: 'admin@example.com', full_name: 'Gonçalo Saldanha' },
    memberships: [{ organization_id: 'o1', organization_name: 'Organização', role: 'admin' }],
  });
  assert.equal(me.user.full_name, 'Gonçalo Saldanha');
  assert.equal(me.memberships[0].organization_id, 'o1');
});

test('survives a flattened user response without full_name', () => {
  const me = normalizeMe({
    id: 'u1',
    email: 'admin@example.com',
    memberships: [{ org_id: 'o1', role: 'admin' }],
  });
  assert.equal(identityLabel(me), 'admin@example.com');
  assert.equal(me.memberships[0].organization_id, 'o1');
});

test('survives data envelopes and alternate display names', () => {
  const me = normalizeMe({
    data: {
      user: { id: 'u1', email: 'admin@example.com', display_name: 'Administrador' },
      memberships: [{ organization: { id: 'o1', name: 'Organização' } }],
    },
  });
  assert.equal(identityLabel(me), 'Administrador');
  assert.equal(me.memberships[0].organization_name, 'Organização');
});

test('returns a safe shape for malformed payloads', () => {
  const me = normalizeMe(null);
  assert.equal(identityLabel(me), 'Utilizador');
  assert.deepEqual(me.memberships, []);
});

const { applyExperienceSnapshot } = require('../assets/contracts.js');

test('applies a coherent experience snapshot without reloading the page', () => {
  const state = { workspace: { graph: { nodes: [] }, audit: [] }, entry: null, map: null, timeline: null };
  const snapshot = {
    generated_at: '2026-07-28T10:00:00Z',
    entry: { attention: [{ rule: 'NEW_OBJECT' }] },
    map: { nodes: [{ id: 'o1', type: 'observation' }], edges: [] },
    timeline: { moments: [{ object_id: 'o1' }] },
  };
  assert.equal(applyExperienceSnapshot(state, snapshot), true);
  assert.equal(state.map.nodes[0].id, 'o1');
  assert.equal(state.workspace.graph.nodes[0].id, 'o1');
  assert.equal(state.workspace.audit[0].rule, 'NEW_OBJECT');
  assert.equal(state.last_experience_refresh, snapshot.generated_at);
});

test('rejects incomplete experience snapshots safely', () => {
  const state = { entry: { previous: true } };
  assert.equal(applyExperienceSnapshot(state, { entry: {} }), false);
  assert.deepEqual(state.entry, { previous: true });
});


test('Decision Workspace is loaded from the backend and explains confidence', () => {
  const fs = require('node:fs');
  const path = require('node:path');
  const app = fs.readFileSync(path.join(__dirname, '../assets/app.js'), 'utf8');
  assert.match(app, /decisions\/\$\{id\}\/workspace/);
  assert.match(app, /Decision Workspace/i);
  assert.match(app, /Sustentação/);
});
