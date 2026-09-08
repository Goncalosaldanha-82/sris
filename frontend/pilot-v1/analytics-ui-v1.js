(()=>{
  'use strict';
  const $=selector=>document.querySelector(selector);
  const token=()=>localStorage.getItem('sris_access_token')||'';
  const number=value=>new Intl.NumberFormat('pt-PT').format(Number(value||0));
  const percent=value=>`${new Intl.NumberFormat('pt-PT',{minimumFractionDigits:1,maximumFractionDigits:1}).format(Number(value||0))}%`;
  let generation=0, controller=null, lastToken=token(), allowed=false;
  const metrics=['analytics-site','analytics-demo','analytics-app','analytics-login','analytics-site-demo','analytics-demo-app'];
  function setText(id,value){const node=$('#'+id);if(node)node.textContent=String(value??'—');}
  function hide(){
    allowed=false;
    ['analytics-nav-group','analytics-overview'].forEach(id=>{
      const node=$('#'+id);if(node){node.classList.add('hidden');node.hidden=true;}
    });
    metrics.forEach(id=>setText(id,'—'));
    setText('analytics-state','');
  }
  function invalidate(){generation+=1;controller?.abort();controller=null;hide();}
  function render(data){
    const views=data.views||{},events=data.events||{},funnel=data.funnel||{};
    setText('analytics-site',number(views.site));setText('analytics-demo',number(views.demo));
    setText('analytics-app',number(views.app));setText('analytics-login',number(events.login_success));
    setText('analytics-site-demo',percent(funnel.site_to_demo_rate_pct));setText('analytics-demo-app',percent(funnel.demo_to_app_rate_pct));
    setText('analytics-period',`Últimos ${Number(data.period_days||30)} dias`);
    setText('analytics-state',data.total_events?`${number(data.total_events)} eventos agregados · telemetria própria do SRIS`:'Recolha ativa · ainda sem volume suficiente para leitura de tendência');
    ['analytics-nav-group','analytics-overview'].forEach(id=>{
      const node=$('#'+id);if(node){node.hidden=false;node.classList.remove('hidden');}
    });
    allowed=true;
  }
  async function loadSummary(){
    // Workspace roles and client-side profiles never authorize platform analytics.
    invalidate();lastToken=token();const credentials=lastToken,sequence=generation;
    if(!credentials||document.hidden)return;
    const active=new AbortController();controller=active;
    const timer=setTimeout(()=>active.abort(),15000);
    const current=()=>sequence===generation&&credentials===token()&&!document.hidden;
    try{
      const response=await fetch('/api/internal-analytics/summary?days=30',{
        headers:{Authorization:`Bearer ${credentials}`},cache:'no-store',signal:active.signal,
      });
      if(!response.ok||!current())return;
      const data=await response.json();
      if(current())render(data);
    }catch{if(current())hide();}
    finally{clearTimeout(timer);if(controller===active)controller=null;}
  }
  function openDashboard(){if(allowed)location.assign('/admin/analytics');}
  $('#analytics-nav')?.addEventListener('click',openDashboard);
  $('#analytics-open')?.addEventListener('click',openDashboard);
  $('#analytics-refresh')?.addEventListener('click',event=>{
    const button=event.currentTarget;button.classList.add('loading');
    void loadSummary().finally(()=>button.classList.remove('loading'));
  });
  document.addEventListener('click',event=>{
    if(event.target?.closest('#logout,#logout-btn,[data-logout]'))invalidate();
  },true);
  window.addEventListener('storage',event=>{if(event.key===null||event.key==='sris_access_token')void loadSummary();});
  window.addEventListener('pagehide',invalidate);
  window.addEventListener('pageshow',()=>void loadSummary());
  document.addEventListener('visibilitychange',()=>document.hidden?invalidate():void loadSummary());
  // Also catch same-tab token changes (login/refresh) without trusting profile roles.
  setInterval(()=>{if(token()!==lastToken){invalidate();lastToken=token();if(!document.hidden)void loadSummary();}},500);
  setInterval(()=>{if(allowed&&!document.hidden)void loadSummary();},60000);
  hide();void loadSummary();
})();
