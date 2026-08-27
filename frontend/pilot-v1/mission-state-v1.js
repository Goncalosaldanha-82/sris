/* SRIS Pilot V1 — one governed mission state, multiple module views */
(()=>{
  'use strict';

  const MODULE_TABS={
    mission:'summary',documents:'documents',evidence:'graph',comparison:'comparison',
    economics:'economics',validation:'validation',decision:'cycle',action:'cycle',
    outcome:'cycle',learning:'learning',memory:'memory',intelligence:'intelligence',
  };
  const HEALTH={
    governed:['Estado coerente','governed'],
    in_progress:['Em estruturação','progress'],
    requires_review:['Revisão necessária','warning'],
    requires_resolution:['Resolver conflitos','critical'],
  };
  const APPLY={required:'Obrigatório',optional:'Opcional',not_applicable:'Não aplicável'};
  let currentCode='';
  let currentState=null;
  let sequence=0;
  let timer=0;

  const esc=(value='')=>String(value??'').replace(/[&<>"']/g,char=>({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;',
  }[char]));

  async function api(path,options={}){
    if(window.SRISApi?.request)return window.SRISApi.request(path,options);
    const headers={...(options.headers||{})};
    if(!(options.body instanceof FormData))headers['Content-Type']='application/json';
    const token=localStorage.getItem('sris_access_token')||sessionStorage.getItem('sris_access_token');
    if(token)headers.Authorization=`Bearer ${token}`;
    const response=await fetch(path,{...options,headers,cache:'no-store',credentials:'same-origin'});
    const data=await response.json().catch(()=>({}));
    if(!response.ok){
      const detail=data?.detail;
      throw new Error(typeof detail==='string'?detail:(detail?.message||`Pedido recusado (${response.status}).`));
    }
    return data;
  }

  function install(){
    const summary=document.querySelector('#mission-tab-summary');
    const anchor=summary?.querySelector('.mission-summary-kpis');
    const tabs=document.querySelector('#mission-detail .mission-tabs');
    if(!summary||!anchor||!tabs)return false;
    if(!document.querySelector('#governed-mission-context')){
      const strip=document.createElement('button');
      strip.type='button';
      strip.id='governed-mission-context';
      strip.className='gms-context-strip';
      strip.dataset.gmsModule='mission';
      strip.innerHTML='<strong>Estado governado</strong><span>A sincronizar todas as vistas da missão…</span>';
      tabs.parentNode.insertBefore(strip,tabs);
    }
    if(!document.querySelector('#governed-mission-state')){
      const root=document.createElement('section');
      root.id='governed-mission-state';
      root.className='gms-shell';
      root.innerHTML='<div class="note">A sincronizar o estado governado da missão…</div>';
      summary.insertBefore(root,anchor);
      root.addEventListener('click',handleClick);
      root.addEventListener('submit',savePolicy);
    }
    installStyles();
    return true;
  }

  function installStyles(){
    if(document.querySelector('#gms-styles'))return;
    const style=document.createElement('style');
    style.id='gms-styles';
    style.textContent=`
      .gms-context-strip{width:100%;margin:14px 0 8px;border:1px solid #cbdad4;border-radius:12px;background:#f2f7f4;color:#173b31;padding:9px 12px;display:flex;justify-content:space-between;gap:10px;align-items:center;text-align:left;cursor:pointer}.gms-context-strip strong{font-size:11px}.gms-context-strip span{font-size:10px;color:#607269}.gms-shell{margin:14px 0 18px;border:1px solid #cddbd5;border-radius:18px;background:linear-gradient(145deg,#fbfdfc,#f2f7f4);padding:17px;display:grid;gap:14px}.gms-head{display:flex;justify-content:space-between;gap:14px;align-items:flex-start}.gms-head h3{margin:3px 0 5px}.gms-identity{font-size:12px;color:#607269}.gms-health{padding:7px 10px;border-radius:999px;font-size:10px;font-weight:900;text-transform:uppercase;letter-spacing:.06em;white-space:nowrap}.gms-health.governed{background:#e4f2e9;color:#205b43}.gms-health.progress{background:#edf2ef;color:#526b60}.gms-health.warning{background:#fff3da;color:#785a20}.gms-health.critical{background:#fee9e7;color:#963f37}.gms-chain{display:flex;gap:7px;overflow-x:auto;padding:2px 0 7px;scrollbar-width:thin}.gms-module{min-width:128px;border:1px solid #d4dfda;border-radius:12px;background:#fff;padding:9px;text-align:left;color:#173b31;cursor:pointer}.gms-module strong,.gms-module span{display:block}.gms-module strong{font-size:11px}.gms-module span{margin-top:4px;font-size:9px;color:#687a72}.gms-module[data-state="missing"],.gms-module[data-state="stale"]{border-color:#dfb7ad;background:#fff7f5}.gms-module[data-state="not_applicable"]{opacity:.62}.gms-conflicts{display:grid;gap:7px}.gms-conflict{border-left:4px solid #c28c2f;border-radius:9px;background:#fff9eb;padding:9px 11px}.gms-conflict.critical{border-left-color:#a54840;background:#fff1ef}.gms-conflict strong,.gms-conflict span{display:block}.gms-conflict span{font-size:11px;line-height:1.45;color:#596d64;margin-top:3px}.gms-boundary{border:1px solid #cfe0db;border-radius:11px;background:#edf6f3;padding:10px 12px;font-size:11px;line-height:1.5}.gms-boundary strong{color:#164c3d}.gms-policy{border-top:1px solid #d9e3df;padding-top:10px}.gms-policy summary{cursor:pointer;font-weight:850;font-size:12px}.gms-policy form{display:grid;gap:10px;margin-top:11px}.gms-policy-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.gms-policy label{display:grid;gap:5px;font-size:10px;font-weight:800}.gms-policy select,.gms-policy textarea{width:100%;border:1px solid #c7d5cf;border-radius:9px;background:#fff;padding:9px;font:inherit;font-size:14px}.gms-policy textarea{min-height:78px;resize:vertical}.gms-policy-actions{display:flex;gap:9px;align-items:center;flex-wrap:wrap}.gms-policy-status{font-size:10px;color:#61746b}.gms-policy-status.error{color:#a13d36}.gms-policy-status.success{color:#25644b}.gms-integrity{font-size:9px;color:#73837c;overflow-wrap:anywhere}
      @media(max-width:700px){.gms-shell{padding:13px}.gms-head{display:grid}.gms-health{justify-self:start}.gms-policy-grid{grid-template-columns:1fr}.gms-policy-actions .btn{width:100%}.gms-module{min-width:116px}}
    `;
    document.head.appendChild(style);
  }

  function moduleStateLabel(item){
    if(item.status==='stale')return 'Revisão invalidada';
    if(item.status==='missing'){
      if(item.key==='action'&&item.applicability==='required')return 'Execução governada e prova da ação em falta';
      return item.applicability==='required'?'Obrigatório em falta':'Sem dados';
    }
    if(item.status==='not_applicable')return 'Não aplicável · revisto';
    if(item.status==='optional')return 'Opcional · não iniciado';
    if(item.review?.status==='current')return `${item.count} · revisão atual`;
    if(item.review?.status==='unreviewed'&&['comparison','economics','validation'].includes(item.key))return `${item.count} · por rever`;
    return `${item.count} registo${item.count===1?'':'s'}`;
  }

  function policySelect(name,value){
    return `<select name="${name}">${Object.entries(APPLY).map(([key,label])=>`<option value="${key}" ${value===key?'selected':''}>${label}</option>`).join('')}</select>`;
  }

  function render(){
    const root=document.querySelector('#governed-mission-state');
    if(!root||!currentState)return;
    const state=currentState;
    const health=HEALTH[state.health?.status]||['Estado por avaliar','progress'];
    const conflicts=(state.conflicts||[]).slice(0,6);
    const policy=state.policy||{};
    const strip=document.querySelector('#governed-mission-context');
    if(strip)strip.innerHTML=`<strong>${esc(state.mission.code)} · estado governado único</strong><span>${esc(health[0])} · ${Number(state.health?.critical_conflicts||0)} críticos · SHA ${esc(String(state.state_hash||'').slice(0,12))}</span>`;
    root.innerHTML=`
      <div class="gms-head">
        <div><div class="eyebrow">ESTADO GOVERNADO ÚNICO</div><h3>${esc(state.mission.code)} · ${esc(state.mission.title)}</h3><div class="gms-identity">Revisão ${Number(state.mission.revision||0)} · todos os módulos abaixo são vistas desta mesma missão</div></div>
        <span class="gms-health ${health[1]}">${health[0]}</span>
      </div>
      <div class="gms-chain" aria-label="Módulos ligados da missão">${(state.modules||[]).map(item=>`<button class="gms-module" type="button" data-gms-module="${esc(item.key)}" data-state="${esc(item.status)}"><strong>${esc(item.label)}</strong><span>${esc(moduleStateLabel(item))}</span></button>`).join('')}</div>
      ${conflicts.length?`<div class="gms-conflicts">${conflicts.map(item=>`<div class="gms-conflict ${esc(item.severity)}"><strong>${esc(item.title)}</strong><span>${esc(item.detail)}</span></div>`).join('')}${state.conflicts.length>conflicts.length?`<div class="note">+ ${state.conflicts.length-conflicts.length} conflito${state.conflicts.length-conflicts.length===1?'':'s'} no estado completo.</div>`:''}</div>`:'<div class="gms-conflict"><strong>Sem conflitos estruturais detetados</strong><span>Isto confirma coerência entre registos estruturados; não substitui avaliação factual ou humana.</span></div>'}
      <div class="gms-boundary"><strong>IA como suporte governado.</strong> Recebe este mesmo estado e pode extrair, pesquisar com fontes, relacionar, desafiar e sintetizar. Não decide, não aprova, não transforma inferência em evidência e não altera o canónico sem promoção humana explícita.</div>
      <details class="gms-policy"><summary>Aplicabilidade e exceções da missão</summary><form id="gms-policy-form"><div class="gms-policy-grid"><label>Alternativas${policySelect('alternatives_applicability',policy.alternatives_applicability)}</label><label>Economia e recursos${policySelect('economics_applicability',policy.economics_applicability)}</label><label>Medição quantitativa${policySelect('measurement_applicability',policy.measurement_applicability)}</label></div><label>Justificação da revisão<textarea name="rationale" minlength="10" maxlength="5000" required>${esc(policy.rationale||'')}</textarea></label><div class="gms-policy-actions"><button class="btn btn-secondary compact" type="submit">Rever aplicabilidade</button><span class="gms-policy-status" role="status"></span></div></form></details>
      <div class="gms-integrity">Estado SHA-256 ${esc(state.state_hash)} · política ${esc(policy.source||'platform_default')} · supervisão humana obrigatória</div>`;
  }

  function scheduleLoad(code=currentCode){
    window.clearTimeout(timer);
    timer=window.setTimeout(()=>void load(code),90);
  }

  async function load(code){
    const requested=String(code||'').trim();
    if(!requested)return;
    if(!install())return;
    const own=++sequence;
    currentCode=requested;
    try{
      const state=await api(`/api/pilot/mission-state/missions/${encodeURIComponent(requested)}`);
      if(own!==sequence||requested!==currentCode)return;
      currentState=state;
      window.SRISGovernedMissionState=state;
      render();
      const title=document.querySelector('#page-title');
      if(title&&document.querySelector('#mission')?.classList.contains('active'))title.textContent=`${state.mission.code} · ${state.mission.title}`;
      document.dispatchEvent(new CustomEvent('sris:mission-state-updated',{detail:state}));
    }catch(error){
      if(own!==sequence||requested!==currentCode)return;
      const root=document.querySelector('#governed-mission-state');
      if(root)root.innerHTML=`<div class="alert error">Não foi possível consolidar o estado da missão: ${esc(error.message)}</div>`;
    }
  }

  function handleClick(event){
    const button=event.target.closest('[data-gms-module]');
    if(!button)return;
    const module=button.dataset.gmsModule;
    const destination=MODULE_TABS[module];
    document.querySelector(`[data-mission-tab="${destination}"]`)?.click();
  }

  async function savePolicy(event){
    if(event.target.id!=='gms-policy-form')return;
    event.preventDefault();
    const form=event.target;
    const status=form.querySelector('.gms-policy-status');
    const button=form.querySelector('button[type="submit"]');
    const payload={
      expected_revision:Number(currentState?.policy?.revision||0),
      alternatives_applicability:form.alternatives_applicability.value,
      economics_applicability:form.economics_applicability.value,
      measurement_applicability:form.measurement_applicability.value,
      rationale:form.rationale.value.trim(),
    };
    button.disabled=true;
    status.textContent='A fixar a política sobre a revisão atual da missão…';
    status.className='gms-policy-status';
    try{
      currentState=await api(`/api/pilot/mission-state/missions/${encodeURIComponent(currentCode)}/policy`,{method:'PUT',body:JSON.stringify(payload)});
      window.SRISGovernedMissionState=currentState;
      render();
      const updated=document.querySelector('.gms-policy-status');
      if(updated){updated.textContent='Aplicabilidade revista e auditada.';updated.className='gms-policy-status success';}
      document.dispatchEvent(new CustomEvent('sris:mission-state-updated',{detail:currentState}));
    }catch(error){
      status.textContent=error.message;
      status.className='gms-policy-status error';
      button.disabled=false;
    }
  }

  document.addEventListener('sris:mission-opened',event=>{
    const mission=event.detail?.mission;
    if(!mission?.code)return;
    currentCode=mission.code;
    currentState=null;
    if(install())document.querySelector('#governed-mission-state').innerHTML='<div class="note">A consolidar documentos, evidência, economia, medição, decisão e memória…</div>';
    scheduleLoad(mission.code);
  });

  [
    'sris:evidence-graph-updated','sris:alternative-matrix-updated',
    'sris:business-case-updated','sris:validation-updated',
    'sris:decision-cycles-updated','sris:learning-published',
    'sris:memory-updated',
  ].forEach(name=>document.addEventListener(name,()=>{if(currentCode)scheduleLoad();}));

  document.addEventListener('DOMContentLoaded',()=>install(),{once:true});
  document.addEventListener('click',event=>{if(event.target.closest('#governed-mission-context'))document.querySelector('[data-mission-tab="summary"]')?.click();});
  window.SRISMissionState={get current(){return currentState;},refresh:()=>scheduleLoad()};
})();
