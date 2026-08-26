(()=>{
  'use strict';

  const token=()=>localStorage.getItem('sris_access_token')||sessionStorage.getItem('sris_access_token');
  const authHeaders=()=>({'Content-Type':'application/json','Authorization':`Bearer ${token()||''}`});
  const esc=(value='')=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const missionCode=()=>{
    const raw=(document.querySelector('#detail-code')?.textContent||'').trim();
    const parts=raw.split('/').map(value=>value.trim()).filter(Boolean);
    return parts[parts.length-1]||raw;
  };

  async function api(url,options={}){
    if(window.SRISApi?.request)return window.SRISApi.request(url,options);
    const response=await fetch(url,{...options,headers:{...authHeaders(),...(options.headers||{})},cache:'no-store'});
    let data={};
    try{data=await response.json();}catch{}
    if(response.status===401){
      localStorage.removeItem('sris_access_token');
      sessionStorage.removeItem('sris_access_token');
      location.href='/';
      throw new Error('Sessão expirada.');
    }
    if(!response.ok){
      const detail=data?.detail;
      throw new Error(typeof detail==='string'?detail:(detail?.message||detail?.code||`Erro ${response.status}`));
    }
    return data;
  }

  function install(){
    const tabs=document.querySelector('.mission-tabs');
    const detail=document.querySelector('#mission-detail');
    if(!tabs||!detail||document.querySelector('[data-mission-tab="learning"]'))return false;

    const button=document.createElement('button');
    button.type='button';
    button.dataset.missionTab='learning';
    button.textContent='Reutilizar aprendizagem';
    tabs.appendChild(button);

    const panel=document.createElement('div');
    panel.className='mission-tab';
    panel.id='mission-tab-learning';
    panel.innerHTML=`
      <div class="ll-head">
        <div><div class="eyebrow">MEMÓRIA ORGANIZACIONAL</div><h3>A missão seguinte começa melhor porque a anterior existiu.</h3><div class="note">A aprendizagem viaja com a evidência, as decisões e os resultados que a justificam. Nada influencia uma missão futura sem revisão humana explícita.</div></div>
        <button class="btn btn-primary" id="ll-refresh" type="button">Atualizar aprendizagem</button>
      </div>
      <div id="ll-status" class="note" role="status" aria-live="polite"></div>
      <section id="ll-active-context" class="ll-active-context"></section>
      <div id="ll-summary" class="ll-summary"></div>
      <div id="ll-candidates" class="ll-list"></div>`;
    detail.appendChild(panel);

    const style=document.createElement('style');
    style.textContent=`
      .ll-head{display:flex;justify-content:space-between;gap:18px;align-items:flex-start}.ll-head h3{margin:5px 0}.ll-head .note{max-width:760px}
      #ll-status{min-height:20px;margin:12px 0}.ll-summary{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:14px 0}.ll-stat{padding:11px;border:1px solid var(--line);border-radius:12px;background:#f8faf8}.ll-stat strong{display:block;font-size:22px;color:var(--forest)}.ll-stat span{font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
      .ll-active-context{display:grid;gap:8px;margin:12px 0}.ll-active-context:empty{display:none}.ll-active-context h4{margin:0}.ll-context-row{border:1px solid #cfe0d6;border-radius:12px;background:#f5faf7;padding:12px}.ll-context-row.revalidate{border-color:#e7d19f;background:#fffaf0}.ll-context-row strong,.ll-context-row small{display:block}.ll-context-row p{margin:6px 0;color:var(--ink);white-space:pre-wrap}.ll-context-row small{color:var(--muted);font-size:9px}
      .ll-list{display:grid;gap:11px}.ll-card{border:1px solid var(--line);border-radius:15px;padding:15px;background:#fff}.ll-top{display:flex;justify-content:space-between;gap:12px}.ll-source{font-size:10px;color:var(--muted);margin:5px 0}.ll-statuses{display:flex;gap:6px;align-items:center;flex-wrap:wrap;justify-content:flex-end}.ll-statement{line-height:1.6;white-space:pre-wrap}.ll-lineage{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}.ll-chip{font-size:9px;padding:4px 7px;border-radius:999px;background:#eef4f1;color:#48695e}.ll-actions{display:flex;gap:7px;flex-wrap:wrap;border-top:1px solid var(--line);padding-top:10px;margin-top:10px}.ll-actions button{padding:8px 10px}.ll-active{border-left:4px solid #2f765f}.ll-revalidate{border-left:4px solid #d49b3e}.ll-not-applicable{border-left:4px solid #8b9691;opacity:.78}
      .ll-review-form{display:grid;gap:10px;margin-top:12px;border:1px solid #d8cba7;border-radius:12px;background:#fffaf0;padding:13px}.ll-review-form h4{margin:0}.ll-review-form .field{margin:0}.ll-review-form textarea{min-height:92px;position:relative;z-index:1;pointer-events:auto!important;touch-action:manipulation;-webkit-user-select:text;user-select:text}.ll-review-actions{display:flex;gap:8px;flex-wrap:wrap}.ll-review-message{min-height:18px;color:var(--muted);font-size:10px}.ll-review-message.error{color:#93483e}
      @media(max-width:760px){.ll-head{display:grid}.ll-head .btn{width:100%}.ll-summary{grid-template-columns:repeat(2,1fr)}.ll-top{display:grid}.ll-actions,.ll-review-actions{display:grid}.ll-actions .btn,.ll-review-actions .btn{width:100%}}
    `;
    document.head.appendChild(style);

    button.addEventListener('click',async()=>{
      document.querySelectorAll('[data-mission-tab]').forEach(item=>item.classList.toggle('active',item===button));
      document.querySelectorAll('.mission-tab').forEach(item=>item.classList.toggle('active',item===panel));
      await load();
    });
    panel.querySelector('#ll-refresh')?.addEventListener('click',load);
    panel.addEventListener('click',handleClick);
    panel.addEventListener('pointerup',ensureMobileEditorFocus,{passive:true});
    panel.addEventListener('submit',handleReviewSubmit);
    return true;
  }

  async function load(){
    const code=missionCode();
    if(!code)return;
    const status=document.querySelector('#ll-status');
    if(status)status.textContent='A procurar aprendizagem publicada noutras missões…';
    try{
      const [candidates,activeContext]=await Promise.all([
        api(`/api/pilot/learning/missions/${encodeURIComponent(code)}/candidates`),
        api(`/api/pilot/learning/missions/${encodeURIComponent(code)}/active-context`),
      ]);
      render(candidates);
      renderActiveContext(activeContext);
      const activeCount=(activeContext?.inheritance?.valid||[]).length;
      const revalidationCount=(activeContext?.inheritance?.requires_revalidation||[]).length;
      if(status)status.textContent=candidates.candidates.length
        ? `${activeCount} aprendizagem(ns) reutilizável(eis) neste contexto · ${revalidationCount} a revalidar. Reveja as restantes antes de as reutilizar.`
        : 'Esta área mostra apenas aprendizagens publicadas por outras missões. A aprendizagem da missão atual fica na Memória canónica e só aparecerá aqui quando abrir outra missão.';
    }catch(error){
      if(status)status.textContent=`Não foi possível carregar aprendizagem: ${error.message}`;
    }
  }

  function renderActiveContext(data){
    const root=document.querySelector('#ll-active-context');
    if(!root)return;
    const valid=data?.inheritance?.valid||[];
    const revalidation=data?.inheritance?.requires_revalidation||[];
    const rows=[
      ...valid.map(item=>({...item,kind:'valid'})),
      ...revalidation.map(item=>({...item,kind:'revalidate'})),
    ];
    root.innerHTML=rows.length?`<h4>Aprendizagem já revista neste contexto</h4>${rows.map(item=>`<article class="ll-context-row ${item.kind==='revalidate'?'revalidate':''}"><strong>${esc(item.title)}</strong><p>${esc(item.statement)}</p><small>Origem ${esc(item.source_mission_code)} · ${item.kind==='valid'?'validada para utilização':'requer nova validação'} · linhagem ${esc(String(item.lineage_sha256||'').slice(0,12))}…</small></article>`).join('')}`:'';
  }

  function render(data){
    const summary=data.summary||{};
    const summaryRoot=document.querySelector('#ll-summary');
    if(summaryRoot)summaryRoot.innerHTML=[
      ['candidate_count','Candidatas'],
      ['reusable_count','Reutilizáveis'],
      ['requires_revalidation_count','Revalidar'],
      ['not_applicable_count','Não aplicáveis'],
    ].map(([key,label])=>`<div class="ll-stat"><strong>${Number(summary[key]||0)}</strong><span>${label}</span></div>`).join('');

    const list=document.querySelector('#ll-candidates');
    if(!list)return;
    list.innerHTML=(data.candidates||[]).length?data.candidates.map(candidate=>{
      const review=candidate.review||{};
      const applicability=review.applicability||'';
      const cssClass=applicability==='reuse'?'ll-active':applicability==='requires_revalidation'?'ll-revalidate':applicability==='not_applicable'?'ll-not-applicable':'';
      const counts=candidate.lineage?.entity_counts||candidate.lineage?.counts||{};
      const applicabilityLabel={reuse:'reutilizar aqui',requires_revalidation:'revalidar antes de usar',not_applicable:'não aplicável aqui'}[applicability]||'aplicabilidade por rever';
      const canonicalLabel={valid:'canonicamente válida',superseded:'substituída',archived:'arquivada',invalidated:'canonicamente invalidada'}[candidate.canonical_status]||candidate.canonical_status||'estado canónico desconhecido';
      return `<article class="ll-card ${cssClass}" data-packet="${esc(candidate.id)}">
        <div class="ll-top"><div><strong>${esc(candidate.title)}</strong><div class="ll-source">${esc(candidate.source_mission?.code)} · ${esc(candidate.source_mission?.title||'')} · relevância ${Math.round((candidate.relevance_score||0)*100)}%</div></div><div class="ll-statuses"><span class="pill">${esc(canonicalLabel)}</span><span class="pill">${esc(applicabilityLabel)}</span></div></div>
        <div class="ll-statement">${esc(candidate.statement)}</div>
        <div class="ll-lineage"><span class="ll-chip">${Number(counts.evidence||0)} evidência(s)</span><span class="ll-chip">${Number(counts.decision||0)} decisão(ões)</span><span class="ll-chip">${Number(counts.outcome||0)} resultado(s)</span><span class="ll-chip">linhagem ${esc(String(candidate.lineage_sha256||'').slice(0,10))}…</span></div>
        ${review.rationale?`<div class="note">Revisão: ${esc(review.rationale)}${review.context_change?` · Diferenças contextuais: ${esc(review.context_change)}`:''}</div>`:''}
        <div class="ll-actions"><button class="btn btn-ghost" type="button" data-applicability="reuse">Reutilizar nesta missão</button><button class="btn btn-ghost" type="button" data-applicability="requires_revalidation">Revalidar antes de reutilizar</button><button class="btn btn-ghost" type="button" data-applicability="not_applicable">Não aplicável a esta missão</button></div>
        <form class="ll-review-form hidden" data-review-form data-applicability="">
          <h4 data-review-title>Rever aplicabilidade</h4>
          <div class="field"><label for="ll-review-rationale-${esc(candidate.id)}">Justificação da aplicabilidade *</label><textarea id="ll-review-rationale-${esc(candidate.id)}" data-review-rationale required maxlength="5000" autocomplete="off" autocapitalize="sentences" enterkeyhint="next" placeholder="Explique por que razão esta aprendizagem deve ou não ser utilizada nesta missão.">${esc(review.rationale||'')}</textarea></div>
          <div class="field hidden" data-context-field><label for="ll-review-context-${esc(candidate.id)}">Que diferenças existem entre os contextos? *</label><textarea id="ll-review-context-${esc(candidate.id)}" data-review-context maxlength="5000" autocomplete="off" autocapitalize="sentences" enterkeyhint="done" placeholder="Registe as diferenças materiais entre a missão de origem e a missão atual que impedem a reutilização automática.">${esc(review.context_change||'')}</textarea></div>
          <div class="ll-review-actions"><button class="btn btn-primary" type="submit">Guardar revisão</button><button class="btn btn-secondary" type="button" data-cancel-review>Cancelar</button></div>
          <div class="ll-review-message" data-review-message role="status" aria-live="polite"></div>
        </form>
      </article>`;
    }).join(''):'<div class="eg-empty"><strong>Nenhuma aprendizagem externa disponível para esta missão.</strong><br>A própria aprendizagem não é apresentada aqui para evitar reutilização circular. Abra outra missão para a testar como candidata.</div>';
  }

  function ensureMobileEditorFocus(event){
    const editor=event.target.closest?.('[data-review-rationale],[data-review-context]');
    if(!editor||editor.disabled||editor.closest('.hidden'))return;
    if(document.activeElement!==editor)requestAnimationFrame(()=>editor.focus({preventScroll:true}));
  }

  function handleClick(event){
    const cancel=event.target.closest?.('[data-cancel-review]');
    if(cancel){
      cancel.closest('[data-review-form]')?.classList.add('hidden');
      return;
    }
    const button=event.target.closest?.('[data-applicability]');
    if(!button)return;
    const card=button.closest('[data-packet]');
    const form=card?.querySelector('[data-review-form]');
    if(!card||!form)return;
    const applicability=button.dataset.applicability;
    form.dataset.applicability=applicability;
    const labels={reuse:'Reutilizar nesta missão',requires_revalidation:'Revalidar antes de reutilizar',not_applicable:'Não aplicar nesta missão'};
    const title=form.querySelector('[data-review-title]');
    if(title)title.textContent=labels[applicability]||'Rever aplicabilidade';
    const contextField=form.querySelector('[data-context-field]');
    const context=form.querySelector('[data-review-context]');
    const requiresChange=applicability==='requires_revalidation';
    contextField?.classList.toggle('hidden',!requiresChange);
    if(context)context.required=requiresChange;
    form.classList.remove('hidden');
    form.querySelector('[data-review-rationale]')?.focus({preventScroll:true});
    form.scrollIntoView({behavior:'smooth',block:'nearest'});
  }

  async function handleReviewSubmit(event){
    const form=event.target.closest?.('[data-review-form]');
    if(!form)return;
    event.preventDefault();
    const card=form.closest('[data-packet]');
    const packetId=card?.dataset.packet;
    const applicability=form.dataset.applicability;
    const code=missionCode();
    const rationale=(form.querySelector('[data-review-rationale]')?.value||'').trim();
    const contextChange=(form.querySelector('[data-review-context]')?.value||'').trim();
    const message=form.querySelector('[data-review-message]');
    if(!packetId||!code||!applicability)return;
    if(!rationale){if(message){message.textContent='Explique a decisão de revisão.';message.classList.add('error');}return;}
    if(applicability==='requires_revalidation'&&!contextChange){if(message){message.textContent='Registe as diferenças materiais entre os contextos.';message.classList.add('error');}return;}
    const submit=form.querySelector('button[type="submit"]');
    submit?.classList.add('loading');
    if(message){message.textContent='A guardar a revisão humana e a proveniência…';message.classList.remove('error');}
    try{
      await api(`/api/pilot/learning/missions/${encodeURIComponent(code)}/candidates/${encodeURIComponent(packetId)}/review`,{
        method:'POST',
        body:JSON.stringify({applicability,rationale,context_change:applicability==='requires_revalidation'?contextChange:''}),
      });
      await load();
      document.dispatchEvent(new CustomEvent('sris:learning-reviewed',{detail:{mission_code:code,packet_id:packetId,applicability}}));
    }catch(error){
      if(message){message.textContent=`Não foi possível guardar a revisão: ${error.message}`;message.classList.add('error');}
    }finally{submit?.classList.remove('loading');}
  }

  if(!install())document.addEventListener('DOMContentLoaded',install,{once:true});
})();
