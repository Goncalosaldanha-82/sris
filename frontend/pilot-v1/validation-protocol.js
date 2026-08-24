(()=>{
  'use strict';

  const BUILD='20260824-measurable-validation-v5';
  const state={mission:null,aggregate:null,evidence:[],loading:false};
  const profiles={
    measurable_decision:{
      label:'Validação mensurável transversal',
      description:'Compara uma baseline e um resultado observável, com fonte, meta e revisão humana.',
    },
    tourism_advance_resource_efficiency:{
      label:'Tourism Advance · Eficiência de recursos',
      description:'Normaliza água, energia, resíduos ou custo pela atividade real da unidade antes de avaliar a intervenção.',
    },
  };
  const targetLabels={met:'Meta atingida',missed:'Meta não atingida',indeterminate:'Não comparável',not_configured:'Meta não configurada'};
  const eventLabels={protocol_seeded:'Perfil inicial criado',protocol_created:'Protocolo criado',protocol_updated:'Protocolo revisto',baseline_recorded:'Baseline registada',result_recorded:'Resultado registado',attribution_reviewed:'Atribuição revista'};

  const $=(selector,root=document)=>root.querySelector(selector);
  const $$=(selector,root=document)=>[...root.querySelectorAll(selector)];
  const esc=(value='')=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const root=()=>$('#validation-root');
  const number=(value,digits=4)=>{
    const parsed=Number(value);
    return Number.isFinite(parsed)?parsed.toLocaleString('pt-PT',{maximumFractionDigits:digits}):'—';
  };
  const nullableNumber=value=>String(value??'').trim()===''?null:Number(value);
  const formValue=(form,name)=>String(new FormData(form).get(name)||'').trim();
  const isoDate=value=>String(value||'').slice(0,10);
  const revision=()=>state.aggregate?.protocol?.revision||null;

  async function api(path,options={}){
    if(window.SRISApi?.request)return window.SRISApi.request(path,options);
    const token=localStorage.getItem('sris_access_token');
    const requestHeaders={'Content-Type':'application/json',...(options.headers||{})};
    if(token)requestHeaders.Authorization=`Bearer ${token}`;
    const response=await fetch(path,{...options,headers:requestHeaders,cache:'no-store'});
    let data={};
    try{data=await response.json()}catch{}
    if(!response.ok){
      const detail=data?.detail;
      throw new Error(typeof detail==='string'?detail:(detail?.message||detail?.code||`Erro ${response.status}`));
    }
    return data;
  }

  function profileCode(){
    const configured=state.aggregate?.protocol?.profile||state.aggregate?.profile||state.mission?.validation_profile;
    return configured&&configured!=='none'?configured:'measurable_decision';
  }

  function evidenceOptions(selected=''){
    const choices=state.evidence.filter(node=>node.node_type==='evidence'&&!['rejected','superseded'].includes(node.status));
    const empty=choices.length?'Selecione a evidência que sustenta esta medição':'Crie primeiro uma evidência no Grafo de Evidência';
    return `<option value="">${esc(empty)}</option>${choices.map(node=>`<option value="${esc(node.id)}" ${node.id===selected?'selected':''}>${esc(node.label||'Evidência')} · ${esc(node.status||'proposta')}</option>`).join('')}`;
  }

  function readinessHtml(){
    const readiness=state.aggregate?.readiness||{};
    const checks=Array.isArray(readiness.checks)?readiness.checks:[];
    if(!checks.length)return'<div class="vp-readiness-empty">Ative um perfil para acrescentar validação quantitativa a esta missão.</div>';
    return `<div class="vp-readiness-head"><div><span>PRONTIDÃO DA VALIDAÇÃO</span><strong>${Number(readiness.progress_percent||0)}%</strong></div><small>${Number(readiness.completed_checks||0)} de ${Number(readiness.total_checks||0)} condições verificadas</small></div><div class="vp-checks">${checks.map(check=>`<div class="vp-check ${check.passed?'passed':''}"><span>${check.passed?'✓':'○'}</span><strong>${esc(check.label)}</strong></div>`).join('')}</div>`;
  }

  function protocolForm(){
    const protocol=state.aggregate?.protocol||{};
    const currentProfile=profileCode();
    return `<details class="vp-section" open>
      <summary><span><b>01</b><strong>Definir o protocolo</strong></span><small>âmbito · indicador · meta · intervenção</small></summary>
      <form id="vp-protocol-form" class="vp-form">
        <div class="vp-grid two">
          <div class="field"><label for="vp-profile">Perfil</label><select id="vp-profile" name="profile"><option value="measurable_decision" ${currentProfile==='measurable_decision'?'selected':''}>Validação mensurável transversal</option><option value="tourism_advance_resource_efficiency" ${currentProfile==='tourism_advance_resource_efficiency'?'selected':''}>Tourism Advance · Eficiência de recursos</option></select></div>
          <div class="field"><label for="vp-subject-type">Tipo de unidade</label><input id="vp-subject-type" name="subject_type" maxlength="200" value="${esc(protocol.subject_type||'')}" placeholder="Ex.: unidade de alojamento, edifício, equipa"></div>
        </div>
        <div id="vp-profile-description" class="vp-profile-description"></div>
        <div class="field"><label for="vp-subject">Unidade observada</label><input id="vp-subject" name="subject" maxlength="500" value="${esc(protocol.subject||'')}" placeholder="Ex.: Hotel piloto · edifício principal"></div>
        <div class="field"><label for="vp-problem">Problema a validar</label><textarea id="vp-problem" name="problem_statement" rows="3" maxlength="5000" placeholder="Que mudança precisa de ser demonstrada e em que âmbito?">${esc(protocol.problem_statement||state.mission?.central_question||'')}</textarea></div>
        <div class="vp-grid four">
          <div class="field"><label for="vp-indicator">Indicador</label><input id="vp-indicator" name="indicator_name" maxlength="300" value="${esc(protocol.indicator_name||'')}" placeholder="Ex.: Consumo de água"></div>
          <div class="field"><label for="vp-indicator-unit">Unidade</label><input id="vp-indicator-unit" name="indicator_unit" maxlength="80" value="${esc(protocol.indicator_unit||'')}" placeholder="Ex.: m³"></div>
          <div class="field"><label for="vp-direction">Direção desejada</label><select id="vp-direction" name="desired_direction"><option value="decrease" ${protocol.desired_direction!=='increase'&&protocol.desired_direction!=='maintain'&&protocol.desired_direction!=='target'?'selected':''}>Reduzir</option><option value="increase" ${protocol.desired_direction==='increase'?'selected':''}>Aumentar</option><option value="maintain" ${protocol.desired_direction==='maintain'?'selected':''}>Manter</option><option value="target" ${protocol.desired_direction==='target'?'selected':''}>Atingir valor</option></select></div>
          <div class="field"><label for="vp-target">Meta numérica</label><input id="vp-target" name="target_value" type="number" step="any" value="${protocol.target_value??''}" placeholder="Valor normalizado"></div>
        </div>
        <div class="vp-grid two">
          <div class="field"><label for="vp-denominator">Atividade para normalização</label><input id="vp-denominator" name="denominator_name" maxlength="300" value="${esc(protocol.denominator_name||'')}" placeholder="Ex.: Quartos ocupados"></div>
          <div class="field"><label for="vp-denominator-unit">Unidade da atividade</label><input id="vp-denominator-unit" name="denominator_unit" maxlength="80" value="${esc(protocol.denominator_unit||'')}" placeholder="Ex.: quarto ocupado"></div>
        </div>
        <div class="field"><label for="vp-target-description">Critério da meta</label><textarea id="vp-target-description" name="target_description" rows="2" maxlength="3000" placeholder="Defina o valor, horizonte e condição de sucesso.">${esc(protocol.target_description||'')}</textarea></div>
        <div class="field"><label for="vp-intervention">Intervenção a testar</label><textarea id="vp-intervention" name="intervention_description" rows="3" maxlength="5000" placeholder="O que muda, onde, por quem e com que reversibilidade?">${esc(protocol.intervention_description||'')}</textarea></div>
        <div class="vp-grid three">
          <div class="field"><label for="vp-start">Início da intervenção</label><input id="vp-start" name="intervention_start_date" type="date" value="${esc(isoDate(protocol.intervention_start_date))}"></div>
          <div class="field"><label for="vp-end">Fim da intervenção</label><input id="vp-end" name="intervention_end_date" type="date" value="${esc(isoDate(protocol.intervention_end_date))}"></div>
          <div class="field"><label for="vp-review-date">Data de revisão</label><input id="vp-review-date" name="review_date" type="date" value="${esc(isoDate(protocol.review_date))}"></div>
        </div>
        <div class="vp-grid two">
          <div class="field"><label for="vp-guardrails">Guardrails</label><textarea id="vp-guardrails" name="guardrails" rows="3" maxlength="5000" placeholder="Que resultados não podem degradar?">${esc(protocol.guardrails||'')}</textarea></div>
          <div class="field"><label for="vp-method">Método de atribuição</label><textarea id="vp-method" name="attribution_method" rows="3" maxlength="5000" placeholder="Como serão consideradas sazonalidade, atividade e fatores externos?">${esc(protocol.attribution_method||'')}</textarea></div>
        </div>
        <div class="vp-actions"><button class="btn btn-primary" type="submit">${protocol.id?'Guardar nova revisão':'Ativar e guardar protocolo'}</button><span class="note">Pode guardar uma estrutura incompleta; a prontidão identifica o que falta.</span></div>
        <div class="vp-message" data-message="protocol" role="status" aria-live="polite"></div>
      </form>
    </details>`;
  }

  function measurementForm(phase,label,index){
    const row=state.aggregate?.[phase]||{};
    const protocol=state.aggregate?.protocol||{};
    const denominatorRequired=Boolean(state.aggregate?.analysis?.denominator_required);
    return `<form class="vp-measurement vp-form" data-phase="${phase}">
      <div class="vp-measurement-title"><span>${index}</span><div><strong>${label}</strong><small>${phase==='baseline'?'Período anterior à intervenção':'Período posterior, com base comparável'}</small></div></div>
      <div class="vp-grid two">
        <div class="field"><label>Início do período</label><input name="period_start" type="date" required value="${esc(isoDate(row.period_start))}"></div>
        <div class="field"><label>Fim do período</label><input name="period_end" type="date" required value="${esc(isoDate(row.period_end))}"></div>
      </div>
      <div class="vp-grid two">
        <div class="field"><label>${esc(protocol.indicator_name||'Valor do indicador')} (${esc(protocol.indicator_unit||'unidade')})</label><input name="numerator_value" type="number" step="any" required value="${row.numerator_value??''}"></div>
        <div class="field"><label>${esc(protocol.denominator_name||'Atividade para normalização')}${denominatorRequired?' *':''}</label><input name="denominator_value" type="number" min="0.00000001" step="any" ${denominatorRequired?'required':''} value="${row.denominator_value??''}"></div>
      </div>
      <div class="field"><label>Evidência de origem</label><select name="evidence_node_id" required>${evidenceOptions(row.evidence_node_id||'')}</select><div class="note">A medição só é válida quando ligada a uma evidência preservada na própria missão.</div></div>
      <div class="vp-grid two">
        <div class="field"><label>Qualidade dos dados</label><select name="data_quality"><option value="high" ${row.data_quality==='high'?'selected':''}>Alta</option><option value="moderate" ${!row.data_quality||row.data_quality==='moderate'?'selected':''}>Moderada</option><option value="low" ${row.data_quality==='low'?'selected':''}>Baixa</option></select></div>
        <div class="field"><label>Notas metodológicas</label><textarea name="notes" rows="2" maxlength="5000">${esc(row.notes||'')}</textarea></div>
      </div>
      <div class="vp-measurement-result"><span>Valor normalizado</span><strong>${row.normalized_value!==undefined&&row.normalized_value!==null?`${number(row.normalized_value)} ${esc(state.aggregate?.analysis?.normalized_unit||'')}`:'Calculado ao guardar'}</strong></div>
      <button class="btn btn-secondary" type="submit">Guardar ${label.toLowerCase()}</button>
      <div class="vp-message" data-message="${phase}" role="status" aria-live="polite"></div>
    </form>`;
  }

  function comparisonHtml(){
    const analysis=state.aggregate?.analysis||{};
    const baseline=state.aggregate?.baseline;
    const result=state.aggregate?.result;
    const status=targetLabels[analysis.target_status]||analysis.target_status||'Por avaliar';
    const change=analysis.comparable?`${analysis.absolute_change>0?'+':''}${number(analysis.absolute_change)} ${esc(analysis.normalized_unit||'')}`:'—';
    const percent=analysis.comparable&&analysis.percent_change!==null?`${analysis.percent_change>0?'+':''}${number(analysis.percent_change,2)}%`:'—';
    return `<section class="vp-comparison ${analysis.target_status==='met'?'met':analysis.target_status==='missed'?'missed':''}">
      <div class="vp-comparison-head"><div><span class="product-index">CÁLCULO DETERMINÍSTICO · SEM IA</span><h4>Baseline → resultado comparável</h4></div><strong>${esc(status)}</strong></div>
      <div class="vp-comparison-grid"><div><span>Baseline</span><strong>${baseline?number(baseline.normalized_value):'—'}</strong><small>${esc(analysis.normalized_unit||'')}</small></div><div><span>Resultado</span><strong>${result?number(result.normalized_value):'—'}</strong><small>${esc(analysis.normalized_unit||'')}</small></div><div><span>Variação</span><strong>${change}</strong><small>${percent}</small></div><div><span>Meta</span><strong>${number(analysis.target_value)}</strong><small>${esc(analysis.normalized_unit||'')}</small></div></div>
      <p>${analysis.comparable?'Os valores foram calculados pela mesma regra e os períodos respeitam a sequência temporal.':'São necessárias medições comparáveis, com períodos coerentes e a mesma normalização.'}</p>
    </section>`;
  }

  function reviewForm(){
    const protocol=state.aggregate?.protocol||{};
    const canReview=Boolean(state.aggregate?.baseline&&state.aggregate?.result);
    return `<details class="vp-section" ${protocol.reviewed_at?'':'open'}>
      <summary><span><b>04</b><strong>Rever a atribuição</strong></span><small>causalidade · limites · fatores externos</small></summary>
      <form id="vp-review-form" class="vp-form">
        <div class="vp-grid two">
          <div class="field"><label for="vp-confidence">Confiança na atribuição</label><select id="vp-confidence" name="attribution_confidence"><option value="high" ${protocol.attribution_confidence==='high'?'selected':''}>Alta</option><option value="moderate" ${!protocol.attribution_confidence||protocol.attribution_confidence==='moderate'?'selected':''}>Moderada</option><option value="low" ${protocol.attribution_confidence==='low'?'selected':''}>Baixa</option><option value="not_evaluable" ${protocol.attribution_confidence==='not_evaluable'?'selected':''}>Não avaliável</option></select></div>
          <div class="vp-review-state"><span>Revisão humana</span><strong>${protocol.reviewed_at?new Date(protocol.reviewed_at).toLocaleString('pt-PT'):'Pendente'}</strong></div>
        </div>
        <div class="field"><label for="vp-rationale">Racional de atribuição</label><textarea id="vp-rationale" name="review_rationale" minlength="10" maxlength="5000" required placeholder="Porque é razoável — ou não — associar a mudança à intervenção?">${esc(protocol.review_rationale||'')}</textarea></div>
        <div class="field"><label for="vp-limitations">Limitações</label><textarea id="vp-limitations" name="limitations" minlength="10" maxlength="5000" required placeholder="Que limitações reduzem a confiança desta leitura?">${esc(protocol.limitations||'')}</textarea></div>
        <div class="vp-grid two">
          <div class="field"><label for="vp-external">Fatores externos</label><textarea id="vp-external" name="external_factors" rows="3" maxlength="5000" placeholder="Sazonalidade, ocupação, clima, obras, alteração de mix…">${esc(protocol.external_factors||'')}</textarea></div>
          <div class="field"><label for="vp-deviation">Desvio de implementação</label><textarea id="vp-deviation" name="implementation_deviation" rows="3" maxlength="5000" placeholder="O que foi executado de forma diferente do previsto?">${esc(protocol.implementation_deviation||'')}</textarea></div>
        </div>
        <div class="vp-actions"><button class="btn btn-primary" type="submit" ${canReview?'':'disabled'}>Registar revisão de atribuição</button><span class="note">Exige baseline e resultado. A revisão é reservada a revisor ou administrador.</span></div>
        <div class="vp-message" data-message="review" role="status" aria-live="polite"></div>
      </form>
    </details>`;
  }

  function historyHtml(){
    const protocol=state.aggregate?.protocol;
    const history=state.aggregate?.history||[];
    if(!protocol)return'';
    return `<details class="vp-history"><summary>Integridade e revisões preservadas</summary><div class="vp-hash"><span>Revisão atual ${Number(protocol.revision||1)}</span><code>SHA-256 ${esc(protocol.content_hash||'a sincronizar')}</code></div>${history.length?history.map(item=>`<div class="vp-history-row"><span>r${Number(item.revision||1)}</span><div><strong>${esc(eventLabels[item.event_type]||item.event_type)}</strong><small>${item.created_at?new Date(item.created_at).toLocaleString('pt-PT'):''}</small></div><code>${esc(String(item.content_hash||'').slice(0,16))}…</code></div>`).join(''):'<div class="note">Sem eventos registados.</div>'}</details>`;
  }

  function render(){
    const container=root();
    if(!container)return;
    if(state.loading){container.innerHTML='<div class="vp-loading">A sincronizar o protocolo, as medições e a evidência…</div>';return;}
    if(!state.mission){container.innerHTML='<div class="vp-loading">Abra uma missão para estruturar a sua validação.</div>';return;}
    const aggregate=state.aggregate||{required:false,profile:state.mission.validation_profile||'none',protocol:null,readiness:{checks:[]},analysis:{}};
    state.aggregate=aggregate;
    const configured=Boolean(aggregate.protocol);
    container.innerHTML=`<div class="vp-shell" data-build="${BUILD}">
      <header class="vp-hero"><div><span class="product-index">PROTOCOLO DE VALIDAÇÃO</span><h3>Do resultado observado ao impacto defensável.</h3><p>O SRIS preserva a amplitude da missão e acrescenta uma camada mensurável quando ela é necessária. O perfil Tourism Advance é uma configuração especializada desta arquitetura transversal.</p></div><span class="vp-state ${aggregate.readiness?.ready?'ready':''}">${aggregate.readiness?.ready?'Validado':configured?'Em construção':'Opcional'}</span></header>
      <div class="vp-chain" aria-label="Percurso de validação"><span>Âmbito</span><i>→</i><span>Indicador</span><i>→</i><span>Baseline</span><i>→</i><span>Intervenção</span><i>→</i><span>Resultado</span><i>→</i><span>Atribuição</span></div>
      <section class="vp-readiness">${readinessHtml()}</section>
      ${protocolForm()}
      ${configured?`<section class="vp-section-static"><div class="vp-section-title"><span><b>02–03</b><strong>Medir antes e depois</strong></span><small>fonte · período · normalização</small></div><div class="vp-measure-grid">${measurementForm('baseline','Baseline','02')}${measurementForm('result','Resultado','03')}</div></section>${comparisonHtml()}${reviewForm()}${historyHtml()}`:'<div class="vp-gate"><strong>Primeiro, guarde o protocolo.</strong><span>Depois poderá ligar a baseline e o resultado a evidência da missão e obter uma comparação reproduzível.</span></div>'}
    </div>`;
    bind();
  }

  function message(key,text,stateName=''){
    const box=$(`[data-message="${key}"]`,root());
    if(!box)return;
    box.textContent=text||'';
    box.dataset.state=stateName;
  }

  function syncProfilePresentation(){
    const select=$('#vp-profile',root());
    const description=$('#vp-profile-description',root());
    const code=select?.value||profileCode();
    if(description)description.innerHTML=`<strong>${esc(profiles[code]?.label||code)}</strong><span>${esc(profiles[code]?.description||'')}</span>`;
    const tourism=code==='tourism_advance_resource_efficiency';
    const denominator=$('#vp-denominator',root());
    const denominatorUnit=$('#vp-denominator-unit',root());
    if(denominator)denominator.placeholder=tourism?'Ex.: Quartos ocupados':'Opcional para indicadores absolutos';
    if(denominatorUnit)denominatorUnit.placeholder=tourism?'Ex.: quarto ocupado':'Ex.: utilizador, unidade produzida';
  }

  async function saveProtocol(event){
    event.preventDefault();
    const form=event.currentTarget;
    const button=event.submitter;
    button?.classList.add('loading');
    const payload={
      expected_revision:revision(),
      profile:formValue(form,'profile'),
      subject:formValue(form,'subject'),
      subject_type:formValue(form,'subject_type'),
      problem_statement:formValue(form,'problem_statement'),
      indicator_name:formValue(form,'indicator_name'),
      indicator_unit:formValue(form,'indicator_unit'),
      desired_direction:formValue(form,'desired_direction')||'decrease',
      denominator_name:formValue(form,'denominator_name'),
      denominator_unit:formValue(form,'denominator_unit'),
      target_value:nullableNumber(formValue(form,'target_value')),
      target_description:formValue(form,'target_description'),
      guardrails:formValue(form,'guardrails'),
      intervention_description:formValue(form,'intervention_description'),
      intervention_start_date:formValue(form,'intervention_start_date')||null,
      intervention_end_date:formValue(form,'intervention_end_date')||null,
      review_date:formValue(form,'review_date')||null,
      attribution_method:formValue(form,'attribution_method'),
    };
    try{
      state.aggregate=await api(`/api/pilot/validation/missions/${encodeURIComponent(state.mission.code)}/protocol`,{method:'PUT',body:JSON.stringify(payload)});
      document.dispatchEvent(new CustomEvent('sris:validation-updated',{detail:state.aggregate}));
      render();
      message('protocol','Protocolo guardado numa nova revisão verificável.','success');
    }catch(error){message('protocol',error.message,'error');}
    finally{button?.classList.remove('loading');}
  }

  async function saveMeasurement(event){
    event.preventDefault();
    const form=event.currentTarget;
    const phase=form.dataset.phase;
    const button=event.submitter;
    button?.classList.add('loading');
    const payload={
      expected_revision:revision(),
      period_start:formValue(form,'period_start'),
      period_end:formValue(form,'period_end'),
      numerator_value:Number(formValue(form,'numerator_value')),
      denominator_value:nullableNumber(formValue(form,'denominator_value')),
      evidence_node_id:formValue(form,'evidence_node_id'),
      data_quality:formValue(form,'data_quality')||'moderate',
      notes:formValue(form,'notes'),
    };
    try{
      state.aggregate=await api(`/api/pilot/validation/missions/${encodeURIComponent(state.mission.code)}/measurements/${phase}`,{method:'PUT',body:JSON.stringify(payload)});
      document.dispatchEvent(new CustomEvent('sris:validation-updated',{detail:state.aggregate}));
      render();
      message(phase,`${phase==='baseline'?'Baseline':'Resultado'} guardado e normalizado sem IA.`,'success');
    }catch(error){message(phase,error.message,'error');}
    finally{button?.classList.remove('loading');}
  }

  async function saveReview(event){
    event.preventDefault();
    const form=event.currentTarget;
    const button=event.submitter;
    button?.classList.add('loading');
    const payload={
      expected_revision:revision(),
      attribution_confidence:formValue(form,'attribution_confidence'),
      review_rationale:formValue(form,'review_rationale'),
      limitations:formValue(form,'limitations'),
      external_factors:formValue(form,'external_factors'),
      implementation_deviation:formValue(form,'implementation_deviation'),
    };
    try{
      state.aggregate=await api(`/api/pilot/validation/missions/${encodeURIComponent(state.mission.code)}/review`,{method:'POST',body:JSON.stringify(payload)});
      document.dispatchEvent(new CustomEvent('sris:validation-updated',{detail:state.aggregate}));
      render();
      message('review','Atribuição, limitações e fatores externos preservados com revisão humana.','success');
    }catch(error){message('review',error.message,'error');}
    finally{button?.classList.remove('loading');}
  }

  function bind(){
    $('#vp-protocol-form',root())?.addEventListener('submit',saveProtocol);
    $('#vp-profile',root())?.addEventListener('change',syncProfilePresentation);
    $$('.vp-measurement',root()).forEach(form=>form.addEventListener('submit',saveMeasurement));
    $('#vp-review-form',root())?.addEventListener('submit',saveReview);
    syncProfilePresentation();
  }

  async function load(){
    if(!state.mission)return;
    const missionCode=state.mission.code;
    state.loading=true;
    render();
    const [aggregateResult,evidenceResult]=await Promise.allSettled([
      api(`/api/pilot/validation/missions/${encodeURIComponent(missionCode)}`),
      api(`/api/pilot/evidence-graph/missions/${encodeURIComponent(missionCode)}`),
    ]);
    if(!state.mission||state.mission.code!==missionCode)return;
    state.loading=false;
    if(aggregateResult.status==='fulfilled')state.aggregate=aggregateResult.value;
    else state.aggregate={required:false,profile:state.mission.validation_profile||'none',protocol:null,analysis:{},readiness:{checks:[]},load_error:aggregateResult.reason?.message||'Falha de sincronização'};
    state.evidence=evidenceResult.status==='fulfilled'?(evidenceResult.value.nodes||[]):[];
    render();
    if(state.aggregate.load_error)message('protocol',state.aggregate.load_error,'error');
  }

  document.addEventListener('sris:mission-opened',event=>{
    state.mission=event.detail?.mission||null;
    state.aggregate=null;
    state.evidence=[];
    void load();
  });
  document.addEventListener('sris:evidence-graph-updated',event=>{
    if(state.mission){
      state.evidence=event.detail?.nodes||state.evidence;
      if($('[data-mission-tab="validation"]')?.classList.contains('active'))void load();
    }
  });
  document.addEventListener('click',event=>{
    if(event.target.closest?.('[data-mission-tab="validation"]')&&state.mission)setTimeout(()=>void load(),0);
  },true);

  window.SRISValidationProtocol={build:BUILD,reload:load,getState:()=>({...state})};
  render();
})();
