(()=>{
  const $=(s)=>document.querySelector(s);
  const $$=(s)=>[...document.querySelectorAll(s)];
  const BUILD='20260822-product-recovery-v1';
  window.__srisPilotBuild=BUILD;
  document.documentElement.dataset.pilotBuild=BUILD;

  async function optionalJson(url,timeoutMs=7000){
    const controller=new AbortController();
    const timer=setTimeout(()=>controller.abort(),timeoutMs);
    const headers={};
    const access=localStorage.getItem('sris_access_token');
    if(access)headers.Authorization=`Bearer ${access}`;
    try{
      const response=await fetch(url,{headers,cache:'no-store',signal:controller.signal});
      if(!response.ok)throw new Error(`HTTP ${response.status}`);
      return await response.json();
    }finally{clearTimeout(timer);}
  }

  async function hydrateOptionalCapabilities(){
    try{
      window.__srisPilotCapabilities=await optionalJson('/api/pilot/capabilities');
    }catch(err){
      /* Capabilities are supplementary. app.js owns authenticated profile,
         workspace and mission state; failure here must never block the product. */
      console.warn('Optional Pilot capabilities unavailable:',err.message);
    }
  }

  function reconcileInjectedTabs(){
    const graph=$('[data-mission-tab="graph"]');
    const graphPlaceholder=$('[data-mission-tab="evidence"]');
    if(graph&&graphPlaceholder){graphPlaceholder.remove();$('#mission-tab-evidence')?.remove();}

    const learning=$('[data-mission-tab="learning"]');
    const memoryPlaceholder=$('[data-mission-tab="memory"]');
    if(learning&&memoryPlaceholder){memoryPlaceholder.remove();$('#mission-tab-memory')?.remove();}
  }

  function installProductTitles(){
    const labels={overview:'Visão geral',mission:'Mission Workspace',copilot:'Análise assistida',billing:'Serviço e utilização',account:'Conta'};
    $$('.nav button[data-section]').forEach(button=>button.addEventListener('click',()=>{
      const title=labels[button.dataset.section];
      if(title&&$('#page-title'))$('#page-title').textContent=title;
    }));
  }

  function auditLoadedModules(){
    reconcileInjectedTabs();
    const expected={
      missionWorkspace:Boolean($('#mission-detail')),
      documents:Boolean($('#mission-tab-documents')),
      history:Boolean($('#mission-tab-history')),
      evidenceGraph:Boolean($('[data-mission-tab="graph"]')),
      organizationalMemory:Boolean($('[data-mission-tab="learning"]')),
      decisionCycle:Boolean($('[data-mission-tab="cycle"]')),
    };
    window.__srisPilotModuleAudit=expected;
    const missing=Object.entries(expected).filter(([,ready])=>!ready).map(([name])=>name);
    if(missing.length)console.warn('Pilot visual modules not mounted:',missing.join(', '));
  }

  function boot(){
    hydrateOptionalCapabilities();
    installProductTitles();
    setTimeout(auditLoadedModules,350);
    setTimeout(auditLoadedModules,1400);
    const detail=$('#mission-detail');
    if(detail)new MutationObserver(()=>reconcileInjectedTabs()).observe(detail,{subtree:true,childList:true});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});
  else boot();
})();
