const $=(selector,root=document)=>root.querySelector(selector);
const $$=(selector,root=document)=>[...root.querySelectorAll(selector)];
const token=()=>localStorage.getItem('sris_access_token');

let profile=null;
let missions=[];
let selectedMission=null;
let profileAvailable=false;

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
  location.href='/';
}

function errText(data,status){
  const detail=data?.detail;
  if(typeof detail==='string')return detail;
  if(detail?.message)return detail.message;
  if(detail?.code)return detail.code;
  return data?.message||`Erro ${status}`;
}

async function api(path,options={}){
  const headers={...(options.headers||{})};
  if(!(options.body instanceof FormData))headers['Content-Type']='application/json';
  if(token())headers.Authorization=`Bearer ${token()}`;
  const response=await fetch(path,{...options,headers,cache:'no-store'});
  let data={};
  try{data=await response.json()}catch{}
  if(response.status===401){logout();throw new Error('Sessão expirada.');}
  if(!response.ok)throw new Error(errText(data,response.status));
  return data;
}

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

function go(section){
  $$('.section').forEach(node=>node.classList.toggle('active',node.id===section));
  $$('.nav button').forEach(button=>button.classList.toggle('active',button.dataset.section===section));
  setText('#page-title',titles[section]||'SRIS');
  $('#sidebar')?.classList.remove('open');
  if(section==='mission'&&orgId())loadMissions({openFirst:true});
  if(section==='copilot')updateCopilotContext();
  window.scrollTo({top:0,behavior:'smooth'});
}

$$('.nav button').forEach(button=>button.addEventListener('click',()=>go(button.dataset.section)));
$$('[data-go]').forEach(button=>button.addEventListener('click',()=>go(button.dataset.go)));
$('#menu-btn')?.addEventListener('click',()=>$('#sidebar')?.classList.toggle('open'));
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

$('#primary-mission-cta')?.addEventListener('click',async()=>{
  go('mission');
  if(!missions.length)resetMissionForm();
  else if(!selectedMission)await openMission(missions[0].id);
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
  answerElement.classList.remove('empty');
  answerElement.textContent='A analisar contexto, evidência e memória…';
  button?.classList.add('loading');
  try{
    const data=await api('/api/pilot/intelligence/ask',{
      method:'POST',
      body:JSON.stringify({
        message,
        context:context||null,
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
}

function resetMissionForm(parent=null,template=null){
  const form=$('#mission-form');
  if(!form)return;
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
  setTimeout(()=>$('#mission-title')?.focus(),50);
}

$('#new-mission-btn')?.addEventListener('click',()=>resetMissionForm());
$('#empty-new-btn')?.addEventListener('click',()=>resetMissionForm());
$$('[data-mission-template]').forEach(button=>button.addEventListener('click',()=>resetMissionForm(null,missionTemplates[button.dataset.missionTemplate])));
$('#cancel-mission-btn')?.addEventListener('click',()=>selectedMission?openMission(selectedMission.id):showMissionMode('empty'));
$('#create-submission-btn')?.addEventListener('click',()=>selectedMission&&resetMissionForm(selectedMission));
$('#detail-submission-btn')?.addEventListener('click',()=>selectedMission&&resetMissionForm(selectedMission));

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
    if(!missions.length){selectedMission=null;showMissionMode('empty');updateCopilotContext();return;}
    if(selectedMission){
      const stillExists=missions.some(mission=>mission.id===selectedMission.id);
      if(!stillExists)selectedMission=null;
    }
    if(openFirst&&!selectedMission)await openMission(missions[0].id);
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

async function openMission(id){
  try{
    const mission=await api(`${miBase()}/missions/${encodeURIComponent(id)}`);
    selectedMission=mission;
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
    const answer=$('#mission-answer');
    if(answer){answer.textContent='A análise assistida é opcional. A missão e a evidência permanecem canónicas independentemente da sua utilização.';answer.classList.add('empty');}
    showMissionMode('detail');
    updateCopilotContext();
    await Promise.allSettled([loadAttachments(),loadHistory(),loadEpistemicCounts(mission.code)]);
  }catch(error){
    $('#mission-list')?.insertAdjacentHTML('afterbegin','<div class="alert error">Não foi possível abrir esta missão.</div>');
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
    const mission=await api(`${miBase()}/missions`,{method:'POST',body:JSON.stringify(payload)});
    const graphResult=await bootstrapEpistemicNodes(mission,epistemic);
    if(box){
      box.textContent=graphResult.failed?'Missão criada. Parte da camada transversal terá de ser confirmada no Grafo de Evidência.':'Missão criada com pressupostos, restrições e critério de sucesso preservados.';
      box.className=graphResult.failed?'alert error':'alert success';
    }
    await loadMissions();
    await openMission(mission.id);
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

$$('[data-mission-tab]').forEach(button=>button.addEventListener('click',()=>{
  $$('[data-mission-tab]').forEach(item=>item.classList.toggle('active',item===button));
  $$('.mission-tab').forEach(tab=>tab.classList.toggle('active',tab.id===`mission-tab-${button.dataset.missionTab}`));
}));

function showMissionMessage(message,type='error'){
  const box=$('#mission-message');
  if(!box)return;
  box.textContent=message;
  box.className=`alert ${type==='success'?'success':'error'}`;
}

async function loadAttachments(){
  if(!selectedMission)return;
  try{
    const rows=await api(`${miBase()}/missions/${encodeURIComponent(selectedMission.code)}/attachments`);
    const root=$('#attachment-list');
    if(!root)return;
    root.innerHTML=rows.length?rows.map(attachment=>`<div class="attachment-row"><span><strong>${escapeHtml(attachment.original_filename||attachment.filename||'Documento')}</strong><small>${escapeHtml(attachment.extraction_status||'registado')}${attachment.byte_size?` · ${Math.ceil(attachment.byte_size/1024)} KB`:''}</small></span><span class="pill">${escapeHtml(attachment.extension||'ficheiro')}</span></div>`).join(''):'<div class="note">Sem documentos carregados.</div>';
  }catch{
    const root=$('#attachment-list');
    if(root)root.innerHTML='<div class="note">Os documentos desta missão não estão disponíveis neste momento.</div>';
  }
}

$('#upload-file-btn')?.addEventListener('click',async event=>{
  if(!selectedMission){showMissionMessage('Abra primeiro uma missão.');return;}
  const input=$('#mission-file');
  const file=input?.files?.[0];
  if(!file){showMissionMessage('Selecione primeiro um documento.');return;}
  const formData=new FormData();
  formData.append('file',file);
  event.currentTarget.classList.add('loading');
  try{
    await api(`${miBase()}/missions/${encodeURIComponent(selectedMission.code)}/attachments`,{method:'POST',body:formData});
    input.value='';
    showMissionMessage('Documento carregado e associado à missão.','success');
    await loadAttachments();
  }catch(error){
    showMissionMessage(`Não foi possível carregar o documento: ${error.message}`);
  }finally{
    event.currentTarget.classList.remove('loading');
  }
});

async function loadHistory(){
  if(!selectedMission)return;
  try{
    const rows=await api(`${miBase()}/dialogues?mission_code=${encodeURIComponent(selectedMission.code)}`);
    const root=$('#dialogue-history');
    if(!root)return;
    root.innerHTML=rows.length?rows.map(dialogue=>`<div class="timeline-row"><span class="timeline-dot"></span><div><strong>${escapeHtml(dialogue.status||'Sessão analítica')}</strong><div class="note">${dialogue.created_at?new Date(dialogue.created_at).toLocaleString('pt-PT'):''}</div></div></div>`).join(''):'<div class="note">Ainda não existem sessões interativas nesta missão.</div>';
  }catch{
    const root=$('#dialogue-history');
    if(root)root.innerHTML='<div class="note">Histórico temporariamente indisponível.</div>';
  }
}

function refineStaticCopy(){
  installCopilotActions();
  updateMissionCTA();
}

(async()=>{
  if(!token()){location.href='/';return;}
  refineStaticCopy();
  try{await refresh();}catch(error){console.warn('Pilot profile unavailable:',error.message);renderDegradedProfile();}
  if(orgId())await loadMissions();
  setTimeout(()=>{if(!profileAvailable&&orgId())loadMissions();},1500);
})();
