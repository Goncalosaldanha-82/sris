import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';

const BASE = (process.env.SRIS_STAGING_URL || 'https://sris-pilot-v1-staging.up.railway.app').replace(/\/$/, '');
const OUT = process.env.QA_OUTPUT_DIR || 'qa-artifacts';
fs.mkdirSync(OUT, { recursive: true });

const report = {
  started_at: new Date().toISOString(),
  base_url: BASE,
  expected_build: process.env.SRIS_EXPECTED_BUILD || '20260902-workspace-continuity-v36',
  checks: [],
  findings: [],
  http: [],
  api_routes: [],
  browser_requests: [],
  console: [],
  page_errors: [],
  request_failures: [],
  dom_inventory: {},
};

function finding(severity, area, title, detail = '', evidence = {}) {
  report.findings.push({ severity, area, title, detail, evidence });
}
function check(name, ok, detail = '', severity = 'major', evidence = {}) {
  report.checks.push({ name, ok: Boolean(ok), detail, severity, evidence });
  if (!ok) finding(severity, 'check', name, detail, evidence);
  return Boolean(ok);
}
function safeJson(text) {
  try { return JSON.parse(text); } catch { return null; }
}
async function http(method, urlPath, { headers = {}, body, expected, timeoutMs = 30000 } = {}) {
  const url = urlPath.startsWith('http') ? urlPath : `${BASE}${urlPath}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const started = performance.now();
  let response;
  let text = '';
  let error = null;
  try {
    response = await fetch(url, { method, headers, body, redirect: 'follow', signal: controller.signal });
    text = await response.text();
  } catch (err) {
    error = String(err?.stack || err);
  } finally {
    clearTimeout(timer);
  }
  const elapsed_ms = Math.round(performance.now() - started);
  const item = {
    method, url, elapsed_ms, error,
    status: response?.status ?? null,
    content_type: response?.headers.get('content-type') || '',
    build: response?.headers.get('x-sris-pilot-build') || '',
    cache_control: response?.headers.get('cache-control') || '',
    request_id: response?.headers.get('x-request-id') || '',
  };
  report.http.push(item);
  if (expected) check(`${method} ${urlPath} status`, expected.includes(item.status), `status=${item.status}; expected=${expected.join(',')}`, 'critical', item);
  if (error) finding('critical', 'network', `${method} ${urlPath} failed`, error, item);
  return { response, text, json: safeJson(text), item };
}

function localAssetUrls(html, basePath = '/') {
  const urls = new Set();
  const re = /(?:src|href)=["']([^"']+)["']/g;
  for (const match of html.matchAll(re)) {
    const value = match[1];
    if (!value || value.startsWith('#') || value.startsWith('mailto:') || value.startsWith('tel:') || value.startsWith('data:') || value.startsWith('http')) continue;
    try { urls.add(new URL(value, `${BASE}${basePath}`).pathname + new URL(value, `${BASE}${basePath}`).search); } catch {}
  }
  return [...urls];
}

function securityHeaderChecks(result, label) {
  if (!result.response) return;
  const h = result.response.headers;
  check(`${label}: X-Content-Type-Options`, h.get('x-content-type-options') === 'nosniff', String(h.get('x-content-type-options')), 'major');
  check(`${label}: X-Frame-Options`, h.get('x-frame-options') === 'DENY', String(h.get('x-frame-options')), 'major');
  check(`${label}: Referrer-Policy`, Boolean(h.get('referrer-policy')), String(h.get('referrer-policy')), 'minor');
  check(`${label}: Permissions-Policy`, Boolean(h.get('permissions-policy')), String(h.get('permissions-policy')), 'minor');
  check(`${label}: Content-Security-Policy`, Boolean(h.get('content-security-policy')), String(h.get('content-security-policy')), 'major');
  check(`${label}: HSTS`, Boolean(h.get('strict-transport-security')), String(h.get('strict-transport-security')), 'major');
}

async function publicAndApiRecon() {
  const publicPaths = ['/', '/app', '/account.html', '/demonstracao', '/api/pilot/capabilities', '/openapi.json'];
  const results = {};
  for (const p of publicPaths) {
    results[p] = await http('GET', p, { expected: [200] });
    securityHeaderChecks(results[p], p);
    check(`${p}: response time under 8s`, results[p].item.elapsed_ms < 8000, `${results[p].item.elapsed_ms}ms`, 'major');
  }

  const home = results['/'];
  const app = results['/app'];
  check('Home has no unreplaced build token', !home.text.includes('__PILOT_BUILD__'), 'Found __PILOT_BUILD__ in live HTML', 'critical');
  check('App has no unreplaced build token', !app.text.includes('__PILOT_BUILD__'), 'Found __PILOT_BUILD__ in live HTML', 'critical');

  const builds = publicPaths.map(p => results[p].item.build).filter(Boolean);
  check('Build header exists on public/API routes', builds.length >= 4, JSON.stringify(builds), 'critical');
  const uniqueBuilds = [...new Set(builds)];
  check('Build header consistent across routes', uniqueBuilds.length === 1, JSON.stringify(uniqueBuilds), 'critical');
  if (uniqueBuilds[0]) check('Deployed build matches expected branch build', uniqueBuilds[0] === report.expected_build, `deployed=${uniqueBuilds[0]} expected=${report.expected_build}`, 'critical');

  for (const [p, r] of Object.entries(results)) {
    if (p === '/openapi.json') continue;
    const cc = r.item.cache_control.toLowerCase();
    check(`${p}: no-store on dynamic route`, cc.includes('no-store'), r.item.cache_control, 'major');
  }

  const assets = new Set([...localAssetUrls(home.text, '/'), ...localAssetUrls(app.text, '/app'), ...localAssetUrls(results['/account.html'].text, '/account.html'), ...localAssetUrls(results['/demonstracao'].text, '/demonstracao')]);
  for (const asset of [...assets].sort()) {
    const r = await http('GET', asset, { expected: [200] });
    if (r.response) {
      check(`Asset content type ${asset}`, !r.item.content_type.includes('text/html') || asset.endsWith('.html'), r.item.content_type, 'major');
      check(`Asset non-empty ${asset}`, r.text.length > 0, `bytes=${r.text.length}`, 'major');
    }
  }

  const openapi = results['/openapi.json'].json;
  check('OpenAPI parses as JSON', Boolean(openapi?.paths), results['/openapi.json'].text.slice(0, 300), 'critical');
  if (openapi?.paths) {
    for (const [route, methods] of Object.entries(openapi.paths)) {
      for (const [method, spec] of Object.entries(methods)) {
        if (!['get','post','put','patch','delete'].includes(method)) continue;
        report.api_routes.push({ method: method.toUpperCase(), route, operationId: spec.operationId || '', tags: spec.tags || [], security: spec.security || [] });
      }
    }
    const opIds = report.api_routes.map(r => r.operationId).filter(Boolean);
    check('OpenAPI operationId values are unique', new Set(opIds).size === opIds.length, `operations=${opIds.length}; unique=${new Set(opIds).size}`, 'major');
  }

  const caps = results['/api/pilot/capabilities'].json || {};
  report.capabilities = caps;
  check('Public signup advertised', caps.public_signup === true, JSON.stringify(caps), 'major');
  if (caps.password_reset_delivery === 'pilot-link') {
    check('Pilot reset link mode only on staging', BASE.includes('staging'), BASE, 'major');
  }

  await http('GET', '/api/pilot/profile', { expected: [401, 403] });
  await http('GET', '/api/pilot/profile', { headers: { Authorization: 'Bearer definitely-invalid' }, expected: [401, 403] });
  const neutral = await http('POST', '/api/auth/password-reset/request', {
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: `unknown-${Date.now()}@example.com` }), expected: [200, 202, 404]
  });
  report.password_reset_auth_probe = { status: neutral.item.status, body: neutral.json || neutral.text.slice(0, 500) };

  return { results, openapi };
}

function writeFixtureFiles() {
  const dir = path.join(OUT, 'fixtures');
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'qa-evidence.txt'), 'SRIS QA EVIDENCE\nObservation: Water consumption increased 15%.\nHypothesis: occupancy explains part of the increase.\nNo conclusion is asserted.\n', 'utf8');
  fs.writeFileSync(path.join(dir, 'qa-metrics.csv'), 'date,occupied_rooms,water_litres\n2026-08-01,8,3200\n2026-08-02,10,3900\n', 'utf8');
  const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl8d9sAAAAASUVORK5CYII=', 'base64');
  fs.writeFileSync(path.join(dir, 'qa-photo.png'), png);
  return [path.join(dir, 'qa-evidence.txt'), path.join(dir, 'qa-metrics.csv'), path.join(dir, 'qa-photo.png')];
}

async function axeScan(page, name) {
  try {
    const result = await new AxeBuilder({ page }).withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa']).analyze();
    report.dom_inventory[`${name}_axe`] = result.violations.map(v => ({ id: v.id, impact: v.impact, description: v.description, help: v.help, nodes: v.nodes.length }));
    for (const violation of result.violations) {
      const severity = ['critical','serious'].includes(violation.impact) ? 'major' : 'minor';
      finding(severity, 'accessibility', `${name}: ${violation.id}`, `${violation.help} (${violation.nodes.length} nodes)`, { impact: violation.impact, description: violation.description });
    }
  } catch (err) {
    finding('major', 'accessibility', `${name}: axe scan failed`, String(err?.stack || err));
  }
}

async function browserAudit() {
  const fixtures = writeFixtureFiles();
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: 'pt-PT' });
  const page = await context.newPage();

  page.on('console', msg => {
    const item = { type: msg.type(), text: msg.text(), url: msg.location()?.url || '' };
    report.console.push(item);
    if (['error','warning'].includes(item.type)) finding(item.type === 'error' ? 'major' : 'minor', 'browser-console', item.text.slice(0, 180), item.url, item);
  });
  page.on('pageerror', err => {
    report.page_errors.push(String(err?.stack || err));
    finding('critical', 'browser-runtime', 'Uncaught page error', String(err?.stack || err));
  });
  page.on('requestfailed', request => {
    const item = { method: request.method(), url: request.url(), failure: request.failure()?.errorText || '' };
    report.request_failures.push(item);
    finding('major', 'browser-network', 'Browser request failed', `${item.method} ${item.url}: ${item.failure}`, item);
  });
  page.on('response', async response => {
    const u = response.url();
    if (u.startsWith(BASE) && (u.includes('/api/') || response.status() >= 400)) {
      report.browser_requests.push({ method: response.request().method(), url: u, status: response.status(), contentType: response.headers()['content-type'] || '' });
    }
  });

  await page.goto(`${BASE}/`, { waitUntil: 'networkidle', timeout: 60000 });
  await page.screenshot({ path: path.join(OUT, '01-home-desktop.png'), fullPage: true });
  check('Home title', (await page.title()).includes('SRIS'), await page.title(), 'major');
  const homeImages = await page.locator('img').evaluateAll(imgs => imgs.map(img => ({ src: img.currentSrc || img.src, complete: img.complete, width: img.naturalWidth, height: img.naturalHeight, alt: img.alt })));
  report.dom_inventory.home_images = homeImages;
  check('All home images load', homeImages.every(i => i.complete && i.width > 0), JSON.stringify(homeImages), 'critical');
  check('Login form visible', await page.locator('#login-form').isVisible(), '', 'critical');
  check('Create-account tab visible', await page.locator('#register-tab').isVisible(), '', 'major');
  await axeScan(page, 'home-desktop');

  const suffix = `${Date.now()}-${crypto.randomBytes(3).toString('hex')}`;
  const account = {
    full_name: 'SRIS Automated QA',
    organization_name: `[QA AUTO] Staging ${suffix}`,
    email: `sris.qa.${suffix}@example.com`,
    password: `Staging-QA-${suffix}-Strong!`,
  };
  report.test_account = { ...account, password: '[redacted]' };

  await page.click('#register-tab');
  await page.fill('#reg-name', account.full_name);
  await page.fill('#reg-org', account.organization_name);
  await page.fill('#reg-email', account.email);
  await page.fill('#reg-password', account.password);
  const registerResponsePromise = page.waitForResponse(r => r.url().includes('/api/pilot/register'), { timeout: 30000 }).catch(() => null);
  await page.click('#register-submit');
  const registerResponse = await registerResponsePromise;
  if (registerResponse) {
    let body = null; try { body = await registerResponse.json(); } catch {}
    report.registration = { status: registerResponse.status(), body: body ? { ...body, access_token: body.access_token ? '[redacted]' : undefined, refresh_token: body.refresh_token ? '[redacted]' : undefined } : null };
    check('UI registration succeeds', registerResponse.status() === 201, JSON.stringify(report.registration), 'critical');
  } else {
    check('UI registration request observed', false, 'No /api/pilot/register response within 30s', 'critical');
  }

  await page.waitForURL(url => url.pathname === '/app', { timeout: 60000 }).catch(() => null);
  check('Registration navigates to /app', new URL(page.url()).pathname === '/app', page.url(), 'critical');
  await page.waitForFunction(() => {
    const text = document.querySelector('#mini-name')?.textContent || '';
    return text && !/sincronizar/i.test(text);
  }, null, { timeout: 60000 }).catch(() => null);
  await page.screenshot({ path: path.join(OUT, '02-app-after-registration.png'), fullPage: true });

  const session = await page.evaluate(() => ({
    access: localStorage.getItem('sris_access_token'),
    refresh: localStorage.getItem('sris_refresh_token'),
    org: localStorage.getItem('sris_org_id'),
    workspaceMode: localStorage.getItem('sris_workspace_selection'),
  }));
  check('Access token stored', Boolean(session.access), JSON.stringify({ ...session, access: session.access ? '[redacted]' : null, refresh: session.refresh ? '[redacted]' : null }), 'critical');
  check('Refresh token stored', Boolean(session.refresh), '', 'critical');
  check('Organization id stored', Boolean(session.org), '', 'critical');
  report.session = { access: session.access ? '[redacted]' : null, refresh: session.refresh ? '[redacted]' : null, org: session.org, workspaceMode: session.workspaceMode };

  const appBuild = await page.locator('meta[name="sris-pilot-build"]').getAttribute('content').catch(() => null);
  check('App build meta present', Boolean(appBuild), String(appBuild), 'critical');
  check('App build meta expected', appBuild === report.expected_build, `actual=${appBuild} expected=${report.expected_build}`, 'critical');

  const cycleLabels = await page.locator('[data-cycle-step]').allTextContents();
  report.dom_inventory.cycle_labels = cycleLabels.map(s => s.trim());
  check('Commercial cycle has exactly 5 moments', cycleLabels.length === 5, JSON.stringify(cycleLabels), 'critical');
  check('Commercial cycle labels canonical', JSON.stringify(cycleLabels.map(s => s.trim())) === JSON.stringify(['Contexto','Evidência','Decisão','Medição','Memória']), JSON.stringify(cycleLabels), 'critical');

  const navLabels = await page.locator('.nav button').allTextContents();
  report.dom_inventory.nav_labels = navLabels.map(s => s.replace(/\s+/g, ' ').trim());
  check('Economia e recursos appears in primary navigation', navLabels.some(v => /Economia e recursos/i.test(v)), JSON.stringify(navLabels), 'critical');
  const tabs = await page.locator('[data-mission-tab]').allTextContents();
  report.dom_inventory.mission_tabs = tabs.map(s => s.trim());
  check('Mission tabs include Economia e recursos', tabs.some(v => /Economia e recursos/i.test(v)), JSON.stringify(tabs), 'critical');

  await axeScan(page, 'app-empty-desktop');

  await page.click('#new-mission-btn');
  const title = `QA Água e ocupação ${suffix}`;
  await page.fill('#mission-title', title);
  await page.fill('#mission-objective', 'Decidir se a subida do consumo de água exige intervenção operacional e qual alternativa testar primeiro.');
  await page.fill('#mission-question', 'O consumo de água aumentou por ineficiência ou por alteração da atividade real da unidade?');
  await page.fill('#mission-context', 'Teste automatizado no staging. Existem dados de ocupação e consumo; não existe ainda causalidade demonstrada.');
  await page.fill('#mission-assumptions', 'A medição dos contadores é comparável entre períodos.');
  await page.fill('#mission-constraints', 'Não interromper a experiência dos hóspedes e limitar o teste a 30 dias.');
  await page.fill('#mission-success', 'Redução de 10% do consumo normalizado por quarto ocupado sem aumento de reclamações.');
  await page.fill('#mission-domain', 'hospitality_resource_efficiency');
  await page.fill('#mission-horizon', '30 dias');
  await page.selectOption('#mission-validation-profile', 'measurable_decision').catch(() => {});
  const missionPost = page.waitForResponse(r => r.request().method() === 'POST' && r.url().includes('/api/') && /mission/i.test(r.url()), { timeout: 30000 }).catch(() => null);
  await page.click('#save-mission-btn');
  const missionResponse = await missionPost;
  if (missionResponse) report.mission_create_response = { url: missionResponse.url(), status: missionResponse.status(), body: await missionResponse.text().catch(() => '') };
  await page.waitForFunction(t => document.querySelector('#detail-title')?.textContent?.includes(t), title, { timeout: 60000 }).catch(() => null);
  check('Mission created and opened', (await page.locator('#detail-title').textContent().catch(() => ''))?.includes(title), await page.locator('#detail-title').textContent().catch(() => ''), 'critical');
  await page.screenshot({ path: path.join(OUT, '03-mission-created.png'), fullPage: true });

  const visibleTextAfterCreate = await page.locator('body').innerText();
  const uuidMatches = visibleTextAfterCreate.match(/\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b/ig) || [];
  check('No raw UUID visible in normal mission view', uuidMatches.length === 0, JSON.stringify(uuidMatches.slice(0, 10)), 'major');
  check('Internal model name not visible', !/gpt-5\.6|gpt-5|openai/i.test(visibleTextAfterCreate), 'Internal model/provider string found in visible text', 'major');

  const input = page.locator('#mission-file');
  if (await input.count()) {
    await input.setInputFiles(fixtures);
    const uploadResponses = [];
    const onResp = r => { if (r.request().method() === 'POST' && /attachment|upload/i.test(r.url())) uploadResponses.push({ url: r.url(), status: r.status() }); };
    page.on('response', onResp);
    await page.click('#upload-file-btn');
    await page.waitForTimeout(5000);
    page.off('response', onResp);
    report.upload_responses = uploadResponses;
    const attachmentText = await page.locator('#attachment-list').innerText().catch(() => '');
    check('Text attachment appears', attachmentText.includes('qa-evidence.txt'), attachmentText, 'critical');
    check('CSV attachment appears', attachmentText.includes('qa-metrics.csv'), attachmentText, 'major');
    check('Image attachment appears', attachmentText.includes('qa-photo.png'), attachmentText, 'major');
    check('Upload calls avoid 5xx', uploadResponses.every(r => r.status < 500), JSON.stringify(uploadResponses), 'critical');
    await page.screenshot({ path: path.join(OUT, '04-documents-uploaded.png'), fullPage: true });
  } else {
    check('Mission upload input exists', false, '', 'critical');
  }

  const areaButtons = page.locator('[data-mission-area]');
  const areaCount = await areaButtons.count();
  report.dom_inventory.mission_areas = [];
  for (let i = 0; i < areaCount; i++) {
    const button = areaButtons.nth(i);
    const area = await button.getAttribute('data-mission-area');
    const label = (await button.innerText()).replace(/\s+/g, ' ').trim();
    report.dom_inventory.mission_areas.push({ area, label });
    await button.click().catch(err => finding('major', 'navigation', `Could not open area ${area}`, String(err)));
    await page.waitForTimeout(1200);
    const visible = await page.locator('main').innerText().catch(() => '');
    check(`Mission area ${area} opens without blank main`, visible.trim().length > 100, `chars=${visible.length}`, 'major');
    const rawUuids = visible.match(/\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b/ig) || [];
    if (rawUuids.length) finding('major', 'usability', `Raw UUID visible in ${area}`, rawUuids.slice(0, 5).join(', '));
    await page.screenshot({ path: path.join(OUT, `area-${String(i + 1).padStart(2, '0')}-${area || 'unknown'}.png`), fullPage: true });
  }

  const allButtons = await page.locator('button:visible').evaluateAll(buttons => buttons.map(b => ({ id: b.id, text: b.innerText.replace(/\s+/g,' ').trim(), disabled: b.disabled, section: b.dataset.section || '', area: b.dataset.missionArea || '', tab: b.dataset.missionTab || '' })));
  const allForms = await page.locator('form').evaluateAll(forms => forms.map(f => ({ id: f.id, visible: !!(f.offsetWidth || f.offsetHeight || f.getClientRects().length), controls: [...f.elements].map(e => ({ id: e.id, name: e.name, type: e.type, required: e.required })) })));
  report.dom_inventory.visible_buttons_after_mission = allButtons;
  report.dom_inventory.forms_after_mission = allForms;

  // Direct authenticated API probes using the same account/session.
  const authHeaders = { Authorization: `Bearer ${session.access}`, 'X-SRIS-Organization': session.org };
  const profile = await http('GET', '/api/pilot/profile', { headers: authHeaders, expected: [200] });
  report.profile = profile.json;
  check('Profile returns selected organization', profile.json?.organization?.id === session.org, JSON.stringify(profile.json?.workspace_selection || profile.json), 'critical');
  check('Profile exposes workspace inventory', Array.isArray(profile.json?.workspaces) && profile.json.workspaces.length >= 1, JSON.stringify(profile.json?.workspaces), 'major');
  if (profile.json?.ai?.model) finding('minor', 'information-exposure', 'Authenticated profile exposes internal AI model identifier', String(profile.json.ai.model));

  const invalidOrgProfile = await http('GET', '/api/pilot/profile', { headers: { ...authHeaders, 'X-SRIS-Organization': crypto.randomUUID() }, expected: [200, 403, 404] });
  if (invalidOrgProfile.item.status === 200) {
    check('Invalid workspace header does not select foreign workspace', invalidOrgProfile.json?.organization?.id === session.org, JSON.stringify(invalidOrgProfile.json?.workspace_selection), 'critical');
  }

  // Password-reset routing consistency, after all stateful UI tests.
  const resetAuth = await http('POST', '/api/auth/password-reset/request', { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: account.email }), expected: [200, 202, 404] });
  const resetPilot = await http('POST', '/api/pilot/password-reset/request', { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: account.email }), expected: [200, 202] });
  report.password_reset_routes = { auth: { status: resetAuth.item.status, body: resetAuth.json }, pilot: { status: resetPilot.item.status, body: resetPilot.json } };
  if (report.capabilities?.password_reset_delivery === 'pilot-link') {
    const uiRouteHasToken = Boolean(resetAuth.json?.reset_token);
    check('UI password-reset route returns pilot one-time token', uiRouteHasToken, JSON.stringify(report.password_reset_routes), 'critical');
  }

  // Mobile pass.
  const mobile = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, locale: 'pt-PT' });
  const mp = await mobile.newPage();
  mp.on('pageerror', err => finding('critical', 'mobile-runtime', 'Mobile page error', String(err?.stack || err)));
  mp.on('console', msg => { if (msg.type() === 'error') finding('major', 'mobile-console', msg.text()); });
  await mp.goto(`${BASE}/`, { waitUntil: 'networkidle', timeout: 60000 });
  await mp.screenshot({ path: path.join(OUT, '05-home-mobile.png'), fullPage: true });
  check('Mobile login input is visible', await mp.locator('#login-email').isVisible(), '', 'critical');
  await mp.focus('#login-email');
  await mp.waitForTimeout(300);
  const mobileMetrics = await mp.evaluate(() => ({ innerHeight: window.innerHeight, viewportHeight: window.visualViewport?.height || null, bodyScrollHeight: document.body.scrollHeight, activeId: document.activeElement?.id || '' }));
  report.dom_inventory.mobile_metrics = mobileMetrics;
  check('Mobile focused login field remains active', mobileMetrics.activeId === 'login-email', JSON.stringify(mobileMetrics), 'major');
  await axeScan(mp, 'home-mobile');
  await mobile.close();

  await context.close();
  await browser.close();
}

function finalise() {
  report.completed_at = new Date().toISOString();
  const order = { critical: 0, major: 1, minor: 2, info: 3 };
  report.findings.sort((a, b) => (order[a.severity] ?? 9) - (order[b.severity] ?? 9));
  report.summary = {
    checks: report.checks.length,
    passed: report.checks.filter(c => c.ok).length,
    failed: report.checks.filter(c => !c.ok).length,
    findings: report.findings.length,
    critical: report.findings.filter(f => f.severity === 'critical').length,
    major: report.findings.filter(f => f.severity === 'major').length,
    minor: report.findings.filter(f => f.severity === 'minor').length,
  };
  fs.writeFileSync(path.join(OUT, 'live-staging-qa-report.json'), JSON.stringify(report, null, 2));
  const md = [
    '# SRIS Live Staging Deep QA',
    '',
    `- Base: ${BASE}`,
    `- Expected build: ${report.expected_build}`,
    `- Checks: ${report.summary.passed}/${report.summary.checks} passed`,
    `- Findings: ${report.summary.critical} critical, ${report.summary.major} major, ${report.summary.minor} minor`,
    '',
    '## Findings',
    ...report.findings.map((f, i) => `${i + 1}. **${f.severity.toUpperCase()} — ${f.area}: ${f.title}**${f.detail ? `\n   ${f.detail.replace(/\n/g, ' ')}` : ''}`),
    '',
    '## Failed checks',
    ...report.checks.filter(c => !c.ok).map((c, i) => `${i + 1}. **${c.severity.toUpperCase()} — ${c.name}** — ${c.detail}`),
  ].join('\n');
  fs.writeFileSync(path.join(OUT, 'live-staging-qa-report.md'), md);
  console.log('\n===== SRIS_QA_SUMMARY_START =====');
  console.log(JSON.stringify(report.summary, null, 2));
  console.log(md);
  console.log('===== SRIS_QA_SUMMARY_END =====\n');
}

let fatal = null;
try {
  await publicAndApiRecon();
  await browserAudit();
} catch (err) {
  fatal = String(err?.stack || err);
  finding('critical', 'runner', 'QA execution aborted', fatal);
} finally {
  finalise();
}

// Do not suppress the evidence: fail the workflow only for runner aborts.
if (fatal) process.exitCode = 2;
