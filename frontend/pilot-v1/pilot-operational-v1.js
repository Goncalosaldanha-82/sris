(()=>{
  const $=(s)=>document.querySelector(s),$$=(s)=>[...document.querySelectorAll(s)];
  const token=()=>localStorage.getItem('sris_access_token');
  const esc=(v='')=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  async function api(path,options={}){
    const headers={...(options.headers||{})};
    if(!(options.body instanceof FormData))headers['Content-Type']='application/json';
    if(token())headers.Authorization=`Bearer ${token()}`;
    const res=await fetch(path,{...options,headers});let data={};try{data=await res.json()}catch{}
    if(res.status===401){localStorage.removeItem('sris_access_token');location.href='/';throw new Error('Sessão expirada.');}
    if(!res.ok){const d=data?.detail;throw new Error(typeof d==='string'?d:(d?.message||d?.code||data?.message||`Erro ${res.status}`));}
    return data;
  }
  function operationalState(profile){
    const ai=profile?.ai||{},integration=profile?.integration||{};
    const workspace=Boolean(integration.workspace_ready&&profile?.organization?.id);
    const provider=Boolean(ai.provider_configured);
    const runtime=Boolean(ai.runtime_enabled);
    const organization=Boolean(ai.organization_enabled);
    const aiReady=workspace&&provider&&runtime&&organization;
    return {workspace,provider,runtime,organization,aiReady,integration};
  }
  function badge(ok,label){return `<span class="opv1-badge ${ok?'ok':'warn'}"><i></i>${esc(label)}</span>`;}
  function installStyles(){if($('#opv1-style'))return;const s=document.createElement('style');s.id='opv1-style';s.textContent=`
    .opv1-panel{margin:16px 0;border:1px solid var(--line);border-radius:18px;background:linear-gradient(135deg,#fbfdfc,#f4f8f6);padding:16px}.opv1-head{display:flex;justify-content:space-between;gap:14px;align-items:flex-start}.opv1-head h3{margin:2px 0 4px}.opv1-badges{display:flex;gap:7px;flex-wrap:wrap;margin-top:12px}.opv1-badge{display:inline-flex;align-items:center;gap:6px;padding:6px 9px;border-radius:999px;font-size:10px;font-weight:750;border:1px solid var(--line);background:#fff}.opv1-badge i{width:7px;height:7px;border-radius:50%;background:#c8943d}.opv1-badge.ok i{background:#2f765f}.opv1-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px;margin-top:13px}.opv1-metric{background:#fff;border:1px solid var(--line);border-radius:13px;padding:11px}.opv1-metric strong{display:block;font-size:20px;color:var(--forest)}.opv1-metric span{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.07em}.opv1-context{margin:0 0 12px;padding:10px 12px;border:1px solid var(--line);border-radius:12px;background:#f7faf8;font-size:11px}.opv1-provenance{margin-top:12px;border-top:1px solid var(--line);padding-top:10px}.opv1-source{padding:8px 0;border-bottom:1px dashed var(--line);font-size:10px;line-height:1.45}.opv1-source:last-child{border-bottom:0}@media(max-width:760px){.opv1-head{display:grid}.opv1-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}}
  `;document.head.appendChild(s);}
  async function hydrateOverview(){
    const overview=$('#overview');if(!overview||!token())return;
    let profile;try{profile=await api('/api/pilot/profile');}catch(err){return;}
    const state=operationalState(profile),ai=profile.ai||{},org=profile.organization||{};
    const pill=$('#provider-state');if(pill){pill.textContent=state.aiReady?'Operacional':state.workspace?'Configuração IA':'Workspace indisponível';pill.dataset.state=state.aiReady?'ready':'degraded';}
    const status=$('#ai-status');if(status)status.textContent=state.aiReady?'Operacional':!state.provider?'Sem chave':!state.runtime?'Desativada no ambiente':!state.organization?'Desativada no workspace':'Indisponível';
    const role=$('#workspace-role');if(role)role.textContent=(org.role||'Membro').toUpperCase();
    const name=$('#workspace-name');if(name)name.textContent=org.name||'Workspace individual';
    const model=$('#model-name');if(model)model.textContent=ai.model||'Não configurado';
    const existing=$('#opv1-panel');if(existing)existing.remove();
    const panel=document.createElement('section');panel.id='opv1-panel';panel.className='opv1-panel';
    panel.innerHTML=`<div class="opv1-head"><div><div class="eyebrow">ESTADO OPERACIONAL</div><h3>${state.aiReady?'Pilot pronto para trabalho assistido por IA':'Pilot disponível com configuração pendente'}</h3><div class="note">Estado real do workspace e das capacidades ligadas a esta conta.</div></div><span class="pill">${esc(org.name||'Workspace')}</span></div><div class="opv1-badges">${badge(state.workspace,'Workspace')}${badge(state.provider,'Fornecedor IA')}${badge(state.runtime,'Runtime IA')}${badge(state.organization,'Política IA')}${badge(Boolean(state.integration.document_intelligence),'Document Intelligence')}${badge(Boolean(state.integration.evidence_graph),'Evidence Graph')}${badge(Boolean(state.integration.organizational_memory),'Memória')}</div><div class="opv1-metrics"><div class="opv1-metric"><strong id="opv1-missions">—</strong><span>missões</span></div><div class="opv1-metric"><strong>${Number(ai.credit_eur||0).toFixed(2)} €</strong><span>crédito IA</span></div><div class="opv1-metric"><strong>${Number(ai.requests_used||0)}</strong><span>pedidos este mês</span></div><div class="opv1-metric"><strong>${Number(ai.request_limit||0)}</strong><span>limite mensal</span></div></div>`;
    const grid=$('.overview-grid');overview.insertBefore(panel,grid||overview.children[1]||null);
    if(org.id){try{const ms=await api(`/api/organizations/${encodeURIComponent(org.id)}/mission-intelligence/missions`);const el=$('#opv1-missions');if(el)el.textContent=Array.isArray(ms)?ms.length:0;}catch{const el=$('#opv1-missions');if(el)el.textContent='0';}}
  }
  function activeMission(){const s=window.__srisMissionWorkspace||{};const raw=($('#detail-code')?.textContent||'').trim();const parts=raw.split('/').map(x=>x.trim()).filter(Boolean);const code=s.mission?.code||parts[parts.length-1]||null;return {id:s.missionId||s.mission?.id||null,code,title:s.mission?.title||($('#detail-title')?.textContent||'').trim()||null};}
  function installMissionAwareCopilot(){
    const form=$('#copilot-form');if(!form||form.dataset.operationalV1)return;form.dataset.operationalV1='1';
    const contextBox=document.createElement('div');contextBox.id='opv1-copilot-context';contextBox.className='opv1-context';form.parentNode.insertBefore(contextBox,form);
    const updateContext=()=>{const m=activeMission();contextBox.innerHTML=m.code?`<strong>Contexto ativo:</strong> ${esc(m.code)}${m.title?` — ${esc(m.title)}`:''}<br><span class="note">O Copiloto usará a missão, documentos recuperados e proveniência disponível.</span>`:'<strong>Contexto:</strong> análise transversal ao workspace.<br><span class="note">Abra uma missão antes de vir ao Copiloto para obter análise documental contextual.</span>';};
    updateContext();document.addEventListener('click',e=>{if(e.target.closest?.('[data-mid], [data-go="copilot"], [data-section="copilot"]'))setTimeout(updateContext,180);},true);
    form.addEventListener('submit',async e=>{
      e.preventDefault();e.stopImmediatePropagation();
      const answer=$('#copilot-answer'),button=e.submitter,msg=$('#copilot-message')?.value.trim(),extra=$('#copilot-context')?.value.trim();if(!msg)return;
      answer.classList.remove('empty');answer.textContent='A analisar contexto, evidência e memória…';button?.classList.add('loading');
      const m=activeMission();
      try{
        const data=await api('/api/pilot/intelligence/ask',{method:'POST',body:JSON.stringify({message:msg,context:extra||null,mission_id:m.id,mission_code:m.code})});
        answer.textContent=data.answer||'Resposta concluída.';
        const old=$('#opv1-provenance');if(old)old.remove();
        const sources=data?.context?.sources||[];if(sources.length){const p=document.createElement('div');p.id='opv1-provenance';p.className='opv1-provenance';p.innerHTML=`<strong>Proveniência usada · ${sources.length} excerto(s)</strong>${sources.map(s=>`<div class="opv1-source"><strong>${esc(s.filename||'Documento')}</strong> · chars ${Number(s.char_start||0)}–${Number(s.char_end||0)} · hybrid ${Number(s.hybrid_score||0).toFixed(3)}<br><span class="note">sha256 ${esc((s.content_sha256||'').slice(0,16))}…</span></div>`).join('')}`;answer.insertAdjacentElement('afterend',p);}
        if($('#last-charge'))$('#last-charge').textContent=`${Number(data.charged_eur||0).toFixed(4)} €`;
        await hydrateOverview();updateContext();
      }catch(err){answer.textContent=`Não foi possível concluir a análise: ${err.message}`;answer.classList.add('empty');}finally{button?.classList.remove('loading');}
    },true);
  }
  function install(){installStyles();hydrateOverview();installMissionAwareCopilot();document.addEventListener('visibilitychange',()=>{if(!document.hidden)hydrateOverview();});}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();