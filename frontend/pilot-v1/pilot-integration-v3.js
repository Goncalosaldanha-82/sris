(()=>{
  const $=(s)=>document.querySelector(s);
  const $$=(s)=>[...document.querySelectorAll(s)];
  const token=()=>localStorage.getItem('sris_access_token');
  const orgId=()=>localStorage.getItem('sris_org_id');
  const BUILD='20260822-integrated-v3';

  function authHeaders(){const h={'Content-Type':'application/json'};if(token())h.Authorization=`Bearer ${token()}`;return h;}
  async function getJson(url){const r=await fetch(url,{headers:authHeaders(),cache:'no-store'});let d={};try{d=await r.json()}catch{}if(!r.ok){const detail=d?.detail;throw new Error(typeof detail==='string'?detail:(detail?.message||detail?.code||d?.message||`Erro ${r.status}`));}return d;}
  function money(v){return Number(v||0).toFixed(2)}
  function setText(selector,value){const el=$(selector);if(el&&value!==undefined&&value!==null)el.textContent=String(value)}
  function setValue(selector,value){const el=$(selector);if(el&&value!==undefined&&value!==null)el.value=String(value)}

  function installBuildMarker(){
    if($('#pilot-build-marker'))return;
    const foot=$('.sidebar-foot');if(!foot)return;
    const el=document.createElement('div');el.id='pilot-build-marker';el.style.cssText='margin-top:10px;padding-top:10px;border-top:1px solid rgba(255,255,255,.12);font-size:10px;color:#9eb5ad;letter-spacing:.04em';el.textContent=`Pilot V1 · ${BUILD}`;foot.appendChild(el);
  }

  function installCapabilitySurface(){
    const empty=$('#mission-empty .mission-empty-state');if(!empty||$('#pilot-capability-surface'))return;
    const box=document.createElement('div');box.id='pilot-capability-surface';box.style.cssText='display:flex;flex-wrap:wrap;justify-content:center;gap:7px;margin:18px auto 0;max-width:760px';
    ['Uploads & Document Intelligence','Diálogo persistente','Sub-missões','Evidence Graph','Provenance','Memória entre missões','Hybrid retrieval'].forEach(label=>{const chip=document.createElement('span');chip.className='pill';chip.textContent=label;box.appendChild(chip)});
    empty.appendChild(box);
  }

  function showIntegrationAlert(message,type='error'){
    let box=$('#pilot-integration-alert');
    if(!box){box=document.createElement('div');box.id='pilot-integration-alert';box.style.cssText='position:fixed;left:50%;transform:translateX(-50%);bottom:18px;z-index:99999;max-width:min(92vw,780px);padding:12px 16px;border-radius:12px;font-size:13px;box-shadow:0 10px 30px rgba(0,0,0,.18)';document.body.appendChild(box)}
    box.style.background=type==='error'?'#fff0f0':'#edf7f2';box.style.color=type==='error'?'#8f2f2f':'#174f3e';box.style.border=`1px solid ${type==='error'?'#efc2c2':'#b9d9ca'}`;box.textContent=message;
  }
  function clearIntegrationAlert(){const box=$('#pilot-integration-alert');if(box)box.remove();}

  async function hydrateRuntime(){
    if(!token())return;
    try{
      const [profile,cap]=await Promise.all([getJson('/api/pilot/profile'),getJson('/api/pilot/capabilities')]);
      const u=profile.user||{},o=profile.organization||{},ai=profile.ai||{};
      if(o.id)localStorage.setItem('sris_org_id',o.id);
      setText('#mini-name',u.full_name||u.email||'Utilizador');setText('#mini-org',o.name||'Workspace');
      setText('#balance-eur',money(ai.credit_eur));setText('#billing-balance',money(ai.credit_eur));setText('#copilot-balance',money(ai.credit_eur));
      setText('#plan-name',(ai.plan||'pilot').replace(/^./,x=>x.toUpperCase()));setText('#model-name',ai.model||cap.ai_model||'—');setText('#copilot-model',ai.model||cap.ai_model||'IA');setText('#copilot-model-2',ai.model||cap.ai_model||'—');
      setText('#requests-used',ai.requests_used||0);setText('#requests-limit',ai.request_limit||0);setText('#workspace-role',(o.role||'—').toUpperCase());setText('#workspace-name',o.name||'—');
      setValue('#account-name',u.full_name||'');setValue('#account-email',u.email||'');setValue('#account-org',o.name||'');setValue('#account-role',o.role||'');
      const ready=Boolean(cap.ai_configured&&cap.ai_enabled);setText('#ai-status',ready?'IA disponível':'IA por configurar');setText('#provider-state',ready?'Operacional':'Configuração');
      clearIntegrationAlert();
    }catch(err){
      setText('#ai-status','Integração com erro');
      showIntegrationAlert(`Pilot V1: a interface carregou, mas o estado do workspace não foi obtido: ${err.message}`,'error');
    }
  }

  function checkModules(){
    const required=[
      ['Mission Workspace',$('[data-mission-tab="intelligence"]')],
      ['Memória persistente',$('[data-mission-tab="memory"]')],
      ['Evidence Graph',window.__srisEvidenceGraph||$('[data-mission-tab="graph"]')||$('[data-mission-tab="evidence-graph"]')],
    ];
    const missing=required.filter(([,ok])=>!ok).map(([name])=>name);
    if(missing.length){showIntegrationAlert(`Pilot V1 carregou, mas faltam módulos visuais: ${missing.join(', ')}. Atualize a página uma vez; se persistir, este build fica marcado como falhado.`,'error');return false;}
    return true;
  }

  function bindMissionRefresh(){
    const missionNav=$('[data-section="mission"]');if(!missionNav||missionNav.dataset.integrationBound)return;missionNav.dataset.integrationBound='1';missionNav.addEventListener('click',()=>setTimeout(()=>{
      const list=$('#mission-list');if(list&&/A carregar missões/i.test(list.textContent||'')&&orgId()){
        showIntegrationAlert('A obter o portfolio persistente de missões…','ok');
        setTimeout(()=>{if(/A carregar missões/i.test(list.textContent||''))showIntegrationAlert('O portfolio de missões continua sem resposta. O problema está no backend/API, não no desenho da interface.','error');},3500);
      }
    },300));
  }

  function boot(){installBuildMarker();installCapabilitySurface();bindMissionRefresh();hydrateRuntime();setTimeout(checkModules,1200);setTimeout(()=>{installCapabilitySurface();hydrateRuntime();},3500);}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
