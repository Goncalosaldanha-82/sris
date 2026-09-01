(()=>{
  'use strict';

  const $=(selector,root=document)=>root.querySelector(selector);
  const orgId=()=>localStorage.getItem('sris_org_id')||'';
  const pilot=()=>window.SRISPlatform?.selected||null;
  const api=(path,options={})=>window.SRISApi?.request(path,options);
  const STORAGE_KEY='sris_pending_pilot_mission_link';
  let submitBoundTo=null;
  let linking=false;

  function activeMissionId(){
    const workspace=window.__srisMissionWorkspace||{};
    const direct=workspace.mission?.id||workspace.selectedMission?.id||workspace.current?.id;
    if(direct)return String(direct);
    const remembered=localStorage.getItem(`sris_active_mission:${orgId()||'workspace'}`);
    return remembered||'';
  }

  function readPending(){
    try{
      const payload=JSON.parse(sessionStorage.getItem(STORAGE_KEY)||'null');
      if(!payload)return null;
      if(Date.now()-Number(payload.createdAt||0)>30*60*1000){clearPending();return null;}
      return payload;
    }catch{clearPending();return null;}
  }
  function writePending(payload){sessionStorage.setItem(STORAGE_KEY,JSON.stringify(payload));}
  function clearPending(){sessionStorage.removeItem(STORAGE_KEY);}

  function showMessage(text,type='success'){
    const node=$('#app-message')||$('#pp-message');if(!node)return;
    node.textContent=text;node.className=`app-message alert ${type}`;node.dataset.state=type;
  }

  function ensureCreateButton(){
    const current=pilot();const panel=$('#pp-detail .pp-panel');
    if(!current||!panel||!$('#pp-detail [data-pp-tab="missions"].active'))return;
    if(panel.querySelector('[data-create-pilot-mission]'))return;
    const host=panel.querySelector('.pp-card');if(!host)return;
    const row=document.createElement('div');row.className='pp-report-actions';row.style.marginTop='12px';row.innerHTML='<button class="btn btn-primary" type="button" data-create-pilot-mission>+ Criar missão deste piloto</button><button class="btn btn-secondary" type="button" data-open-mission-portfolio>Abrir portefólio de missões</button>';
    host.appendChild(row);
  }

  async function startMission(){
    const current=pilot();if(!current)return;
    writePending({
      pilotId:current.id,
      pilotCode:current.code,
      pilotTitle:current.title,
      previousMissionId:activeMissionId(),
      submitted:false,
      createdAt:Date.now(),
    });
    $('.nav button[data-section="mission"]')?.click();
    await waitFor(()=>$('#new-mission-btn')||$('#empty-new-btn'),5000);
    ($('#new-mission-btn')||$('#empty-new-btn'))?.click();
    await waitFor(()=>$('#mission-form')&&!$('#mission-editor')?.classList.contains('hidden'),7000);
    prefill(current);
    bindMissionSubmit();
    showMessage('Missão preparada a partir do contrato do piloto. Reveja os campos e guarde para a ligar automaticamente.','success');
  }

  function prefill(current){
    const set=(selector,value)=>{const node=$(selector);if(node&&!node.value)node.value=value||'';};
    set('#mission-title',`${current.code} — ${current.title}`);
    set('#mission-objective',current.objective);
    set('#mission-question',current.decision_question);
    set('#mission-context',[
      current.problem_statement,
      current.scope?`Âmbito: ${current.scope}`:'',
      current.partner_name?`Parceiro: ${current.partner_name}`:'',
      current.context_name?`Contexto operacional: ${current.context_name}`:'',
      current.program_source?`Origem do piloto: ${current.program_source}`:'',
    ].filter(Boolean).join('\n\n'));
    set('#mission-assumptions','Declarar pressupostos ainda não confirmados antes de comprometer a intervenção.');
    set('#mission-constraints',[current.exclusions?`Exclusões: ${current.exclusions}`:'',current.charter?.suspension_conditions?`Condições de suspensão: ${current.charter.suspension_conditions}`:''].filter(Boolean).join('\n'));
    set('#mission-success',current.charter?.success_definition||'Definir um resultado observável, uma baseline, um período e as limitações de atribuição.');
    set('#mission-success-criteria',current.charter?.success_definition||'Definir um resultado observável, uma baseline, um período e as limitações de atribuição.');
  }

  function bindMissionSubmit(){
    const form=$('#mission-form');if(!form||submitBoundTo===form)return;submitBoundTo=form;
    form.addEventListener('submit',()=>{const pending=readPending();if(!pending)return;writePending({...pending,submitted:true,submittedAt:Date.now()});},{capture:true});
  }

  async function linkCreatedMission(){
    if(linking)return;
    const pending=readPending();if(!pending?.submitted||!orgId())return;
    const missionId=activeMissionId();
    if(!missionId||missionId===pending.previousMissionId)return;
    linking=true;
    try{
      await api(`/api/organizations/${encodeURIComponent(orgId())}/pilots/${encodeURIComponent(pending.pilotId)}/missions`,{
        method:'POST',body:JSON.stringify({mission_id:missionId,link_role:'primary'}),
      });
      clearPending();
      showMessage(`Missão criada e ligada automaticamente ao piloto ${pending.pilotCode}.`,'success');
      window.SRISPlatform?.refresh?.();
    }catch(error){
      showMessage(`A missão foi criada, mas a ligação automática falhou: ${error.message}`,'error');
    }finally{linking=false;}
  }

  function waitFor(predicate,timeout=5000){
    return new Promise((resolve,reject)=>{const start=Date.now();const timer=setInterval(()=>{const value=predicate();if(value){clearInterval(timer);resolve(value);}else if(Date.now()-start>timeout){clearInterval(timer);reject(new Error('A interface demorou demasiado a preparar a missão.'));}},80);});
  }

  document.addEventListener('click',event=>{
    if(event.target.closest('[data-create-pilot-mission]')){startMission().catch(error=>showMessage(error.message,'error'));return;}
    if(event.target.closest('[data-open-mission-portfolio]'))$('.nav button[data-section="mission"]')?.click();
  });
  document.addEventListener('click',()=>{if(readPending())setTimeout(bindMissionSubmit,100);});

  setInterval(()=>{ensureCreateButton();if(readPending()){bindMissionSubmit();linkCreatedMission();}},300);
  window.SRISPilotMissionBridge={start:startMission,clear:clearPending};
})();
