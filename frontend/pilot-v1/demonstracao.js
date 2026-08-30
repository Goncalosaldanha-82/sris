(()=>{
  'use strict';
  const $=selector=>document.querySelector(selector);
  const esc=value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#039;');
  const set=(selector,value)=>{const element=$(selector);if(element)element.textContent=value||'—';};

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
    $('#learning-list').innerHTML=(mission.learning||[]).map(item=>`<article class="card"><small>${esc(item.id)}</small><h3>${esc(item.title)}</h3><p>${esc(item.description)}</p></article>`).join('');
  }

  fetch('/api/mission-intelligence/demo/fictional/missions',{cache:'no-store'})
    .then(response=>{if(!response.ok)throw new Error('A demonstração não está disponível.');return response.json();})
    .then(catalog=>{const mission=Object.values(catalog.missions||{})[0];if(!mission)throw new Error('O caso demonstrativo não foi encontrado.');render(mission);})
    .catch(error=>{const box=$('#demo-error');box.textContent=error.message;box.classList.remove('hidden');set('#mission-title','Demonstração temporariamente indisponível');});
})();
