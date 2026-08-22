(()=>{
  const $=(s)=>document.querySelector(s);
  const $$=(s)=>[...document.querySelectorAll(s)];
  const token=()=>localStorage.getItem('sris_access_token');
  const BUILD='20260822-r15-product-reset';
  let workspaceReady=false;
  let statusLabel='A sincronizar';
  let enforcing=false;

  window.__srisPilotBuild=BUILD;
  document.documentElement.dataset.pilotBuild=BUILD;

  function authHeaders(){
    const headers={'Content-Type':'application/json'};
    if(token())headers.Authorization=`Bearer ${token()}`;
    return headers;
  }

  async function getJson(url,timeoutMs=8000){
    const controller=new AbortController();
    const timer=setTimeout(()=>controller.abort(),timeoutMs);
    try{
      const response=await fetch(url,{headers:authHeaders(),cache:'no-store',signal:controller.signal});
      let data={};
      try{data=await response.json()}catch{}
      if(!response.ok){
        const detail=data?.detail;
        const message=typeof detail==='string'?detail:(detail?.message||detail?.code||data?.message||`Erro ${response.status}`);
        throw new Error(message);
      }
      return data;
    }finally{
      clearTimeout(timer);
    }
  }

  function setText(selector,value){
    const element=$(selector);
    if(element&&value!==undefined&&value!==null)element.textContent=String(value);
  }

  function money(value){return Number(value||0).toFixed(2)}

  function setStatus(label,state='ready'){
    statusLabel=label;
    const element=$('#provider-state');
    if(!element)return;
    if(element.textContent!==label)element.textContent=label;
    element.dataset.state=state;
  }

  function removeLegacyNoise(){
    $('#pilot-integration-alert')?.remove();
    $('#pilot-capability-surface')?.remove();
    $$('.capability-chips').forEach(element=>element.remove());

    // AI and commercial information remain accessible from Conta. They do not
    // compete with the Mission Workspace in the primary navigation.
    $$('.nav-group').forEach(group=>{
      const label=group.querySelector('.nav-group-label')?.textContent?.trim().toLowerCase();
      if(label==='utilitários')group.hidden=true;
    });

    const labels={
      overview:'Visão geral',
      mission:'Mission Workspace',
      copilot:'Análise assistida',
      billing:'Serviço e utilização',
      account:'Conta',
    };
    $$('[data-section]').forEach(button=>{
      const text=button.querySelector('span');
      if(text&&labels[button.dataset.section])text.textContent=labels[button.dataset.section];
    });
  }

  function reconcileInjectedTabs(){
    const graph=$('[data-mission-tab="graph"]');
    const graphPlaceholder=$('[data-mission-tab="evidence"]');
    if(graph&&graphPlaceholder){graphPlaceholder.remove();$('#mission-tab-evidence')?.remove();}

    const learning=$('[data-mission-tab="learning"]');
    const memoryPlaceholder=$('[data-mission-tab="memory"]');
    if(learning&&memoryPlaceholder){memoryPlaceholder.remove();$('#mission-tab-memory')?.remove();}
  }

  function syncPageTitle(){
    const active=$('.section.active');
    if(!active)return;
    const titles={
      overview:'Visão geral',
      mission:'Mission Workspace',
      copilot:'Análise assistida',
      billing:'Serviço e utilização',
      account:'Conta',
    };
    setText('#page-title',titles[active.id]||'SRIS');
  }

  function hydrateProfile(profile){
    const user=profile?.user||{};
    const organization=profile?.organization||{};
    const ai=profile?.ai||{};
    const integration=profile?.integration||{};

    if(organization.id)localStorage.setItem('sris_org_id',organization.id);
    setText('#mini-name',user.full_name||user.email||'Utilizador');
    setText('#mini-org',organization.name||'Workspace');
    setText('#workspace-role',(organization.role||'membro').toUpperCase());
    setText('#workspace-name',organization.name||'Workspace individual');

    // Technical information is hydrated only inside the explicitly secondary
    // technical/administrative surfaces.
    setText('#balance-eur',money(ai.credit_eur));
    setText('#billing-balance',money(ai.credit_eur));
    setText('#copilot-balance',money(ai.credit_eur));
    setText('#plan-name',(ai.plan||'pilot').replace(/^./,char=>char.toUpperCase()));
    setText('#model-name',ai.model||'a confirmar');
    setText('#copilot-model',ai.model||'Assistência');
    setText('#copilot-model-2',ai.model||'a confirmar');
    setText('#requests-used',ai.requests_used||0);
    setText('#requests-limit',ai.request_limit||0);
    setText('#ai-status',ai.provider_configured&&ai.runtime_enabled?'Disponível':'Não ativa');

    workspaceReady=Boolean(integration.workspace_ready||organization.id);
    setStatus(workspaceReady?'Workspace sincronizado':'Workspace por concluir',workspaceReady?'ready':'degraded');
  }

  async function hydrateRuntime(){
    if(!token())return;

    const [profileResult,capabilityResult]=await Promise.allSettled([
      getJson('/api/pilot/profile'),
      getJson('/api/pilot/capabilities'),
    ]);

    if(profileResult.status==='fulfilled'){
      hydrateProfile(profileResult.value);
    }else{
      workspaceReady=false;
      setStatus('Ligação a recuperar','degraded');
      console.warn('SRIS workspace profile unavailable:',profileResult.reason?.message||profileResult.reason);
    }

    if(capabilityResult.status==='fulfilled'){
      window.__srisPilotCapabilities=capabilityResult.value;
      document.documentElement.dataset.pilotBuild=capabilityResult.value.build||BUILD;
    }else{
      console.warn('Optional Pilot capabilities unavailable:',capabilityResult.reason?.message||capabilityResult.reason);
    }

    removeLegacyNoise();
    reconcileInjectedTabs();
    syncPageTitle();
  }

  function auditLoadedModules(){
    reconcileInjectedTabs();
    window.__srisPilotModuleAudit={
      missionWorkspace:Boolean($('#mission-detail')),
      documents:Boolean($('#mission-tab-documents')),
      history:Boolean($('#mission-tab-history')),
      evidenceGraph:Boolean($('[data-mission-tab="graph"]')||$('[data-mission-tab="evidence"]')),
      organizationalMemory:Boolean($('[data-mission-tab="learning"]')||$('[data-mission-tab="memory"]')),
      decisionCycle:Boolean($('[data-mission-tab="cycle"]')),
    };
  }

  function enforceProductHierarchy(){
    if(enforcing)return;
    enforcing=true;
    try{
      removeLegacyNoise();
      reconcileInjectedTabs();
      syncPageTitle();
      const state=$('#provider-state');
      if(state&&state.textContent!==statusLabel)setStatus(statusLabel,workspaceReady?'ready':'degraded');
    }finally{
      enforcing=false;
    }
  }

  function boot(){
    enforceProductHierarchy();
    hydrateRuntime();
    setTimeout(auditLoadedModules,500);
    setTimeout(auditLoadedModules,1600);

    $$('[data-section],[data-go]').forEach(element=>{
      element.addEventListener('click',()=>setTimeout(enforceProductHierarchy,0));
    });

    const observer=new MutationObserver(()=>setTimeout(enforceProductHierarchy,0));
    observer.observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['class']});

    // A silent second synchronization handles slow Railway/database wake-up
    // without interrupting the user with a global error banner.
    setTimeout(hydrateRuntime,2500);
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});
  else boot();
})();
