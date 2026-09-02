import fs from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';

const BASE=(process.env.SRIS_STAGING_URL||'https://sris-pilot-v1-staging.up.railway.app').replace(/\/$/,'');
const EXPECTED=process.env.SRIS_EXPECTED_BUILD||'20260902-workspace-continuity-v36';
const OUT=process.env.QA_OUTPUT_DIR||'qa-public-artifacts';
fs.mkdirSync(OUT,{recursive:true});
const report={started_at:new Date().toISOString(),base:BASE,expected_build:EXPECTED,checks:[],findings:[],pages:{},requests:[],console:[]};
const rank={critical:0,major:1,minor:2,info:3};
function addFinding(severity,area,title,detail='',evidence={}){report.findings.push({severity,area,title,detail,evidence});}
function check(name,ok,detail='',severity='major',evidence={}){report.checks.push({name,ok:!!ok,detail,severity,evidence});if(!ok)addFinding(severity,'check',name,detail,evidence);return !!ok;}
function cleanText(v){return String(v||'').replace(/\s+/g,' ').trim();}
async function axe(page,name){try{const r=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa']).analyze();report.pages[name].axe=r.violations.map(v=>({id:v.id,impact:v.impact,help:v.help,nodes:v.nodes.length,targets:v.nodes.slice(0,5).map(n=>n.target)}));for(const v of r.violations){addFinding(['critical','serious'].includes(v.impact)?'major':'minor','accessibility',`${name}: ${v.id}`,`${v.help}; nodes=${v.nodes.length}`,{impact:v.impact,targets:v.nodes.slice(0,5).map(n=>n.target)})}}catch(e){addFinding('major','accessibility',`${name}: axe failed`,String(e?.stack||e));}}
async function overflow(page,name){const data=await page.evaluate(()=>({viewport:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,offenders:[...document.querySelectorAll('body *')].filter(el=>{const r=el.getBoundingClientRect();return r.right>document.documentElement.clientWidth+2||r.left<-2}).slice(0,30).map(el=>({tag:el.tagName,id:el.id,cls:el.className?.toString?.()||'',left:Math.round(el.getBoundingClientRect().left),right:Math.round(el.getBoundingClientRect().right)}))}));report.pages[name].overflow=data;check(`${name}: no page-level horizontal overflow`,data.scroll<=data.viewport+2,JSON.stringify(data),'major');}
function wire(page,name){report.pages[name]={console:[],errors:[],failed_requests:[],axe:[]};page.on('console',m=>{const x={type:m.type(),text:m.text(),url:m.location()?.url||''};report.pages[name].console.push(x);report.console.push({page:name,...x});if(m.type()==='error')addFinding('major','browser-console',`${name}: console error`,x.text,x)});page.on('pageerror',e=>{const x=String(e?.stack||e);report.pages[name].errors.push(x);addFinding('critical','browser-runtime',`${name}: uncaught error`,x)});page.on('requestfailed',r=>{const x={method:r.method(),url:r.url(),error:r.failure()?.errorText||''};report.pages[name].failed_requests.push(x);addFinding('major','browser-network',`${name}: request failed`,`${x.method} ${x.url} ${x.error}`,x)});page.on('response',r=>{if(r.url().startsWith(BASE)){report.requests.push({page:name,method:r.request().method(),url:r.url(),status:r.status(),type:r.headers()['content-type']||''});if(r.status()>=500)addFinding('critical','http',`${name}: server error ${r.status()}`,r.url())}});}
async function screenshot(page,name){await page.screenshot({path:path.join(OUT,`${name}.png`),fullPage:true});}
async function headers(pathname){const r=await fetch(`${BASE}${pathname}`,{redirect:'manual'});const h=Object.fromEntries(r.headers.entries());report.pages[`http:${pathname}`]={status:r.status,headers:h};check(`${pathname}: HTTP 200`,r.status===200,`status=${r.status}`,'critical');check(`${pathname}: build header`,h['x-sris-pilot-build']===EXPECTED,`actual=${h['x-sris-pilot-build']||''}`,'critical');check(`${pathname}: CSP`,!!h['content-security-policy'],JSON.stringify(h),'major');check(`${pathname}: HSTS`,!!h['strict-transport-security'],JSON.stringify(h),'major');check(`${pathname}: nosniff`,h['x-content-type-options']==='nosniff',JSON.stringify(h),'major');check(`${pathname}: frame denied`,h['x-frame-options']==='DENY',JSON.stringify(h),'major');return {r,h,text:await r.text()};}

const browser=await chromium.launch({headless:true});
try{
  const homeHttp=await headers('/');
  const appHttp=await headers('/app');
  const accountHttp=await headers('/account.html');
  const demoHttp=await headers('/demonstracao');
  for(const [name,item] of Object.entries({home:homeHttp,app:appHttp,account:accountHttp,demo:demoHttp}))check(`${name}: no unreplaced build placeholder`,!item.text.includes('__PILOT_BUILD__'),'__PILOT_BUILD__ present','critical');
  check('Account page uses current build cache token',accountHttp.text.includes(`v=${EXPECTED}`),accountHttp.text.match(/pilot\.css\?v=[^"']+/)?.[0]||'no stylesheet token','major');
  check('Account page has current build meta',accountHttp.text.includes(`name="sris-pilot-build" content="${EXPECTED}"`),'build meta missing','minor');

  const caps=await fetch(`${BASE}/api/pilot/capabilities`).then(r=>r.json());report.capabilities=caps;
  check('Runtime build matches expected',caps.build===EXPECTED,JSON.stringify(caps),'critical');
  check('Transactional email ready',caps.transactional_email_ready===true,JSON.stringify(caps),'critical');
  check('Password reset delivery is email',caps.password_reset_delivery==='email',JSON.stringify(caps),'critical');
  check('Invitations enabled',caps.invitations_enabled===true,JSON.stringify(caps),'critical');
  check('Public signup disabled deliberately',caps.public_signup===false,JSON.stringify(caps),'info');
  check('Workspace selection advertised',caps.explicit_workspace_selection===true,JSON.stringify(caps),'critical');

  const release=await fetch(`${BASE}/api/pilot/release-state`).then(r=>r.json());report.release_state=release;
  check('Database is at migration head',release.database_at_head===true,JSON.stringify(release),'critical');
  check('Staging is deployed from intended branch',release.branch==='pilot-v1-september-2026',JSON.stringify(release),'critical');
  check('Staging is deployed from intended commit',release.commit_sha==='c096fd47b3f6d733b6fa3c89bce4b3696baf0380',JSON.stringify(release),'critical');

  // Desktop entry page.
  const c=await browser.newContext({viewport:{width:1440,height:1000},locale:'pt-PT'});const p=await c.newPage();wire(p,'home-desktop');
  await p.goto(`${BASE}/`,{waitUntil:'networkidle',timeout:45000});await screenshot(p,'01-home-desktop');
  const imgs=await p.locator('img').evaluateAll(xs=>xs.map(x=>({src:x.currentSrc,complete:x.complete,w:x.naturalWidth,h:x.naturalHeight,alt:x.alt})));report.pages['home-desktop'].images=imgs;
  check('Home images loaded',imgs.every(x=>x.complete&&x.w>0),JSON.stringify(imgs),'critical');
  check('Hero photograph visible',await p.locator('.auth-photo').isVisible(),'', 'critical');
  check('Login visible',await p.locator('#login-form').isVisible(),'', 'critical');
  await p.waitForTimeout(500);
  const register=await p.locator('#register-tab').evaluate(el=>({disabled:el.disabled,title:el.title,visible:!!(el.offsetWidth||el.offsetHeight||el.getClientRects().length)}));report.pages['home-desktop'].register=register;
  check('Create-account remains visible',register.visible,JSON.stringify(register),'major');
  check('Create-account correctly disabled by runtime configuration',register.disabled===true,JSON.stringify(register),'major');
  check('Disabled signup explains why',cleanText(register.title).length>5,JSON.stringify(register),'minor');

  await p.fill('#login-email','definitely-not-an-account@example.com');await p.fill('#login-password','Definitely-Wrong-Password-123!');
  const loginResp=p.waitForResponse(r=>r.url().includes('/api/auth/login'),{timeout:15000});await p.click('#login-submit');const lr=await loginResp;
  check('Invalid login rejected',lr.status()===401,`status=${lr.status()}`,'critical');
  await p.waitForTimeout(250);const loginMessage=cleanText(await p.locator('#message').innerText());check('Invalid-login message is human-readable',/incorret/i.test(loginMessage),loginMessage,'major');
  await axe(p,'home-desktop');await overflow(p,'home-desktop');

  // Unknown-address reset request must remain neutral and should not create an exposed token.
  await p.click('#forgot-link');await p.fill('#reset-email',`unknown-${Date.now()}@example.com`);const rrPromise=p.waitForResponse(r=>r.url().includes('/api/auth/password-reset/request'),{timeout:15000});await p.click('#reset-request-submit');const rr=await rrPromise;let rrBody={};try{rrBody=await rr.json()}catch{}report.pages['home-desktop'].unknown_reset={status:rr.status(),body:rrBody};
  check('Unknown-address reset request accepted neutrally',rr.status()===202,JSON.stringify(rrBody),'major');
  check('Reset response does not expose token',!rrBody.reset_token,JSON.stringify(rrBody),'critical');
  check('Reset response does not disclose account existence',/se .*conta|se existir/i.test(cleanText(rrBody.message)),JSON.stringify(rrBody),'major');

  // Account page desktop.
  const ap=await c.newPage();wire(ap,'account-desktop');await ap.goto(`${BASE}/account.html`,{waitUntil:'networkidle',timeout:45000});await screenshot(ap,'02-account-desktop');
  check('Account recovery view visible',await ap.locator('#request-view').isVisible(),'', 'critical');
  check('Account reset submit enabled when email is configured',!(await ap.locator('#request-submit').isDisabled()),'', 'critical');
  await axe(ap,'account-desktop');await overflow(ap,'account-desktop');

  // Public demonstration desktop and interactions.
  const dp=await c.newPage();wire(dp,'demo-desktop');await dp.goto(`${BASE}/demonstracao`,{waitUntil:'networkidle',timeout:45000});
  await dp.waitForFunction(()=>{const t=document.querySelector('#mission-title')?.textContent||'';return t&&!/carregar/i.test(t)},null,{timeout:30000});await screenshot(dp,'03-demo-desktop');
  const demoText=cleanText(await dp.locator('body').innerText());report.pages['demo-desktop'].body_excerpt=demoText.slice(0,5000);
  check('Demo explicitly labels all data fictitious',/dados.*fict[ií]ci/i.test(demoText),demoText.slice(0,500),'critical');
  check('Demo mission loads',!/A carregar demonstração/i.test(demoText),demoText.slice(0,500),'critical');
  check('Demo includes Business Case Vivo',/Business Case Vivo/i.test(demoText),demoText.slice(0,2000),'critical');
  check('Demo includes evidence graph',/Grafo de evidência/i.test(demoText),demoText.slice(0,2000),'major');
  check('Demo includes alternatives matrix',/Matriz de alternativas/i.test(demoText),demoText.slice(0,2000),'major');
  const rawUuids=demoText.match(/\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b/ig)||[];check('Demo exposes no raw UUIDs',rawUuids.length===0,JSON.stringify(rawUuids.slice(0,10)),'major');
  const scenarioButtons=dp.locator('#scenario-controls button');const scenarioCount=await scenarioButtons.count();check('Economic scenario controls exist',scenarioCount>=2,`count=${scenarioCount}`,'critical');if(scenarioCount>=2){const before=cleanText(await dp.locator('#business-case-timeline').innerText());await scenarioButtons.nth(1).click();await dp.waitForTimeout(350);const after=cleanText(await dp.locator('#business-case-timeline').innerText());check('Economic scenario control changes output',after!==before,`before=${before.slice(0,300)} after=${after.slice(0,300)}`,'major');}
  const graphNodes=dp.locator('#evidence-graph button,[data-graph-node]');const graphCount=await graphNodes.count();check('Demo evidence graph has interactive nodes',graphCount>0,`count=${graphCount}`,'major');if(graphCount){await graphNodes.first().click();await dp.waitForTimeout(250);check('Graph interaction exposes detail',cleanText(await dp.locator('#graph-detail').innerText()).length>20,cleanText(await dp.locator('#graph-detail').innerText()),'major');}
  const externalLinks=await dp.locator('a[href^="http"]').evaluateAll(xs=>xs.map(x=>x.href));report.pages['demo-desktop'].external_links=externalLinks;
  await axe(dp,'demo-desktop');await overflow(dp,'demo-desktop');

  // Unauthenticated application should not leak protected content and should return to login.
  const up=await c.newPage();wire(up,'app-unauthenticated');await up.goto(`${BASE}/app`,{waitUntil:'domcontentloaded',timeout:45000});await up.waitForTimeout(2500);report.pages['app-unauthenticated'].final_url=up.url();await screenshot(up,'04-app-unauthenticated');check('Unauthenticated app returns to entry page',new URL(up.url()).pathname==='/',up.url(),'critical');
  await c.close();

  // Mobile entry.
  const mc=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true,locale:'pt-PT'});const mp=await mc.newPage();wire(mp,'home-mobile');await mp.goto(`${BASE}/`,{waitUntil:'networkidle',timeout:45000});await screenshot(mp,'05-home-mobile');check('Mobile login email visible',await mp.locator('#login-email').isVisible(),'', 'critical');await mp.focus('#login-email');await mp.waitForTimeout(300);const focus=await mp.evaluate(()=>({active:document.activeElement?.id,innerHeight:window.innerHeight,visualHeight:window.visualViewport?.height||null,scrollWidth:document.documentElement.scrollWidth,clientWidth:document.documentElement.clientWidth}));report.pages['home-mobile'].focus=focus;check('Mobile input remains focused',focus.active==='login-email',JSON.stringify(focus),'major');await axe(mp,'home-mobile');await overflow(mp,'home-mobile');

  // Mobile demo.
  const md=await mc.newPage();wire(md,'demo-mobile');await md.goto(`${BASE}/demonstracao`,{waitUntil:'networkidle',timeout:45000});await md.waitForFunction(()=>!document.querySelector('#mission-title')?.textContent?.includes('carregar'),null,{timeout:30000});await screenshot(md,'06-demo-mobile');await overflow(md,'demo-mobile');await axe(md,'demo-mobile');
  const table=md.locator('.table-scroll');if(await table.count()){const m=await table.evaluate(el=>({clientWidth:el.clientWidth,scrollWidth:el.scrollWidth,tabindex:el.getAttribute('tabindex')}));report.pages['demo-mobile'].table=m;check('Mobile comparison matrix is scrollable and focusable',m.scrollWidth>=m.clientWidth&&m.tabindex==='0',JSON.stringify(m),'major');}
  await mc.close();
} catch(e){addFinding('critical','runner','Public audit aborted',String(e?.stack||e));report.fatal=String(e?.stack||e);process.exitCode=2;} finally {
  await browser.close();report.completed_at=new Date().toISOString();report.findings.sort((a,b)=>(rank[a.severity]??9)-(rank[b.severity]??9));report.summary={checks:report.checks.length,passed:report.checks.filter(x=>x.ok).length,failed:report.checks.filter(x=>!x.ok).length,critical:report.findings.filter(x=>x.severity==='critical').length,major:report.findings.filter(x=>x.severity==='major').length,minor:report.findings.filter(x=>x.severity==='minor').length,info:report.findings.filter(x=>x.severity==='info').length};fs.writeFileSync(path.join(OUT,'public-qa-report.json'),JSON.stringify(report,null,2));const md=['# SRIS live staging public QA','',`Base: ${BASE}`,`Expected build: ${EXPECTED}`,`Checks: ${report.summary.passed}/${report.summary.checks} passed`,`Findings: ${report.summary.critical} critical · ${report.summary.major} major · ${report.summary.minor} minor`,'','## Findings',...report.findings.map((f,i)=>`${i+1}. **${f.severity.toUpperCase()} · ${f.area} · ${f.title}**${f.detail?`\n   ${cleanText(f.detail)}`:''}`),'','## Failed checks',...report.checks.filter(x=>!x.ok).map((x,i)=>`${i+1}. **${x.severity.toUpperCase()} · ${x.name}** — ${cleanText(x.detail)}`)].join('\n');fs.writeFileSync(path.join(OUT,'public-qa-report.md'),md);console.log('===== SRIS_PUBLIC_QA_START =====');console.log(JSON.stringify(report.summary));console.log(md);console.log('===== SRIS_PUBLIC_QA_END =====');
}
