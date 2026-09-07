(()=>{
  'use strict';

  const ADMIN_ROLES=new Set(['owner','admin']);
  const $=selector=>document.querySelector(selector);
  let profilePoll=0;
  let summaryLoading=false;

  function adminRole(){
    return String(window.SRISProfile?.organization?.role||'').toLowerCase();
  }

  function setAccess(allowed){
    $('#analytics-nav-group')?.classList.toggle('hidden',!allowed);
    $('#analytics-overview')?.classList.toggle('hidden',!allowed);
  }

  function setText(selector,value){
    const node=$(selector);
    if(node)node.textContent=String(value??'—');
  }

  function number(value){
    return new Intl.NumberFormat('pt-PT').format(Number(value||0));
  }

  function percent(value){
    return `${new Intl.NumberFormat('pt-PT',{minimumFractionDigits:1,maximumFractionDigits:1}).format(Number(value||0))}%`;
  }

  function analyticsHeaders(){
    const headers={};
    const token=localStorage.getItem('sris_access_token');
    const organization=localStorage.getItem('sris_org_id');
    if(token)headers.Authorization=`Bearer ${token}`;
    if(organization)headers['X-SRIS-Organization']=organization;
    return headers;
  }

  function renderSummary(data){
    const views=data?.views||{};
    const funnel=data?.funnel||{};
    const events=data?.events||{};
    setText('#analytics-site',number(views.site));
    setText('#analytics-demo',number(views.demo));
    setText('#analytics-app',number(views.app));
    setText('#analytics-login',number(events.login_success));
    setText('#analytics-site-demo',percent(funnel.site_to_demo_rate_pct));
    setText('#analytics-demo-app',percent(funnel.demo_to_app_rate_pct));
    setText('#analytics-period',`Últimos ${Number(data?.period_days||30)} dias`);
    const state=$('#analytics-state');
    if(state){
      state.textContent=data?.total_events
        ?`${number(data.total_events)} eventos agregados · telemetria própria do SRIS`
        :'Recolha ativa · ainda sem volume suficiente para leitura de tendência';
      state.dataset.state='ready';
    }
  }

  async function loadSummary(){
    if(summaryLoading||!ADMIN_ROLES.has(adminRole()))return;
    summaryLoading=true;
    const state=$('#analytics-state');
    if(state){state.textContent='A atualizar leitura de interesse…';state.dataset.state='loading';}
    try{
      const response=await fetch('/api/internal-analytics/summary?days=30',{
        headers:analyticsHeaders(),
        cache:'no-store',
      });
      if(response.status===401){
        if(state)state.textContent='Sessão a renovar. Volte a abrir a Visão geral.';
        return;
      }
      if(response.status===403){
        setAccess(false);
        return;
      }
      if(!response.ok)throw new Error(`HTTP ${response.status}`);
      renderSummary(await response.json());
    }catch(error){
      console.warn('SRIS internal analytics summary unavailable:',error.message);
      if(state){state.textContent='Analytics temporariamente indisponível.';state.dataset.state='error';}
    }finally{
      summaryLoading=false;
    }
  }

  function openDashboard(){
    location.assign('/admin/analytics');
  }

  function activate(){
    const role=adminRole();
    if(!role){
      profilePoll+=1;
      if(profilePoll<60)setTimeout(activate,250);
      return;
    }
    const allowed=ADMIN_ROLES.has(role);
    setAccess(allowed);
    if(!allowed)return;
    void loadSummary();
  }

  $('#analytics-nav')?.addEventListener('click',openDashboard);
  $('#analytics-open')?.addEventListener('click',openDashboard);
  $('#analytics-refresh')?.addEventListener('click',event=>{
    event.currentTarget.classList.add('loading');
    Promise.resolve(loadSummary()).finally(()=>event.currentTarget.classList.remove('loading'));
  });

  document.addEventListener('visibilitychange',()=>{
    if(document.visibilityState==='visible'&&ADMIN_ROLES.has(adminRole()))void loadSummary();
  });

  activate();
})();
