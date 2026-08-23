(()=>{
  'use strict';

  const BUILD='20260823-decision-first';
  const $=(selector,root=document)=>root.querySelector(selector);
  const $$=(selector,root=document)=>[...root.querySelectorAll(selector)];
  const token=()=>localStorage.getItem('sris_access_token');
  let workspaceReady=false;
  let statusLabel='Workspace a sincronizar';
  let enforcing=false;

  window.__srisPilotBuild=BUILD;
  document.documentElement.dataset.pilotBuild=BUILD;

  const roleLabels={
    owner:'Proprietário e administrador',
    admin:'Administrador',
    reviewer:'Revisor',
    contributor:'Colaborador',
    observer:'Observador',
    member:'Membro',
  };

  function displayWorkspaceName(value){
    const clean=String(value||'').trim();
    if(!clean)return'SRIS Pilot';
    if(['fundador','founder','workspace','workspace individual'].includes(clean.toLowerCase()))return'SRIS Pilot';
    return clean;
  }

  function displayRole(value){
    const key=String(value||'member').toLowerCase();
    return roleLabels[key]||String(value||'Membro');
  }

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

  function setValue(selector,value){
    const element=$(selector);
    if(element)element.value=value??'';
  }

  function setStatus(label,state='ready'){
    statusLabel=label;
    const element=$('#provider-state');
    if(!element)return;
    element.textContent=label;
    element.dataset.state=state;
  }

  function removeLegacyNoise(){
    $('#pilot-integration-alert')?.remove();
    $('#pilot-capability-surface')?.remove();
    $('#opv1-panel')?.remove();
    $('#billing')?.remove();
    $$('.capability-chips').forEach(element=>element.remove());
    $$('[data-section="billing"],[data-go="billing"]').forEach(element=>element.remove());

    const labels={
      overview:'Visão geral',
      mission:'Missões',
      copilot:'Análise assistida',
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

    const labels={
      summary:'Resumo',
      documents:'Documentos',
      graph:'Evidência',
      evidence:'Evidência',
      cycle:'Decisão',
      intelligence:'Diálogo',
      learning:'Memória',
      memory:'Memória',
      history:'Auditoria',
    };
    $$('[data-mission-tab]').forEach(button=>{
      if(labels[button.dataset.missionTab])button.textContent=labels[button.dataset.missionTab];
    });
  }

  function syncPageTitle(){
    const active=$('.section.active');
    if(!active)return;
    const titles={
      overview:'Visão geral',
      mission:'Espaço de missão',
      copilot:'Análise assistida',
      account:'Conta',
    };
    setText('#page-title',titles[active.id]||'SRIS');
  }

  function hydrateProfile(profile){
    const user=profile?.user||{};
    const organization=profile?.organization||{};
    const ai=profile?.ai||{};
    const integration=profile?.integration||{};
    const workspaceName=displayWorkspaceName(organization.name);
    const role=displayRole(organization.role);

    if(organization.id)localStorage.setItem('sris_org_id',organization.id);
    setText('#mini-name',user.full_name||user.email||'Utilizador');
    setText('#mini-org',workspaceName);
    setText('#workspace-role',role);
    setText('#workspace-name',workspaceName);
    setValue('#account-name',user.full_name||'');
    setValue('#account-email',user.email||'');
    setValue('#account-org',workspaceName);
    setValue('#account-role',role);

    const assistanceReady=Boolean(ai.provider_configured&&ai.runtime_enabled&&ai.organization_enabled!==false);
    setText('#ai-status',assistanceReady?'Disponível':'Não ativa');
    setText('#copilot-availability',assistanceReady?'Disponível':'Não ativa');

    workspaceReady=Boolean(integration.workspace_ready||organization.id);
    setText('#persistence-state',workspaceReady?'Ativa':'A recuperar');
    setStatus(workspaceReady?'Workspace sincronizado':'Workspace a recuperar',workspaceReady?'ready':'degraded');
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
      setStatus('Workspace a recuperar','degraded');
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
      optionalAssistance:Boolean($('#copilot')),
      billingVisible:Boolean($('#billing')||$('[data-section="billing"]')),
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

    setTimeout(hydrateRuntime,2500);
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});
  else boot();
})();
