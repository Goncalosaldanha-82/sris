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
const missionRuntime={attachments:[],graph:null,cycles:[],readiness:null,dialogues:[],memory:[],extraction:null};

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
    title:'Normalizar e reduzir o consumo de água por quarto ocupado',
    objective:'Decidir que intervenção operacional deve ser testada para reduzir o consumo de água normalizado pela atividade real, sem degradar a experiência do hóspede nem transferir custo para outra parte da operação.',
    question:'Que fatores explicam a variação observada e qual é a intervenção mais pequena, mensurável e reversível que deve ser testada primeiro?',
    context:'Reunir consumos de água, ocupação, quartos vendidos, hóspedes/noite, rega, lavandaria, manutenção, ocorrências e alterações de procedimento do período em análise.',
    assumptions:'O aumento observado pode estar relacionado com atividade e não apenas com ineficiência.\nOs dados existentes permitem construir uma baseline minimamente comparável.',
    constraints:'Não reduzir qualidade percebida pelo hóspede.\nNão interromper a operação.\nUsar inicialmente dados já disponíveis.',
    success:'Redução sustentada do consumo por quarto ocupado, sem aumento material de reclamações, custo operacional ou consumo noutro recurso.',
    domain:'hospitality_resource_efficiency',
    priority:'strategic',
    horizon:'90 dias',
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
  setText('#metric-results',metrics.pending_results??0);
  setText('#metric-learning',metrics.published_learning??0);
  const rows=Array.isArray(summary?.missions)?summary.missions:[];
  const recent=$('#command-missions');
  if(recent)recent.innerHTML=rows.length?rows.slice(0,5).map(row=>commandMissionRow(row)).join(''):'<div class="command-empty"><strong>Ainda não existem missões.</strong><span>Crie a primeira missão a partir de uma decisão real.</span></div>';
  const attentionRows=rows.filter(row=>['active','paused'].includes(row.lifecycle_state)&&(row.attention>0||row.progress_percent<100)).sort((a,b)=>(b.attention-a.attention)||(a.progress_percent-b.progress_percent));
  const attentionRoot=$('#command-attention');
  if(attentionRoot)attentionRoot.innerHTML=attentionRows.length?attentionRows.slice(0,6).map(row=>commandMissionRow(row,{attention:true})).join(''):'<div class="command-empty success"><strong>Sem bloqueios operacionais.</strong><span>As missões ativas não apresentam ações pendentes.</span></div>';
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
  const order=['summary','documents','graph','cycle','intelligence','memory','learning','history'];
  const labels={summary:'Resumo',documents:'Documentos',graph:'Evidência',cycle:'Decisão e resultado',intelligence:'Diálogo',memory:'Memória canónica',learning:'Reutilizar aprendizagem',history:'Auditoria'};
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

function renderMissionOperationalState(){
  if(!selectedMission)return;
  const graph=missionRuntime.graph||{};
  const counts=graph.counts||{};
  const cycles=missionRuntime.cycles||[];
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
    <div><strong>${reviewedLearning}</strong><span>aprendizagens revistas</span></div>`;
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
  const [graphResult,cyclesResult,readinessResult]=await Promise.allSettled([
    api(`/api/pilot/evidence-graph/missions/${encodeURIComponent(code)}`),
    api(`/api/pilot/decision-cycles/missions/${encodeURIComponent(code)}`),
    api(`/api/pilot/missions/${encodeURIComponent(code)}/completion-readiness`),
  ]);
  if(!selectedMission||selectedMission.id!==missionId)return;
  if(graphResult.status==='fulfilled')missionRuntime.graph=graphResult.value;
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
document.addEventListener('sris:learning-published',()=>{void loadMissionOperationalState();});

document.addEventListener('click',event=>{
  const tab=event.target.closest('.mission-tabs [data-mission-tab]');
  if(tab){
    $$('.mission-tabs [data-mission-tab]').forEach(item=>item.classList.toggle('active',item===tab));
    $$('.mission-tab').forEach(panel=>panel.classList.toggle('active',panel.id===`mission-tab-${tab.dataset.missionTab}`));
  }
  const opener=event.target.closest('[data-open-mission-tab]');
  if(opener)activateMissionTab(opener.dataset.openMissionTab);
});

async function openMission(id){
  try{
    const mission=await api(`${miBase()}/missions/${encodeURIComponent(id)}`);
    selectedMission=mission;
    rememberMission(mission.id);
    missionRuntime.attachments=[];
    missionRuntime.graph=null;
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
  if(epistemic.success)jobs.push(createGraphNode(mission.code,'outcome','Critério de sucesso',epistemic.success));
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

function downloadBlob(blob,filename){
  const url=URL.createObjectURL(blob);
  const anchor=document.createElement('a');
  anchor.href=url;
  anchor.download=filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
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
    panel.innerHTML=`<div class="document-extraction-head"><div><div class="eyebrow">EXTRAÇÃO DOCUMENTAL · SEM IA</div><h4>${escapeHtml(filename)}</h4><p>${Number(data.total_fragments||0)} excerto(s) indexado(s) · SHA-256 ${escapeHtml(String(data.source_sha256||'').slice(0,16))}…</p></div><button type="button" class="inline-link" id="close-extraction">Fechar</button></div><div class="document-fragments">${fragments.length?fragments.map(fragment=>`<article class="document-fragment"><div class="document-fragment-head"><div><strong>Excerto ${Number(fragment.ordinal||0)}</strong><small>${escapeHtml(fragment.location||`caracteres ${fragment.char_start}–${fragment.char_end}`)} · hash ${escapeHtml(String(fragment.content_sha256||'').slice(0,12))}…</small></div><button class="btn btn-secondary compact" type="button" data-promote-document-evidence="${escapeHtml(fragment.id)}">Registar como evidência</button></div><pre>${escapeHtml(fragment.excerpt||'')}</pre></article>`).join(''):`<form id="visual-evidence-form" class="visual-evidence-form"><div><strong>Fonte sem texto extraível</strong><p>A fonte original está preservada. Abra-a, descreva apenas o que observou diretamente e registe essa observação com proveniência visual.</p></div><div class="field"><label for="visual-evidence-body">Observação humana sobre a fonte *</label><textarea id="visual-evidence-body" required maxlength="10000" placeholder="Descreva o elemento observável, sem o converter automaticamente numa conclusão."></textarea></div><button class="btn btn-primary" type="submit">Registar fonte visual como evidência</button><div class="note" id="visual-evidence-status"></div></form>`}</div>`;
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
    if(status)status.textContent='Evidência visual registada com proveniência.';
    button.disabled=true;
    await Promise.allSettled([loadMissionOperationalState(),loadWorkspaceSummary()]);
    showMissionMessage('A observação visual foi registada como evidência humana ligada à fonte original.','success');
  }catch(error){if(status)status.textContent=error.message;}
  finally{button?.classList.remove('loading');}
}

async function promoteDocumentEvidence(chunkId,button){
  if(!selectedMission||!chunkId)return;
  button?.classList.add('loading');
  try{
    await api(`/api/pilot/evidence-graph/missions/${encodeURIComponent(selectedMission.code)}/document-evidence`,{method:'POST',body:JSON.stringify({chunk_id:chunkId})});
    button.textContent='Evidência registada ✓';
    button.disabled=true;
    await Promise.allSettled([loadMissionOperationalState(),loadWorkspaceSummary()]);
    showMissionMessage('O excerto foi registado como evidência com fonte, posição e hashes preservados.','success');
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
  const mission={...selectedMission};
  const code=mission.code;
  const [attachmentsResult,graphResult,cyclesResult,dialoguesResult,readinessResult,memoryResult,revisionsResult]=await Promise.allSettled([
    api(`${miBase()}/missions/${encodeURIComponent(code)}/attachments`),
    api(`/api/pilot/evidence-graph/missions/${encodeURIComponent(code)}`),
    api(`/api/pilot/decision-cycles/missions/${encodeURIComponent(code)}`),
    api(`${miBase()}/dialogues?mission_code=${encodeURIComponent(code)}`),
    api(`/api/pilot/missions/${encodeURIComponent(code)}/completion-readiness`),
    api(`${miBase()}/memory/items?limit=500`),
    api(`${miBase()}/missions/${encodeURIComponent(mission.id)}/revisions`),
  ]);
  const value=(result,fallback)=>result.status==='fulfilled'?result.value:fallback;
  const memory=value(memoryResult,[]);
  const archive={
    schema:'sris.pilot.mission-export.v1',
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
    mission_memory:(Array.isArray(memory)?memory:memory.items||[]).filter(item=>item.mission_id===mission.id),
    mission_revisions:value(revisionsResult,[]),
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

function completeReportHtml(snapshot){
  const mission=snapshot.mission||{};
  const graph=snapshot.evidence_graph||{};
  const nodes=graph.nodes||[];
  const cycles=snapshot.decision_cycles||[];
  const section=(heading,content)=>`<section><h2>${escapeHtml(heading)}</h2>${content}</section>`;
  const text=value=>`<div class="pre">${escapeHtml(value||'Não registado')}</div>`;
  const list=(rows,renderer,empty='Sem registos.')=>rows.length?`<ol>${rows.map(renderer).join('')}</ol>`:`<p class="muted">${escapeHtml(empty)}</p>`;
  const evidence=list(nodes,node=>`<li><strong>${escapeHtml(node.node_type)} · ${escapeHtml(node.label)}</strong><div>${escapeHtml(node.body||'')}</div><small>${escapeHtml(node.status||'')} · ${escapeHtml(node.source_kind||'')} ${node.source_sha256?`· hash ${escapeHtml(String(node.source_sha256).slice(0,16))}…`:''}</small></li>`,'Sem objetos no Evidence Graph.');
  const decisions=list(cycles,cycle=>`<li><strong>${escapeHtml(cycle.decision)}</strong><div>Ação: ${escapeHtml(cycle.action||'não definida')}<br>Responsável/prazo: ${escapeHtml(cycle.owner||'—')} · ${escapeHtml(cycle.due_date||'—')}<br>Esperado: ${escapeHtml(cycle.expected_outcome||'—')}<br>Observado: ${escapeHtml(cycle.actual_outcome||'—')}<br>Aprendizagem: ${escapeHtml(cycle.learning||'—')}</div><small>Estado: ${escapeHtml(cycle.status||'')}</small></li>`,'Sem ciclos de decisão.');
  const documents=list(snapshot.attachments||[],item=>`<li><strong>${escapeHtml(item.filename||'Documento')}</strong><div>${escapeHtml(item.extraction_status||'registado')} · ${Number(item.byte_size||0)} bytes</div><small>SHA-256 ${escapeHtml(item.sha256||'não disponível')}</small></li>`,'Sem documentos.');
  const checks=list(snapshot.completion_readiness?.checks||[],check=>`<li><strong>${check.passed?'✓':'○'} ${escapeHtml(check.label)}</strong><small>${Number(check.count||0)} registo(s)</small></li>`,'Prontidão não calculada.');
  const generated=new Date(snapshot.generated_at).toLocaleString('pt-PT');
  return `<!doctype html><html lang="pt-PT"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escapeHtml(mission.code)} — ${escapeHtml(mission.title)}</title><style>body{margin:0;background:#f6f3ea;color:#10231d;font:15px/1.65 Arial,sans-serif}main{max-width:940px;margin:auto;padding:54px}header{padding-bottom:28px;border-bottom:2px solid #c99a43}.brand{font-weight:800;letter-spacing:.13em;color:#103d32}h1,h2{font-family:Georgia,serif;font-weight:500}h1{font-size:42px;line-height:1.05;margin:20px 0 8px}h2{font-size:24px;margin:28px 0 9px}section{padding-bottom:18px;border-bottom:1px solid #d8dfda}.pre{white-space:pre-wrap}li{margin:0 0 14px}li small,.muted,.meta,.stamp{color:#687971}.stamp{margin-top:34px;font-size:12px;overflow-wrap:anywhere}@media print{body{background:#fff}main{padding:16mm}}</style></head><body><main><header><div class="brand">SRIS · MISSION INTELLIGENCE</div><h1>${escapeHtml(mission.title)}</h1><div class="meta">${escapeHtml(mission.code)} · revisão ${Number(mission.revision||1)} · ${escapeHtml(mission.lifecycle_state||'active')}</div></header>${section('Objetivo',text(mission.objective))}${section('Pergunta central',text(mission.central_question))}${section('Contexto',text(mission.context))}${section('Documentos e integridade',documents)}${section('Evidência, hipóteses e alternativas',evidence)}${section('Decisão → ação → resultado → aprendizagem',decisions)}${section('Prontidão para conclusão',checks)}${section('Memória da missão',list(snapshot.mission_memory||[],item=>`<li><strong>${escapeHtml(item.title||item.item_type||'Memória')}</strong><div>${escapeHtml(item.summary||'')}</div></li>`,'Sem itens de memória canónica.'))}${section('Revisões preservadas',list(snapshot.mission_revisions||[],item=>`<li><strong>Revisão ${Number(item.revision||1)}</strong><div>${escapeHtml(item.change_note||'')}</div><small>SHA-256 ${escapeHtml(item.content_hash||'')}</small></li>`,'Sem revisões.'))}<div class="stamp">Gerado em ${escapeHtml(generated)} · arquivo ${escapeHtml(snapshot.integrity.digest)} · hash canónico da missão ${escapeHtml(snapshot.integrity.mission_content_hash||'não disponível')}. Documento de trabalho sujeito a revisão humana.</div></main></body></html>`;
}

function reportMarkdown(snapshot){
  const mission=snapshot.mission;
  const nodes=snapshot.evidence_graph?.nodes||[];
  const cycles=snapshot.decision_cycles||[];
  const lines=[`# ${mission.title}`,``,`**Missão:** ${mission.code} · revisão ${mission.revision} · ${mission.lifecycle_state}`,`**Integridade do arquivo:** SHA-256 \`${snapshot.integrity.digest}\``,``,`## Objetivo`,``,mission.objective||'Não registado',``,`## Pergunta central`,``,mission.central_question||'Não registada',``,`## Contexto`,``,mission.context||'Não registado',``,`## Documentos`,``,...(snapshot.attachments.length?snapshot.attachments.map(item=>`- ${item.filename} — ${item.extraction_status} — SHA-256 ${item.sha256||'—'}`):['- Sem documentos.']),``,`## Evidência e raciocínio`,``,...(nodes.length?nodes.map(node=>`- **${node.node_type} · ${node.label}** [${node.status}] — ${node.body||''}`):['- Sem objetos no grafo.']),``,`## Decisão, resultado e aprendizagem`,``,...(cycles.length?cycles.map(cycle=>`- **${cycle.decision}** [${cycle.status}]\n  - Ação: ${cycle.action||'—'}\n  - Responsável/prazo: ${cycle.owner||'—'} · ${cycle.due_date||'—'}\n  - Esperado: ${cycle.expected_outcome||'—'}\n  - Observado: ${cycle.actual_outcome||'—'}\n  - Aprendizagem: ${cycle.learning||'—'}`):['- Sem decisões.']),``,`## Prontidão`,``,...(snapshot.completion_readiness?.checks||[]).map(check=>`- [${check.passed?'x':' '}] ${check.label}`),``,`---`,`Gerado pelo SRIS Mission Intelligence em ${new Date(snapshot.generated_at).toLocaleString('pt-PT')}. Revisão humana obrigatória.`];
  return lines.join('\n');
}

async function exportReport(kind,button){
  if(!selectedMission){showMissionMessage('Abra primeiro uma missão.');return;}
  button?.classList.add('loading');
  try{
    const snapshot=await reportSnapshot();
    const base=slug(`${snapshot.mission.code}-${snapshot.mission.title}`);
    if(kind==='json'){
      downloadBlob(new Blob([JSON.stringify(snapshot,null,2)],{type:'application/json;charset=utf-8'}),`${base}-arquivo-verificavel.json`);
      return;
    }
    if(kind==='html'){
      downloadBlob(new Blob([completeReportHtml(snapshot)],{type:'text/html;charset=utf-8'}),`${base}-relatorio-completo.html`);
      return;
    }
    if(kind==='md'){
      downloadBlob(new Blob([reportMarkdown(snapshot)],{type:'text/markdown;charset=utf-8'}),`${base}-relatorio-completo.md`);
      return;
    }
    const reportWindow=window.open('','_blank');
    if(!reportWindow){showMissionMessage('O browser bloqueou a janela de impressão. Autorize pop-ups para guardar o relatório em PDF.');return;}
    reportWindow.opener=null;
    reportWindow.document.open();
    reportWindow.document.write(completeReportHtml(snapshot));
    reportWindow.document.close();
    setTimeout(()=>{reportWindow.focus();reportWindow.print();},250);
  }catch(error){
    showMissionMessage(`Não foi possível gerar o relatório completo: ${error.message}`);
  }finally{
    button?.classList.remove('loading');
  }
}

$$('[data-report]').forEach(button=>button.addEventListener('click',()=>exportReport(button.dataset.report,button)));

async function loadHistory(){
  if(!selectedMission)return;
  try{
    const rows=await api(`${miBase()}/dialogues?mission_code=${encodeURIComponent(selectedMission.code)}`);
    missionRuntime.dialogues=rows;
    const root=$('#dialogue-history');
    if(!root)return;
    root.innerHTML=rows.length?rows.map(dialogue=>`<div class="timeline-row"><span class="timeline-dot"></span><div><strong>${escapeHtml(dialogue.status||'Sessão analítica')}</strong><div class="note">${dialogue.created_at?new Date(dialogue.created_at).toLocaleString('pt-PT'):''}</div></div></div>`).join(''):'<div class="note">Ainda não existem sessões interativas nesta missão.</div>';
  }catch{
    const root=$('#dialogue-history');
    if(root)root.innerHTML='<div class="note">Histórico temporariamente indisponível.</div>';
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
