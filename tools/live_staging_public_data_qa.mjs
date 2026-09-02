import fs from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright';

const BASE=(process.env.SRIS_STAGING_URL||'https://sris-pilot-v1-staging.up.railway.app').replace(/\/$/,'');
const OUT=process.env.QA_OUTPUT_DIR||'qa-public-data-artifacts';
fs.mkdirSync(OUT,{recursive:true});
const report={started_at:new Date().toISOString(),base:BASE,checks:[],findings:[],raw:{}};
const severityOrder={critical:0,major:1,minor:2,info:3};
function finding(severity,area,title,detail='',evidence={}){report.findings.push({severity,area,title,detail,evidence});}
function check(name,ok,detail='',severity='major',evidence={}){report.checks.push({name,ok:!!ok,detail,severity,evidence});if(!ok)finding(severity,'check',name,detail,evidence);return !!ok;}
function text(v){return String(v??'').replace(/\s+/g,' ').trim();}
function approx(a,b,t=1){return Number.isFinite(a)&&Number.isFinite(b)&&Math.abs(a-b)<=t;}
function scanObject(value,pathName='$',hits=[]){if(typeof value==='string'){if(/\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b/i.test(value))hits.push({type:'uuid',path:pathName,value});if(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i.test(value))hits.push({type:'email',path:pathName,value});if(/\+351\s?\d{9}/.test(value))hits.push({type:'phone',path:pathName,value});}else if(Array.isArray(value)){value.forEach((v,i)=>scanObject(v,`${pathName}[${i}]`,hits));}else if(value&&typeof value==='object'){Object.entries(value).forEach(([k,v])=>scanObject(v,`${pathName}.${k}`,hits));}return hits;}

try{
  const [capsR,authCapsR,buildR,releaseR,demoR,openapiR]=await Promise.all([
    fetch(`${BASE}/api/pilot/capabilities`),
    fetch(`${BASE}/api/auth/capabilities`),
    fetch(`${BASE}/api/pilot/build`),
    fetch(`${BASE}/api/pilot/release-state`),
    fetch(`${BASE}/api/mission-intelligence/demo/fictional/missions`),
    fetch(`${BASE}/openapi.json`),
  ]);
  check('Capabilities endpoint succeeds',capsR.status===200,`status=${capsR.status}`,'critical');
  check('Auth capabilities endpoint succeeds',authCapsR.status===200,`status=${authCapsR.status}`,'critical');
  check('Build endpoint succeeds',buildR.status===200,`status=${buildR.status}`,'critical');
  check('Release-state endpoint succeeds',releaseR.status===200,`status=${releaseR.status}`,'critical');
  check('Fictional demo API succeeds',demoR.status===200,`status=${demoR.status}`,'critical');
  check('OpenAPI endpoint succeeds',openapiR.status===200,`status=${openapiR.status}`,'major');
  const caps=await capsR.json(),authCaps=await authCapsR.json(),build=await buildR.json(),release=await releaseR.json(),catalog=await demoR.json(),openapi=await openapiR.json();
  report.raw={caps,authCaps,build,release,catalog,openapi_info:openapi.info};

  check('Public signup flags agree',caps.public_signup===authCaps.public_registration_enabled,JSON.stringify({pilot:caps.public_signup,auth:authCaps.public_registration_enabled}),'critical');
  check('Invitation flags agree',caps.invitations_enabled===authCaps.invitations_enabled,JSON.stringify({pilot:caps.invitations_enabled,auth:authCaps.invitations_enabled}),'major');
  check('Password-reset flags agree',caps.transactional_email_ready===authCaps.password_reset_enabled,JSON.stringify({pilot:caps.transactional_email_ready,auth:authCaps.password_reset_enabled}),'major');
  check('Build and release commit agree',build.commit_sha===release.commit_sha,JSON.stringify({build,release}),'critical');
  check('Build and release branch agree',build.branch===release.branch,JSON.stringify({build,release}),'critical');
  check('Database has exactly one revision and is at head',release.database_at_head===true&&release.database_revisions?.length===1&&release.migration_heads?.length===1,JSON.stringify(release),'critical');

  const missions=Object.values(catalog.missions||{});
  check('Demo catalog has exactly one bounded case',missions.length===1,`missions=${missions.length}`,'major');
  const mission=missions[0]||{};
  check('Demo organization is explicitly fictitious',/fict[ií]ci/i.test(text(mission.organization))||/fict[ií]ci/i.test(JSON.stringify(catalog)),text(mission.organization),'critical');
  const sensitive=scanObject(catalog);
  check('Demo catalog contains no UUID/email/phone leakage',sensitive.length===0,JSON.stringify(sensitive.slice(0,20)),'critical');

  const chain=mission.situation?.chain||[];
  const canonical=['Observação','Evidência','Hipótese','Alternativa','Decisão','Ação','Resultado','Aprendizagem'];
  check('Demo chain has eight records',chain.length===8,JSON.stringify(chain),'critical');
  check('Demo chain follows canonical order',canonical.every((label,i)=>text(chain[i]?.label).toLocaleLowerCase('pt-PT')===label.toLocaleLowerCase('pt-PT')),JSON.stringify(chain.map(x=>x.label)),'critical');
  check('Demo chain numbering is contiguous 01–08',chain.every((item,i)=>String(item.number).padStart(2,'0')===String(i+1).padStart(2,'0')),JSON.stringify(chain.map(x=>x.number)),'major');
  check('Learning remains pending rather than fabricated',chain.length===0||/pendent|não confirm|por rever|aguarda/i.test(text(chain[7]?.value)+' '+text(chain[7]?.note)),JSON.stringify(chain[7]),'critical');

  const matrix=mission.analysis?.decision_matrix||{};
  const criteria=matrix.criteria||[],rows=matrix.rows||[];
  check('Decision matrix has six required criteria',criteria.length===6,JSON.stringify(criteria),'critical');
  const expectedCriteria=['eficácia','custo','risco','reversibilidade','experiência','robustez'];
  check('Decision matrix criteria cover the agreed six dimensions',expectedCriteria.every(term=>criteria.some(c=>text(c.label).toLocaleLowerCase('pt-PT').includes(term))),JSON.stringify(criteria.map(c=>c.label)),'critical');
  check('Decision matrix has at least three alternatives',rows.length>=3,`rows=${rows.length}`,'major');
  for(const row of rows){
    const scores=row.scores||[];
    check(`Matrix ${row.alternative_id}: score count matches criteria`,scores.length===criteria.length,JSON.stringify(row),'major');
    check(`Matrix ${row.alternative_id}: scores within 1–5`,scores.every(v=>Number.isFinite(Number(v))&&Number(v)>=1&&Number(v)<=5),JSON.stringify(scores),'major');
    check(`Matrix ${row.alternative_id}: total equals score sum`,Number(row.total)===scores.reduce((s,v)=>s+Number(v),0),JSON.stringify(row),'critical');
  }

  const evidence=mission.evidence||[];
  check('Demo has multiple evidence records',evidence.length>=3,`count=${evidence.length}`,'major');
  for(const [i,item] of evidence.entries()){
    check(`Evidence ${i+1}: method explicit`,text(item.method).length>=10,JSON.stringify(item),'major');
    check(`Evidence ${i+1}: limitation explicit`,text(item.limitation).length>=10,JSON.stringify(item),'major');
    check(`Evidence ${i+1}: status explicit`,text(item.status).length>0,JSON.stringify(item),'major');
  }

  const graph=mission.evidence_graph||{},nodes=graph.nodes||[],edges=graph.edges||[];
  const ids=new Set(nodes.map(n=>n.id));
  check('Evidence graph has nodes and edges',nodes.length>=4&&edges.length>=3,JSON.stringify({nodes:nodes.length,edges:edges.length}),'major');
  check('Evidence graph node IDs are unique',ids.size===nodes.length,JSON.stringify(nodes.map(n=>n.id)),'critical');
  check('Every graph edge resolves to existing nodes',edges.every(e=>ids.has(e.from)||ids.has(e.source_id))&&edges.every(e=>ids.has(e.to)||ids.has(e.target_id)),JSON.stringify(edges),'critical');

  const bc=mission.business_case||{},baseline=bc.baseline||{},pilot=bc.pilot||{},scenarios=bc.scenarios||[];
  check('Business Case clearly marks data as fictitious/projected',/fict[ií]ci|projetad|simula/i.test(text(bc.notice)+' '+text(bc.scenario_scope_note)),JSON.stringify({notice:bc.notice,note:bc.scenario_scope_note}),'critical');
  check('Business Case has at least three scenarios',scenarios.length>=3,`scenarios=${scenarios.length}`,'critical');
  check('Selected scenario exists',scenarios.some(s=>s.id===bc.selected_scenario_id),JSON.stringify({selected:bc.selected_scenario_id,ids:scenarios.map(s=>s.id)}),'critical');
  for(const s of scenarios){
    const direct=Number(s.water_saving_m3_per_year)*Number(s.water_tariff_eur_per_m3)+Number(s.energy_saving_kwh_per_year)*Number(s.energy_tariff_eur_per_kwh);
    check(`Scenario ${s.id}: direct savings arithmetic`,approx(Number(s.direct_savings_eur_per_year),direct,2),JSON.stringify({stored:s.direct_savings_eur_per_year,calculated:direct,s}),'critical');
    const net=Number(s.direct_savings_eur_per_year)+Number(s.protected_revenue_eur_per_year)-Number(s.recurring_cost_eur_per_year);
    check(`Scenario ${s.id}: net benefit arithmetic`,approx(Number(s.net_benefit_eur_per_year),net,2),JSON.stringify({stored:s.net_benefit_eur_per_year,calculated:net,s}),'critical');
    const payback=Number(s.net_benefit_eur_per_year)>0?Number(pilot.investment_eur)/Number(s.net_benefit_eur_per_year)*12:null;
    if(payback!==null)check(`Scenario ${s.id}: payback arithmetic`,approx(Number(s.payback_months),payback,1),JSON.stringify({stored:s.payback_months,calculated:payback,s}),'major');
    const net3=Number(s.net_benefit_eur_per_year)*3-Number(pilot.investment_eur);
    check(`Scenario ${s.id}: 3-year net return arithmetic`,approx(Number(s.net_return_3y_eur),net3,2),JSON.stringify({stored:s.net_return_3y_eur,calculated:net3,s}),'critical');
    const roi=Number(pilot.investment_eur)>0?net3/Number(pilot.investment_eur)*100:null;
    if(roi!==null)check(`Scenario ${s.id}: 3-year ROI arithmetic`,approx(Number(s.roi_3y_percent),roi,1),JSON.stringify({stored:s.roi_3y_percent,calculated:roi,s}),'major');
  }
  check('Baseline annual spend reconciles water and energy',approx(Number(baseline.annual_resource_spend_eur),Number(baseline.water_consumption_m3_per_year)*Number(baseline.water_tariff_eur_per_m3)+Number(baseline.energy_consumption_kwh_per_year)*Number(baseline.energy_tariff_eur_per_kwh),2),JSON.stringify(baseline),'critical');

  const browser=await chromium.launch({headless:true});
  try{
    const context=await browser.newContext({viewport:{width:1440,height:1000},locale:'pt-PT'});const page=await context.newPage();
    const consoleErrors=[];page.on('console',m=>{if(m.type()==='error')consoleErrors.push({text:m.text(),url:m.location()?.url||''});});
    await page.goto(`${BASE}/demonstracao`,{waitUntil:'networkidle',timeout:45000});
    await page.waitForFunction(()=>!document.querySelector('#mission-title')?.textContent?.includes('carregar'),null,{timeout:20000});
    const buttons=await page.locator('#scenario-controls button').evaluateAll(xs=>xs.map(x=>({id:x.dataset.scenarioId,label:text(x.textContent),active:x.classList.contains('active'),pressed:x.getAttribute('aria-pressed')})));
    report.raw.scenario_buttons=buttons;
    check('Exactly one scenario button starts active',buttons.filter(x=>x.active).length===1,JSON.stringify(buttons),'major');
    const target=buttons.find(x=>!x.active);
    check('A non-active scenario is available for interaction',!!target,JSON.stringify(buttons),'major');
    if(target){
      const before=await page.locator('#business-case-timeline').innerText();
      await page.locator(`#scenario-controls button[data-scenario-id="${target.id}"]`).click();
      await page.waitForFunction(id=>document.querySelector('.economy-phase.projection .phase-heading span')?.textContent?.toLowerCase().includes(id.toLowerCase())||document.querySelector(`#scenario-controls button[data-scenario-id="${id}"]`)?.classList.contains('active'),target.id,{timeout:5000}).catch(()=>{});
      const after=await page.locator('#business-case-timeline').innerText();
      const afterButtons=await page.locator('#scenario-controls button').evaluateAll(xs=>xs.map(x=>({id:x.dataset.scenarioId,active:x.classList.contains('active'),pressed:x.getAttribute('aria-pressed')})));
      report.raw.scenario_interaction={target,before,after,afterButtons};
      check('Scenario selection moves active state',afterButtons.some(x=>x.id===target.id&&x.active&&x.pressed==='true'),JSON.stringify(afterButtons),'critical');
      check('Scenario selection changes projected output',text(after)!==text(before),JSON.stringify({target:target.id,before:text(before).slice(-900),after:text(after).slice(-900)}),'critical');
    }
    check('Demo produces no console errors',consoleErrors.length===0,JSON.stringify(consoleErrors),'major');

    await page.goto(`${BASE}/`,{waitUntil:'networkidle',timeout:45000});
    const ui=await page.evaluate(()=>({subtitle:document.querySelector('#auth-subtitle')?.textContent||'',trial:document.querySelector('#trial-copy')?.textContent||'',registerDisabled:document.querySelector('#register-tab')?.disabled,registerTitle:document.querySelector('#register-tab')?.title||''}));
    report.raw.entry_ui=ui;
    check('Disabled public signup is not contradicted by entry copy',!(ui.registerDisabled&&/crie uma conta|criar conta/i.test(ui.subtitle)),JSON.stringify(ui),'major');
    await context.close();
  } finally {await browser.close();}

  // Public diagnostic exposure is factual, not a failed functional test.
  const openapiPaths=Object.keys(openapi.paths||{});
  if(openapiPaths.includes('/api/pilot/build')||openapiPaths.includes('/api/pilot/release-state'))finding('major','information-exposure','Exact deployment and database fingerprint is public',JSON.stringify({build,release}));
  if(openapiPaths.length>100)finding('minor','attack-surface','Full API schema is publicly enumerable',`OpenAPI paths=${openapiPaths.length}`);
} catch(error){finding('critical','runner','Public data audit aborted',String(error?.stack||error));report.fatal=String(error?.stack||error);process.exitCode=2;} finally {
  report.completed_at=new Date().toISOString();report.findings.sort((a,b)=>(severityOrder[a.severity]??9)-(severityOrder[b.severity]??9));report.summary={checks:report.checks.length,passed:report.checks.filter(c=>c.ok).length,failed:report.checks.filter(c=>!c.ok).length,critical:report.findings.filter(f=>f.severity==='critical').length,major:report.findings.filter(f=>f.severity==='major').length,minor:report.findings.filter(f=>f.severity==='minor').length};fs.writeFileSync(path.join(OUT,'public-data-qa.json'),JSON.stringify(report,null,2));const md=['# SRIS public data and calculation QA','',`Checks: ${report.summary.passed}/${report.summary.checks} passed`,`Findings: ${report.summary.critical} critical · ${report.summary.major} major · ${report.summary.minor} minor`,'','## Findings',...report.findings.map((f,i)=>`${i+1}. **${f.severity.toUpperCase()} · ${f.area} · ${f.title}** — ${text(f.detail)}`),'','## Failed checks',...report.checks.filter(c=>!c.ok).map((c,i)=>`${i+1}. **${c.severity.toUpperCase()} · ${c.name}** — ${text(c.detail)}`)].join('\n');fs.writeFileSync(path.join(OUT,'public-data-qa.md'),md);console.log('===== SRIS_PUBLIC_DATA_QA_START =====');console.log(JSON.stringify(report.summary));console.log(md);console.log('===== SRIS_PUBLIC_DATA_QA_END =====');
}
