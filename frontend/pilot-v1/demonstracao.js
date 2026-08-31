(()=>{
  'use strict';
  const $=selector=>document.querySelector(selector);
  const esc=value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#039;');
  const set=(selector,value)=>{const element=$(selector);if(element)element.textContent=value||'—';};
  const money=value=>Number.isFinite(value)?new Intl.NumberFormat('pt-PT',{style:'currency',currency:'EUR',maximumFractionDigits:0}).format(value):'Pendente';
  const metric=(label,value,detail='')=>`<div class="financial-metric"><span>${esc(label)}</span><strong>${esc(value)}</strong>${detail?`<small>${esc(detail)}</small>`:''}</div>`;

  function renderBusinessCase(data={}){
    const baseline=data.baseline||{},pilot=data.pilot||{},projection=data.projection||{},actual=data.actual||{};
    set('#business-case-notice',data.notice);
    $('#business-case-timeline').innerHTML=`
      <article class="economy-phase"><div class="phase-heading"><span>ANTES</span><strong>${esc(baseline.status)}</strong></div>
        ${metric('Água + energia',`${money(baseline.annual_resource_spend_eur)} / ano`)}
        ${metric('Perda operacional evitável',`${money(baseline.avoidable_operating_loss_eur)} / ano`)}
        ${metric('Receita sob risco',`${money(baseline.revenue_at_risk_eur)} / ano`,'Não é perda realizada')}
      </article>
      <article class="economy-phase"><div class="phase-heading"><span>DURANTE</span><strong>${esc(pilot.status)}</strong></div>
        ${metric('Investimento do piloto',money(pilot.investment_eur))}
        ${metric('Equipamento e instrumentação',money(pilot.equipment_eur))}
        ${metric('Custo interno da equipa',money(pilot.internal_people_cost_eur))}
        ${metric('Duração e esforço',`${esc(pilot.duration_weeks)} semanas · ${esc(pilot.internal_hours)} h`)}
        ${metric('Interrupção planeada',`≤ ${esc(pilot.planned_interruption_hours)} h`)}
      </article>
      <article class="economy-phase projection"><div class="phase-heading"><span>DEPOIS</span><strong>${esc(projection.status)}</strong></div>
        ${metric('Poupança direta projetada',`${money(projection.direct_savings_eur_per_year)} / ano`)}
        ${metric('Receita protegida projetada',`${money(projection.protected_revenue_eur_per_year)} / ano`)}
        ${metric('Custo recorrente projetado',`${money(projection.recurring_cost_eur_per_year)} / ano`)}
        ${metric('Benefício líquido projetado',`${money(projection.net_benefit_eur_per_year)} / ano`)}
        ${metric('Payback projetado',`${esc(projection.payback_months)} meses`)}
        ${metric('Retorno líquido / ROI a 3 anos',`${money(projection.net_return_3y_eur)} · ${esc(projection.roi_3y_percent)}%`)}
        <div class="actual-result"><span>RESULTADO MEDIDO</span><strong>${esc(actual.status)}</strong></div>
      </article>`;
    $('#human-resources').innerHTML=(data.human_resources||[]).map(item=>`<div><span>${esc(item.role)}</span><strong>${esc(item.hours)} h</strong></div>`).join('');
    $('#material-resources').innerHTML=(data.material_resources||[]).map(item=>`<div><span>${esc(item.resource)}</span><strong>${esc(item.quantity)} un.</strong></div>`).join('');
    $('#business-case-formulas').innerHTML=(data.formulas||[]).map(item=>`<li>${esc(item)}</li>`).join('');
  }

  function render(mission){
    set('#mission-title',mission.title);set('#mission-subtitle',mission.subtitle);
    set('#mission-meta',`${mission.organization} · ${mission.domain}`);
    set('#mission-status',mission.status);set('#mission-confidence',mission.confidence);set('#mission-decision',mission.decision);
    set('#situation-summary',mission.situation?.summary);set('#central-question',mission.analysis?.central_question);
    set('#available-evidence',mission.analysis?.available_evidence);set('#unknowns',mission.analysis?.unknowns);
    $('#attention-list').innerHTML=(mission.situation?.attention||[]).map(item=>`<article class="card"><small>${esc(item.level)}</small><h3>${esc(item.title)}</h3><p>${esc(item.description)}</p></article>`).join('');
    $('#decision-chain').innerHTML=(mission.situation?.chain||[]).map(item=>`<article class="chain-step"><div class="chain-number">${esc(item.number)}</div><div><strong>${esc(item.label)} · ${esc(item.value)}</strong><p>${esc(item.note)}</p></div></article>`).join('');
    $('#alternatives-list').innerHTML=(mission.analysis?.alternatives||[]).map(item=>`<article class="alternative"><small>${esc(item.state)}</small><h3>${esc(item.title)}</h3><p>${esc(item.rationale)}</p></article>`).join('');
    $('#evidence-list').innerHTML=(mission.evidence||[]).map(item=>`<article class="evidence"><small>${esc(item.type)} · ${esc(item.status)}</small><h3>${esc(item.title)}</h3><p>${esc(item.description)}</p><p><strong>Método:</strong> ${esc(item.method)}</p><p><strong>Limitação:</strong> ${esc(item.limitation)}</p></article>`).join('');
    renderBusinessCase(mission.business_case);
    $('#learning-list').innerHTML=(mission.learning||[]).map(item=>`<article class="card"><small>${esc(item.id)}</small><h3>${esc(item.title)}</h3><p>${esc(item.description)}</p></article>`).join('');
  }

  fetch('/api/mission-intelligence/demo/fictional/missions',{cache:'no-store'})
    .then(response=>{if(!response.ok)throw new Error('A demonstração não está disponível.');return response.json();})
    .then(catalog=>{const mission=Object.values(catalog.missions||{})[0];if(!mission)throw new Error('O caso demonstrativo não foi encontrado.');render(mission);})
    .catch(error=>{const box=$('#demo-error');box.textContent=error.message;box.classList.remove('hidden');set('#mission-title','Demonstração temporariamente indisponível');});
})();
