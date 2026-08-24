/* SRIS Pilot V1 — Governed Decision Loop V2 */
(()=>{
  'use strict';

  const BUILD='20260824-operational-core-v3';
  if(window.__srisDecisionLoopV2?.installed){
    window.__srisDecisionLoopV2.refresh?.();
    return;
  }

  const $=(s,r=document)=>r.querySelector(s);
  const $$=(s,r=document)=>[...r.querySelectorAll(s)];
  const esc=(v='')=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const missionCode=()=>{
    const raw=(($('#detail-code')?.textContent||'').trim());
    const parts=raw.split('/').map(x=>x.trim()).filter(Boolean);
    return parts[parts.length-1]||raw;
  };

  const statusLabels={
    proposed:'Proposta',
    committed:'Decidida',
    in_progress:'Em execução',
    completed:'Concluída',
    abandoned:'Abandonada',
  };
  const statusOrder=['proposed','committed','in_progress','completed'];
  let installed=false;
  let loading=false;
  let rows=[];
  let evidenceNodes=[];

  window.__srisDecisionLoopV2={
    installed:true,
    build:BUILD,
    refresh:()=>load(false),
    openCreate:(seed={})=>openCreate(seed),
  };
  document.documentElement.dataset.decisionLoop=BUILD;

  async function api(path,options={}){
    if(window.SRISApi?.request)return window.SRISApi.request(path,options);
    const headers={...(options.headers||{})};
    if(!(options.body instanceof FormData))headers['Content-Type']='application/json';
    const currentToken=localStorage.getItem('sris_access_token');
    if(currentToken)headers.Authorization=`Bearer ${currentToken}`;
    const res=await fetch(path,{...options,headers,cache:'no-store'});
    let data={};
    try{data=await res.json()}catch{}
    if(res.status===401){
      ['sris_access_token','sris_refresh_token'].forEach(k=>localStorage.removeItem(k));
      location.href='/';
      throw new Error('Sessão expirada.');
    }
    if(!res.ok){
      const d=data?.detail;
      throw new Error(typeof d==='string'?d:(d?.message||d?.code||data?.message||`Erro ${res.status}`));
    }
    return data;
  }

  function installStyles(){
    if($('#dc2-style'))return;
    const style=document.createElement('style');
    style.id='dc2-style';
    style.textContent=`
      .dc1-panel{display:grid;gap:14px}.dc1-toolbar{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}.dc1-toolbar h3{margin:4px 0 6px}.dc1-toolbar .note{max-width:760px}.dc1-message{min-height:20px;margin:0!important}.dc1-message[data-state="success"]{color:#276349}.dc1-message[data-state="error"]{color:#a33f3f}.dc1-message[data-state="working"]{color:#806126}
      .dc1-editor{border:1px solid var(--line);border-radius:16px;background:#f8fbf9;padding:16px;box-shadow:0 14px 32px rgba(13,32,26,.055)}.dc1-editor.hidden{display:none!important}.dc1-editor-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:10px}.dc1-editor-head h4{margin:3px 0;font-size:20px}.dc1-editor-grid{display:grid;grid-template-columns:1fr 1fr;gap:11px}.dc1-editor .field{margin-bottom:10px}.dc1-editor textarea{min-height:86px}.dc1-editor-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:4px}
      .dc1-kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px}.dc1-kpi{border:1px solid var(--line);border-radius:12px;background:#fff;padding:11px}.dc1-kpi strong{display:block;font-size:22px;color:var(--forest)}.dc1-kpi span{display:block;margin-top:4px;font-size:8px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}.dc1-kpi.warn{background:#fff9ef;border-color:#e8d6ae}.dc1-kpi.warn strong{color:#8a6429}
      .dc1-list{display:grid;gap:12px}.dc1-card{border:1px solid var(--line);border-radius:16px;padding:15px;background:#fff;box-shadow:0 10px 24px rgba(13,32,26,.035)}.dc1-card[data-overdue="true"]{border-color:#d9a9a9}.dc1-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.dc1-title{min-width:0}.dc1-title .eyebrow{margin-bottom:5px}.dc1-title strong{display:block;font-size:15px;line-height:1.45;overflow-wrap:anywhere}.dc1-head-meta{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}.dc1-status{font-size:9px;font-weight:850;text-transform:uppercase;letter-spacing:.08em;padding:5px 8px;border-radius:999px;background:#edf4f1;color:#41685a;white-space:nowrap}.dc1-status[data-status="completed"]{background:#e4f1e9;color:#225d47}.dc1-status[data-status="abandoned"]{background:#f0f0ed;color:#6d756f}.dc1-due{font-size:9px;font-weight:800;padding:5px 8px;border-radius:999px;background:#f2f4f2;color:#62736c;white-space:nowrap}.dc1-due.overdue{background:#faeaea;color:#9a3e3e}.dc1-due.today{background:#fff1d6;color:#8a6429}
      .dc1-stage{display:grid;grid-template-columns:repeat(4,1fr);gap:5px;margin:13px 0 11px}.dc1-stage span{position:relative;padding:7px 5px;border-radius:9px;background:#f0f3f1;color:#7b8983;text-align:center;font-size:8px;font-weight:850;letter-spacing:.05em;text-transform:uppercase}.dc1-stage span.done{background:#e6f1eb;color:#2e6551}.dc1-stage span.current{outline:1px solid #c49a4c;background:#fbf3e4;color:#805f24}.dc1-stage.abandoned span{opacity:.5}.dc1-stage.abandoned span:last-child{opacity:1;background:#efefec;color:#616964}
      .dc1-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.dc1-field{border:1px solid var(--line);border-radius:12px;padding:10px;background:#fafcfb}.dc1-field strong{display:block;font-size:8px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:5px}.dc1-field p{margin:0;font-size:12px;line-height:1.5;white-space:pre-wrap;overflow-wrap:anywhere}.dc1-field.missing{border-style:dashed;background:#fffdf8}.dc1-field.missing p{color:#8a7550}
      .dc1-quality{display:grid;grid-template-columns:auto 1fr auto;gap:9px;align-items:center;margin-top:10px;padding:9px 10px;border:1px solid var(--line);border-radius:11px;background:#f8faf9}.dc1-quality span{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}.dc1-quality-track{height:6px;border-radius:999px;background:#e4eae6;overflow:hidden}.dc1-quality-track i{display:block;height:100%;border-radius:inherit;background:linear-gradient(90deg,#b78d3e,#2c6c55)}.dc1-quality b{font-size:10px;color:#47655a}
      .dc1-edit{margin-top:11px;border:1px solid var(--line);border-radius:12px;background:#fbfcfb;overflow:hidden}.dc1-edit summary{cursor:pointer;list-style:none;padding:11px 12px;font-size:10px;font-weight:850;color:#49675c}.dc1-edit summary::-webkit-details-marker{display:none}.dc1-edit summary:after{content:'+';float:right;font-size:16px;font-weight:500}.dc1-edit[open] summary:after{content:'−'}.dc1-edit-body{padding:0 12px 12px}.dc1-form-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px}.dc1-edit textarea{min-height:76px}.dc1-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.dc1-inline{min-height:18px;margin-top:7px;font-size:10px;color:var(--muted)}.dc1-inline.error{color:#a33f3f}.dc1-inline.success{color:#276349}.dc1-learning{margin-top:9px;padding:10px;border:1px solid #d9e5df;border-radius:11px;background:#f5faf7;font-size:11px;line-height:1.5}.dc1-learning.warn{border-color:#ead7ad;background:#fff9ed;color:#715a2e}
      .dc1-review{display:flex;gap:6px;flex-wrap:wrap;margin-top:9px;padding-top:9px;border-top:1px solid var(--line)}.dc1-review-note{font-size:9px;color:var(--muted);width:100%}.dc1-empty{padding:25px;border:1px dashed var(--line);border-radius:14px;text-align:center;color:var(--muted)}
      @media(max-width:900px){.dc1-kpis{grid-template-columns:repeat(3,1fr)}.dc1-form-grid{grid-template-columns:1fr 1fr}.dc1-editor-grid{grid-template-columns:1fr}}
      @media(max-width:650px){.dc1-toolbar{display:grid}.dc1-toolbar .btn{width:100%}.dc1-kpis{grid-template-columns:repeat(2,1fr)}.dc1-grid,.dc1-form-grid{grid-template-columns:1fr}.dc1-stage{grid-template-columns:repeat(2,1fr)}.dc1-head{display:grid}.dc1-head-meta{justify-content:flex-start}.dc1-editor-actions{display:grid}.dc1-editor-actions .btn,.dc1-actions .btn{width:100%}}
    `;
    document.head.appendChild(style);
  }

  function install(){
    if(installed)return true;
    const tabs=$('.mission-tabs');
    const detail=$('#mission-detail');
    if(!tabs||!detail)return false;
    installStyles();

    let button=$('[data-mission-tab="cycle"]',tabs);
    let panel=$('#mission-tab-cycle',detail);
    if(!button){
      button=document.createElement('button');
      button.type='button';
      button.dataset.missionTab='cycle';
      button.textContent='Decisão';
      tabs.appendChild(button);
    }
    if(!panel){
      panel=document.createElement('div');
      panel.className='mission-tab';
      panel.id='mission-tab-cycle';
      detail.appendChild(panel);
    }
    if(!$('#dc1-create',panel)){
      panel.innerHTML=`
        <div class="dc1-panel">
          <div class="dc1-toolbar">
            <div>
              <div class="eyebrow">DECISION LOOP</div>
              <h3>Decisão → Ação → Resultado → Aprendizagem</h3>
              <div class="note">Registe uma decisão concreta, acompanhe a execução e compare o resultado observado com o esperado. A aprendizagem só entra na memória depois de revisão humana.</div>
            </div>
            <button class="btn btn-primary" id="dc1-new" type="button">Registar decisão</button>
          </div>
          <div id="dc1-status" class="dc1-message note" role="status" aria-live="polite"></div>
          <section id="dc1-create" class="dc1-editor hidden" aria-label="Nova decisão">
            <div class="dc1-editor-head">
              <div><div class="eyebrow">NOVA DECISÃO</div><h4 id="dc1-create-title">Registar uma decisão acompanhável</h4></div>
              <span class="pill">revisão humana</span>
            </div>
            <form id="dc1-create-form">
              <div class="field"><label for="dc1-decision">Decisão *</label><textarea id="dc1-decision" required maxlength="5000" placeholder="Que decisão foi ou será tomada?"></textarea></div>
              <div class="field"><label for="dc1-evidence-node">Fundamento da decisão *</label><select id="dc1-evidence-node" required><option value="">A carregar evidência da missão…</option></select><div class="note">Selecione a fonte ou evidência que fundamenta esta decisão. A ligação ficará preservada no grafo.</div></div>
              <div class="dc1-editor-grid">
                <div class="field"><label for="dc1-owner">Responsável</label><input id="dc1-owner" maxlength="200" placeholder="Pessoa ou função responsável"></div>
                <div class="field"><label for="dc1-due">Prazo</label><input id="dc1-due" type="date"></div>
              </div>
              <div class="field"><label for="dc1-action">Ação principal</label><textarea id="dc1-action" maxlength="5000" placeholder="O que será executado para materializar a decisão?"></textarea></div>
              <div class="field"><label for="dc1-expected">Resultado esperado</label><textarea id="dc1-expected" maxlength="5000" placeholder="Que mudança observável permitirá avaliar a decisão?"></textarea></div>
              <div class="dc1-editor-actions">
                <button class="btn btn-primary" type="submit" id="dc1-create-save">Guardar decisão</button>
                <button class="btn btn-secondary" type="button" id="dc1-create-cancel">Cancelar</button>
              </div>
              <div id="dc1-create-message" class="dc1-inline" role="status" aria-live="polite"></div>
            </form>
          </section>
          <div id="dc1-kpis" class="dc1-kpis"></div>
          <div id="dc1-list" class="dc1-list"><div class="dc1-empty">A carregar ciclos de decisão…</div></div>
        </div>`;
    }

    button.addEventListener('click',()=>{activate();load(false)});
    $('#dc1-new',panel)?.addEventListener('click',()=>openCreate());
    $('#dc1-create-cancel',panel)?.addEventListener('click',closeCreate);
    $('#dc1-create-form',panel)?.addEventListener('submit',createCycle);

    document.addEventListener('click',event=>{
      const workbenchButton=event.target.closest?.('[data-dw-cycle]');
      if(workbenchButton){
        event.preventDefault();
        const card=workbenchButton.closest('[data-dw-index]');
        if(card)openFromWorkbench(card);
      }
      if(event.target.closest?.('[data-mission-tab="cycle"]'))setTimeout(()=>load(false),0);
    },true);
    document.addEventListener('sris:mission-opened',()=>{
      rows=[];
      evidenceNodes=[];
      renderKPIs();
      if($('[data-mission-tab="cycle"]')?.classList.contains('active'))load(false);
    });
    document.addEventListener('sris:evidence-graph-updated',augmentGraph);
    document.addEventListener('sris:workbench-updated',augmentWorkbench);

    installed=true;
    augmentWorkbench();
    augmentGraph();
    return true;
  }

  function activate(){
    const button=$('.mission-tabs [data-mission-tab="cycle"]');
    const panel=$('#mission-tab-cycle');
    if(!button||!panel)return;
    $$('.mission-tabs [data-mission-tab]').forEach(x=>x.classList.toggle('active',x===button));
    $$('.mission-tab').forEach(x=>x.classList.toggle('active',x===panel));
    panel.scrollIntoView({behavior:'smooth',block:'start'});
  }

  function announce(message,state=''){
    const box=$('#dc1-status');
    if(!box)return;
    box.textContent=message||'';
    box.dataset.state=state;
  }

  function inline(card,message,state=''){
    const box=$('.dc1-inline',card);
    if(!box)return;
    box.textContent=message||'';
    box.className=`dc1-inline${state?` ${state}`:''}`;
  }

  function openCreate(seed={}){
    const code=missionCode();
    if(!code||code==='MISSÃO'){
      announce('Abra primeiro uma missão antes de registar uma decisão.','error');
      return;
    }
    activate();
    const editor=$('#dc1-create');
    const form=$('#dc1-create-form');
    form?.reset();
    if($('#dc1-decision'))$('#dc1-decision').value=seed.decision||'';
    if($('#dc1-action'))$('#dc1-action').value=seed.action||'';
    if($('#dc1-owner'))$('#dc1-owner').value=seed.owner||'';
    if($('#dc1-due'))$('#dc1-due').value=seed.due_date||'';
    if($('#dc1-expected'))$('#dc1-expected').value=seed.expected_outcome||'';
    void loadEvidenceOptions(seed.evidence_node_id||'');
    const title=$('#dc1-create-title');
    if(title)title.textContent=seed.source==='workbench'?'Rever decisão proposta antes de a guardar':'Registar uma decisão acompanhável';
    const message=$('#dc1-create-message');
    if(message){message.textContent=seed.source==='workbench'?'A proposta foi trazida do Decision Workbench. Confirme e complete os campos antes de guardar.':'';message.className='dc1-inline';}
    editor?.classList.remove('hidden');
    setTimeout(()=>$('#dc1-decision')?.focus(),80);
  }

  function closeCreate(){
    $('#dc1-create')?.classList.add('hidden');
    $('#dc1-create-form')?.reset();
    const message=$('#dc1-create-message');
    if(message)message.textContent='';
  }

  function openFromWorkbench(card){
    const label=$('p strong',card)?.textContent?.trim()||'Decisão candidata';
    const full=$('p',card)?.textContent?.trim()||label;
    const body=full.startsWith(label)?full.slice(label.length).replace(/^\s*[:·-]?\s*/,'').trim():full;
    openCreate({
      decision:body?`${label}: ${body}`:label,
      source:'workbench',
    });
  }

  async function createCycle(event){
    event.preventDefault();
    const message=$('#dc1-create-message');
    const button=$('#dc1-create-save');
    const decision=$('#dc1-decision')?.value.trim()||'';
    if(decision.length<2){
      if(message){message.textContent='A decisão precisa de ser explicitada.';message.className='dc1-inline error';}
      $('#dc1-decision')?.focus();
      return;
    }
    const foundation=$('#dc1-evidence-node')?.value||'';
    if(!foundation){
      if(message){message.textContent='Selecione a evidência que fundamenta a decisão.';message.className='dc1-inline error';}
      $('#dc1-evidence-node')?.focus();
      return;
    }
    const payload={
      mission_code:missionCode(),
      decision,
      action:$('#dc1-action')?.value.trim()||null,
      owner:$('#dc1-owner')?.value.trim()||null,
      due_date:$('#dc1-due')?.value||null,
      expected_outcome:$('#dc1-expected')?.value.trim()||null,
      evidence_node_id:foundation,
    };
    button?.classList.add('loading');
    if(message){message.textContent='A guardar a decisão…';message.className='dc1-inline';}
    try{
      await api('/api/pilot/decision-cycles',{method:'POST',body:JSON.stringify(payload)});
      if(message){message.textContent='Decisão guardada.';message.className='dc1-inline success';}
      announce('Decisão registada. Complete a ação, o responsável e o resultado esperado antes de iniciar a execução.','success');
      closeCreate();
      await load(true);
    }catch(err){
      if(message){message.textContent=err.message;message.className='dc1-inline error';}
      announce(`Não foi possível guardar a decisão: ${err.message}`,'error');
    }finally{
      button?.classList.remove('loading');
    }
  }

  async function load(force=true){
    const code=missionCode();
    const list=$('#dc1-list');
    if(!code||code==='MISSÃO'||!list)return;
    if(loading)return;
    loading=true;
    if(force||!rows.length)list.innerHTML='<div class="dc1-empty">A carregar ciclos de decisão…</div>';
    try{
      const data=await api(`/api/pilot/decision-cycles/missions/${encodeURIComponent(code)}`);
      if(code!==missionCode())return;
      rows=Array.isArray(data)?data:[];
      render();
      announce(rows.length?'Ciclos de decisão sincronizados.':'Ainda não existem decisões em acompanhamento.');
    }catch(err){
      list.innerHTML=`<div class="dc1-empty">${esc(err.message)}</div>`;
      announce(`Não foi possível carregar as decisões: ${err.message}`,'error');
    }finally{
      loading=false;
    }
  }

  function render(){
    renderKPIs();
    const list=$('#dc1-list');
    if(!list)return;
    list.innerHTML=rows.length?rows.map(renderCard).join(''):'<div class="dc1-empty">Ainda não existem decisões em acompanhamento. Registe a primeira decisão desta missão.</div>';
    $$('[data-dc-save]',list).forEach(button=>button.addEventListener('click',()=>save(button.dataset.dcSave)));
    $$('[data-dc-materialize]',list).forEach(button=>button.addEventListener('click',()=>materialize(button.dataset.dcMaterialize)));
    document.dispatchEvent(new CustomEvent('sris:decision-cycles-updated',{detail:{mission_code:missionCode(),cycles:rows}}));
  }

  function renderKPIs(){
    const counts={proposed:0,committed:0,in_progress:0,completed:0,attention:0};
    rows.forEach(row=>{
      if(counts[row.status]!==undefined)counts[row.status]++;
      const due=dueInfo(row.due_date,row.status);
      if(due.overdue||needsAttention(row))counts.attention++;
    });
    const box=$('#dc1-kpis');
    if(!box)return;
    box.innerHTML=`
      <div class="dc1-kpi"><strong>${counts.proposed}</strong><span>Propostas</span></div>
      <div class="dc1-kpi"><strong>${counts.committed}</strong><span>Decididas</span></div>
      <div class="dc1-kpi"><strong>${counts.in_progress}</strong><span>Em execução</span></div>
      <div class="dc1-kpi"><strong>${counts.completed}</strong><span>Concluídas</span></div>
      <div class="dc1-kpi ${counts.attention?'warn':''}"><strong>${counts.attention}</strong><span>Requerem atenção</span></div>`;
  }

  function renderCard(row){
    const due=dueInfo(row.due_date,row.status);
    const quality=qualityScore(row);
    const ready=row.status==='completed'&&Boolean((row.actual_outcome||'').trim())&&Boolean((row.learning||'').trim());
    const learningNotice=ready
      ? '<div class="dc1-learning">O ciclo está completo. Envie a aprendizagem para revisão no Evidence Graph; só depois poderá ser publicada na memória organizacional.</div>'
      : row.status==='completed'&&!row.learning
        ? '<div class="dc1-learning warn">O resultado está concluído, mas falta explicitar a aprendizagem antes de a enviar para revisão.</div>'
        : '';
    return `<article class="dc1-card" data-cycle="${esc(row.id)}" data-overdue="${due.overdue?'true':'false'}">
      <div class="dc1-head">
        <div class="dc1-title"><div class="eyebrow">DECISÃO</div><strong>${esc(row.decision)}</strong></div>
        <div class="dc1-head-meta"><span class="dc1-status" data-status="${esc(row.status)}">${esc(statusLabels[row.status]||row.status)}</span>${due.label?`<span class="dc1-due ${due.className}">${esc(due.label)}</span>`:''}</div>
      </div>
      ${renderStage(row.status)}
      <div class="dc1-grid">
        ${summaryField('Fundamento',row.evidence_node_id?`Evidência ${String(row.evidence_node_id).slice(0,12)}…`:'','Ainda não associado')}
        ${summaryField('Ação',row.action,'Ainda não definida')}
        ${summaryField('Responsável / prazo',[row.owner,row.due_date?formatDate(row.due_date):null].filter(Boolean).join(' · '),'Ainda não definidos')}
        ${summaryField('Resultado esperado',row.expected_outcome,'Ainda não definido')}
        ${summaryField('Resultado observado',row.actual_outcome,'Ainda não registado')}
      </div>
      <div class="dc1-quality"><span>Completude operacional</span><div class="dc1-quality-track"><i style="width:${quality.percent}%"></i></div><b>${quality.complete}/${quality.total}</b></div>
      <details class="dc1-edit" ${row.status==='proposed'?'open':''}>
        <summary>Atualizar decisão e execução</summary>
        <div class="dc1-edit-body">
          <div class="dc1-form-grid">
            <div class="field"><label>Estado</label><select data-f="status">${statusOptions(row.status)}</select></div>
            <div class="field"><label>Responsável</label><input data-f="owner" maxlength="200" value="${esc(row.owner||'')}"></div>
            <div class="field"><label>Prazo</label><input data-f="due_date" type="date" value="${esc(row.due_date||'')}"></div>
          </div>
          <div class="field"><label>Ação executada / próxima ação</label><textarea data-f="action" maxlength="5000">${esc(row.action||'')}</textarea></div>
          <div class="field"><label>Resultado esperado</label><textarea data-f="expected_outcome" maxlength="5000">${esc(row.expected_outcome||'')}</textarea></div>
          <div class="field"><label>Resultado observado</label><textarea data-f="actual_outcome" maxlength="8000" placeholder="Registe o que aconteceu, incluindo efeitos não previstos.">${esc(row.actual_outcome||'')}</textarea></div>
          <div class="field"><label>Aprendizagem</label><textarea data-f="learning" maxlength="8000" placeholder="O que deve ser preservado, revisto ou não repetido numa missão futura?">${esc(row.learning||'')}</textarea></div>
          <div class="dc1-actions"><button class="btn btn-primary" type="button" data-dc-save="${esc(row.id)}">Guardar evolução</button>${ready?`<button class="btn btn-secondary" type="button" data-dc-materialize="${esc(row.id)}">Enviar aprendizagem para revisão</button>`:''}</div>
          <div class="dc1-inline" role="status" aria-live="polite"></div>
        </div>
      </details>
      ${learningNotice}
    </article>`;
  }

  function summaryField(label,value,empty){
    const missing=!String(value||'').trim();
    return `<div class="dc1-field ${missing?'missing':''}"><strong>${esc(label)}</strong><p>${esc(missing?empty:value)}</p></div>`;
  }

  function renderStage(status){
    if(status==='abandoned'){
      return `<div class="dc1-stage abandoned"><span>Proposta</span><span>Decidida</span><span>Execução</span><span>Abandonada</span></div>`;
    }
    const index=Math.max(0,statusOrder.indexOf(status));
    return `<div class="dc1-stage">${statusOrder.map((key,i)=>`<span class="${i<index?'done':i===index?'current':''}">${key==='proposed'?'Proposta':key==='committed'?'Decidida':key==='in_progress'?'Execução':'Concluída'}</span>`).join('')}</div>`;
  }

  function statusOptions(selected){
    return Object.entries(statusLabels).map(([value,label])=>`<option value="${value}" ${selected===value?'selected':''}>${label}</option>`).join('');
  }

  function qualityScore(row){
    const values=[row.evidence_node_id,row.action,row.owner,row.due_date,row.expected_outcome,row.actual_outcome,row.learning];
    return {complete:values.filter(v=>String(v||'').trim()).length,total:values.length,percent:Math.round(values.filter(v=>String(v||'').trim()).length/values.length*100)};
  }

  function needsAttention(row){
    if(row.status==='abandoned')return false;
    if(['committed','in_progress'].includes(row.status)&&(!row.evidence_node_id||!row.action||!row.owner||!row.expected_outcome))return true;
    if(row.status==='completed'&&(!row.actual_outcome||!row.learning))return true;
    return false;
  }

  function dueInfo(value,status){
    if(!value||['completed','abandoned'].includes(status))return {label:value?formatDate(value):'',className:'',overdue:false};
    const today=new Date();today.setHours(0,0,0,0);
    const due=new Date(`${value}T00:00:00`);
    const diff=Math.round((due-today)/86400000);
    if(diff<0)return {label:`Atrasada ${Math.abs(diff)} dia${Math.abs(diff)===1?'':'s'}`,className:'overdue',overdue:true};
    if(diff===0)return {label:'Prazo hoje',className:'today',overdue:false};
    if(diff<=7)return {label:`Faltam ${diff} dia${diff===1?'':'s'}`,className:'today',overdue:false};
    return {label:formatDate(value),className:'',overdue:false};
  }

  function formatDate(value){
    try{return new Intl.DateTimeFormat('pt-PT',{day:'2-digit',month:'short',year:'numeric'}).format(new Date(`${value}T00:00:00`));}catch{return value;}
  }

  function collect(card){
    const payload={};
    $$('[data-f]',card).forEach(field=>payload[field.dataset.f]=field.value||null);
    return payload;
  }

  function validateUpdate(payload){
    const status=payload.status;
    if(['committed','in_progress','completed'].includes(status)&&!String(payload.action||'').trim())return 'Defina a ação antes de avançar o estado da decisão.';
    if(['in_progress','completed'].includes(status)&&!String(payload.owner||'').trim())return 'Identifique o responsável antes de iniciar ou concluir a execução.';
    if(['in_progress','completed'].includes(status)&&!payload.due_date)return 'Defina o prazo antes de iniciar ou concluir a execução.';
    if(['committed','in_progress','completed'].includes(status)&&!String(payload.expected_outcome||'').trim())return 'Defina o resultado esperado para que a decisão possa ser avaliada.';
    if(status==='completed'&&!String(payload.actual_outcome||'').trim())return 'Registe o resultado observado antes de concluir a decisão.';
    if(status==='completed'&&!String(payload.learning||'').trim())return 'Registe a aprendizagem antes de concluir a decisão.';
    return '';
  }

  async function save(id){
    const card=$$('[data-cycle]').find(x=>x.dataset.cycle===id);
    if(!card)return;
    const payload=collect(card);
    const validation=validateUpdate(payload);
    if(validation){inline(card,validation,'error');return;}
    const button=$('[data-dc-save]',card);
    button?.classList.add('loading');
    inline(card,'A guardar a evolução…');
    try{
      await api(`/api/pilot/decision-cycles/${encodeURIComponent(id)}`,{method:'PATCH',body:JSON.stringify(payload)});
      inline(card,'Evolução guardada.','success');
      announce('O ciclo de decisão foi atualizado.','success');
      await load(true);
    }catch(err){
      inline(card,err.message,'error');
      announce(`Não foi possível atualizar a decisão: ${err.message}`,'error');
    }finally{
      button?.classList.remove('loading');
    }
  }

  async function materialize(id){
    const card=$$('[data-cycle]').find(x=>x.dataset.cycle===id);
    const button=$('[data-dc-materialize]',card);
    button?.classList.add('loading');
    inline(card,'A criar a linhagem de decisão, resultado e aprendizagem…');
    try{
      const data=await api(`/api/pilot/decision-cycles/${encodeURIComponent(id)}/materialize-learning`,{method:'POST'});
      inline(card,'Aprendizagem enviada para revisão humana no Evidence Graph.','success');
      announce('Resultado e aprendizagem materializados com linhagem explícita. Reveja a aprendizagem no Evidence Graph antes de a publicar na memória.','success');
      window.__srisLastLearningNode=data.learning_node_id;
      const graphButton=$('.mission-tabs [data-mission-tab="graph"]')||$('.mission-tabs [data-mission-tab="evidence"]');
      graphButton?.click();
      setTimeout(()=>$('#eg-sync')?.click(),250);
    }catch(err){
      inline(card,err.message,'error');
      announce(`Não foi possível enviar a aprendizagem para revisão: ${err.message}`,'error');
    }finally{
      button?.classList.remove('loading');
    }
  }

  function augmentWorkbench(){
    $$('.dw1-card').forEach(card=>{
      if($('[data-dw-cycle]',card))return;
      const actions=$('.dw1-actions',card);
      if(!actions)return;
      const button=document.createElement('button');
      button.className='btn btn-secondary';
      button.type='button';
      button.dataset.dwCycle='1';
      button.textContent='Rever como decisão';
      actions.appendChild(button);
    });
  }

  function augmentGraph(){
    const graph=window.__srisEvidenceGraph;
    if(graph){
      evidenceNodes=(graph.nodes||[]).filter(node=>node.node_type==='evidence'&&!['rejected','superseded'].includes(node.status));
      renderEvidenceOptions();
    }
    if(!graph?.nodes?.length)return;
    $$('.eg-node[data-type="learning"]').forEach(card=>{
      if($('.dc1-review',card))return;
      const title=$('.eg-node-head strong',card)?.textContent||'';
      const node=(graph.nodes||[]).find(item=>item.node_type==='learning'&&item.label===title);
      if(!node)return;
      const wrap=document.createElement('div');
      wrap.className='dc1-review';
      const reviewButtons=node.status==='proposed'
        ? `<button class="btn btn-secondary" type="button" data-learning-accept="${esc(node.id)}">Aceitar aprendizagem</button><button class="btn btn-secondary" type="button" data-learning-reject="${esc(node.id)}">Rejeitar</button>`
        : '';
      const publishButton=['accepted','verified'].includes(node.status)
        ? `<button class="btn btn-primary" type="button" data-learning-publish="${esc(node.id)}">Publicar na memória organizacional</button>`
        : '';
      wrap.innerHTML=`<div class="dc1-review-note">Governança da aprendizagem: revisão humana obrigatória antes de reutilização noutras missões.</div>${reviewButtons}${publishButton}<div class="dc1-inline"></div>`;
      card.appendChild(wrap);
      $('[data-learning-accept]',wrap)?.addEventListener('click',()=>reviewNode(node.id,'accepted',wrap));
      $('[data-learning-reject]',wrap)?.addEventListener('click',()=>reviewNode(node.id,'rejected',wrap));
      $('[data-learning-publish]',wrap)?.addEventListener('click',()=>publishLearning(node.id,wrap));
    });
  }

  function renderEvidenceOptions(selected=''){
    const select=$('#dc1-evidence-node');
    if(!select)return;
    const current=selected||select.value||'';
    select.innerHTML=`<option value="">${evidenceNodes.length?'Escolha evidência…':'Registe evidência documental ou manual primeiro'}</option>${evidenceNodes.map(node=>`<option value="${esc(node.id)}" ${current===node.id?'selected':''}>${esc((node.label||'Evidência').slice(0,100))} · ${esc(node.status||'proposta')}</option>`).join('')}`;
  }

  async function loadEvidenceOptions(selected=''){
    const code=missionCode();
    if(!code)return;
    try{
      const graph=await api(`/api/pilot/evidence-graph/missions/${encodeURIComponent(code)}`);
      window.__srisEvidenceGraph=graph;
      evidenceNodes=(graph.nodes||[]).filter(node=>node.node_type==='evidence'&&!['rejected','superseded'].includes(node.status));
      renderEvidenceOptions(selected);
    }catch(err){
      const select=$('#dc1-evidence-node');
      if(select)select.innerHTML='<option value="">Não foi possível carregar a evidência</option>';
      announce(`Não foi possível carregar os fundamentos disponíveis: ${err.message}`,'error');
    }
  }

  async function reviewNode(id,status,wrap){
    const code=missionCode();
    const button=$(`[data-learning-${status==='accepted'?'accept':'reject'}]`,wrap);
    button?.classList.add('loading');
    inline(wrap,status==='accepted'?'A aceitar aprendizagem…':'A rejeitar aprendizagem…');
    try{
      await api(`/api/pilot/evidence-graph/missions/${encodeURIComponent(code)}/nodes/${encodeURIComponent(id)}`,{method:'PATCH',body:JSON.stringify({status})});
      inline(wrap,status==='accepted'?'Aprendizagem aceite. Já pode ser publicada na memória organizacional.':'Aprendizagem rejeitada e excluída da memória reutilizável.','success');
      const graphStatus=$('#eg-status');
      if(graphStatus)graphStatus.textContent=status==='accepted'?'Aprendizagem aceite por revisão humana.':'Aprendizagem rejeitada por revisão humana.';
      setTimeout(()=>$('#eg-sync')?.click(),300);
    }catch(err){
      inline(wrap,err.message,'error');
    }finally{
      button?.classList.remove('loading');
    }
  }

  async function publishLearning(id,wrap){
    const code=missionCode();
    const button=$('[data-learning-publish]',wrap);
    button?.classList.add('loading');
    inline(wrap,'A publicar aprendizagem com linhagem verificável…');
    try{
      const packet=await api(`/api/pilot/learning/missions/${encodeURIComponent(code)}/publish/${encodeURIComponent(id)}`,{method:'POST'});
      wrap.innerHTML=`<div class="dc1-review-note"><strong>Publicada na memória organizacional</strong><br>Linhagem ${esc((packet.lineage_sha256||'').slice(0,16))}… · preserva evidência, decisão e resultado.</div>`;
      const graphStatus=$('#eg-status');
      if(graphStatus)graphStatus.textContent='Aprendizagem publicada com linhagem verificável. Pode surgir como candidata noutras missões, sempre sujeita a validação contextual.';
      document.dispatchEvent(new CustomEvent('sris:learning-published',{detail:{mission_code:code,node_id:id,packet}}));
    }catch(err){
      inline(wrap,err.message,'error');
    }finally{
      button?.classList.remove('loading');
    }
  }

  function boot(){
    if(!install()){
      document.addEventListener('DOMContentLoaded',()=>{install();load(false)},{once:true});
      return;
    }
    setTimeout(()=>load(false),420);
  }

  boot();
})();
