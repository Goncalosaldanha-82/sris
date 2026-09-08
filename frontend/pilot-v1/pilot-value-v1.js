(()=>{
  'use strict';

  const BUILD=document.querySelector('meta[name="sris-pilot-build"]')?.content||'integrated';
  const $=(selector,root=document)=>root.querySelector(selector);
  const $$=(selector,root=document)=>[...root.querySelectorAll(selector)];
  const esc=(value='')=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const orgId=()=>localStorage.getItem('sris_org_id')||'';
  const pilot=()=>window.SRISPlatform?.selected||null;
  const api=(path,options={})=>window.SRISApi?.request(path,options);
  const state={pilotId:'',value:null,team:null,reports:null,active:'',loading:false};

  const dimensionLabels={economic:'Económica',operational:'Operacional',resource:'Recursos',experience:'Experiência',governance:'Governação',learning:'Aprendizagem'};
  const statusLabels={expected:'Esperado',estimated:'Estimado',observed:'Observado',realized:'Realizado'};
  const roleLabels={sponsor:'Sponsor',pilot_owner:'Pilot Owner',mission_owner:'Mission Owner',data_owner:'Data Owner',operator:'Operação',reviewer:'Revisor',program_mentor:'Mentor do programa',observer:'Observador'};
  const reportLabels={pilot_brief:'Pilot Brief',data_readiness:'Data Readiness Report',decision_dossier:'Decision Dossier',progress:'Pilot Progress Report',outcome:'Pilot Outcome Report',scale_recommendation:'Scale Recommendation',full:'Dossier completo'};

  function base(){const current=pilot();return `/api/organizations/${encodeURIComponent(orgId())}/pilots/${encodeURIComponent(current?.id||'')}`;}
  function message(text,type='working'){
    const node=$('#pp-message');if(!node)return;
    node.textContent=text||'';node.dataset.state=text?type:'';
  }
  function value(value,unit=''){
    if(value==null||value==='')return'—';
    const formatted=new Intl.NumberFormat('pt-PT',{maximumFractionDigits:2}).format(Number(value));
    return `${formatted}${unit?` ${unit}`:''}`;
  }
  function download(filename,content,type='application/json'){
    const blob=new Blob([content],{type:`${type};charset=utf-8`});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=filename;document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
  }

  function installStyles(){
    if($('#pp-value-style'))return;
    const style=document.createElement('style');style.id='pp-value-style';style.textContent=`
      .pp-value-summary{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px}.pp-value-kpi{border:1px solid var(--line);border-radius:13px;background:#fff;padding:12px}.pp-value-kpi strong,.pp-value-kpi span{display:block}.pp-value-kpi strong{font-size:20px;color:var(--forest)}.pp-value-kpi span{margin-top:5px;color:var(--muted);font-size:7px;font-weight:850;letter-spacing:.06em;text-transform:uppercase}.pp-value-kpi.realized{background:#eff8f3;border-color:#bad6c5}.pp-value-kpi.evidence{background:#faf6ed;border-color:#ddcda8}
      .pp-value-list,.pp-team-list,.pp-report-grid{display:grid;gap:9px}.pp-value-item,.pp-team-item,.pp-report-card{border:1px solid var(--line);border-radius:14px;background:#fff;padding:14px}.pp-value-head,.pp-team-head,.pp-report-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.pp-value-head strong,.pp-team-head strong,.pp-report-head strong{font-size:12px;line-height:1.4}.pp-value-amount{font-size:18px!important;color:var(--forest)}.pp-value-proof{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin-top:10px}.pp-value-proof div{border-radius:10px;background:#f7f9f8;padding:9px}.pp-value-proof b,.pp-value-proof span{display:block}.pp-value-proof b{font-size:7px;color:var(--muted);letter-spacing:.06em;text-transform:uppercase}.pp-value-proof span{margin-top:4px;font-size:9px;line-height:1.45;white-space:pre-wrap}.pp-value-form{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.pp-value-form .wide{grid-column:1/-1}.pp-value-form .half{grid-column:span 2}.pp-value-form-actions{grid-column:1/-1;display:flex;gap:8px;flex-wrap:wrap}.pp-integrity-note{border-left:4px solid var(--gold);background:#fbf7ee;padding:13px;color:#6d5b37;font-size:10px;line-height:1.55}.pp-team-grid{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(280px,.8fr);gap:14px}.pp-permissions{display:flex;gap:5px;flex-wrap:wrap;margin-top:8px}.pp-permission{border-radius:999px;background:#edf3f0;padding:4px 7px;color:#48645a;font-size:7px;font-weight:850;text-transform:uppercase}.pp-report-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.pp-report-card{display:grid;gap:11px}.pp-report-actions{display:flex;gap:7px;flex-wrap:wrap}.pp-report-card p{margin:0;color:var(--muted);font-size:9px;line-height:1.5}.pp-custom-tab.active{background:#eaf3ef!important;color:var(--forest)!important}
      @media(max-width:1000px){.pp-value-summary{grid-template-columns:repeat(3,1fr)}.pp-team-grid{grid-template-columns:1fr}.pp-value-proof{grid-template-columns:1fr}.pp-value-form{grid-template-columns:repeat(2,1fr)}.pp-value-form .half{grid-column:1/-1}}
      @media(max-width:620px){.pp-value-summary,.pp-report-grid,.pp-value-form{grid-template-columns:1fr}.pp-value-form .wide,.pp-value-form .half{grid-column:auto}.pp-value-head,.pp-team-head,.pp-report-head{display:grid}.pp-value-form-actions .btn,.pp-report-actions .btn{width:100%}}
    `;document.head.appendChild(style);
  }

  function ensureTabs(){
    const tabs=$('#pp-detail .pp-tabs');if(!tabs||!pilot())return;
    if(!tabs.querySelector('[data-pp-extension="value"]')){
      const valueButton=document.createElement('button');valueButton.type='button';valueButton.className='pp-custom-tab';valueButton.dataset.ppExtension='value';valueButton.textContent='Valor do piloto';tabs.appendChild(valueButton);
      const teamButton=document.createElement('button');teamButton.type='button';teamButton.className='pp-custom-tab';teamButton.dataset.ppExtension='team';teamButton.textContent='Equipa e relatórios';tabs.appendChild(teamButton);
    }
  }

  async function synchronize(force=false){
    const current=pilot();if(!current||!orgId())return;
    ensureTabs();
    if(!force&&state.pilotId===current.id&&state.value&&state.team&&state.reports)return;
    state.pilotId=current.id;state.loading=true;
    try{
      const [valuePayload,teamPayload,reportPayload]=await Promise.all([
        api(`${base()}/value-case`),
        api(`${base()}/collaborators`),
        api(`${base()}/reports`),
      ]);
      state.value=valuePayload;state.team=teamPayload;state.reports=reportPayload;
      if(state.active)renderActive();
    }catch(error){message(error.message,'error');}
    finally{state.loading=false;}
  }

  function activate(name){
    state.active=name;ensureTabs();
    $$('#pp-detail .pp-tabs button').forEach(button=>button.classList.toggle('active',button.dataset.ppExtension===name));
    renderActive();
  }
  function renderActive(){
    const panel=$('#pp-detail .pp-panel');if(!panel)return;
    if(state.active==='value')panel.innerHTML=renderValue();
    else if(state.active==='team')panel.innerHTML=renderTeamAndReports();
  }

  function renderValue(){
    if(!state.value)return'<div class="pp-card"><div class="note">A sincronizar o valor do piloto…</div></div>';
    const monetary=state.value.monetary_eur||{};
    const items=state.value.items?.length?state.value.items.map(item=>`<article class="pp-value-item"><div class="pp-value-head"><div><div class="pp-tags"><span class="pp-tag">${esc(dimensionLabels[item.dimension]||item.dimension)}</span><span class="pp-tag ${item.value_status==='realized'?'success':item.value_status==='observed'?'':'attention'}">${esc(statusLabels[item.value_status]||item.value_status)}</span>${item.recurring?'<span class="pp-tag">recorrente</span>':''}</div><strong style="display:block;margin-top:8px">${esc(item.label)}</strong><div class="note">${esc(item.owner||'Responsável por atribuir')} · confiança ${esc(item.confidence||'não avaliável')}</div></div><div><strong class="pp-value-amount">${value(item.numeric_value,item.unit)}</strong><button class="inline-link" type="button" data-value-delete="${item.id}">Retirar</button></div></div><div class="pp-value-proof"><div><b>Período e baseline</b><span>${esc(item.period||'—')}\n${esc(item.baseline_reference||'—')}</span></div><div><b>Fonte e cálculo</b><span>${esc(item.source||'—')}\n${esc(item.calculation||'—')}</span></div><div><b>Atribuição e limites</b><span>${esc(item.attribution||'—')}\n${esc(item.limitations||'—')}</span></div></div></article>`).join(''):'<div class="note">Ainda não existem elementos de valor. Registe primeiro o que é esperado; promova apenas quando a prova o permitir.</div>';
    return `<section class="pp-value-summary"><div class="pp-value-kpi"><strong>${value(monetary.expected,'EUR')}</strong><span>Esperado</span></div><div class="pp-value-kpi"><strong>${value(monetary.estimated,'EUR')}</strong><span>Estimado</span></div><div class="pp-value-kpi"><strong>${value(monetary.observed,'EUR')}</strong><span>Observado</span></div><div class="pp-value-kpi realized"><strong>${value(monetary.realized,'EUR')}</strong><span>Realizado</span></div><div class="pp-value-kpi evidence"><strong>${state.value.evidence_completeness_pct||0}%</strong><span>Prova completa</span></div></section><section class="pp-card"><div class="pp-section-head"><div><div class="eyebrow">VALOR DO PILOTO</div><h3>Valor económico, operacional, de recursos, experiência, governação e aprendizagem</h3></div><span class="pp-status" style="background:#edf3f0;color:#405f53">${state.value.items?.length||0} elementos</span></div><div class="pp-value-list">${items}</div><details class="pp-form-card"><summary>+ Registar valor esperado, estimado, observado ou realizado</summary><form id="pp-value-form" class="pp-value-form"><div class="field"><label>Dimensão</label><select name="dimension">${Object.entries(dimensionLabels).map(([key,label])=>`<option value="${key}">${label}</option>`).join('')}</select></div><div class="field half"><label>Descrição</label><input name="label" required placeholder="Ex.: horas libertadas, água poupada, risco reduzido"></div><div class="field"><label>Estatuto</label><select name="value_status">${Object.entries(statusLabels).map(([key,label])=>`<option value="${key}">${label}</option>`).join('')}</select></div><div class="field"><label>Valor</label><input name="numeric_value" type="number" step="any"></div><div class="field"><label>Unidade</label><input name="unit" placeholder="EUR, h, L, kWh, %, índice"></div><div class="field"><label>Período</label><input name="period"></div><div class="field"><label>Confiança</label><select name="confidence"><option value="not_evaluable">Não avaliável</option><option value="low">Baixa</option><option value="moderate">Moderada</option><option value="high">Alta</option></select></div><div class="field"><label>Responsável</label><input name="owner"></div><div class="field wide"><label>Referência da baseline</label><textarea name="baseline_reference" rows="2"></textarea></div><div class="field wide"><label>Fonte</label><textarea name="source" rows="2"></textarea></div><div class="field wide"><label>Cálculo</label><textarea name="calculation" rows="2"></textarea></div><div class="field wide"><label>Avaliação de atribuição</label><textarea name="attribution" rows="2"></textarea></div><div class="field wide"><label>Limitações</label><textarea name="limitations" rows="2"></textarea></div><label class="field"><span>Recorrente</span><input name="recurring" type="checkbox" style="width:auto"></label><div class="pp-value-form-actions"><button class="btn btn-primary" type="submit">Guardar elemento de valor</button></div></form></details></section><div class="pp-integrity-note"><strong>Regra de integridade:</strong> esperado, estimado, observado e realizado são estatutos diferentes. Um valor realizado exige período, baseline, fonte, cálculo e avaliação de atribuição.</div>`;
  }

  function renderTeamAndReports(){
    if(!state.team||!state.reports)return'<div class="pp-card"><div class="note">A sincronizar equipa e relatórios…</div></div>';
    const collaborators=state.team.collaborators?.length?state.team.collaborators.map(person=>`<article class="pp-team-item"><div class="pp-team-head"><div><span class="pp-tag">${esc(roleLabels[person.role_key]||person.role_key)}</span><strong style="display:block;margin-top:8px">${esc(person.display_name)}</strong><div class="note">${esc(person.organization_name||'Organização não indicada')} · ${esc(person.email||'sem email associado')}</div><div class="pp-permissions">${person.can_edit?'<span class="pp-permission">pode editar</span>':''}${person.can_review?'<span class="pp-permission">pode rever</span>':''}${person.active?'<span class="pp-permission">ativo</span>':'<span class="pp-permission">inativo</span>'}</div></div><button class="inline-link" type="button" data-collaborator-delete="${person.id}">Retirar</button></div>${person.notes?`<p class="note">${esc(person.notes)}</p>`:''}</article>`).join(''):'<div class="note">Ainda não existe uma equipa formalizada para este piloto.</div>';
    const reports=(state.reports.reports||[]).map(report=>`<article class="pp-report-card"><div class="pp-report-head"><div><span class="pp-tag">${esc(report.type)}</span><strong style="display:block;margin-top:8px">${esc(reportLabels[report.type]||report.type)}</strong></div></div><p>${esc(reportDescription(report.type))}</p><div class="pp-report-actions"><button class="btn btn-secondary compact" type="button" data-report-download="${report.type}">Exportar JSON</button><button class="btn btn-secondary compact" type="button" data-report-print="${report.type}">Ver / imprimir</button></div></article>`).join('');
    return `<div class="pp-team-grid"><section class="pp-card"><div class="pp-section-head"><div><div class="eyebrow">EQUIPA DO PILOTO</div><h3>Papéis, autoridade e colaboração externa</h3></div><span class="pp-status" style="background:#edf3f0;color:#405f53">${state.team.collaborators?.length||0} pessoas</span></div><div class="pp-team-list">${collaborators}</div><details class="pp-form-card"><summary>+ Formalizar um papel no piloto</summary><form id="pp-collaborator-form" class="pp-value-form"><div class="field"><label>Papel</label><select name="role_key">${Object.entries(roleLabels).map(([key,label])=>`<option value="${key}">${label}</option>`).join('')}</select></div><div class="field half"><label>Nome</label><input name="display_name" required></div><div class="field"><label>Email</label><input name="email" type="email"></div><div class="field"><label>Organização</label><input name="organization_name"></div><div class="field wide"><label>Notas e limites de autoridade</label><textarea name="notes" rows="2"></textarea></div><label class="field"><span>Pode editar</span><input name="can_edit" type="checkbox" style="width:auto"></label><label class="field"><span>Pode rever</span><input name="can_review" type="checkbox" style="width:auto"></label><div class="pp-value-form-actions"><button class="btn btn-primary" type="submit">Adicionar à equipa</button></div></form></details></section><section class="pp-card"><div class="eyebrow">REPORT SUITE</div><h3>Entregáveis para programa, parceiro e cliente</h3><div class="pp-report-grid">${reports}</div></section></div>`;
  }

  function reportDescription(type){return {pilot_brief:'Problema, decisão, objetivo, contexto, governação e prontidão.',data_readiness:'Fontes, acesso, qualidade, baseline, métricas e limitações.',decision_dossier:'Missões, scorecard e Value Case ligados ao fundamento da decisão.',progress:'Plano, ações, marcos, bloqueios, responsáveis e estado atual.',outcome:'Baseline, resultado, valor, confiança e limites de atribuição.',scale_recommendation:'Condições para escalar, repetir, adaptar, suspender ou parar.',full:'Dossier consolidado com todas as secções verificáveis.'}[type]||'';}

  async function createValue(form){
    const data=new FormData(form);const payload={dimension:data.get('dimension'),label:data.get('label'),value_status:data.get('value_status'),numeric_value:data.get('numeric_value')===''?null:Number(data.get('numeric_value')),unit:data.get('unit'),recurring:data.get('recurring')==='on',period:data.get('period'),baseline_reference:data.get('baseline_reference'),source:data.get('source'),calculation:data.get('calculation'),attribution:data.get('attribution'),limitations:data.get('limitations'),confidence:data.get('confidence'),owner:data.get('owner')};
    await mutate(`${base()}/value-case/items`,'POST',payload,'Elemento de valor registado.');form.reset();
  }
  async function createCollaborator(form){
    const data=new FormData(form);const payload={role_key:data.get('role_key'),display_name:data.get('display_name'),email:data.get('email'),organization_name:data.get('organization_name'),can_edit:data.get('can_edit')==='on',can_review:data.get('can_review')==='on',active:true,notes:data.get('notes')};
    await mutate(`${base()}/collaborators`,'POST',payload,'Papel formalizado no piloto.');form.reset();
  }
  async function removeValue(id){await mutate(`${base()}/value-case/items/${encodeURIComponent(id)}`,'DELETE',null,'Elemento de valor retirado.');}
  async function removeCollaborator(id){await mutate(`${base()}/collaborators/${encodeURIComponent(id)}`,'DELETE',null,'Pessoa retirada da equipa do piloto.');}
  async function mutate(path,method,payload,success){
    message('A guardar e a registar na auditoria…','working');
    try{await api(path,{method,...(payload==null?{}:{body:JSON.stringify(payload)})});await synchronize(true);renderActive();message(success,'success');}
    catch(error){message(error.message,'error');throw error;}
  }

  async function report(type,mode){
    message('A gerar o relatório a partir do estado persistente…','working');
    try{const payload=await api(`${base()}/reports/${encodeURIComponent(type)}`);const name=`${String(pilot()?.code||'pilot').toLowerCase()}-${type}`;if(mode==='json')download(`${name}.json`,JSON.stringify(payload,null,2));else{const html=reportHtml(payload);const win=window.open('','_blank','noopener,noreferrer');if(!win)throw new Error('O browser bloqueou a janela do relatório.');win.document.write(html);win.document.close();win.focus();}message('Relatório gerado.','success');}
    catch(error){message(error.message,'error');}
  }
  function reportHtml(payload){const content=payload.content||payload.sections||{};return `<!doctype html><html lang="pt-PT"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>${esc(reportLabels[payload.report_type]||payload.report_type)}</title><style>body{margin:0;background:#f3f5f2;color:#142a23;font-family:Arial,sans-serif}main{max-width:980px;margin:auto;background:#fff;padding:50px}h1{font-family:Georgia,serif;font-size:42px;margin:7px 0 12px}.ey{color:#8a6a31;font-size:10px;font-weight:800;letter-spacing:.12em}.meta{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:20px 0}.box{border:1px solid #dce4df;padding:12px}.box b,.box span{display:block}.box b{font-size:9px;text-transform:uppercase;color:#68766f}.box span{margin-top:5px}pre{white-space:pre-wrap;overflow-wrap:anywhere;border-left:4px solid #b18c48;background:#f8f6ef;padding:18px;font:12px/1.6 ui-monospace,monospace}@media(max-width:700px){main{padding:25px}.meta{grid-template-columns:1fr}}@media print{body{background:#fff}main{padding:0}}</style></head><body><main><div class="ey">SRIS · PILOT & MISSION INTELLIGENCE</div><h1>${esc(reportLabels[payload.report_type]||payload.report_type)}</h1><p>${esc(payload.pilot?.title||'')}</p><div class="meta"><div class="box"><b>Código</b><span>${esc(payload.pilot?.code||'—')}</span></div><div class="box"><b>Parceiro</b><span>${esc(payload.pilot?.partner_name||'—')}</span></div><div class="box"><b>Contexto</b><span>${esc(payload.pilot?.context_name||'—')}</span></div></div><pre>${esc(JSON.stringify(content,null,2))}</pre></main></body></html>`;}

  document.addEventListener('click',event=>{
    const extension=event.target.closest('[data-pp-extension]');if(extension){activate(extension.dataset.ppExtension);return;}
    if(event.target.closest('#pp-detail .pp-tabs button:not(.pp-custom-tab)'))state.active='';
    const valueDelete=event.target.closest('[data-value-delete]');if(valueDelete){removeValue(valueDelete.dataset.valueDelete);return;}
    const collaboratorDelete=event.target.closest('[data-collaborator-delete]');if(collaboratorDelete){removeCollaborator(collaboratorDelete.dataset.collaboratorDelete);return;}
    const reportDownload=event.target.closest('[data-report-download]');if(reportDownload){report(reportDownload.dataset.reportDownload,'json');return;}
    const reportPrint=event.target.closest('[data-report-print]');if(reportPrint){report(reportPrint.dataset.reportPrint,'print');}
  });
  document.addEventListener('submit',event=>{
    if(event.target.id==='pp-value-form'){event.preventDefault();createValue(event.target);}
    if(event.target.id==='pp-collaborator-form'){event.preventDefault();createCollaborator(event.target);}
  });

  function boot(){installStyles();setInterval(()=>{const current=pilot();if(current){ensureTabs();if(state.pilotId!==current.id)synchronize(true);}},300);}
  window.SRISPilotValue={build:BUILD,refresh:()=>synchronize(true)};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
