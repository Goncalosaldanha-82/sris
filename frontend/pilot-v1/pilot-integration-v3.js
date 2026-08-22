(()=>{
  const $=(s)=>document.querySelector(s);
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

  function auditLoadedModules(){
    const expected={
      missionWorkspace:Boolean($('#mission-detail')),
      documents:Boolean($('#mission-tab-documents')),
      history:Boolean($('#mission-tab-history')),
      evidenceGraph:Boolean($('#mission-tab-evidence')),
      memory:Boolean($('#mission-tab-memory')),
    };
    window.__srisPilotModuleAudit=expected;
    const missing=Object.entries(expected).filter(([,ready])=>!ready).map(([name])=>name);
    if(missing.length)console.warn('Pilot visual modules not mounted:',missing.join(', '));
  }

  function boot(){
    hydrateOptionalCapabilities();
    auditLoadedModules();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});
  else boot();
})();
