import fs from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright';

const BASE=(process.env.SRIS_STAGING_URL||'https://sris-pilot-v1-staging.up.railway.app').replace(/\/$/,'');
const OUT=process.env.QA_OUTPUT_DIR||'qa-public-data-v2-artifacts';
fs.mkdirSync(OUT,{recursive:true});
const report={started_at:new Date().toISOString(),base:BASE,checks:[],findings:[],raw:{}};
const order={critical:0,major:1,minor:2,info:3};
const norm=v=>String(v??'').replace(/\s+/g,' ').trim();
function finding(severity,area,title,detail='',evidence={}){report.findings.push({severity,area,title,detail,evidence});}
function check(name,ok,detail='',severity='major',evidence={}){report.checks.push({name,ok:!!ok,detail,severity,evidence});if(!ok)finding(severity,'check',name,detail,evidence);return !!ok;}
const approx=(a,b,t=1)=>Number.isFinite(Number(a))&&Number.isFinite(Number(b))&&Math.abs(Number(a)-Number(b))<=t;

try{
  const endpoints={
    caps:'/api/pilot/capabilities',auth:'/api/auth/capabilities',build:'/api/pilot/build',release:'/api/pilot/release-state',catalog:'/api/mission-intelligence/demo/fictional/missions',openapi:'/openapi.json'
  };
  const values={};
  for(const [key,route] of Object.entries(endpoints)){
    const response=await fetch(`${BASE}${route}`);
    check(`${route} responds 200`,response.status===200,`status=${response.status}`,'critical');
    values[key]=await response.json();
  }
  report.raw=values;
  const {caps,auth,build,release,catalog,openapi}=values;
  check('Capability flags agree across APIs',caps.public_signup===auth.public_registration_enabled&&caps.invitations_enabled===auth.invitations_enabled&&caps.transactional_email_ready===auth.password_reset_enabled,JSON.stringify({caps,auth}),'critical');
  check('Runtime release identity is internally coherent',build.commit_sha===release.commit_sha&&build.branch===release.branch&&release.database_at_head===true&&release.database_revisions?.length===1&&release.migration_heads?.length===1,JSON.stringify({build,release}),'critical');

  const missions=Object.values(catalog.missions||{});
  check('Public demo remains a single bounded fictional case',missions.length===1&&/fict[ií]ci/i.test(JSON.stringify(catalog)),`missions=${missions.length}`,'critical');
  const mission=missions[0]||{};
  const serialized=JSON.stringify(catalog);
  const leaked=[...(serialized.match(/\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b/ig)||[]),...(serialized.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig)||[])];
  check('Public demo contains no UUID or email leakage',leaked.length===0,JSON.stringify(leaked.slice(0,10)),'critical');

  const chain=mission.situation?.chain||[];
  const exact=['Observação','Evidência','Hipótese','Alternativa','Decisão','Ação','Resultado','Aprendizagem'];
  check('Demo has eight numbered canonical records',chain.length===8&&chain.every((x,i)=>String(x.number).padStart(2,'0')===String(i+1).padStart(2,'0')),JSON.stringify(chain.map(x=>({number:x.number,label:x.label}))),'critical');
  const labels=chain.map(x=>norm(x.label));
  if(JSON.stringify(labels)!==JSON.stringify(exact))finding('major','semantic-consistency','Public demo diverges from the fixed canonical label',`actual=${JSON.stringify(labels)} expected=${JSON.stringify(exact)}`);
  check('Demo does not fabricate a realized result or learning',/não demonstrado/i.test(norm(chain[6]?.value)+' '+norm(chain[6]?.note))&&/pendent|nenhuma conclusão/i.test(norm(chain[7]?.value)+' '+norm(chain[7]?.note)),JSON.stringify(chain.slice(6)),'critical');

  const matrix=mission.analysis?.decision_matrix||{};
  const criteria=matrix.criteria||[],rows=matrix.rows||[];
  const required=['eficácia','custo','risco','reversibilidade','experiência','robustez'];
  check('Matrix covers all six agreed decision dimensions',required.every(term=>criteria.some(c=>norm(c.label).toLocaleLowerCase('pt-PT').includes(term))),JSON.stringify(criteria),'critical');
  if(criteria.length!==6)finding('major','semantic-consistency','Public demo uses a seventh scored criterion',`The agreed matrix has six dimensions; live demo has ${criteria.length}: ${criteria.map(c=>c.label).join(', ')}`);
  check('Matrix has at least three alternatives',rows.length>=3,`rows=${rows.length}`,'major');
  for(const row of rows){
    const scores=(row.scores||[]).map(Number);
    check(`${row.alternative_id}: score structure and total are valid`,scores.length===criteria.length&&scores.every(v=>v>=1&&v<=5)&&Number(row.total)===scores.reduce((a,b)=>a+b,0),JSON.stringify(row),'critical');
  }

  const graph=mission.evidence_graph||{},nodes=graph.nodes||[],links=graph.links||graph.edges||[];
  const ids=new Set(nodes.map(n=>n.id));
  check('Evidence graph contains a real connected structure',nodes.length>=4&&links.length>=3,JSON.stringify({nodes:nodes.length,links:links.length}),'critical');
  check('Every evidence-graph relation resolves',links.every(link=>ids.has(link.from??link.source_id)&&ids.has(link.to??link.target_id)),JSON.stringify(links),'critical');

  const bc=mission.business_case||{},baseline=bc.baseline||{},pilot=bc.pilot||{},scenarios=bc.scenarios||[];
  check('Business Case is explicitly fictitious/projected',/fict[ií]ci|projeç/i.test(norm(bc.notice)+' '+JSON.stringify(scenarios)),norm(bc.notice),'critical');
  check('Business Case provides three scenarios and a valid default',scenarios.length===3&&scenarios.some(s=>s.id===bc.selected_scenario_id),JSON.stringify({selected:bc.selected_scenario_id,ids:scenarios.map(s=>s.id)}),'critical');
  for(const s of scenarios){
    const direct=Number(s.water_saving_m3_per_year)*Number(s.water_tariff_eur_per_m3)+Number(s.energy_saving_kwh_per_year)*Number(s.energy_tariff_eur_per_kwh);
    const net=direct+Number(s.protected_revenue_eur_per_year)-Number(s.recurring_cost_eur_per_year);
    const net3=net*3-Number(pilot.investment_eur);
    const payback=Number(pilot.investment_eur)/net*12;
    const roi=net3/Number(pilot.investment_eur)*100;
    check(`${s.id}: economic formulae reconcile`,approx(s.direct_savings_eur_per_year,direct,2)&&approx(s.net_benefit_eur_per_year,net,2)&&approx(s.net_return_3y_eur,net3,2)&&approx(s.payback_months,payback,1)&&approx(s.roi_3y_percent,roi,1),JSON.stringify({stored:s,calculated:{direct,net,net3,payback,roi}}),'critical');
  }
  const baselineSpend=Number(baseline.water_consumption_m3_per_year)*Number(baseline.water_tariff_eur_per_m3)+Number(baseline.energy_consumption_kwh_per_year)*Number(baseline.energy_tariff_eur_per_kwh);
  check('Baseline annual resource spend reconciles',approx(baseline.annual_resource_spend_eur,baselineSpend,2),JSON.stringify({stored:baseline.annual_resource_spend_eur,calculated:baselineSpend}),'critical');

  const browser=await chromium.launch({headless:true});
  try{
    const context=await browser.newContext({viewport:{width:1440,height:1000},locale:'pt-PT'});
    const page=await context.newPage();
    const errors=[];page.on('pageerror',e=>errors.push(String(e)));page.on('console',m=>{if(m.type()==='error')errors.push(m.text())});
    await page.goto(`${BASE}/demonstracao`,{waitUntil:'networkidle',timeout:45000});
    await page.waitForFunction(()=>!document.querySelector('#mission-title')?.textContent?.toLowerCase().includes('carregar'),null,{timeout:20000});
    const buttons=await page.locator('#scenario-controls button').evaluateAll(xs=>xs.map(x=>({id:x.dataset.scenarioId,label:String(x.textContent||'').replace(/\s+/g,' ').trim(),active:x.classList.contains('active'),pressed:x.getAttribute('aria-pressed')})));
    report.raw.scenario_buttons=buttons;
    check('One economic scenario starts selected',buttons.filter(x=>x.active&&x.pressed==='true').length===1,JSON.stringify(buttons),'major');
    const target=buttons.find(x=>!x.active);
    check('At least one alternative economic scenario is selectable',!!target,JSON.stringify(buttons),'major');
    if(target){
      const before=norm(await page.locator('#business-case-timeline').innerText());
      await page.locator(`#scenario-controls button[data-scenario-id="${target.id}"]`).click();
      await page.waitForTimeout(250);
      const after=norm(await page.locator('#business-case-timeline').innerText());
      const afterButtons=await page.locator('#scenario-controls button').evaluateAll(xs=>xs.map(x=>({id:x.dataset.scenarioId,active:x.classList.contains('active'),pressed:x.getAttribute('aria-pressed')})));
      report.raw.scenario_interaction={target,before,after,afterButtons};
      check('Scenario selection updates its active/pressed state',afterButtons.some(x=>x.id===target.id&&x.active&&x.pressed==='true'),JSON.stringify(afterButtons),'critical');
      check('Scenario selection changes projected figures',after!==before,JSON.stringify({target:target.id,before:before.slice(-800),after:after.slice(-800)}),'critical');
    }
    check('Demo browser execution has no uncaught error',errors.length===0,JSON.stringify(errors),'major');

    await page.goto(`${BASE}/`,{waitUntil:'networkidle',timeout:45000});
    const entry=await page.evaluate(()=>({subtitle:document.querySelector('#auth-subtitle')?.textContent||'',registerDisabled:document.querySelector('#register-tab')?.disabled,registerTitle:document.querySelector('#register-tab')?.title||''}));
    report.raw.entry=entry;
    check('Entry copy does not promise a signup action that is disabled',!(entry.registerDisabled&&/crie uma conta|criar conta/i.test(entry.subtitle)),JSON.stringify(entry),'major');
    await context.close();
  } finally {await browser.close();}

  const paths=Object.keys(openapi.paths||{});
  if(paths.includes('/api/pilot/build')||paths.includes('/api/pilot/release-state'))finding('major','information-exposure','Deployment and database fingerprint are publicly exposed',JSON.stringify({build,release}));
  if(paths.length>100)finding('minor','attack-surface','The complete API schema is publicly enumerable',`paths=${paths.length}`);
} catch(error){report.fatal=String(error?.stack||error);finding('critical','runner','Corrected public data audit aborted',report.fatal);process.exitCode=2;} finally {
  report.completed_at=new Date().toISOString();report.findings.sort((a,b)=>(order[a.severity]??9)-(order[b.severity]??9));report.summary={checks:report.checks.length,passed:report.checks.filter(c=>c.ok).length,failed:report.checks.filter(c=>!c.ok).length,critical:report.findings.filter(f=>f.severity==='critical').length,major:report.findings.filter(f=>f.severity==='major').length,minor:report.findings.filter(f=>f.severity==='minor').length};fs.writeFileSync(path.join(OUT,'public-data-v2.json'),JSON.stringify(report,null,2));const md=['# SRIS public data QA v2','',`Checks: ${report.summary.passed}/${report.summary.checks} passed`,`Findings: ${report.summary.critical} critical · ${report.summary.major} major · ${report.summary.minor} minor`,'','## Findings',...report.findings.map((f,i)=>`${i+1}. **${f.severity.toUpperCase()} · ${f.area} · ${f.title}** — ${norm(f.detail)}`),'','## Failed checks',...report.checks.filter(c=>!c.ok).map((c,i)=>`${i+1}. **${c.severity.toUpperCase()} · ${c.name}** — ${norm(c.detail)}`)].join('\n');fs.writeFileSync(path.join(OUT,'public-data-v2.md'),md);console.log('===== SRIS_PUBLIC_DATA_QA_V2_START =====');console.log(JSON.stringify(report.summary));console.log(md);console.log('===== SRIS_PUBLIC_DATA_QA_V2_END =====');
}
