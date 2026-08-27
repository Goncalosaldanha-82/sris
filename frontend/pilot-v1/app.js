const $=(selector,root=document)=>root.querySelector(selector);
const $$=(selector,root=document)=>[...root.querySelectorAll(selector)];
const token=()=>localStorage.getItem('sris_access_token');
const refreshToken=()=>localStorage.getItem('sris_refresh_token');

let profile=null;
let missions=[];
let selectedMission=null;
let profileAvailable=false;
let refreshPromise=null;
let editingMissionId=null;
let workspaceSummary=null;
const missionRuntime={attachments:[],graph:null,validation:null,businessCase:null,cycles:[],readiness:null,dialogues:[],memory:[],extraction:null};

const titles={
  overview:'Visão geral',
  mission:'Espaço de missão',
  copilot:'Análise assistida',
  account:'Conta',
};

const roleLabels={
  owner:'Proprietário e administrador',
  admin:'Administrador',
  reviewer:'Revisor',
  contributor:'Colaborador',
  observer:'Observador',
  member:'Membro',
};

const priorityLabels={
  critical:'Crítica',
  strategic:'Estratégica',
  standard:'Normal',
  exploratory:'Exploratória',
};

const lifecycleLabels={
  active:'Ativa',
  paused:'Pausada',
  completed:'Concluída',
  archived:'Arquivada',
};

const missionTemplates={
  resource:{
    title:'Normalizar e reduzir o consumo de água por quarto-noite ocupado',
    objective:'Decidir que intervenção operacional deve ser testada para reduzir o consumo de água normalizado pela atividade real, sem degradar a experiência do hóspede nem transferir custo para outra parte da operação.',
    question:'Que fatores explicam a variação observada e qual é a intervenção mais pequena, mensurável e reversível que deve ser testada primeiro?',
    context:'Reunir consumos de água, ocupação, quartos vendidos, hóspedes/noite, rega, lavandaria, manutenção, ocorrências e alterações de procedimento do período em análise.',
    assumptions:'O aumento observado pode estar relacionado com atividade e não apenas com ineficiência.\nOs dados existentes permitem construir uma baseline minimamente comparável.',
    constraints:'Não reduzir qualidade percebida pelo hóspede.\nNão interromper a operação.\nUsar inicialmente dados já disponíveis.',
    success:'Redução sustentada do consumo por quarto-noite ocupado, sem aumento material de reclamações, custo operacional ou consumo noutro recurso.',
    domain:'hospitality_resource_efficiency',
    priority:'strategic',
    horizon:'90 dias',
    validationProfile:'tourism_advance_resource_efficiency',
  },
  incident:{
    title:'Resolver uma ocorrência operacional sem perder a aprendizagem',
    objective:'Decidir a resposta operacional adequada, limitar o impacto imediato e preservar as causas, ações e resultados para evitar que a organização volte a aprender o mesmo problema do zero.',
    question:'O que aconteceu, que explicações permanecem abertas e que ação deve ser executada agora sem confundir urgência com certeza?',
    context:'Registar a ocorrência, momento, local, pessoas envolvidas, impacto, evidência disponível, intervenções já tentadas e alterações recentes na operação.',
    assumptions:'A primeira explicação pode não ser a causa real.\nA ocorrência pode resultar de mais do que um fator.',
    constraints:'Segurança e continuidade operacional prevalecem.\nA resposta deve ser rastreável e proporcional à evidência disponível.',
    success:'Ocorrência estabilizada, causa ou causas materialmente esclarecidas, ação acompanhada e aprendizagem validada para reutilização futura.',
    domain:'operations_incident',
    priority:'critical',
    horizon:'30 dias',
    validationProfile:'measurable_decision',
  },
  investment:{
    title:'Avaliar um investimento ou uma alteração operacional',
    objective:'Decidir entre manter, alterar, testar ou investir, comparando alternativas, risco, reversibilidade, custo total e resultado esperado antes de comprometer recursos.',
    question:'Qual alternativa cria maior valor ajustado ao risco e que evidência falta obter antes de a decisão se tornar suficientemente fundamentada?',
    context:'Reunir problema de partida, alternativas consideradas, custos diretos e indiretos, responsáveis, dependências, prazos, dados operacionais e consequências de não agir.',
    assumptions:'As estimativas disponíveis são provisórias e devem ser separadas de factos confirmados.\nO custo de oportunidade pode ser material.',
    constraints:'Orçamento, prazo, capacidade da equipa, reversibilidade, requisitos legais e impacto na operação corrente.',
    success:'Decisão tomada com critérios explícitos, alternativa escolhida comparável às rejeitadas, ação atribuída e resultado observado revisto no horizonte definido.',
    domain:'investment_decision',
    priority:'strategic',
    horizon:'120 dias',
    validationProfile:'measurable_decision',
  },
};

function logout(){
  ['sris_access_token','sris_refresh_token','sris_org_id'].forEach(key=>localStorage.removeItem(key));
  location.assign('/');
}

function errText(data,status){
  const detail=data?.detail;
  if(typeof detail==='string')return detail;
  if(detail?.message)return detail.message;
  if(detail?.code)return detail.code;
  return data?.message||`Erro ${status}`;
}

function storeTokens(data){
  if(data?.access_token)localStorage.setItem('sris_access_token',data.access_token);
  if(data?.refresh_token)localStorage.setItem('sris_refresh_token',data.refresh_token);
}

async function renewSession(){
  if(refreshPromise)return refreshPromise;
  const current=refreshToken();
  if(!current)throw new Error('Sessão expirada.');
  refreshPromise=(async()=>{
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),20000);
    try{
      const response=await fetch('/api/auth/refresh',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({refresh_token:current}),
        cache:'no-store',
        signal:controller.signal,
      });
      let data={};
      try{data=await response.json();}catch{}
      if(!response.ok)throw new Error(errText(data,response.status));
      storeTokens(data);
      return data;
    }finally{
      clearTimeout(timeout);
      refreshPromise=null;
    }
  })();
  return refreshPromise;
}

async function rawApi(path,options={}){
  const {retryAuth=true,timeoutMs,...fetchOptions}=options;
  const headers={...(fetchOptions.headers||{})};
  if(!(fetchOptions.body instanceof FormData))headers['Content-Type']='application/json';
  if(token())headers.Authorization=`Bearer ${token()}`;
  const controller=new AbortController();
  const timeout=setTimeout(()=>controller.abort(),timeoutMs||((fetchOptions.body instanceof FormData)?120000:45000));
  try{
    const response=await fetch(path,{...fetchOptions,headers,cache:'no-store',signal:controller.signal});
    if(response.status===401&&retryAuth&&refreshToken()){
      await renewSession();
      return rawApi(path,{...options,retryAuth:false});
    }
    if(response.status===401){logout();throw new Error('Sessão expirada.');}
    return response;
  }catch(error){
    if(error.name==='AbortError')throw new Error('O serviço demorou demasiado a responder. Tente novamente.');
    if(error instanceof TypeError)throw new Error('Não foi possível contactar o serviço. Verifique a ligação.');
    throw error;
  }finally{
    clearTimeout(timeout);
  }
}

async function api(path,options={}){
  const response=await rawApi(path,options);
  let data={};
  try{data=await response.json();}catch{}
  if(!response.ok)throw new Error(errText(data,response.status));
  return data;
}

window.SRISApi={request:api,raw:rawApi,renew:renewSession,logout,token};

function setText(selector,value){
  const element=$(selector);
  if(element&&value!==undefined&&value!==null)element.textContent=String(value);
}

function setValue(selector,value){
  const element=$(selector);
  if(element)element.value=value??'';
}

function initials(name){
  return(name||'S').split(/\s+/).filter(Boolean).slice(0,2).map(part=>part[0]).join('').toUpperCase();
}

function orgId(){
  return profile?.organization?.id||localStorage.getItem('sris_org_id');
}

function activeMissionStorageKey(){
  return `sris_active_mission:${orgId()||'workspace'}`;
}

function rememberedMissionId(){
  return localStorage.getItem(activeMissionStorageKey())||'';
}

function rememberMission(id){
  if(id)localStorage.setItem(activeMissionStorageKey(),id);
}

function miBase(){
  return `/api/organizations/${encodeURIComponent(orgId())}/mission-intelligence`;
}

function displayWorkspaceName(name){
  const clean=String(name||'').trim();
  if(!clean)return'SRIS Pilot';
  if(['fundador','founder','workspace','workspace individual'].includes(clean.toLowerCase()))return'SRIS Pilot';
  return clean;
}

function displayRole(role){
  return roleLabels[String(role||'member').toLowerCase()]||String(role||'Membro');
}

function setWorkspaceState(label,state='ready'){
  const element=$('#provider-state');
  if(!element)return;
  element.textContent=label;
  element.dataset.state=state;
}

function showAppMessage(message,{retry=false}={}){
  const box=$('#app-message');
  if(!box)return;
  box.textContent=message;
  box.className='app-message alert error';
  if(retry){
    const button=document.createElement('button');
    button.type='button';
    button.className='btn btn-secondary compact';
    button.style.marginLeft='10px';
    button.textContent='Tentar novamente';
    button.addEventListener('click',async()=>{
      button.classList.add('loading');
      try{
        await refresh();
        if(orgId())await loadMissions();
      }catch(error){
        box.firstChild.textContent=`${error.message} `;
      }finally{button.classList.remove('loading');}
    });
    box.append(' ',button);
  }
}

function clearAppMessage(){
  const box=$('#app-message');
  if(box){box.textContent='';box.className='app-message alert hidden';}
}

function setAssistanceState(ready){
  document.documentElement.dataset.assistance=ready?'ready':'unavailable';
  const section=$('#copilot');
  if(section)section.dataset.state=ready?'ready':'unavailable';
  $('#assistance-unavailable')?.classList.toggle('hidden',ready);
  $('#assistance-workspace')?.classList.toggle('hidden',!ready);
  const submit=$('#copilot-form [type="submit"]');
  if(submit){
    submit.disabled=!ready;
    submit.title=ready?'':'A assistência ainda não está configurada neste serviço.';
    submit.textContent=ready?'Analisar':'Assistência não configurada';
  }
  window.SRISRuntime={...(window.SRISRuntime||{}),assistanceReady:ready};
}

function go(section){
  $$('.section').forEach(node=>node.classList.toggle('active',node.id===section));
  $$('.nav button').forEach(button=>button.classList.toggle('active',button.dataset.section===section));
  setText('#page-title',titles[section]||'SRIS');
  setMenu(false);
  const missionSync=section==='mission'&&orgId()
    ? loadMissions({openFirst:true})
    : section==='overview'&&orgId()
      ? loadWorkspaceSummary()
      : Promise.resolve();
  if(section==='copilot')updateCopilotContext();
  window.scrollTo({top:0,behavior:'smooth'});
  return missionSync;
}

$$('.nav button[data-section]').forEach(button=>button.addEventListener('click',()=>{void go(button.dataset.section);}));
$$('.nav button[data-mission-area]').forEach(button=>button.addEventListener('click',async()=>{
  await go('mission');
  normaliseMissionTabs();
  const tab=$(`[data-mission-tab="${button.dataset.missionArea}"]`);
  if(tab)tab.click();
  $$('.nav button').forEach(item=>item.classList.toggle('active',item===button));
  setText('#page-title',button.querySelector('span')?.textContent||'Espaço de missão');
}));
$$('[data-go]').forEach(button=>button.addEventListener('click',async()=>{
  await go(button.dataset.go);
  if(button.hasAttribute('data-create-mission')&&!missions.length)resetMissionForm();
}));

function setMenu(open){
  const sidebar=$('#sidebar');
  const button=$('#menu-btn');
  sidebar?.classList.toggle('open',Boolean(open));
  button?.setAttribute('aria-expanded',open?'true':'false');
  button?.setAttribute('aria-label',open?'Fechar menu':'Abrir menu');
  document.body.classList.toggle('menu-open',Boolean(open));
}

$('#menu-btn')?.addEventListener('click',()=>setMenu(!$('#sidebar')?.classList.contains('open')));
$('#sidebar-backdrop')?.addEventListener('click',()=>setMenu(false));
document.addEventListener('keydown',event=>{if(event.key==='Escape')setMenu(false);});
window.matchMedia('(min-width: 801px)').addEventListener?.('change',event=>{if(event.matches)setMenu(false);});
$('#logout-btn')?.addEventListener('click',logout);
$('#logout-btn-2')?.addEventListener('click',logout);

function renderProfile(payload){
  profile=payload;
  profileAvailable=true;
  const user=payload.user||{};
  const organization=payload.organization||{};
  const ai=payload.ai||{};
  const integration=payload.integration||{};
  if(organization.id)localStorage.setItem('sris_org_id',organization.id);
  else localStorage.removeItem('sris_org_id');

  const workspaceName=displayWorkspaceName(organization.name);
  const role=displayRole(organization.role);
  setText('#mini-name',user.full_name||user.email||'Utilizador');
  setText('#mini-org',workspaceName);
  setText('#avatar',initials(user.full_name||user.email));
  setText('#welcome-title',`Olá${user.full_name?' '+user.full_name.split(' ')[0]:''}. Que decisão precisa de ficar melhor fundamentada?`);
  setText('#workspace-role',role);
  setText('#workspace-name',workspaceName);
  setValue('#account-name',user.full_name||'');
  setValue('#account-email',user.email||'');
  setValue('#account-org',workspaceName);
  setValue('#account-role',role);

  const workspaceReady=Boolean(integration.workspace_ready||organization.id);
  const assistanceReady=Boolean(ai.provider_configured&&ai.runtime_enabled&&ai.organization_enabled!==false);
  setText('#ai-status',assistanceReady?'Disponível':'Não ativa');
  setText('#copilot-availability',assistanceReady?'Disponível':'Não ativa');
  setText('#persistence-state',workspaceReady?'Ativa':'A recuperar');
  setWorkspaceState(workspaceReady?'Workspace sincronizado':'Workspace a recuperar',workspaceReady?'ready':'degraded');
  setAssistanceState(assistanceReady);
  clearAppMessage();
  if(!workspaceReady)showAppMessage('A conta foi autenticada, mas ainda não tem um workspace associado.');
  updateCopilotContext();
}

function renderDegradedProfile(){
  profileAvailable=false;
  setWorkspaceState('Workspace a recuperar','degraded');
  setText('#workspace-role','A sincronizar');
  setText('#workspace-name',orgId()?'Workspace identificado':'Por associar');
  setText('#persistence-state','A recuperar');
  setText('#ai-status','A confirmar');
  setText('#copilot-availability','A confirmar');
  setAssistanceState(false);
}

async function refresh(){
  const data=await api('/api/pilot/profile');
  renderProfile(data);
  return data;
}

function updateMissionCTA(){
  const primary=$('#primary-mission-cta');
  const secondary=$('#open-missions-cta');
  if(primary)primary.textContent=missions.length?'Continuar missão':'Criar primeira missão';
  if(secondary)secondary.textContent=missions.length?`Abrir missões (${missions.length})`:'Ver como funciona';
  setText('#mission-count',missions.length);
}

function commandMissionRow(mission,{attention=false}={}){
  const progress=Math.max(0,Math.min(100,Number(mission.progress_percent||0)));
  return `<button class="command-row" type="button" data-command-mission="${escapeHtml(mission.id)}">
    <span class="command-row-main"><strong>${escapeHtml(mission.title)}</strong><small>${escapeHtml(mission.code)} · ${escapeHtml(lifecycleLabels[mission.lifecycle_state]||mission.lifecycle_state)}</small></span>
    <span class="command-row-status"><b>${progress}%</b><i><em style="width:${progress}%"></em></i>${attention?`<small>${escapeHtml(mission.next_action)}</small>`:''}</span>
  </button>`;
}

function renderWorkspaceSummary(summary){
  workspaceSummary=summary;
  const metrics=summary?.metrics||{};
  setText('#metric-active',metrics.missions_active??0);
  setText('#metric-attention',metrics.missions_attention??0);
  setText('#metric-gaps',metrics.evidence_gaps??0);
  setText('#metric-conflicts',metrics.governance_conflicts??0);
  setText('#metric-results',metrics.pending_results??0);
  setText('#metric-learning',metrics.published_learning??0);
  const rows=Array.isArray(summary?.missions)?summary.missions:[];
  const recent=$('#command-missions');
  if(recent)recent.innerHTML=rows.length?rows.slice(0,5).map(row=>commandMissionRow(row)).join(''):'<div class="command-empty"><strong>Ainda não existem missões.</strong><span>Crie a primeira missão a partir de uma decisão real.</span></div>';
  const attentionRows=rows.filter(row=>['active','paused','completed'].includes(row.lifecycle_state)&&(row.attention>0||row.progress_percent<100)).sort((a,b)=>(b.attention-a.attention)||(a.progress_percent-b.progress_percent));
  const attentionRoot=$('#command-attention');
  if(attentionRoot)attentionRoot.innerHTML=attentionRows.length?attentionRows.slice(0,6).map(row=>commandMissionRow(row,{attention:true})).join(''):'<div class="command-empty success"><strong>Sem bloqueios operacionais.</strong><span>As missões em curso ou concluídas não apresentam reconciliações pendentes.</span></div>';
}

async function loadWorkspaceSummary(){
  if(!orgId())return null;
  try{
    const summary=await api('/api/pilot/workspace-summary');
    renderWorkspaceSummary(summary);
    return summary;
  }catch(error){
    const root=$('#command-attention');
    if(root)root.innerHTML=`<div class="alert error">Não foi possível calcular o estado operacional: ${escapeHtml(error.message)}</div>`;
    return null;
  }
}

$('#overview')?.addEventListener('click',async event=>{
  const button=event.target.closest('[data-command-mission]');
  if(!button)return;
  await go('mission');
  await openMission(button.dataset.commandMission);
});

async function loadAccountCapabilities(){
  const root=$('#account-capabilities');
  if(!root)return;
  try{
    const [authCapabilities,pilotCapabilities]=await Promise.all([api('/api/auth/capabilities'),api('/api/pilot/capabilities')]);
    root.innerHTML=`<div><dt>Convites</dt><dd>${authCapabilities.invitations_enabled?'Disponíveis':'Configuração necessária'}</dd></div><div><dt>Email transacional</dt><dd>${pilotCapabilities.transactional_email_ready?'Ativo':'Não configurado'}</dd></div><div><dt>Auditoria</dt><dd>Ativa</dd></div>`;
  }catch{
    root.innerHTML='<div><dt>Convites</dt><dd>A confirmar</dd></div><div><dt>Email transacional</dt><dd>A confirmar</dd></div><div><dt>Auditoria</dt><dd>Ativa</dd></div>';
  }
}

$('#primary-mission-cta')?.addEventListener('click',async()=>{
  await go('mission');
  if(!missions.length)resetMissionForm();
  else if(!selectedMission){
    const remembered=missions.find(mission=>mission.id===rememberedMissionId());
    await openMission((remembered||missions[0]).id);
  }
});

$('#open-missions-cta')?.addEventListener('click',()=>go('mission'));

function installCopilotActions(){
  const form=$('#copilot-form');
  if(!form||$('#copilot-quick-actions'))return;
  const wrapper=document.createElement('div');
  wrapper.id='copilot-quick-actions';
  wrapper.className='button-row';
  wrapper.style.margin='0 0 16px';
  const actions=[
    ['Pontos cegos','Identifica os três pontos cegos mais importantes nesta decisão e explica o impacto potencial de cada um.'],
    ['Contradições','Procura contradições, pressupostos frágeis e informação que possa alterar materialmente esta decisão.'],
    ['Evidência em falta','Indica a evidência que falta obter, ordenada pelo valor que pode ter para a decisão.'],
    ['Alternativas','Propõe alternativas reais e compara custos, riscos, reversibilidade e informação necessária.'],
  ];
  actions.forEach(([label,prompt])=>{
    const button=document.createElement('button');
    button.type='button';
    button.className='btn btn-secondary compact';
    button.textContent=label;
    button.addEventListener('click',()=>{
      setValue('#copilot-message',prompt);
      $('#copilot-message')?.focus();
    });
    wrapper.appendChild(button);
  });
  form.parentNode.insertBefore(wrapper,form);
}

function updateCopilotContext(){
  const note=$('#copilot-context-note');
  const state=$('#copilot-context-state');
  if(!note||!state)return;
  if(selectedMission){
    note.innerHTML=`<strong>Missão ativa:</strong> ${escapeHtml(selectedMission.code)} — ${escapeHtml(selectedMission.title)}<br><span class="note">A análise pode usar o contexto da missão, documentos recuperados e proveniência disponível.</span>`;
    state.textContent=selectedMission.code;
  }else{
    note.textContent='Abra uma missão para usar o respetivo contexto, documentos recuperados e proveniência.';
    state.textContent='Workspace';
  }
}

function escapeHtml(value=''){
  return String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
}

function renderProvenance(sources=[]){
  const root=$('#copilot-provenance');
  if(!root)return;
  if(!sources.length){root.classList.add('hidden');root.innerHTML='';return;}
  root.classList.remove('hidden');
  root.innerHTML=`<h4>Proveniência utilizada · ${sources.length} excerto(s)</h4>${sources.map(source=>`<div class="provenance-row"><strong>${escapeHtml(source.filename||'Documento')}</strong><br>posição ${Number(source.char_start||0)}–${Number(source.char_end||0)} · recuperação híbrida ${Number(source.hybrid_score||0).toFixed(3)}</div>`).join('')}`;
}

async function askAssistance(message,context,answerElement,button){
  const ai=profile?.ai||{};
  const ready=Boolean(ai.provider_configured&&ai.runtime_enabled&&ai.organization_enabled!==false);
  if(!ready){
    answerElement.textContent='A assistência não está configurada neste serviço. A missão, os documentos, a evidência e o ciclo de decisão continuam disponíveis.';
    answerElement.classList.add('empty');
    return null;
  }
  answerElement.classList.remove('empty');
  answerElement.textContent='A analisar contexto, evidência e memória…';
  button?.classList.add('loading');
  try{
    let governedContext=context||'';
    if(selectedMission?.code){
      try{
        const inherited=await api(`/api/pilot/learning/missions/${encodeURIComponent(selectedMission.code)}/active-context`);
        if(inherited?.context_text){
          governedContext=[governedContext,inherited.context_text].filter(Boolean).join('\n\n--- Aprendizagem revista de missões anteriores ---\n\n');
        }
      }catch(error){
        console.warn('Reviewed learning context unavailable; continuing without it:',error.message);
      }
    }
    const data=await api('/api/pilot/intelligence/ask',{
      method:'POST',
      body:JSON.stringify({
        message,
        context:governedContext||null,
        mission_id:selectedMission?.id||null,
        mission_code:selectedMission?.code||null,
      }),
    });
    answerElement.textContent=data.answer||'Análise concluída.';
    renderProvenance(data?.context?.sources||[]);
    return data;
  }catch(error){
    answerElement.textContent=`Não foi possível concluir a análise: ${error.message}`;
    answerElement.classList.add('empty');
    renderProvenance([]);
    throw error;
  }finally{
    button?.classList.remove('loading');
  }
}

$('#copilot-form')?.addEventListener('submit',async event=>{
  event.preventDefault();
  const message=$('#copilot-message')?.value.trim();
  if(!message)return;
  try{await askAssistance(message,$('#copilot-context')?.value.trim(),$('#copilot-answer'),event.submitter);}catch{}
});

function showMissionMode(mode){
  $('#mission-empty')?.classList.toggle('hidden',mode!=='empty');
  $('#mission-editor')?.classList.toggle('hidden',mode!=='editor');
  $('#mission-detail')?.classList.toggle('hidden',mode!=='detail');
  const section=$('#mission');
  if(section)section.dataset.mode=mode;
}

function revealMissionWorkspace(target){
  if(!window.matchMedia('(max-width: 800px)').matches)return;
  requestAnimationFrame(()=>target?.scrollIntoView({behavior:'smooth',block:'start'}));
}

function resetMissionForm(parent=null,template=null){
  const form=$('#mission-form');
  if(!form)return;
  editingMissionId=null;
  $('#mission-editor')?.classList.remove('editing');
  form.reset();
  setValue('#mission-domain','cross_domain');
  setValue('#mission-kind','mission');
  setValue('#mission-priority','strategic');
  setValue('#mission-validation-profile','none');
  const validationProfile=$('#mission-validation-profile');
  if(validationProfile){validationProfile.disabled=false;validationProfile.title='';}
  setValue('#mission-parent-id',parent?.id||'');
  setText('#mission-code-label',parent?`SUB-MISSÃO DE ${parent.code}`:'NOVA MISSÃO');
  setText('#mission-editor-title',parent?'Criar sub-missão':'Criar missão');
  setText('#save-mission-btn',parent?'Criar sub-missão':'Criar missão');
  $('#cancel-mission-btn')?.classList.remove('hidden');
  const box=$('#mission-message');
  if(box){box.className='alert hidden';box.textContent='';}

  if(template){
    setValue('#mission-title',template.title);
    setValue('#mission-objective',template.objective);
    setValue('#mission-question',template.question);
    setValue('#mission-context',template.context);
    setValue('#mission-assumptions',template.assumptions);
    setValue('#mission-constraints',template.constraints);
    setValue('#mission-success',template.success);
    setValue('#mission-domain',template.domain);
    setValue('#mission-priority',template.priority);
    setValue('#mission-horizon',template.horizon);
    setValue('#mission-validation-profile',template.validationProfile||'none');
  }
  showMissionMode('editor');
  revealMissionWorkspace($('#mission-editor'));
  setTimeout(()=>$('#mission-title')?.focus({preventScroll:true}),280);
}

function editCurrentMission(){
  if(!selectedMission)return;
  const form=$('#mission-form');
  if(!form)return;
  editingMissionId=selectedMission.id;
  $('#mission-editor')?.classList.add('editing');
  form.reset();
  setValue('#mission-parent-id',selectedMission.parent_mission_id||'');
  setValue('#mission-title',selectedMission.title);
  setValue('#mission-objective',selectedMission.objective);
  setValue('#mission-question',selectedMission.central_question);
  setValue('#mission-context',selectedMission.context);
  setValue('#mission-kind',selectedMission.mission_kind||'mission');
  setValue('#mission-domain',selectedMission.domain||'cross_domain');
  setValue('#mission-priority',selectedMission.priority||'strategic');
  setValue('#mission-horizon',selectedMission.horizon||'');
  setValue('#mission-validation-profile',selectedMission.validation_profile||'none');
  const validationProfile=$('#mission-validation-profile');
  if(validationProfile&&selectedMission.validation_profile&&selectedMission.validation_profile!=='none'){
    validationProfile.disabled=true;
    validationProfile.title='O perfil ativo é governado na área Medição da missão.';
  }
  setText('#mission-code-label',`${selectedMission.code} · REVISÃO ${Number(selectedMission.revision||1)}`);
  setText('#mission-editor-title','Editar enquadramento da missão');
  setText('#save-mission-btn','Guardar nova revisão');
  const box=$('#mission-message');
  if(box){box.className='alert hidden';box.textContent='';}
  showMissionMode('editor');
  revealMissionWorkspace($('#mission-editor'));
  setTimeout(()=>$('#mission-title')?.focus({preventScroll:true}),180);
}

$('#new-mission-btn')?.addEventListener('click',()=>resetMissionForm());
$('#empty-new-btn')?.addEventListener('click',()=>resetMissionForm());
$$('[data-mission-template]').forEach(button=>button.addEventListener('click',()=>resetMissionForm(null,missionTemplates[button.dataset.missionTemplate])));
$('#cancel-mission-btn')?.addEventListener('click',()=>{
  editingMissionId=null;
  $('#mission-editor')?.classList.remove('editing');
  return selectedMission?openMission(selectedMission.id):showMissionMode('empty');
});
$('#create-submission-btn')?.addEventListener('click',()=>selectedMission&&resetMissionForm(selectedMission));
$('#detail-submission-btn')?.addEventListener('click',()=>selectedMission&&resetMissionForm(selectedMission));
$('#detail-edit-btn')?.addEventListener('click',editCurrentMission);

function missionRow(mission){
  const indent=Math.min(Number(mission.depth||0),5)*14;
  const kind=mission.mission_kind==='program'?'Programa':'Missão';
  const state=lifecycleLabels[mission.lifecycle_state]||mission.lifecycle_state||'Ativa';
  return `<button class="mission-item ${selectedMission?.id===mission.id?'active':''}" data-mid="${escapeHtml(mission.id)}" style="padding-left:${14+indent}px"><span><strong>${escapeHtml(mission.title)}</strong><small>${escapeHtml(mission.code)} · ${kind}${mission.children_count?` · ${mission.children_count} sub`:''}</small></span><span class="mission-state">${escapeHtml(state)}</span></button>`;
}

function renderMissionList(){
  const search=($('#mission-search')?.value||'').trim().toLowerCase();
  const rows=missions.filter(mission=>!search||`${mission.title} ${mission.code}`.toLowerCase().includes(search));
  const root=$('#mission-list');
  if(!root)return;
  $('#mission-rail')?.classList.toggle('no-missions',missions.length===0);
  root.innerHTML=rows.length?rows.map(missionRow).join(''):'<div class="note">Nenhuma missão encontrada.</div>';
  $$('[data-mid]',root).forEach(button=>button.addEventListener('click',()=>openMission(button.dataset.mid)));
}

$('#mission-search')?.addEventListener('input',renderMissionList);

async function loadMissions({openFirst=false}={}){
  const root=$('#mission-list');
  if(!orgId()){
    showMissionMode('empty');
    if(root)root.innerHTML='<div class="note">O workspace ainda está a sincronizar.</div>';
    return;
  }
  if(root)root.innerHTML='<div class="note">A sincronizar missões…</div>';
  try{
    const rows=await api(`${miBase()}/missions`);
    missions=Array.isArray(rows)?rows:[];
    renderMissionList();
    updateMissionCTA();
    if(!missions.length){
      selectedMission=null;
      if($('#mission')?.dataset.mode!=='editor')showMissionMode('empty');
      updateCopilotContext();
      return;
    }
    if(selectedMission){
      const stillExists=missions.some(mission=>mission.id===selectedMission.id);
      if(!stillExists)selectedMission=null;
    }
    if(openFirst&&!selectedMission){
      const remembered=missions.find(mission=>mission.id===rememberedMissionId());
      await openMission((remembered||missions[0]).id);
    }
  }catch(error){
    if(root){
      root.innerHTML='<div class="alert error">Não foi possível sincronizar as missões.<br><button class="btn btn-secondary compact" id="retry-missions" style="margin-top:10px">Tentar novamente</button></div>';
      $('#retry-missions')?.addEventListener('click',()=>loadMissions({openFirst}));
    }
  }
}

async function loadEpistemicCounts(code){
  const root=$('#detail-epistemic-counts');
  if(!root||!code)return;
  try{
    const graph=await api(`/api/pilot/evidence-graph/missions/${encodeURIComponent(code)}`);
    const counts=graph.counts||{};
    const gaps=Number(counts.gap||0)+Number(counts.claim_gap||0);
    root.innerHTML=`<span>Pressupostos · ${Number(counts.assumption||0)}</span><span>Restrições · ${Number(counts.constraint||0)}</span><span>Lacunas · ${gaps}</span><span>Proveniência · ativa</span>`;
  }catch{
    root.innerHTML='<span>Pressupostos · —</span><span>Restrições · —</span><span>Lacunas · —</span><span>Proveniência · ativa</span>';
  }
}

function normaliseMissionTabs(){
  const tabs=$('.mission-tabs');
  const detail=$('#mission-detail');
  if(!tabs||!detail)return;
  const order=['summary','documents','graph','comparison','economics','validation','cycle','intelligence','memory','learning','history'];
  const labels={summary:'Resumo',documents:'Documentos',graph:'Evidência',comparison:'Comparação',economics:'Economia e recursos',validation:'Medição',cycle:'Decisão e resultado',intelligence:'Diálogo',memory:'Memória canónica',learning:'Reutilizar aprendizagem',history:'Auditoria'};
  order.forEach(name=>{
    const button=$(`[data-mission-tab="${name}"]`,tabs);
    const panel=$(`#mission-tab-${name}`,detail);
    if(button){button.textContent=labels[name]||button.textContent;tabs.appendChild(button);}
    if(panel)detail.appendChild(panel);
  });
}

function activateMissionTab(name){
  normaliseMissionTabs();
  const button=$(`.mission-tabs [data-mission-tab="${name}"]`);
  if(!button)return false;
  button.click();
  return true;
}

function renderMissionLifecycleBoundary(mission){
  const detail=$('#mission-detail');
  const banner=$('#mission-lock-banner');
  const lifecycle=mission?.lifecycle_state||'active';
  if(detail)detail.dataset.lifecycle=lifecycle;
  if(!banner)return;
  const terminal=['completed','archived'].includes(lifecycle);
  banner.classList.toggle('hidden',!terminal);
  banner.textContent=terminal
    ? `Missão ${lifecycle==='archived'?'arquivada':'concluída'}: versão encerrada em modo de leitura. Para corrigir qualquer módulo, reative primeiro a missão no separador Resumo.`
    : '';
}

function renderMissionOperationalState(){
  if(!selectedMission)return;
  const graph=missionRuntime.graph||{};
  const counts=graph.counts||{};
  const cycles=missionRuntime.cycles||[];
  const validation=missionRuntime.validation||{};
  const businessCase=missionRuntime.businessCase||{};
  const economics=businessCase.metrics||{};
  const economicStates=businessCase.metric_states||{};
  const semanticValue=(value,state,formatter)=>{
    if(!state||state==='unknown_not_zero'||value===null||value===undefined)return'—';
    const rendered=formatter(value);
    return state==='partial_observed_or_estimated'?`Parcial · ${rendered}`:rendered;
  };
  const economicMoney=value=>Number(value).toLocaleString('pt-PT',{style:'currency',currency:businessCase.case?.currency||'EUR',maximumFractionDigits:0});
  const forecastCostState=economicStates.forecast_cost||economicStates.costs;
  const forecastFinancialState=economicStates.forecast_financial||economicStates.financial;
  const readiness=missionRuntime.readiness||{};
  const attachments=missionRuntime.attachments||[];
  const readyDocuments=attachments.filter(item=>['ready','visual_ready','provider_ready'].includes(item.extraction_status)).length;
  const completedCycles=cycles.filter(item=>item.status==='completed').length;
  const reviewedLearning=(graph.nodes||[]).filter(item=>item.node_type==='learning'&&['accepted','verified'].includes(item.status)).length;
  const kpis=$('#mission-summary-kpis');
  if(kpis)kpis.innerHTML=`
    <div><strong>${readyDocuments}</strong><span>fontes prontas</span></div>
    <div><strong>${Number(counts.evidence||0)}</strong><span>evidências</span></div>
    <div><strong>${Number(counts.hypothesis||0)}</strong><span>hipóteses</span></div>
    <div><strong>${Number(counts.alternative||0)}</strong><span>alternativas</span></div>
    <div><strong>${cycles.length}</strong><span>decisões</span></div>
    <div><strong>${completedCycles}</strong><span>resultados</span></div>
    <div><strong>${reviewedLearning}</strong><span>aprendizagens revistas</span></div>
    <div><strong>${validation.required?`${Number(validation.readiness?.completed_checks||0)}/${Number(validation.readiness?.total_checks||0)}`:'—'}</strong><span>validação mensurável</span></div>
    <div><strong>${semanticValue(economics.forecast_cost_at_completion,forecastCostState,economicMoney)}</strong><span>custo projetado</span></div>
    <div><strong>${!forecastFinancialState||forecastFinancialState==='unknown_not_zero'||economics.forecast_roi_pct===null||economics.forecast_roi_pct===undefined?'—':`${semanticValue(economics.forecast_roi_pct,forecastFinancialState,value=>Number(value).toLocaleString('pt-PT',{maximumFractionDigits:1}))}%`}</strong><span>ROI projetado</span></div>`;
  const progress=Number(readiness.progress_percent||0);
  setText('#mission-progress-value',`${progress}%`);
  const checks=Array.isArray(readiness.checks)?readiness.checks:[];
  const readinessRoot=$('#mission-readiness');
  if(readinessRoot)readinessRoot.innerHTML=checks.length?checks.map(check=>`<div class="readiness-row ${check.passed?'passed':'pending'}"><span aria-hidden="true">${check.passed?'✓':'○'}</span><strong>${escapeHtml(check.label)}</strong><small>${Number(check.count||0)}</small></div>`).join(''):'<div class="note">Ainda não foi possível calcular a prontidão desta missão.</div>';
  const next=checks.find(check=>!check.passed);
  setText('#mission-next-action',next?next.label:'Missão pronta para conclusão e reutilização.');
  setValue('#mission-lifecycle',selectedMission.lifecycle_state||'active');
  const hash=String(selectedMission.content_hash||'');
  setText('#mission-integrity',`Revisão ${Number(selectedMission.revision||1)} · hash ${hash?hash.slice(0,16)+'…':'a sincronizar'}`);
}

async function loadMissionOperationalState(){
  if(!selectedMission)return;
  const missionId=selectedMission.id;
  const code=selectedMission.code;
  const [graphResult,validationResult,businessCaseResult,cyclesResult,readinessResult]=await Promise.allSettled([
    api(`/api/pilot/evidence-graph/missions/${encodeURIComponent(code)}`),
    api(`/api/pilot/validation/missions/${encodeURIComponent(code)}`),
    api(`/api/pilot/business-cases/missions/${encodeURIComponent(code)}`),
    api(`/api/pilot/decision-cycles/missions/${encodeURIComponent(code)}`),
    api(`/api/pilot/missions/${encodeURIComponent(code)}/completion-readiness`),
  ]);
  if(!selectedMission||selectedMission.id!==missionId)return;
  if(graphResult.status==='fulfilled')missionRuntime.graph=graphResult.value;
  if(validationResult.status==='fulfilled')missionRuntime.validation=validationResult.value;
  if(businessCaseResult.status==='fulfilled')missionRuntime.businessCase=businessCaseResult.value;
  if(cyclesResult.status==='fulfilled')missionRuntime.cycles=cyclesResult.value;
  if(readinessResult.status==='fulfilled')missionRuntime.readiness=readinessResult.value;
  renderMissionOperationalState();
}

document.addEventListener('sris:evidence-graph-updated',event=>{
  missionRuntime.graph=event.detail||missionRuntime.graph;
  void loadMissionOperationalState();
});
document.addEventListener('sris:decision-cycles-updated',event=>{
  missionRuntime.cycles=event.detail?.cycles||event.detail||missionRuntime.cycles;
  void loadMissionOperationalState();
});
document.addEventListener('sris:validation-updated',event=>{
  missionRuntime.validation=event.detail||missionRuntime.validation;
  void loadMissionOperationalState();
});
document.addEventListener('sris:alternative-matrix-updated',()=>{void loadMissionOperationalState();});
document.addEventListener('sris:business-case-updated',event=>{missionRuntime.businessCase=event.detail||missionRuntime.businessCase;void loadMissionOperationalState();});
document.addEventListener('sris:learning-published',()=>{void loadMissionOperationalState();});

document.addEventListener('click',event=>{
  const tab=event.target.closest('.mission-tabs [data-mission-tab]');
  if(tab){
    $$('.mission-tabs [data-mission-tab]').forEach(item=>item.classList.toggle('active',item===tab));
    $$('.mission-tab').forEach(panel=>panel.classList.toggle('active',panel.id===`mission-tab-${tab.dataset.missionTab}`));
    tab.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'nearest',inline:'center'});
  }
  const opener=event.target.closest('[data-open-mission-tab]');
  if(opener)activateMissionTab(opener.dataset.openMissionTab);
});

async function openMission(id){
  try{
    const mission=await api(`${miBase()}/missions/${encodeURIComponent(id)}`);
    const detailMessage=$('#detail-message');
    if(detailMessage){detailMessage.className='alert hidden';detailMessage.textContent='';}
    selectedMission=mission;
    rememberMission(mission.id);
    missionRuntime.attachments=[];
    missionRuntime.graph=null;
    missionRuntime.validation=null;
    missionRuntime.businessCase=null;
    missionRuntime.cycles=[];
    missionRuntime.readiness=null;
    missionRuntime.extraction=null;
    const extractionPanel=$('#attachment-extraction-panel');
    if(extractionPanel){extractionPanel.classList.add('hidden');extractionPanel.innerHTML='';}
    if(window.__srisMissionWorkspace){
      window.__srisMissionWorkspace.missionId=mission.id;
      window.__srisMissionWorkspace.mission=mission;
    }
    renderMissionList();
    setText('#detail-code',mission.path_codes?.join(' / ')||mission.code);
    setText('#detail-title',mission.title);
    setText('#mission-tab-code',mission.path_codes?.join(' / ')||mission.code);
    setText('#mission-tab-title',mission.title);
    renderMissionLifecycleBoundary(mission);
    setText('#detail-objective',mission.objective||'Ainda não definido');
    setText('#detail-question',mission.central_question||'Ainda não definida');
    setText('#detail-context',mission.context||'Ainda não existe contexto registado.');
    const meta=$('#detail-meta');
    if(meta)meta.innerHTML=`<span>${mission.mission_kind==='program'?'Programa':'Missão'}</span><span>${escapeHtml(priorityLabels[mission.priority]||mission.priority||'Estratégica')}</span><span>Rev. ${Number(mission.revision||1)}</span><span>${escapeHtml(lifecycleLabels[mission.lifecycle_state]||mission.lifecycle_state||'Ativa')}</span>`;
    setValue('#mission-lifecycle',mission.lifecycle_state||'active');
    const revisionRoot=$('#mission-revision-history');
    if(revisionRoot)revisionRoot.innerHTML=`<div class="timeline-row"><span class="timeline-dot"></span><div><strong>Revisão canónica ${Number(mission.revision||1)}</strong><div class="note">${mission.updated_at?new Date(mission.updated_at).toLocaleString('pt-PT'):''} · hash ${escapeHtml(String(mission.content_hash||'').slice(0,16))}…</div></div></div>`;
    const answer=$('#mission-answer');
    if(answer){answer.textContent='A análise assistida é opcional. A missão e a evidência permanecem canónicas independentemente da sua utilização.';answer.classList.add('empty');}
    showMissionMode('detail');
    revealMissionWorkspace($('#mission-detail'));
    updateCopilotContext();
    document.dispatchEvent(new CustomEvent('sris:mission-opened',{detail:{mission}}));
    setTimeout(normaliseMissionTabs,0);
    await Promise.allSettled([loadAttachments(),loadHistory(),loadMissionRevisions(),loadEpistemicCounts(mission.code),loadMissionOperationalState()]);
    renderMissionOperationalState();
  }catch(error){
    $('#mission-list')?.insertAdjacentHTML('afterbegin',`<div class="alert error">Não foi possível abrir esta missão: ${escapeHtml(error.message)}</div>`);
  }
}

async function refreshSelectedMissionRecord(){
  const currentId=selectedMission?.id;
  if(!currentId)return null;
  const latest=await api(`${miBase()}/missions/${encodeURIComponent(currentId)}`);
  if(!selectedMission||selectedMission.id!==currentId)return latest;
  selectedMission=latest;
  missions=missions.map(item=>item.id===latest.id?latest:item);
  if(window.__srisMissionWorkspace){
    window.__srisMissionWorkspace.missionId=latest.id;
    window.__srisMissionWorkspace.mission=latest;
  }
  setText('#detail-code',latest.path_codes?.join(' / ')||latest.code);
  setText('#detail-title',latest.title);
  setText('#mission-tab-code',latest.path_codes?.join(' / ')||latest.code);
  setText('#mission-tab-title',latest.title);
  renderMissionLifecycleBoundary(latest);
  setText('#detail-objective',latest.objective||'Ainda não definido');
  setText('#detail-question',latest.central_question||'Ainda não definida');
  setText('#detail-context',latest.context||'Ainda não existe contexto registado.');
  const meta=$('#detail-meta');
  if(meta)meta.innerHTML=`<span>${latest.mission_kind==='program'?'Programa':'Missão'}</span><span>${escapeHtml(priorityLabels[latest.priority]||latest.priority||'Estratégica')}</span><span>Rev. ${Number(latest.revision||1)}</span><span>${escapeHtml(lifecycleLabels[latest.lifecycle_state]||latest.lifecycle_state||'Ativa')}</span>`;
  renderMissionList();
  renderMissionOperationalState();
  return latest;
}

document.addEventListener('sris:canonical-mission-refresh',()=>{
  void refreshSelectedMissionRecord().catch(error=>console.warn('Não foi possível atualizar a revisão canónica:',error.message));
});

function epistemicPayload(){
  return {
    assumptions:($('#mission-assumptions')?.value||'').trim(),
    constraints:($('#mission-constraints')?.value||'').trim(),
    success:($('#mission-success')?.value||'').trim(),
  };
}

async function createGraphNode(missionCode,nodeType,label,body){
  if(!body)return null;
  return api(`/api/pilot/evidence-graph/missions/${encodeURIComponent(missionCode)}/nodes`,{
    method:'POST',
    body:JSON.stringify({
      node_type:nodeType,
      label,
      body,
      status:'proposed',
      provenance:{source:'mission_onboarding',human_authored:true,review:'human'},
    }),
  });
}

async function bootstrapEpistemicNodes(mission,epistemic){
  const jobs=[];
  if(epistemic.assumptions)jobs.push(createGraphNode(mission.code,'assumption','Pressupostos declarados',epistemic.assumptions));
  if(epistemic.constraints)jobs.push(createGraphNode(mission.code,'constraint','Restrições conhecidas',epistemic.constraints));
  if(epistemic.success)jobs.push(createGraphNode(mission.code,'target','Critério de sucesso',epistemic.success));
  if(!jobs.length)return{created:0,failed:0};
  const results=await Promise.allSettled(jobs);
  return {created:results.filter(result=>result.status==='fulfilled').length,failed:results.filter(result=>result.status==='rejected').length};
}

$('#mission-form')?.addEventListener('submit',async event=>{
  event.preventDefault();
  const box=$('#mission-message');
  const epistemic=epistemicPayload();
  const payload={
    title:$('#mission-title').value.trim(),
    objective:$('#mission-objective').value.trim(),
    context:$('#mission-context').value.trim(),
    central_question:$('#mission-question').value.trim(),
    parent_mission_id:$('#mission-parent-id').value||null,
    mission_kind:$('#mission-kind').value,
    domain:$('#mission-domain').value.trim()||'cross_domain',
    priority:$('#mission-priority').value,
    horizon:$('#mission-horizon').value.trim(),
    validation_profile:$('#mission-validation-profile')?.value||'none',
    stakeholders:[],
  };
  event.submitter?.classList.add('loading');
  try{
    if(editingMissionId&&selectedMission?.id===editingMissionId){
      const updated=await api(`${miBase()}/missions/${encodeURIComponent(editingMissionId)}`,{
        method:'PATCH',
        body:JSON.stringify({
          ...payload,
          expected_revision:Number(selectedMission.revision||1),
          change_note:'Enquadramento revisto no espaço operacional do Pilot V1.',
        }),
      });
      editingMissionId=null;
      $('#mission-editor')?.classList.remove('editing');
      await loadMissions();
      await openMission(updated.id);
      showMissionMessage(`Missão revista. Revisão ${updated.revision} preservada com hash canónico.`,'success');
      await loadWorkspaceSummary();
      return;
    }
    const mission=await api(`${miBase()}/missions`,{method:'POST',body:JSON.stringify(payload)});
    const graphResult=await bootstrapEpistemicNodes(mission,epistemic);
    if(box){
      box.textContent=graphResult.failed?'Missão criada. Parte da camada transversal terá de ser confirmada no Grafo de Evidência.':'Missão criada com pressupostos, restrições e critério de sucesso preservados.';
      box.className=graphResult.failed?'alert error':'alert success';
    }
    await loadMissions();
    await openMission(mission.id);
    await loadWorkspaceSummary();
  }catch(error){
    if(box){box.textContent=error.message;box.className='alert error';}
  }finally{
    event.submitter?.classList.remove('loading');
  }
});

$('#detail-analyze-btn')?.addEventListener('click',event=>{
  if(!selectedMission)return;
  event.preventDefault();
  setValue('#copilot-message','Que pressupostos, contradições, lacunas de evidência e alternativas podem alterar materialmente esta decisão?');
  setValue('#copilot-context',selectedMission.context||'');
  go('copilot');
});

$('#save-lifecycle-btn')?.addEventListener('click',async event=>{
  if(!selectedMission)return;
  const button=event.currentTarget;
  const next=$('#mission-lifecycle')?.value||'active';
  if(next===selectedMission.lifecycle_state){
    showMissionMessage('O estado da missão não foi alterado.','success');
    return;
  }
  button.classList.add('loading');
  try{
    if(next==='completed'){
      const readiness=await api(`/api/pilot/missions/${encodeURIComponent(selectedMission.code)}/completion-readiness`);
      missionRuntime.readiness=readiness;
      renderMissionOperationalState();
      if(!readiness.ready){
        const first=readiness.checks.find(check=>!check.passed);
        throw new Error(`A missão ainda não pode ser concluída. Próximo passo: ${first?.label||'complete o percurso operacional'}.`);
      }
    }
    const updated=await api(`${miBase()}/missions/${encodeURIComponent(selectedMission.id)}`,{
      method:'PATCH',
      body:JSON.stringify({
        expected_revision:Number(selectedMission.revision||1),
        lifecycle_state:next,
        change_note:`Estado alterado de ${selectedMission.lifecycle_state||'active'} para ${next} no Pilot V1.`,
      }),
    });
    await loadMissions();
    await openMission(updated.id);
    await loadWorkspaceSummary();
    showMissionMessage(`Estado atualizado para ${lifecycleLabels[next]||next}. A revisão anterior permanece preservada.`,'success');
  }catch(error){
    setValue('#mission-lifecycle',selectedMission.lifecycle_state||'active');
    showMissionMessage(error.message);
  }finally{
    button.classList.remove('loading');
  }
});

$$('[data-mission-tab]').forEach(button=>button.addEventListener('click',()=>{
  $$('[data-mission-tab]').forEach(item=>item.classList.toggle('active',item===button));
  $$('.mission-tab').forEach(tab=>tab.classList.toggle('active',tab.id===`mission-tab-${button.dataset.missionTab}`));
}));

function showMissionMessage(message,type='error'){
  const detailVisible=!$('#mission-detail')?.classList.contains('hidden');
  const box=$(detailVisible?'#detail-message':'#mission-message');
  if(!box)return;
  box.textContent=message;
  box.className=`alert ${type==='success'?'success':'error'}`;
}

function downloadBlob(blob,filename,revokeDelay=30000){
  const url=URL.createObjectURL(blob);
  const anchor=document.createElement('a');
  anchor.href=url;
  anchor.download=filename;
  anchor.style.display='none';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(()=>URL.revokeObjectURL(url),revokeDelay);
  return filename;
}

async function downloadAttachment(id,filename,button){
  if(!selectedMission)return;
  button?.classList.add('loading');
  try{
    const response=await rawApi(`${miBase()}/missions/${encodeURIComponent(selectedMission.code)}/attachments/${encodeURIComponent(id)}/download`);
    if(!response.ok){
      let data={};try{data=await response.json();}catch{}
      throw new Error(errText(data,response.status));
    }
    downloadBlob(await response.blob(),filename||'documento');
  }catch(error){
    showMissionMessage(`Não foi possível descarregar o documento: ${error.message}`);
  }finally{button?.classList.remove('loading');}
}

async function loadAttachments(){
  if(!selectedMission)return;
  try{
    const rows=await api(`${miBase()}/missions/${encodeURIComponent(selectedMission.code)}/attachments`);
    missionRuntime.attachments=rows;
    const root=$('#attachment-list');
    if(!root)return;
    root.innerHTML=rows.length?rows.map(attachment=>{
      const filename=attachment.original_filename||attachment.filename||'Documento';
      const status=attachment.extraction_status||'received';
      const ready=status==='ready';
      const failed=['error','partial'].includes(status);
      const stateLabel={ready:'Texto extraído e indexado',visual_ready:'Imagem recebida · revisão visual disponível',provider_ready:'Recebido · sem texto local',partial:'Extração parcial',error:'Erro de extração',received:'Recebido',processing:'A processar'}[status]||status;
      return `<div class="attachment-row"><span><strong>${escapeHtml(filename)}</strong><small>${escapeHtml(stateLabel)}${attachment.byte_size?` · ${Math.ceil(attachment.byte_size/1024)} KB`:''}${attachment.archive_chunk_count?` · ${Number(attachment.archive_chunk_count)} excerto(s)`:''}</small><span class="document-flow" aria-label="Estado: recebido, processado e ${failed?'com erro':'pronto'}"><i class="done">Recebido</i><i class="${status==='received'?'':'done'}">Processamento</i><i class="${ready?'done':failed?'failed':''}">${failed?'Erro':ready?'Pronto':'Revisão'}</i></span>${attachment.extraction_error?`<small class="document-error">${escapeHtml(attachment.extraction_error)}</small>`:''}</span><span class="attachment-actions"><span class="pill">${escapeHtml(attachment.extension||'ficheiro')}</span>${attachment.id?`<button type="button" data-inspect-extraction="${escapeHtml(attachment.id)}">${attachment.archive_indexed?'Ver texto extraído':'Rever fonte'}</button><button type="button" data-download-attachment="${escapeHtml(attachment.id)}" data-filename="${escapeHtml(filename)}">Descarregar</button>`:''}</span></div>`;
    }).join(''):'<div class="note">Sem documentos carregados.</div>';
    $$('[data-download-attachment]',root).forEach(button=>button.addEventListener('click',()=>downloadAttachment(button.dataset.downloadAttachment,button.dataset.filename,button)));
    $$('[data-inspect-extraction]',root).forEach(button=>button.addEventListener('click',()=>loadAttachmentExtraction(button.dataset.inspectExtraction,button)));
    document.dispatchEvent(new CustomEvent('sris:attachments-updated',{detail:{mission:selectedMission,attachments:rows}}));
    renderMissionOperationalState();
  }catch(error){
    const root=$('#attachment-list');
    if(root)root.innerHTML=`<div class="note">Os documentos desta missão não estão disponíveis neste momento: ${escapeHtml(error.message)}</div>`;
  }
}

async function loadAttachmentExtraction(attachmentId,button){
  if(!selectedMission)return;
  const panel=$('#attachment-extraction-panel');
  if(!panel)return;
  button?.classList.add('loading');
  panel.classList.remove('hidden');
  panel.innerHTML='<div class="note">A verificar a extração e a proveniência da fonte…</div>';
  try{
    const data=await api(`${miBase()}/missions/${encodeURIComponent(selectedMission.code)}/attachments/${encodeURIComponent(attachmentId)}/extraction?limit=50`);
    missionRuntime.extraction=data;
    const source=data.attachment||{};
    const filename=source.filename||'Documento';
    const fragments=data.fragments||[];
    panel.innerHTML=`<div class="document-extraction-head"><div><div class="eyebrow">EXTRAÇÃO DOCUMENTAL · SEM IA</div><h4>${escapeHtml(filename)}</h4><p>${Number(data.total_fragments||0)} excerto(s) indexado(s) · SHA-256 ${escapeHtml(String(data.source_sha256||'').slice(0,16))}…</p><p class="note"><strong>Integridade da fonte ≠ validade factual.</strong> Registar o excerto preserva a origem e o hash; o conteúdo permanece por validar.</p></div><button type="button" class="inline-link" id="close-extraction">Fechar</button></div><div class="document-fragments">${fragments.length?fragments.map(fragment=>`<article class="document-fragment"><div class="document-fragment-head"><div><strong>Excerto ${Number(fragment.ordinal||0)}</strong><small>${escapeHtml(fragment.location||`caracteres ${fragment.char_start}–${fragment.char_end}`)} · hash ${escapeHtml(String(fragment.content_sha256||'').slice(0,12))}…</small></div><button class="btn btn-secondary compact" type="button" data-promote-document-evidence="${escapeHtml(fragment.id)}">Registar fonte no grafo</button></div><pre>${escapeHtml(fragment.excerpt||'')}</pre></article>`).join(''):`<form id="visual-evidence-form" class="visual-evidence-form"><div><strong>Fonte sem texto extraível</strong><p>A fonte original está preservada. Abra-a, descreva apenas o que observou diretamente e registe essa observação com proveniência visual.</p></div><div class="field"><label for="visual-evidence-body">Observação humana sobre a fonte *</label><textarea id="visual-evidence-body" required maxlength="10000" placeholder="Descreva o elemento observável, sem o converter automaticamente numa conclusão."></textarea></div><button class="btn btn-primary" type="submit">Registar fonte visual no grafo</button><div class="note" id="visual-evidence-status"></div></form>`}</div>`;
    $('#close-extraction',panel)?.addEventListener('click',()=>{panel.classList.add('hidden');panel.innerHTML='';});
    $$('[data-promote-document-evidence]',panel).forEach(promote=>promote.addEventListener('click',()=>promoteDocumentEvidence(promote.dataset.promoteDocumentEvidence,promote)));
    $('#visual-evidence-form',panel)?.addEventListener('submit',event=>promoteVisualEvidence(source.id,event));
    panel.scrollIntoView({behavior:'smooth',block:'start'});
  }catch(error){
    panel.innerHTML=`<div class="alert error">Não foi possível abrir o texto extraído: ${escapeHtml(error.message)}</div>`;
  }finally{button?.classList.remove('loading');}
}

async function promoteVisualEvidence(attachmentId,event){
  event.preventDefault();
  if(!selectedMission||!attachmentId)return;
  const form=event.currentTarget;
  const body=$('#visual-evidence-body',form)?.value.trim()||'';
  const status=$('#visual-evidence-status',form);
  if(!body){if(status)status.textContent='Descreva primeiro a observação feita sobre a fonte.';return;}
  const button=$('button[type="submit"]',form);
  button?.classList.add('loading');
  if(status)status.textContent='A preservar a fonte, a autoria humana e o hash…';
  try{
    await api(`/api/pilot/evidence-graph/missions/${encodeURIComponent(selectedMission.code)}/document-evidence`,{method:'POST',body:JSON.stringify({attachment_id:attachmentId,body})});
    if(status)status.textContent='Fonte visual registada com proveniência; validade factual por avaliar.';
    button.disabled=true;
    await Promise.allSettled([loadMissionOperationalState(),loadWorkspaceSummary()]);
    showMissionMessage('A fonte visual foi preservada no grafo. O conteúdo permanece proposto até revisão factual humana.','success');
  }catch(error){if(status)status.textContent=error.message;}
  finally{button?.classList.remove('loading');}
}

async function promoteDocumentEvidence(chunkId,button){
  if(!selectedMission||!chunkId)return;
  button?.classList.add('loading');
  try{
    await api(`/api/pilot/evidence-graph/missions/${encodeURIComponent(selectedMission.code)}/document-evidence`,{method:'POST',body:JSON.stringify({chunk_id:chunkId})});
    button.textContent='Fonte registada ✓';
    button.disabled=true;
    await Promise.allSettled([loadMissionOperationalState(),loadWorkspaceSummary()]);
    showMissionMessage('O excerto foi preservado com fonte, posição e hashes. A validade factual permanece por avaliar.','success');
  }catch(error){
    showMissionMessage(`Não foi possível registar a evidência: ${error.message}`);
  }finally{button?.classList.remove('loading');}
}

async function uploadFiles(fileList,button=$('#upload-file-btn')){
  if(!selectedMission){showMissionMessage('Abra primeiro uma missão.');return;}
  const files=[...(fileList||[])];
  if(!files.length){showMissionMessage('Selecione primeiro pelo menos um documento.');return;}
  const progress=$('#upload-progress');
  const failures=[];
  button?.classList.add('loading');
  button?.setAttribute('aria-busy','true');
  for(let index=0;index<files.length;index++){
    const file=files[index];
    if(progress)progress.textContent=`Receção ${index+1} de ${files.length}: ${file.name} · a validar e processar…`;
    const formData=new FormData();
    formData.append('file',file);
    try{
      await api(`${miBase()}/missions/${encodeURIComponent(selectedMission.code)}/attachments`,{method:'POST',body:formData,timeoutMs:120000});
    }catch(error){failures.push(`${file.name}: ${error.message}`);}
  }
  $('#mission-file').value='';
  button?.classList.remove('loading');
  button?.removeAttribute('aria-busy');
  if(progress)progress.textContent=failures.length?`${files.length-failures.length} de ${files.length} ficheiro(s) carregado(s).`:`${files.length} ficheiro(s) carregado(s) com sucesso.`;
  if(failures.length)showMissionMessage(`Alguns documentos não foram carregados: ${failures.join(' · ')}`);
  else showMissionMessage(`${files.length} documento(s) carregado(s) e associado(s) à missão.`,'success');
  await loadAttachments();
  await Promise.allSettled([loadMissionOperationalState(),loadWorkspaceSummary()]);
}

$('#upload-file-btn')?.addEventListener('click',event=>uploadFiles($('#mission-file')?.files,event.currentTarget));
$('#mission-file')?.addEventListener('change',event=>{
  const count=event.currentTarget.files?.length||0;
  const progress=$('#upload-progress');
  if(progress)progress.textContent=count?`${count} ficheiro(s) selecionado(s).`:'';
});

const dropZone=$('#upload-drop-zone');
['dragenter','dragover'].forEach(name=>dropZone?.addEventListener(name,event=>{event.preventDefault();dropZone.classList.add('dragging');}));
['dragleave','drop'].forEach(name=>dropZone?.addEventListener(name,event=>{event.preventDefault();dropZone.classList.remove('dragging');}));
dropZone?.addEventListener('drop',event=>uploadFiles(event.dataTransfer?.files));

function slug(value){
  return String(value||'relatorio').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'').slice(0,90)||'relatorio';
}

function stableJson(value){
  if(Array.isArray(value))return`[${value.map(stableJson).join(',')}]`;
  if(value&&typeof value==='object')return`{${Object.keys(value).sort().map(key=>`${JSON.stringify(key)}:${stableJson(value[key])}`).join(',')}}`;
  return JSON.stringify(value);
}

async function sha256(value){
  const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map(byte=>byte.toString(16).padStart(2,'0')).join('');
}

async function reportSnapshot(){
  if(!selectedMission)return null;
  // Reports must be built from the current canonical row, not from the copy
  // that happened to be selected when the screen was first opened.
  const latest=await api(`${miBase()}/missions/${encodeURIComponent(selectedMission.id)}`);
  if(selectedMission?.id===latest.id){
    selectedMission=latest;
    missions=missions.map(item=>item.id===latest.id?latest:item);
  }
  const mission={...latest};
  const code=mission.code;
  const [attachmentsResult,graphResult,cyclesResult,dialoguesResult,validationResult,businessCaseResult,readinessResult,memoryResult,revisionsResult,auditResult]=await Promise.allSettled([
    api(`${miBase()}/missions/${encodeURIComponent(code)}/attachments`),
    api(`/api/pilot/evidence-graph/missions/${encodeURIComponent(code)}`),
    api(`/api/pilot/decision-cycles/missions/${encodeURIComponent(code)}`),
    api(`${miBase()}/dialogues?mission_code=${encodeURIComponent(code)}`),
    api(`/api/pilot/validation/missions/${encodeURIComponent(code)}`),
    api(`/api/pilot/business-cases/missions/${encodeURIComponent(code)}`),
    api(`/api/pilot/missions/${encodeURIComponent(code)}/completion-readiness`),
    api(`${miBase()}/memory/items?limit=500`),
    api(`${miBase()}/missions/${encodeURIComponent(mission.id)}/revisions`),
    api(`/api/pilot/audit/missions/${encodeURIComponent(code)}?limit=500`),
  ]);
  const value=(result,fallback)=>result.status==='fulfilled'?result.value:fallback;
  const memory=value(memoryResult,[]);
  const archive={
    schema:'sris.pilot.mission-export.v3',
    generated_at:new Date().toISOString(),
    human_review_required:true,
    mission,
    attachments:value(attachmentsResult,[]).map(item=>({
      id:item.id,
      filename:item.original_filename||item.filename,
      media_type:item.media_type,
      byte_size:item.byte_size,
      sha256:item.sha256,
      extraction_status:item.extraction_status,
      extraction_error:item.extraction_error||'',
      created_at:item.created_at,
    })),
    evidence_graph:value(graphResult,{nodes:[],edges:[],counts:{}}),
    decision_cycles:value(cyclesResult,[]),
    dialogue_sessions:value(dialoguesResult,[]),
    validation_protocol:value(validationResult,{required:false,profile:'none',protocol:null,baseline:null,result:null,analysis:{comparable:false},readiness:{checks:[]}}),
    live_business_case:value(businessCaseResult,{case:{id:null},items:[],metrics:{scenarios:{}},quality:{},readiness:{checks:[]},warnings:[]}),
    mission_memory:(Array.isArray(memory)?memory:memory.items||[]).filter(item=>item.mission_id===mission.id),
    mission_revisions:value(revisionsResult,[]),
    mission_audit:value(auditResult,{events:[],count:0,scope_complete:false}),
    completion_readiness:value(readinessResult,{ready:false,checks:[]}),
  };
  archive.integrity={
    algorithm:'SHA-256',
    scope:'canonical-json-without-integrity',
    digest:await sha256(stableJson(archive)),
    mission_content_hash:mission.content_hash||null,
    mission_revision:Number(mission.revision||1),
  };
  return archive;
}

function reportNumber(value,maximumFractionDigits=4){
  if(value===null||value===undefined||value==='')return'—';
  const number=Number(value);
  return Number.isFinite(number)?number.toLocaleString('pt-PT',{maximumFractionDigits}):'—';
}

function validationReportHtml(validation,policy={}){
  if(!validation?.required){
    const applicability=policy.measurement_applicability||'optional';
    if(applicability==='required')return'<p class="muted">A medição é obrigatória nesta missão, mas o protocolo quantitativo ainda não foi iniciado.</p>';
    if(applicability==='not_applicable')return'<p class="muted">A medição foi marcada como não aplicável numa revisão humana da política da missão.</p>';
    return'<p class="muted">A medição é opcional nesta missão e o protocolo quantitativo ainda não foi iniciado.</p>';
  }
  const protocol=validation.protocol||{};
  const baseline=validation.baseline||{};
  const result=validation.result||{};
  const analysis=validation.analysis||{};
  const targetLabels={met:'Meta atingida',missed:'Meta não atingida',indeterminate:'Não comparável',not_configured:'Meta não configurada'};
  const measurement=(label,row)=>`<li><strong>${escapeHtml(label)}</strong><div>${escapeHtml(row.period_start||'—')} → ${escapeHtml(row.period_end||'—')} · bruto ${reportNumber(row.numerator_value)}${row.denominator_value!==null&&row.denominator_value!==undefined?` / atividade ${reportNumber(row.denominator_value)}`:''} · normalizado ${reportNumber(row.normalized_value)} ${escapeHtml(analysis.normalized_unit||'')}</div><small>Evidência ${escapeHtml(row.evidence_node_id||'não associada')} · qualidade ${escapeHtml(reportLabel('data_quality',row.data_quality))}</small></li>`;
  return `<p><strong>${escapeHtml(validation.profile_definition?.label||validation.profile||'Validação mensurável')}</strong></p><dl class="measure"><div><dt>Unidade observada</dt><dd>${escapeHtml(protocol.subject||'—')}</dd></div><div><dt>Indicador</dt><dd>${escapeHtml(protocol.indicator_name||'—')} · ${escapeHtml(protocol.indicator_unit||'—')}</dd></div><div><dt>Normalização</dt><dd>${escapeHtml(protocol.denominator_name||'Sem denominador')} · ${escapeHtml(protocol.denominator_unit||'—')}</dd></div><div><dt>Intervenção</dt><dd>${escapeHtml(protocol.intervention_description||'—')}</dd></div><div><dt>Meta</dt><dd>${reportNumber(protocol.target_value)} · ${escapeHtml(protocol.target_description||'—')}</dd></div></dl><ol>${measurement('Baseline',baseline)}${measurement('Resultado',result)}</ol><p><strong>Comparação determinística:</strong> ${analysis.comparable?`${reportNumber(analysis.absolute_change)} ${escapeHtml(analysis.normalized_unit||'')} · ${reportNumber(analysis.percent_change,2)}% · ${escapeHtml(targetLabels[analysis.target_status]||analysis.target_status||'—')}`:'Os períodos ainda não são comparáveis.'}</p><p><strong>Revisão humana de atribuição:</strong> ${escapeHtml(protocol.attribution_confidence?reportLabel('confidence',protocol.attribution_confidence):'Pendente')}<br>${escapeHtml(protocol.review_rationale||'Sem racional revisto.')}<br><strong>Limitações:</strong> ${escapeHtml(protocol.limitations||'Ainda não revistas.')}</p><small>Revisão ${Number(protocol.revision||1)} · SHA-256 ${escapeHtml(protocol.content_hash||'a sincronizar')}</small>`;
}

function reportMoney(value,currency='EUR'){
  if(value===null||value===undefined||value==='')return'—';
  const number=Number(value);
  return Number.isFinite(number)?number.toLocaleString('pt-PT',{style:'currency',currency,maximumFractionDigits:2}):'—';
}

const REPORT_LABELS={
  lifecycle:{active:'Ativa',paused:'Pausada',completed:'Concluída',archived:'Arquivada'},
  node_type:{observation:'Observação',evidence:'Evidência',assumption:'Pressuposto',constraint:'Restrição',gap:'Lacuna',hypothesis:'Hipótese',target:'Critério ou meta',alternative:'Alternativa',decision:'Decisão',action:'Ação',outcome:'Resultado observado',learning:'Aprendizagem',claim:'Afirmação'},
  node_status:{active:'Ativo',proposed:'Proposto',verified:'Verificado',accepted:'Aceite',rejected:'Rejeitado',superseded:'Substituído'},
  source_kind:{human_entry:'Registo humano',document_chunk:'Excerto documental',visual_document:'Documento visual',decision_cycle:'Ciclo de decisão',mission_onboarding:'Configuração da missão'},
  cycle_status:{proposed:'Proposta',committed:'Decidida',in_progress:'Em execução',completed:'Concluída',abandoned:'Abandonada'},
  item_kind:{monetary_cost:'Custo monetário',monetary_benefit:'Benefício monetário',non_monetary_benefit:'Benefício não monetizado',human_resource:'Recurso humano',material_resource:'Material ou consumível',equipment_resource:'Equipamento ou capacidade',financial_resource:'Financiamento disponível'},
  phase:{planning:'Planeamento',execution:'Execução',post_mission:'Após a missão'},
  recurrence:{one_off:'Única',monthly:'Mensal',quarterly:'Trimestral',annual:'Anual'},
  operational_status:{planned:'Planeado',committed:'Comprometido',active:'Em curso',completed:'Concluído',blocked:'Bloqueado'},
  confidence:{low:'Baixa',moderate:'Moderada',high:'Alta',not_evaluable:'Não avaliável'},
  data_quality:{low:'Baixa',moderate:'Moderada',high:'Alta',verified:'Verificada',demonstrative:'Demonstrativa'},
  target_status:{met:'Meta atingida',missed:'Meta não atingida',indeterminate:'Não comparável',not_configured:'Meta não configurada'},
  extraction_status:{pending:'Pendente',processing:'Em processamento',ready:'Preparado',visual_ready:'Preparado visualmente',provider_ready:'Preparado pelo fornecedor',error:'Erro'},
};

const AUDIT_ACTION_LABELS={
  'mission_intelligence.mission_created':'Missão criada',
  'mission_intelligence.mission_revised':'Missão revista',
  'mission_intelligence.attachment_uploaded':'Documento recebido',
  'mission_intelligence.attachment_deleted':'Documento retirado',
  'mission_intelligence.dialogue_started':'Sessão assistida iniciada',
  'mission_intelligence.dialogue_turn_executed':'Turno assistido executado',
  'mission_intelligence.evidence_asset_registered':'Ativo de evidência registado',
  'mission_intelligence.learning_created':'Aprendizagem institucional criada',
  'mission_intelligence.memory_synchronized':'Memória sincronizada',
  'mission_intelligence.memory_item_superseded':'Item de memória substituído',
  'mission_intelligence.learning_inheritance_reviewed':'Aprendizagem contextual revista',
  'mission_intelligence.proposal_reviewed':'Proposta da IA revista por uma pessoa',
  'pilot.alternative.created':'Alternativa criada',
  'pilot.alternative.duplicate_retired':'Alternativa duplicada substituída',
  'pilot.alternative_matrix.revision_created':'Revisão da matriz criada',
  'pilot.alternative_matrix.reviewed':'Matriz revista por uma pessoa',
  'pilot.business_case.item_created':'Linha económica criada',
  'pilot.business_case.item_updated':'Linha económica atualizada',
  'pilot.business_case.item_retired':'Linha económica substituída',
  'pilot.business_case.case_created':'Fundação económica criada',
  'pilot.business_case.case_updated':'Fundação económica atualizada',
  'pilot.business_case.reviewed':'Business case revisto por uma pessoa',
  'pilot.decision_cycle.created':'Ciclo de decisão criado',
  'pilot.decision_cycle.updated':'Ciclo de decisão atualizado',
  'pilot.decision_cycle.lineage_materialized':'Cadeia operacional materializada',
  'pilot.decision_cycle.reopened':'Ciclo reaberto para correção',
  'pilot.evidence_graph.node_created':'Objeto governado criado',
  'pilot.evidence_graph.node_updated':'Objeto governado atualizado',
  'pilot.evidence_graph.document_evidence_promoted':'Fonte documental promovida a evidência proposta',
  'pilot.evidence_graph.edge_created':'Relação do grafo criada',
  'pilot.evidence_graph.edge_deleted':'Relação do grafo retirada',
  'pilot.evidence_graph.edge_reversed':'Relação do grafo invertida',
  'pilot.evidence_graph.synchronized':'Candidatos da IA sincronizados no grafo',
  'pilot.learning.published':'Aprendizagem publicada com linhagem',
  'pilot.learning.applicability_reviewed':'Aplicabilidade da aprendizagem revista',
  'pilot.mission_state.policy_reviewed':'Aplicabilidade dos módulos revista',
  'pilot.validation.protocol_seeded':'Protocolo de validação proposto',
  'pilot.validation.protocol_created':'Protocolo de validação criado',
  'pilot.validation.protocol_updated':'Protocolo de validação atualizado',
  'pilot.validation.baseline_recorded':'Baseline registada',
  'pilot.validation.result_recorded':'Resultado medido registado',
  'pilot.validation.attribution_reviewed':'Atribuição revista por uma pessoa',
};

function reportLabel(group,value){
  if(value===null||value===undefined||value==='')return'—';
  return REPORT_LABELS[group]?.[value]||String(value).replaceAll('_',' ');
}

function businessDefinitionLabel(businessCase,group,value){
  const defined=businessCase?.definitions?.[group]?.[value];
  if(typeof defined==='string')return defined;
  if(defined?.label)return defined.label;
  const fallbacks={item_kinds:'item_kind',phases:'phase'};
  return reportLabel(fallbacks[group]||group,value);
}

function businessCaseReportHtml(businessCase,policy={}){
  if(!businessCase?.case?.id){
    const applicability=policy.economics_applicability||'required';
    if(applicability==='required')return'<p class="muted">Economia e recursos são obrigatórios nesta missão, mas o business case vivo ainda não foi iniciado.</p>';
    if(applicability==='not_applicable')return'<p class="muted">Economia e recursos foram marcados como não aplicáveis numa revisão humana da política da missão.</p>';
    return'<p class="muted">Economia e recursos são opcionais nesta missão e o business case vivo ainda não foi iniciado.</p>';
  }
  const item=businessCase.case||{};
  const metrics=businessCase.metrics||{};
  const currency=item.currency||'EUR';
  const metricsKnown=businessCase.metrics_state==='observed_or_estimated';
  const metricStates=businessCase.metric_states||{};
  const stateOf=(key,fallback)=>metricStates[key]||metricStates[fallback]||'unknown_not_zero';
  const stateAvailable=state=>state!=='unknown_not_zero';
  const stateValue=(value,state,formatter)=>{
    if(!stateAvailable(state)||value===null||value===undefined)return'—';
    const rendered=formatter(value);
    return state==='partial_observed_or_estimated'?`Parcial · ${rendered}`:rendered;
  };
  const metricMoney=(value,key='forecast_financial',fallback='financial')=>stateValue(value,stateOf(key,fallback),amount=>reportMoney(amount,currency));
  const metricNumber=(value,digits=2,key='any_lines',fallback)=>stateValue(value,stateOf(key,fallback),amount=>reportNumber(amount,digits));
  const hasPartial=Object.values(metricStates).includes('partial_observed_or_estimated');
  const scenarioLabels={conservative:'Conservador',base:'Base',favorable:'Favorável'};
  const scenarios=Object.entries(metrics.scenarios||{}).map(([key,row])=>{
    const financialState=stateOf(`scenario_${key}_financial`,'financial');
    const ratio=(value,digits,suffix)=>value==null?'—':`${stateValue(value,financialState,amount=>reportNumber(amount,digits))}${suffix}`;
    return`<tr><td>${escapeHtml(scenarioLabels[key]||key)}</td><td>${metricMoney(row.total_cost,`scenario_${key}_costs`,'costs')}</td><td>${metricMoney(row.gross_benefit,`scenario_${key}_benefits`,'benefits')}</td><td>${metricMoney(row.net_benefit,`scenario_${key}_financial`,'financial')}</td><td>${stateAvailable(financialState)?ratio(row.roi_pct,2,'%'):'—'}</td><td>${stateAvailable(financialState)?ratio(row.payback_months,0,' meses'):'—'}</td><td>${metricMoney(row.npv,`scenario_${key}_financial`,'financial')}</td></tr>`;
  }).join('');
  const lines=(businessCase.items||[]).length?`<ol>${businessCase.items.map(row=>{
    const scope=row.alternative_node_id?`Alternativa · ${row.alternative_label||'indisponível'}`:'Missão';
    const basis=row.amount_basis==='per_unit'?`valor unitário × ${reportNumber(row.planned_quantity)} ${row.unit||'unidades'}`:'valor total por ocorrência';
    const blocked=row.operational_status==='blocked'?` · BLOQUEADO: ${row.blocker||'sem motivo descrito'}`:'';
    return`<li><strong>${escapeHtml(row.label)} · ${escapeHtml(businessDefinitionLabel(businessCase,'item_kinds',row.kind))}</strong><div>${escapeHtml(scope)} · ${escapeHtml(businessDefinitionLabel(businessCase,'phases',row.phase))} · ${escapeHtml(reportLabel('recurrence',row.recurrence))} · ${escapeHtml(basis)} · base ${reportMoney(row.base_amount,currency)} · comprometido ${reportMoney(row.committed_amount,currency)} · realizado ${reportMoney(row.realized_amount,currency)} · projeção ${reportMoney(row.forecast_amount,currency)}</div><small>Quantidade ${reportNumber(row.planned_quantity)} → ${reportNumber(row.actual_quantity)} ${escapeHtml(row.unit||'')} · estado ${escapeHtml(reportLabel('operational_status',row.operational_status||'planned'))}${escapeHtml(blocked)} · confiança ${escapeHtml(reportLabel('confidence',row.confidence))} · origem ${escapeHtml(row.source_label||row.evidence_label||'não declarada')}</small></li>`;
  }).join('')}</ol>`:'<p class="muted">Sem linhas económicas ou de recursos.</p>';
  const alternativeRows=(businessCase.alternative_comparison?.profiles||[]).map(row=>{
    const states=row.metric_states||{};
    const profileState=(key,fallback=key)=>states[key]||states[fallback]||'unknown_not_zero';
    const costsState=profileState('scenario_base_costs','costs');
    const benefitsState=profileState('scenario_base_benefits','benefits');
    const financialState=profileState('scenario_base_financial','financial');
    const profileValue=(value,valueState,formatter)=>stateValue(value,valueState,formatter);
    const plannedHoursState=profileState('planned_human_hours');
    const resourceText=[
      row.resources?.human_roles?`${row.resources.human_roles} ${row.resources.human_roles===1?'função':'funções'} · ${profileValue(row.resources?.planned_human_hours,plannedHoursState,value=>reportNumber(value,1))} h previstas`:null,
      row.resources?.material_lines?`${Number(row.resources.material_lines)} materiais`:null,
      row.resources?.equipment_lines?`${Number(row.resources.equipment_lines)} equipamentos`:null,
      row.resources?.funding_lines?`${Number(row.resources.funding_lines)} fontes de financiamento`:null,
    ].filter(Boolean).join(' · ')||'Recurso identificado';
    const resources=profileValue(resourceText,profileState('resources'),value=>escapeHtml(value));
    return`<tr><td>${escapeHtml(row.alternative_label)}</td><td>${profileValue(row.total_cost,costsState,value=>reportMoney(value,currency))}</td><td>${resources}</td><td>${profileValue(row.probable_gross_benefit,benefitsState,value=>reportMoney(value,currency))}</td><td>${profileValue(row.probable_net_benefit,financialState,value=>reportMoney(value,currency))}</td><td>${!stateAvailable(financialState)||row.roi_pct==null?'—':`${profileValue(row.roi_pct,financialState,value=>reportNumber(value,2))}%`}</td><td>${!stateAvailable(financialState)||row.payback_months==null?'—':`${profileValue(row.payback_months,financialState,value=>reportNumber(value,0))} meses`}</td></tr>`;
  }).join('');
  const warnings=(businessCase.warnings||[]).length?`<ul>${businessCase.warnings.map(row=>`<li>${escapeHtml(row.message)}</li>`).join('')}</ul>`:'<p class="muted">Sem alertas materiais registados.</p>';
  const qualityKnown=Number(businessCase.quality?.monetary_line_count||0)>0;
  const qualityLabel=qualityKnown?`${reportNumber(businessCase.quality?.overall_score,1)}%`:'— · ainda não avaliável';
  const valuesStatus=!metricsKnown
    ?'Por determinar — ausência de linhas não significa zero'
    :hasPartial
      ?'Existem valores parciais; “—” identifica o que continua por determinar'
      :'Existem estimativas ou observações; cada indicador sem fonte permanece “—”';
  const forecastFinancialState=stateOf('forecast_financial','financial');
  const roi=!stateAvailable(forecastFinancialState)||metrics.forecast_roi_pct==null
    ?'—'
    :`${stateValue(metrics.forecast_roi_pct,forecastFinancialState,value=>reportNumber(value,2))}%`;
  const payback=!stateAvailable(forecastFinancialState)||metrics.forecast_payback_months==null
    ?'—'
    :`${stateValue(metrics.forecast_payback_months,forecastFinancialState,value=>reportNumber(value,0))} meses`;
  return [
    `<p><strong>${escapeHtml(businessCase.definitions?.case_kinds?.[item.case_kind]?.label||item.case_kind)}</strong> · horizonte ${Number(item.horizon_months||0)} meses · taxa de desconto ${reportNumber(item.discount_rate_pct,2)}%</p>`,
    `<p><strong>Estado dos valores:</strong> ${valuesStatus}</p>`,
    `<p><strong>Conclusão automática auditável:</strong> ${escapeHtml(businessCase.executive_conclusion||'Ainda sem dados suficientes.')}</p>`,
    '<dl class="measure">',
    `<div><dt>Orçamento / custo projetado</dt><dd>${metricMoney(metrics.budget_base,'budget_base','costs')} · ${metricMoney(metrics.forecast_cost_at_completion,'forecast_cost','costs')}</dd></div>`,
    `<div><dt>Custo comprometido / realizado</dt><dd>${metricMoney(metrics.committed_cost,'committed_cost','costs')} · ${metricMoney(metrics.realized_cost,'realized_cost','costs')}</dd></div>`,
    `<div><dt>Benefício esperado</dt><dd>${metricMoney(metrics.expected_gross_benefit,'expected_benefit','benefits')}</dd></div>`,
    `<div><dt>Benefício realizado / com evidência revista</dt><dd>${metricMoney(metrics.realized_benefit,'realized_benefit','benefits')} · ${metricMoney(metrics.reviewed_evidence_realized_benefit,'reviewed_evidence_realized_benefit','benefits')}</dd></div>`,
    `<div><dt>Benefício líquido projetado</dt><dd>${metricMoney(metrics.forecast_net_benefit,'forecast_financial','financial')}</dd></div>`,
    `<div><dt>ROI / payback</dt><dd>${roi} · ${payback}</dd></div>`,
    `<div><dt>Esforço / bloqueios</dt><dd>${metricNumber(metrics.actual_human_hours,2,'actual_human_hours','human_hours')} h realizadas · ${metricNumber(metrics.planned_human_hours,2,'planned_human_hours','human_hours')} h previstas · ${metricNumber(metrics.blocked_resource_count,0,'resources')} recursos bloqueados</dd></div>`,
    `<div><dt>Encargo anual posterior</dt><dd>${metricMoney(metrics.annual_post_mission_burden,'post_mission_costs')}</dd></div>`,
    `<div><dt>Financiamento / lacuna</dt><dd>${metricMoney(metrics.funding_available,'funding')} · ${metricMoney(metrics.funding_gap,'funding_gap')}</dd></div>`,
    '</dl>',
    `<h3>Cenários</h3><div style="overflow-x:auto"><table><thead><tr><th>Cenário</th><th>Custo</th><th>Benefício</th><th>Líquido</th><th>ROI</th><th>Payback</th><th>VAL</th></tr></thead><tbody>${scenarios}</tbody></table></div>`,
    alternativeRows?`<h3>Alternativas · economia e recursos</h3><div style="overflow-x:auto"><table><thead><tr><th>Alternativa</th><th>Custo</th><th>Recursos</th><th>Benefício provável</th><th>Líquido</th><th>ROI</th><th>Payback</th></tr></thead><tbody>${alternativeRows}</tbody></table></div>`:'',
    `<h3>Custos, benefícios e recursos</h3>${lines}<h3>Alertas e limites</h3>${warnings}`,
    `<small>Revisão ${Number(item.revision||0)} · estado ${escapeHtml(item.status||'')} · qualidade ${qualityLabel} · SHA-256 ${escapeHtml(item.content_hash||'a sincronizar')}</small>`,
  ].join('');
}

function completeReportHtml(snapshot){
  const mission=snapshot.mission||{};
  const governedPolicy=snapshot.completion_readiness?.governed_state?.policy||{};
  const graph=snapshot.evidence_graph||{};
  const nodes=graph.nodes||[];
  const cycles=snapshot.decision_cycles||[];
  const section=(heading,content)=>`<section><h2>${escapeHtml(heading)}</h2>${content}</section>`;
  const text=value=>`<div class="pre">${escapeHtml(value||'Não registado')}</div>`;
  const list=(rows,renderer,empty='Sem registos.')=>rows.length?`<ol>${rows.map(renderer).join('')}</ol>`:`<p class="muted">${escapeHtml(empty)}</p>`;
  const evidence=list(nodes,node=>`<li><strong>${escapeHtml(reportLabel('node_type',node.node_type))} · ${escapeHtml(node.label)}</strong><div>${escapeHtml(node.body||'')}</div><small>${escapeHtml(reportLabel('node_status',node.status))} · ${escapeHtml(reportLabel('source_kind',node.source_kind))} ${node.source_sha256?`· hash ${escapeHtml(String(node.source_sha256).slice(0,16))}…`:''}</small></li>`,'Sem objetos no Evidence Graph.');
  const decisions=list(cycles,cycle=>`<li><strong>${escapeHtml(cycle.decision)}</strong><div>Ação: ${escapeHtml(cycle.action||'não definida')}<br>Responsável/prazo: ${escapeHtml(cycle.owner||'—')} · ${escapeHtml(cycle.due_date||'—')}<br>Esperado: ${escapeHtml(cycle.expected_outcome||'—')}<br>Observado: ${escapeHtml(cycle.actual_outcome||'—')}<br>Aprendizagem: ${escapeHtml(cycle.learning||'—')}</div><small>Estado: ${escapeHtml(reportLabel('cycle_status',cycle.status))}</small></li>`,'Sem ciclos de decisão.');
  const documents=list(snapshot.attachments||[],item=>`<li><strong>${escapeHtml(item.filename||'Documento')}</strong><div>${escapeHtml(item.extraction_status||'registado')} · ${Number(item.byte_size||0)} bytes</div><small>SHA-256 ${escapeHtml(item.sha256||'não disponível')}</small></li>`,'Sem documentos.');
  const checks=list(snapshot.completion_readiness?.checks||[],check=>`<li><strong>${check.passed?'✓':'○'} ${escapeHtml(check.label)}</strong><small>${Number(check.count||0)} registo(s)</small></li>`,'Prontidão não calculada.');
  const audit=list(snapshot.mission_audit?.events||[],event=>`<li><strong>${escapeHtml(AUDIT_ACTION_LABELS[event.action]||String(event.action||'Alteração auditada').replaceAll('_',' ').replaceAll('.',' · '))}</strong><div>${escapeHtml(event.payload?.rationale||'')}</div><small>${escapeHtml(event.actor||'Sistema')}${event.created_at?` · ${escapeHtml(new Date(event.created_at).toLocaleString('pt-PT'))}`:''}</small></li>`,'Sem eventos auditáveis nesta janela.');
  const auditScope=snapshot.mission_audit?.scope_complete===false?'<p class="muted">A cronologia contém a janela mais recente; podem existir eventos anteriores no arquivo do workspace.</p>':'';
  const generated=new Date(snapshot.generated_at).toLocaleString('pt-PT');
  return `<!doctype html><html lang="pt-PT"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escapeHtml(mission.code)} — ${escapeHtml(mission.title)}</title><style>body{margin:0;background:#f6f3ea;color:#10231d;font:15px/1.65 Arial,sans-serif}main{max-width:940px;margin:auto;padding:54px}header{padding-bottom:28px;border-bottom:2px solid #c99a43}.brand{font-weight:800;letter-spacing:.13em;color:#103d32}h1,h2{font-family:Georgia,serif;font-weight:500}h1{font-size:42px;line-height:1.05;margin:20px 0 8px}h2{font-size:24px;margin:28px 0 9px}section{padding-bottom:18px;border-bottom:1px solid #d8dfda}.pre{white-space:pre-wrap}li{margin:0 0 14px}li small,.muted,.meta,.stamp{color:#687971}.measure{display:grid;gap:1px;border:1px solid #d8dfda;background:#d8dfda}.measure div{display:grid;grid-template-columns:180px 1fr;gap:16px;background:#fff;padding:9px}.measure dt{color:#687971}.measure dd{margin:0;font-weight:700}table{width:100%;border-collapse:collapse}th,td{padding:7px;border:1px solid #d8dfda;text-align:right}th:first-child,td:first-child{text-align:left}.stamp{margin-top:34px;font-size:12px;overflow-wrap:anywhere}@media(max-width:680px){main{padding:24px 16px}.measure div{grid-template-columns:1fr;gap:3px}h1{font-size:32px}}@media print{body{background:#fff}main{padding:16mm}}</style></head><body><main><header><div class="brand">SRIS · MISSION INTELLIGENCE</div><h1>${escapeHtml(mission.title)}</h1><div class="meta">${escapeHtml(mission.code)} · revisão ${Number(mission.revision||1)} · ${escapeHtml(reportLabel('lifecycle',mission.lifecycle_state||'active'))}</div></header>${section('Objetivo',text(mission.objective))}${section('Pergunta central',text(mission.central_question))}${section('Contexto',text(mission.context))}${section('Documentos e integridade',documents)}${section('Evidência, hipóteses e alternativas',evidence)}${section('Baseline → intervenção → resultado',validationReportHtml(snapshot.validation_protocol,governedPolicy))}${section('Business case vivo · economia e recursos',businessCaseReportHtml(snapshot.live_business_case,governedPolicy))}${section('Decisão → ação → resultado → aprendizagem',decisions)}${section('Prontidão para conclusão',checks)}${section('Memória da missão',list(snapshot.mission_memory||[],item=>`<li><strong>${escapeHtml(item.title||reportLabel('node_type',item.item_type)||'Memória')}</strong><div>${escapeHtml(item.summary||'')}</div><small>${escapeHtml(reportLabel('node_status',item.state))}</small></li>`,'Sem itens de memória canónica.'))}${section('Revisões preservadas',list(snapshot.mission_revisions||[],item=>`<li><strong>Revisão ${Number(item.revision||1)}</strong><div>${escapeHtml(item.change_note||'')}</div><small>SHA-256 ${escapeHtml(item.content_hash||'')}</small></li>`,'Sem revisões.'))}${section('Histórico auditável',audit+auditScope)}<div class="stamp">Gerado em ${escapeHtml(generated)} · arquivo ${escapeHtml(snapshot.integrity.digest)} · hash canónico da missão ${escapeHtml(snapshot.integrity.mission_content_hash||'não disponível')}. Documento de trabalho sujeito a revisão humana.</div></main></body></html>`;
}

function reportMarkdown(snapshot){
  const mission=snapshot.mission;
  const nodes=snapshot.evidence_graph?.nodes||[];
  const cycles=snapshot.decision_cycles||[];
  const validation=snapshot.validation_protocol||{};
  const protocol=validation.protocol||{};
  const analysis=validation.analysis||{};
  const businessCase=snapshot.live_business_case||{};
  const governedPolicy=snapshot.completion_readiness?.governed_state?.policy||{};
  const economic=businessCase.metrics||{};
  const economicCase=businessCase.case||{};
  const auditEvents=snapshot.mission_audit?.events||[];
  const measurement=(label,row)=>row?[`- **${label}:** ${row.period_start} → ${row.period_end}`,`  - Valor bruto: ${reportNumber(row.numerator_value)}`,`  - Atividade: ${reportNumber(row.denominator_value)}`,`  - Normalizado: ${reportNumber(row.normalized_value)} ${analysis.normalized_unit||''}`,`  - Evidência: ${row.evidence_node_id||'—'} · qualidade ${reportLabel('data_quality',row.data_quality)}`]:[`- **${label}:** não registada`];
  const validationMissingMessage=governedPolicy.measurement_applicability==='required'
    ?'- A medição é obrigatória nesta missão, mas o protocolo quantitativo ainda não foi iniciado.'
    :governedPolicy.measurement_applicability==='not_applicable'
      ?'- A medição foi marcada como não aplicável numa revisão humana da política da missão.'
      :'- A medição é opcional nesta missão e o protocolo quantitativo ainda não foi iniciado.';
  const validationLines=validation.required?[`- **Perfil:** ${validation.profile_definition?.label||validation.profile}`,`- **Unidade observada:** ${protocol.subject||'—'}`,`- **Indicador:** ${protocol.indicator_name||'—'} · ${protocol.indicator_unit||'—'}`,`- **Normalização:** ${protocol.denominator_name||'sem denominador'} · ${protocol.denominator_unit||'—'}`,`- **Intervenção:** ${protocol.intervention_description||'—'}`,`- **Meta:** ${reportNumber(protocol.target_value)} · ${protocol.target_description||'—'}`,...measurement('Baseline',validation.baseline),...measurement('Resultado',validation.result),`- **Comparação determinística:** ${analysis.comparable?`${reportNumber(analysis.absolute_change)} ${analysis.normalized_unit||''} · ${reportNumber(analysis.percent_change,2)}% · ${reportLabel('target_status',analysis.target_status)}`:'períodos ainda não comparáveis'}`,`- **Atribuição revista:** ${protocol.attribution_confidence?reportLabel('confidence',protocol.attribution_confidence):'Pendente'}`,`- **Racional:** ${protocol.review_rationale||'—'}`,`- **Limitações:** ${protocol.limitations||'—'}`,`- **Integridade do protocolo:** revisão ${protocol.revision||1} · SHA-256 ${protocol.content_hash||'—'}`]:[validationMissingMessage];
  const economicStates=businessCase.metric_states||{};
  const economicKnown=businessCase.metrics_state==='observed_or_estimated';
  const economicState=(key,fallback=key)=>economicStates[key]||economicStates[fallback]||'unknown_not_zero';
  const economicAvailable=state=>state!=='unknown_not_zero';
  const economicValue=(value,state,formatter)=>{
    if(!economicAvailable(state)||value===null||value===undefined)return'—';
    const rendered=formatter(value);
    return state==='partial_observed_or_estimated'?`Parcial · ${rendered}`:rendered;
  };
  const economicMoney=(value,key='forecast_financial',fallback='financial')=>economicValue(value,economicState(key,fallback),amount=>reportMoney(amount,economicCase.currency));
  const economicNumber=(value,digits,key,fallback=key)=>economicValue(value,economicState(key,fallback),amount=>reportNumber(amount,digits));
  const economicHasPartial=Object.values(economicStates).includes('partial_observed_or_estimated');
  const economicStatus=!economicKnown
    ?'por determinar — ausência de linhas não significa zero'
    :economicHasPartial
      ?'parcial — alguns indicadores continuam por determinar'
      :'estimativas ou observações registadas';
  const forecastFinancialState=economicState('forecast_financial','financial');
  const forecastRoi=!economicAvailable(forecastFinancialState)||economic.forecast_roi_pct==null?'—':`${economicValue(economic.forecast_roi_pct,forecastFinancialState,value=>reportNumber(value,2))}%`;
  const forecastPayback=!economicAvailable(forecastFinancialState)||economic.forecast_payback_months==null?'—':`${economicValue(economic.forecast_payback_months,forecastFinancialState,value=>reportNumber(value,0))} meses`;
  const economicQuality=Number(businessCase.quality?.monetary_line_count||0)>0?`${reportNumber(businessCase.quality?.overall_score,1)}%`:'— · ainda não avaliável';
  const businessLines=economicCase.id?[
    `- **Modelo:** ${businessCase.definitions?.case_kinds?.[economicCase.case_kind]?.label||economicCase.case_kind}`,
    `- **Estado dos valores:** ${economicStatus}`,
    `- **Conclusão automática auditável:** ${businessCase.executive_conclusion||'Ainda sem dados suficientes.'}`,
    `- **Horizonte:** ${economicCase.horizon_months} meses · taxa ${reportNumber(economicCase.discount_rate_pct,2)}%`,
    `- **Orçamento / custo projetado:** ${economicMoney(economic.budget_base,'budget_base','costs')} / ${economicMoney(economic.forecast_cost_at_completion,'forecast_cost','costs')}`,
    `- **Custo comprometido / realizado:** ${economicMoney(economic.committed_cost,'committed_cost','costs')} / ${economicMoney(economic.realized_cost,'realized_cost','costs')}`,
    `- **Benefício esperado / realizado / com evidência revista:** ${economicMoney(economic.expected_gross_benefit,'expected_benefit','benefits')} / ${economicMoney(economic.realized_benefit,'realized_benefit','benefits')} / ${economicMoney(economic.reviewed_evidence_realized_benefit,'reviewed_evidence_realized_benefit','benefits')}`,
    `- **Benefício líquido projetado:** ${economicMoney(economic.forecast_net_benefit,'forecast_financial','financial')}`,
    `- **ROI / payback:** ${forecastRoi} / ${forecastPayback}`,
    `- **Esforço humano / bloqueios:** ${economicNumber(economic.actual_human_hours,2,'actual_human_hours','human_hours')} h realizadas / ${economicNumber(economic.planned_human_hours,2,'planned_human_hours','human_hours')} h previstas / ${economicNumber(economic.blocked_resource_count,0,'resources')} recursos bloqueados`,
    `- **Encargo anual posterior:** ${economicMoney(economic.annual_post_mission_burden,'post_mission_costs')}`,
    `- **Financiamento / lacuna:** ${economicMoney(economic.funding_available,'funding')} / ${economicMoney(economic.funding_gap,'funding_gap')}`,
    `- **Qualidade / revisão:** ${economicQuality} · ${economicCase.status}`,
    ...(businessCase.alternative_comparison?.profiles||[]).map(row=>{
      const states=row.metric_states||{};
      const profileState=(key,fallback=key)=>states[key]||states[fallback]||'unknown_not_zero';
      const costsState=profileState('scenario_base_costs','costs');
      const benefitsState=profileState('scenario_base_benefits','benefits');
      const financialState=profileState('scenario_base_financial','financial');
      const cost=economicValue(row.total_cost,costsState,value=>reportMoney(value,economicCase.currency));
      const benefit=economicValue(row.probable_gross_benefit,benefitsState,value=>reportMoney(value,economicCase.currency));
      const roi=!economicAvailable(financialState)||row.roi_pct==null?'—':`${economicValue(row.roi_pct,financialState,value=>reportNumber(value,2))}%`;
      return`- **Alternativa · ${row.alternative_label}:** custo ${cost} · benefício provável ${benefit} · ROI ${roi}`;
    }),
    ...(businessCase.items||[]).map(row=>`- **${row.alternative_node_id?`Alternativa ${row.alternative_label||'indisponível'}`:'Missão'} · ${row.label}** · ${businessDefinitionLabel(businessCase,'item_kinds',row.kind)} · ${row.amount_basis==='per_unit'?'unitário':'total'} · base ${reportMoney(row.base_amount,economicCase.currency)} · realizado ${reportMoney(row.realized_amount,economicCase.currency)} · estado ${reportLabel('operational_status',row.operational_status||'planned')}${row.blocker?` · bloqueio ${row.blocker}`:''} · origem ${row.source_label||row.evidence_label||'não declarada'}`),
  ]:[governedPolicy.economics_applicability==='not_applicable'
    ?'- Economia e recursos foram marcados como não aplicáveis numa revisão humana da política da missão.'
    :governedPolicy.economics_applicability==='optional'
      ?'- Economia e recursos são opcionais nesta missão e o business case vivo ainda não foi iniciado.'
      :'- Economia e recursos são obrigatórios nesta missão, mas o business case vivo ainda não foi iniciado.'];
  const lines=[`# ${mission.title}`,``,`**Missão:** ${mission.code} · revisão ${mission.revision} · ${reportLabel('lifecycle',mission.lifecycle_state)}`,`**Integridade do arquivo:** SHA-256 \`${snapshot.integrity.digest}\``,``,`## Objetivo`,``,mission.objective||'Não registado',``,`## Pergunta central`,``,mission.central_question||'Não registada',``,`## Contexto`,``,mission.context||'Não registado',``,`## Documentos`,``,...(snapshot.attachments.length?snapshot.attachments.map(item=>`- ${item.filename} — ${reportLabel('extraction_status',item.extraction_status)} — SHA-256 ${item.sha256||'—'}`):['- Sem documentos.']),``,`## Evidência e raciocínio`,``,...(nodes.length?nodes.map(node=>`- **${reportLabel('node_type',node.node_type)} · ${node.label}** [${reportLabel('node_status',node.status)}] — ${node.body||''}`):['- Sem objetos no grafo.']),``,`## Baseline → intervenção → resultado`,``,...validationLines,``,`## Business case vivo · economia e recursos`,``,...businessLines,``,`## Decisão, resultado e aprendizagem`,``,...(cycles.length?cycles.map(cycle=>`- **${cycle.decision}** [${reportLabel('cycle_status',cycle.status)}]\n  - Ação: ${cycle.action||'—'}\n  - Responsável/prazo: ${cycle.owner||'—'} · ${cycle.due_date||'—'}\n  - Esperado: ${cycle.expected_outcome||'—'}\n  - Observado: ${cycle.actual_outcome||'—'}\n  - Aprendizagem: ${cycle.learning||'—'}`):['- Sem decisões.']),``,`## Prontidão`,``,...(snapshot.completion_readiness?.checks||[]).map(check=>`- [${check.passed?'x':' '}] ${check.label}`),``,`## Histórico auditável`,``,...(auditEvents.length?auditEvents.map(event=>`- **${AUDIT_ACTION_LABELS[event.action]||String(event.action||'Alteração auditada').replaceAll('_',' ').replaceAll('.',' · ')}** — ${event.actor||'Sistema'}${event.created_at?` · ${new Date(event.created_at).toLocaleString('pt-PT')}`:''}${event.payload?.rationale?`\n  - Justificação: ${event.payload.rationale}`:''}`):['- Sem eventos auditáveis nesta janela.']),...(snapshot.mission_audit?.scope_complete===false?['- Nota: podem existir eventos anteriores fora da janela mais recente.']:[]),``,`---`,`Gerado pelo SRIS Mission Intelligence em ${new Date(snapshot.generated_at).toLocaleString('pt-PT')}. Revisão humana obrigatória.`];
  return lines.join('\n');
}

async function exportReport(kind,button){
  if(!selectedMission){showMissionMessage('Abra primeiro uma missão.');return;}
  button?.classList.add('loading');
  try{
    const snapshot=await reportSnapshot();
    const base=slug(`${snapshot.mission.code}-${snapshot.mission.title}`);
    if(kind==='json'){
      const filename=downloadBlob(new Blob([JSON.stringify(snapshot,null,2)],{type:'application/json;charset=utf-8'}),`${base}-arquivo-verificavel.json`);
      showMissionMessage(`Arquivo verificável gerado: ${filename}`,'success');
      return;
    }
    if(kind==='html'){
      const filename=downloadBlob(new Blob([completeReportHtml(snapshot)],{type:'text/html;charset=utf-8'}),`${base}-relatorio-completo.html`);
      showMissionMessage(`Relatório HTML gerado: ${filename}`,'success');
      return;
    }
    if(kind==='md'){
      const filename=downloadBlob(new Blob([reportMarkdown(snapshot)],{type:'text/markdown;charset=utf-8'}),`${base}-relatorio-completo.md`);
      showMissionMessage(`Relatório Markdown gerado: ${filename}`,'success');
      return;
    }
    const reportWindow=window.open('','_blank');
    if(!reportWindow){showMissionMessage('O browser bloqueou a janela de impressão. Autorize pop-ups para guardar o relatório em PDF.');return;}
    reportWindow.opener=null;
    reportWindow.document.open();
    reportWindow.document.write(completeReportHtml(snapshot));
    reportWindow.document.close();
    setTimeout(()=>{reportWindow.focus();reportWindow.print();},250);
    showMissionMessage('Relatório preparado numa nova janela. Use a opção do navegador para imprimir ou guardar em PDF.','success');
  }catch(error){
    showMissionMessage(`Não foi possível gerar o relatório completo: ${error.message}`);
  }finally{
    button?.classList.remove('loading');
  }
}

$$('[data-report]').forEach(button=>button.addEventListener('click',()=>exportReport(button.dataset.report,button)));

async function loadHistory(){
  if(!selectedMission)return;
  const root=$('#dialogue-history');
  if(!root)return;
  try{
    const [dialogueResult,auditResult]=await Promise.allSettled([
      api(`${miBase()}/dialogues?mission_code=${encodeURIComponent(selectedMission.code)}`),
      api(`/api/pilot/audit/missions/${encodeURIComponent(selectedMission.code)}?limit=300`),
    ]);
    const dialogues=dialogueResult.status==='fulfilled'?(dialogueResult.value||[]):[];
    const auditPayload=auditResult.status==='fulfilled'?(auditResult.value||{}):{};
    const audit=auditPayload.events||[];
    missionRuntime.dialogues=dialogues;
    const items=audit.map(event=>{
      const payload=event.payload||{};
      const details=[
        payload.rationale,
        payload.previous_status&&payload.status?`${reportLabel('cycle_status',payload.previous_status)} → ${reportLabel('cycle_status',payload.status)}`:'',
        payload.revision?`Revisão ${payload.revision}`:'',
        Array.isArray(payload.changed_fields)&&payload.changed_fields.length?`${payload.changed_fields.length} campo(s) alterado(s)`:''
      ].filter(Boolean).join(' · ');
      return{
        key:`audit:${event.id}`,
        created_at:event.created_at,
        label:AUDIT_ACTION_LABELS[event.action]||String(event.action||'Alteração auditada').replaceAll('_',' ').replaceAll('.',' · '),
        detail:details,
        actor:event.actor||'Sistema',
      };
    });
    const auditedSessionIds=new Set(audit.map(event=>String(event.resource_id||'')));
    dialogues.forEach(dialogue=>{
      if(auditedSessionIds.has(String(dialogue.id||'')))return;
      items.push({
        key:`dialogue:${dialogue.id}`,
        created_at:dialogue.created_at,
        label:'Sessão assistida',
        detail:dialogue.status?`Estado: ${dialogue.status}`:'',
        actor:'Utilizador autenticado',
      });
    });
    items.sort((left,right)=>new Date(right.created_at||0)-new Date(left.created_at||0));
    root.innerHTML=items.length?items.map(item=>`<div class="timeline-row"><span class="timeline-dot"></span><div><strong>${escapeHtml(item.label)}</strong>${item.detail?`<div>${escapeHtml(item.detail)}</div>`:''}<div class="note">${escapeHtml(item.actor)}${item.created_at?` · ${new Date(item.created_at).toLocaleString('pt-PT')}`:''}</div></div></div>`).join(''):'<div class="note">Ainda não existem alterações auditadas nesta missão.</div>';
    if(auditResult.status==='rejected')root.insertAdjacentHTML('beforeend','<div class="note">A auditoria transversal está temporariamente indisponível; são mostradas apenas as sessões acessíveis.</div>');
    else if(auditPayload.scope_complete===false)root.insertAdjacentHTML('beforeend','<div class="note">Este histórico cobre os eventos mais recentes do workspace; podem existir registos mais antigos fora desta janela.</div>');
  }catch(error){
    root.innerHTML=`<div class="note">Histórico temporariamente indisponível: ${escapeHtml(error.message)}</div>`;
  }
}

async function loadMissionRevisions(){
  if(!selectedMission)return;
  const root=$('#mission-revision-history');
  if(!root)return;
  try{
    const rows=await api(`${miBase()}/missions/${encodeURIComponent(selectedMission.id)}/revisions`);
    root.innerHTML=rows.length?rows.map(row=>`<div class="timeline-row"><span class="timeline-dot"></span><div><strong>Revisão ${Number(row.revision||1)}</strong><div>${escapeHtml(row.change_note||'Revisão canónica preservada.')}</div><div class="note">${row.created_at?new Date(row.created_at).toLocaleString('pt-PT'):''} · hash ${escapeHtml(String(row.content_hash||'').slice(0,16))}…</div></div></div>`).join(''):'<div class="note">Sem revisões disponíveis.</div>';
  }catch(error){
    root.innerHTML=`<div class="note">Não foi possível carregar as revisões: ${escapeHtml(error.message)}</div>`;
  }
}

function refineStaticCopy(){
  installCopilotActions();
  updateMissionCTA();
}

(async()=>{
  if(!token()&&refreshToken()){
    try{await renewSession();}catch{logout();return;}
  }
  if(!token()){location.assign('/');return;}
  refineStaticCopy();
  try{await refresh();}
  catch(error){
    console.warn('Pilot profile unavailable:',error.message);
    renderDegradedProfile();
    showAppMessage(`A sessão foi iniciada, mas o workspace não conseguiu sincronizar: ${error.message}`,{retry:true});
  }
  if(orgId())await Promise.allSettled([loadMissions(),loadWorkspaceSummary(),loadAccountCapabilities()]);
  setTimeout(normaliseMissionTabs,500);
})();
