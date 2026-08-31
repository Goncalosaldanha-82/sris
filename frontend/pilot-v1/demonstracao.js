(()=>{
  'use strict';
  const $=selector=>document.querySelector(selector);
  const esc=value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#039;');
  const set=(selector,value)=>{const element=$(selector);if(element)element.textContent=value||'—';};
  const money=value=>Number.isFinite(value)?new Intl.NumberFormat('pt-PT',{style:'currency',currency:'EUR',maximumFractionDigits:0}).format(value):'Pendente';
  const unitMoney=value=>Number.isFinite(value)?new Intl.NumberFormat('pt-PT',{style:'currency',currency:'EUR',minimumFractionDigits:value<1?2:0,maximumFractionDigits:2}).format(value):'Pendente';
  const number=value=>Number.isFinite(value)?new Intl.NumberFormat('pt-PT').format(value):'Pendente';
  const metric=(label,value,detail='')=>`<div class="financial-metric"><span>${esc(label)}</span><strong>${esc(value)}</strong>${detail?`<small>${esc(detail)}</small>`:''}</div>`;
  let activeScenarioId='central';

  function renderMatrix(matrix={}){
    set('#matrix-scale',matrix.scale);
    const criteria=matrix.criteria||[];
    $('#matrix-head').innerHTML=`<tr><th>Alternativa</th>${criteria.map(item=>`<th>${esc(item.label)}</th>`).join('')}<th>Total</th></tr>`;
    $('#matrix-body').innerHTML=(matrix.rows||[]).map(row=>`<tr class="${row.alternative_id==='ALT-TA-002'?'preferred-row':''}"><th>${esc(row.label)}${row.alternative_id==='ALT-TA-002'?'<small>Preferida sob validação</small>':''}</th>${(row.scores||[]).map(score=>`<td><span class="score score-${esc(score)}">${esc(score)}</span></td>`).join('')}<td><strong>${esc(row.total)}</strong></td></tr>`).join('');
  }

  function renderEvidenceGraph(graph={}){
    const nodes=graph.nodes||[];
    const byKind=kind=>nodes.filter(node=>node.kind===kind);
    const nodeButton=node=>`<button type="button" class="graph-node" data-node-id="${esc(node.id)}"><small>${esc(node.kind)}</small><strong>${esc(node.label)}</strong></button>`;
    $('#evidence-graph').innerHTML=`<div class="graph-column evidence-source">${byKind('Evidência').map(nodeButton).join('')}</div><span class="graph-arrow" aria-hidden="true">→</span><div class="graph-column">${byKind('Hipótese').map(nodeButton).join('')}</div><span class="graph-arrow" aria-hidden="true">→</span><div class="graph-column">${byKind('Alternativa').map(nodeButton).join('')}</div><span class="graph-arrow" aria-hidden="true">→</span><div class="graph-column">${byKind('Decisão').map(nodeButton).join('')}</div>`;
    const show=node=>{document.querySelectorAll('.graph-node').forEach(button=>button.classList.toggle('active',button.dataset.nodeId===node.id));$('#graph-detail').innerHTML=`<span>${esc(node.kind)} · ${esc(node.id)}</span><strong>${esc(node.label)}</strong><p>${esc(node.detail)}</p>`;};
    document.querySelectorAll('.graph-node').forEach(button=>button.addEventListener('click',()=>{const node=nodes.find(item=>item.id===button.dataset.nodeId);if(node)show(node);}));
    if(nodes[0])show(nodes[0]);
  }

  function renderBusinessCase(data={}){
    const baseline=data.baseline||{},pilot=data.pilot||{},actual=data.actual||{},scenarios=data.scenarios||[];
    const projection=scenarios.find(item=>item.id===activeScenarioId)||scenarios.find(item=>item.id===data.selected_scenario_id)||data.projection||{};
    activeScenarioId=projection.id||data.selected_scenario_id||'central';
    set('#business-case-notice',data.notice);
    $('#scenario-controls').innerHTML=scenarios.map(item=>`<button type="button" data-scenario-id="${esc(item.id)}" class="${item.id===activeScenarioId?'active':''}" aria-pressed="${item.id===activeScenarioId?'true':'false'}">${esc(item.label)}</button>`).join('');
    $('#business-case-timeline').innerHTML=`
      <article class="economy-phase"><div class="phase-heading"><span>ANTES</span><strong>${esc(baseline.status)}</strong></div>
        ${metric('Água + energia',`${money(baseline.annual_resource_spend_eur)} / ano`,baseline.annual_resource_spend_basis)}
        ${metric('Perda operacional evitável',`${money(baseline.avoidable_operating_loss_eur)} / ano`,baseline.avoidable_operating_loss_basis)}
        ${metric('Receita sob risco',`${money(baseline.revenue_at_risk_eur)} / ano`,baseline.revenue_at_risk_basis)}
      </article>
      <article class="economy-phase"><div class="phase-heading"><span>DURANTE</span><strong>${esc(pilot.status)}</strong></div>
        ${metric('Investimento do piloto',money(pilot.investment_eur))}
        ${metric('Equipamento e instrumentação',money(pilot.equipment_eur))}
        ${metric('Custo interno da equipa',money(pilot.internal_people_cost_eur))}
        ${metric('Duração e esforço',`${esc(pilot.duration_weeks)} semanas · ${esc(pilot.internal_hours)} h`)}
        ${metric('Interrupção planeada',`≤ ${esc(pilot.planned_interruption_hours)} h`)}
      </article>
      <article class="economy-phase projection"><div class="phase-heading"><span>DEPOIS · CENÁRIO ${esc(projection.label||'CENTRAL').toUpperCase()}</span><strong>${esc(projection.status)}</strong></div>
        <div class="provenance-box"><span>ORIGEM DA POUPANÇA DIRETA</span><p><strong>Água:</strong> ${number(projection.water_saving_m3_per_year)} m³ × ${unitMoney(projection.water_tariff_eur_per_m3)}/m³</p><p><strong>Energia:</strong> ${number(projection.energy_saving_kwh_per_year)} kWh × ${unitMoney(projection.energy_tariff_eur_per_kwh)}/kWh</p><small>Pressupostos fictícios a confirmar por submedição.</small></div>
        ${metric('Poupança direta projetada',`${money(projection.direct_savings_eur_per_year)} / ano`)}
        ${metric('Receita protegida projetada',`${money(projection.protected_revenue_eur_per_year)} / ano`,projection.protected_revenue_basis)}
        ${metric('Custo recorrente projetado',`${money(projection.recurring_cost_eur_per_year)} / ano`,projection.recurring_cost_basis)}
        ${metric('Benefício líquido projetado',`${money(projection.net_benefit_eur_per_year)} / ano`)}
        ${metric('Payback projetado',`${esc(projection.payback_months)} meses`)}
        ${metric('Retorno líquido / ROI a 3 anos',`${money(projection.net_return_3y_eur)} · ${esc(projection.roi_3y_percent)}%`)}
        <div class="actual-result"><span>RESULTADO MEDIDO</span><strong>${esc(actual.status)}</strong></div>
      </article>`;
    $('#scenario-controls').querySelectorAll('button').forEach(button=>button.addEventListener('click',()=>{activeScenarioId=button.dataset.scenarioId;renderBusinessCase(data);}));
    $('#human-resources').innerHTML=(data.human_resources||[]).map(item=>`<div><span>${esc(item.role)}</span><strong>${esc(item.hours)} h</strong></div>`).join('');
    $('#material-resources').innerHTML=(data.material_resources||[]).map(item=>`<div><span>${esc(item.resource)}</span><strong>${esc(item.quantity)} un.</strong></div>`).join('');
    $('#business-case-formulas').innerHTML=(data.formulas||[]).map(item=>`<li>${esc(item)}</li>`).join('');
  }

  function render(mission){
    set('#mission-title',mission.title);set('#mission-subtitle',mission.subtitle);
    set('#mission-meta',`${mission.organization} · ${mission.domain}`);
    set('#mission-status',mission.status);set('#mission-confidence',mission.confidence);set('#confidence-definition',mission.confidence_definition);set('#mission-decision',mission.decision);
    const profile=mission.property_profile||{};
    $('#property-profile').innerHTML=`<span><strong>${esc(profile.rooms)}</strong> quartos</span><span><strong>${esc(profile.average_occupancy_percent)}%</strong> ocupação média</span><span><strong>${number(profile.annual_occupied_room_nights)}</strong> quartos-noite/ano</span><span>${esc(profile.operating_model)}</span>`;
    set('#situation-summary',mission.situation?.summary);set('#central-question',mission.analysis?.central_question);
    set('#available-evidence',mission.analysis?.available_evidence);set('#unknowns',mission.analysis?.unknowns);
    $('#attention-list').innerHTML=(mission.situation?.attention||[]).map(item=>`<article class="card"><small>${esc(item.level)}</small><h3>${esc(item.title)}</h3><p>${esc(item.description)}</p></article>`).join('');
    $('#decision-chain').innerHTML=(mission.situation?.chain||[]).map(item=>`<article class="chain-step"><div class="chain-number">${esc(item.number)}</div><div><strong>${esc(item.label)} · ${esc(item.value)}</strong><p>${esc(item.note)}</p></div></article>`).join('');
    $('#alternatives-list').innerHTML=(mission.analysis?.alternatives||[]).map(item=>`<article class="alternative"><small>${esc(item.state)}</small><h3>${esc(item.title)}</h3><p>${esc(item.rationale)}</p></article>`).join('');
    renderMatrix(mission.analysis?.decision_matrix);
    $('#evidence-list').innerHTML=(mission.evidence||[]).map(item=>`<article class="evidence"><small>${esc(item.type)} · ${esc(item.status)}</small><h3>${esc(item.title)}</h3><p>${esc(item.description)}</p><p><strong>Método:</strong> ${esc(item.method)}</p><p><strong>Limitação:</strong> ${esc(item.limitation)}</p></article>`).join('');
    renderEvidenceGraph(mission.evidence_graph);
    renderBusinessCase(mission.business_case);
    $('#learning-list').innerHTML=(mission.learning||[]).map(item=>`<article class="card"><small>${esc(item.id)}</small><h3>${esc(item.title)}</h3><p>${esc(item.description)}</p></article>`).join('');
  }

  fetch('/api/mission-intelligence/demo/fictional/missions',{cache:'no-store'})
    .then(response=>{if(!response.ok)throw new Error('A demonstração não está disponível.');return response.json();})
    .then(catalog=>{const mission=Object.values(catalog.missions||{})[0];if(!mission)throw new Error('O caso demonstrativo não foi encontrado.');render(mission);})
    .catch(error=>{const box=$('#demo-error');box.textContent=error.message;box.classList.remove('hidden');set('#mission-title','Demonstração temporariamente indisponível');});
})();
