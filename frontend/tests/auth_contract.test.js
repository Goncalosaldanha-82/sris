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

test('Mission portfolio UI creates canonical missions and renders hierarchy', () => {
  const fs = require('node:fs');
  const path = require('node:path');
  const html = fs.readFileSync(path.join(__dirname, '../atlas-os/index.html'), 'utf8');
  assert.match(html, /id="missionCreateForm"/);
  assert.match(html, /parent_mission_id/);
  assert.match(html, /mission_kind/);
  assert.match(html, /mission-intelligence\/missions`/);
  assert.match(html, /method:editing\?"PATCH":"POST"/);
  assert.match(html, /data-depth=/);
  assert.match(html, /function missionOrder/);
  assert.match(html, /children\.get\(item\.id\)/);
  assert.match(html, /\|\| "M-002"/);
});

test('institutional sessions renew automatically before retrying protected requests', () => {
  const fs = require('node:fs');
  const path = require('node:path');
  const html = fs.readFileSync(path.join(__dirname, '../atlas-os/index.html'), 'utf8');
  assert.match(html, /\/api\/auth\/refresh/);
  assert.match(html, /async function authenticatedFetch/);
  assert.match(html, /if\(response\.status!==401\)return response/);
  assert.match(html, /Authorization:`Bearer \$\{renewedToken\}`/);
  assert.match(html, /async function recoverLatestDialogueSession[\s\S]*?authenticatedFetch\([\s\S]*?dialogues\?mission_code/);
  assert.match(html, /async function refreshAIGovernanceStatus[\s\S]*?authenticatedFetch\([\s\S]*?ai-governance/);
});

test('choice questions accept a predefined option, free text, or both', () => {
  const fs = require('node:fs');
  const path = require('node:path');
  const html = fs.readFileSync(path.join(__dirname, '../atlas-os/index.html'), 'utf8');
  assert.match(html, /data-mi-choice-custom/);
  assert.match(html, /Outra resposta ou complemento \(opcional\)/);
  assert.match(html, /selected&&custom\?`\$\{selected\} — \$\{custom\}`:custom\|\|selected/);
});

test('Mission Intelligence reads governed attachments from each question', () => {
  const fs = require('node:fs');
  const path = require('node:path');
  const html = fs.readFileSync(path.join(__dirname, '../atlas-os/index.html'), 'utf8');
  assert.match(html, /data-mi-upload-trigger/);
  assert.match(html, /\.pdf,\.html,\.htm,\.md,\.markdown,\.txt,\.csv,\.tsv,\.xlsx,\.xls,\.docx,\.pptx,\.png,\.jpg,\.jpeg,\.webp,\.gif/);
  assert.match(html, /async function uploadMIAttachments/);
  assert.match(html, /mission-intelligence\/missions\/\$\{encodeURIComponent\(m\.id\)\}\/attachments/);
  assert.match(html, /attachment_ids:\[\.\.\.pendingMIAttachmentIds\]/);
  assert.match(html, /function attachmentProcessingLabel/);
  assert.match(html, /archive_chunk_count/);
  assert.match(html, /function miAttachmentTraceHTML/);
  assert.match(html, /Anexos efetivamente processados neste turno/);
  assert.match(html, /citation_locations/);
  assert.match(html, /provider_attachments_not_cited:"A resposta não demonstrou uso dos anexos selecionados"/);
  assert.match(html, /## Anexos processados e citados/);
});

test('Mission Intelligence exposes concise epistemic confidence and export views', () => {
  const fs = require('node:fs');
  const path = require('node:path');
  const html = fs.readFileSync(path.join(__dirname, '../atlas-os/index.html'), 'utf8');
  assert.match(html, /Mapa epistemológico deste turno/);
  assert.match(html, /Facto verificado/);
  assert.match(html, /Declaração do utilizador/);
  assert.match(html, /Evidência necessária/);
  assert.match(html, /Confiança na decisão/);
  assert.match(html, /function miConfidenceCalibrationHTML/);
  assert.match(html, /Gate epistemológico aplicado/);
  assert.match(html, /result\.confidence_calibration/);
  assert.match(html, /Ver raciocínio completo e fontes/);
  assert.match(html, /data-mi-print="turn"/);
  assert.match(html, /data-mi-export="session"/);
  assert.match(html, /function exportMissionIntelligence/);
  assert.match(html, /detalhes técnicos recolhidos/);
  assert.match(html, /provider_output_invalid:"A resposta da IA não cumpriu o contrato estruturado"/);
  assert.match(html, /provider_output_incomplete:"A resposta da IA terminou antes de concluir"/);
  assert.match(html, /provider_context_limit:"O fornecedor recusou até a janela mínima/);
  assert.match(html, /Arquivo integral:/);
  assert.match(html, /result\.context_manifest\|\|\{\}/);
  assert.match(html, /provider_refused:"A IA recusou este pedido"/);
  assert.match(html, /Código técnico:/);
  assert.match(html, /O limiar mensal de monitorização foi ultrapassado/);
});

test('the situation chain always includes the ninth learning card', () => {
  const fs = require('node:fs');
  const path = require('node:path');
  const html = fs.readFileSync(path.join(__dirname, '../atlas-os/index.html'), 'utf8');
  assert.match(html, /function missionDecisionChain/);
  assert.match(html, /label:"Aprendizagem"/);
  assert.match(html, /missionDecisionChain\(m\)\.map/);
});
