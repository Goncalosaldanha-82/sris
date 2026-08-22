(()=>{
  const baseFetch=window.fetch.bind(window);
  const token=()=>localStorage.getItem('sris_access_token');
  const authHeaders=()=>({'Content-Type':'application/json','Authorization':`Bearer ${token()}`});
  const esc=(v='')=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const missionCode=()=>{const raw=(document.querySelector('#detail-code')?.textContent||'').trim();const p=raw.split('/').map(x=>x.trim()).filter(Boolean);return p[p.length-1]||raw;};
  async function api(url,options={}){const res=await baseFetch(url,{...options,headers:{...authHeaders(),...(options.headers||{})}});let data={};try{data=await res.json()}catch{}if(res.status===401){localStorage.removeItem('sris_access_token');location.href='/';throw new Error('Sessão expirada.');}if(!res.ok){const d=data?.detail;throw new Error(typeof d==='string'?d:(d?.message||d?.code||`Erro ${res.status}`));}return data;}

  // This hook is the product thesis in code: reviewed learning changes the next mission's AI context.
  window.fetch=async(input,init={})=>{
    const url=typeof input==='string'?input:input?.url||'';
    if(url==='/api/pilot/intelligence/ask' && init?.body){
      try{
        const payload=JSON.parse(init.body);
        if(payload.mission_code){
          const inherited=await api(`/api/pilot/learning/missions/${encodeURIComponent(payload.mission_code)}/active-context`);
          if(inherited?.context_text){
            payload.context=[payload.context||'',inherited.context_text].filter(Boolean).join('\n\n---\n\n');
            init={...init,body:JSON.stringify(payload),headers:{...(init.headers||{}),'X-SRIS-Learning-Inheritance':'applied'}};
          }
        }
      }catch(err){console.warn('SRIS learning inheritance unavailable; continuing without inherited context.',err);}
    }
    return baseFetch(input,init);
  };

  function install(){
    const tabs=document.querySelector('.mission-tabs'),detail=document.querySelector('#mission-detail');
    if(!tabs||!detail||document.querySelector('[data-mission-tab="learning"]'))return false;
    const btn=document.createElement('button');btn.type='button';btn.dataset.missionTab='learning';btn.textContent='Aprendizagem';tabs.appendChild(btn);
    const panel=document.createElement('div');panel.className='mission-tab';panel.id='mission-tab-learning';panel.innerHTML=`
      <div class="ll-head"><div><div class="eyebrow">ORGANIZATIONAL MEMORY</div><h3>A missão seguinte começa melhor porque a anterior existiu.</h3><div class="note">A aprendizagem viaja com a cadeia de evidência, claims, decisões e outcomes que a justificou. Nada altera uma missão futura sem revisão humana.</div></div><button class="btn btn-primary" id="ll-refresh">Atualizar candidatos</button></div>
      <div id="ll-status" class="note" style="margin:12px 0"></div><div id="ll-summary" class="ll-summary"></div><div id="ll-candidates" class="ll-list"></div>`;
    detail.appendChild(panel);
    const style=document.createElement('style');style.textContent=`.ll-head{display:flex;justify-content:space-between;gap:18px;align-items:flex-start}.ll-head h3{margin:5px 0}.ll-summary{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:14px 0}.ll-stat{padding:11px;border:1px solid var(--line);border-radius:12px;background:#f8faf8}.ll-stat strong{display:block;font-size:22px;color:var(--forest)}.ll-stat span{font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}.ll-list{display:grid;gap:11px}.ll-card{border:1px solid var(--line);border-radius:15px;padding:15px;background:#fff}.ll-top{display:flex;justify-content:space-between;gap:12px}.ll-source{font-size:10px;color:var(--muted);margin:5px 0}.ll-statement{line-height:1.6;white-space:pre-wrap}.ll-lineage{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}.ll-chip{font-size:9px;padding:4px 7px;border-radius:999px;background:#eef4f1;color:#48695e}.ll-actions{display:flex;gap:7px;flex-wrap:wrap;border-top:1px solid var(--line);padding-top:10px;margin-top:10px}.ll-actions button{padding:8px 10px}.ll-active{border-left:4px solid #2f765f}.ll-revalidate{border-left:4px solid #d49b3e}.ll-invalid{opacity:.64}.ll-publish{margin-left:auto}@media(max-width:760px){.ll-head{display:grid}.ll-summary{grid-template-columns:repeat(2,1fr)}}`;document.head.appendChild(style);
    btn.addEventListener('click',async()=>{document.querySelectorAll('[data-mission-tab]').forEach(x=>x.classList.toggle('active',x===btn));document.querySelectorAll('.mission-tab').forEach(x=>x.classList.toggle('active',x===panel));await load();});
    panel.querySelector('#ll-refresh').addEventListener('click',load);
    panel.addEventListener('click',handleClick);
    return true;
  }
  async function load(){const code=missionCode();if(!code)return;const status=document.querySelector('#ll-status');status.textContent='A procurar aprendizagem publicada noutras missões…';try{const data=await api(`/api/pilot/learning/missions/${encodeURIComponent(code)}/candidates`);render(data);status.textContent=data.candidates.length?'Revise cada aprendizagem antes de permitir que influencie esta missão.':'Ainda não há aprendizagens publicadas por outras missões.';}catch(err){status.textContent=`Não foi possível carregar aprendizagem: ${err.message}`;}}
  function render(data){const s=data.summary||{};document.querySelector('#ll-summary').innerHTML=[['candidate_count','Candidatas'],['still_valid_count','Ainda válidas'],['requires_revalidation_count','Revalidar'],['invalidated_count','Invalidadas']].map(([k,l])=>`<div class="ll-stat"><strong>${s[k]||0}</strong><span>${l}</span></div>`).join('');const list=document.querySelector('#ll-candidates');list.innerHTML=(data.candidates||[]).length?data.candidates.map(c=>{const review=c.review||{};const cls=review.disposition==='still_valid'?'ll-active':review.disposition==='requires_revalidation'?'ll-revalidate':review.disposition==='invalidated'?'ll-invalid':'';const counts=c.lineage?.counts||{};return `<article class="ll-card ${cls}" data-packet="${esc(c.id)}"><div class="ll-top"><div><strong>${esc(c.title)}</strong><div class="ll-source">${esc(c.source_mission?.code)} · ${esc(c.source_mission?.title||'')} · relevância ${Math.round((c.relevance_score||0)*100)}%</div></div><span class="pill">${esc(review.disposition||'por rever')}</span></div><div class="ll-statement">${esc(c.statement)}</div><div class="ll-lineage"><span class="ll-chip">${counts.evidence||0} evidência(s)</span><span class="ll-chip">${counts.claim||0} claim(s)</span><span class="ll-chip">${counts.decision||0} decisão(ões)</span><span class="ll-chip">${counts.outcome||0} outcome(s)</span><span class="ll-chip">lineage ${esc((c.lineage_sha256||'').slice(0,10))}…</span></div>${review.rationale?`<div class="note">Revisão: ${esc(review.rationale)}${review.context_change?` · Mudança: ${esc(review.context_change)}`:''}</div>`:''}<div class="ll-actions"><button class="btn btn-ghost" data-disposition="still_valid">Ainda válida</button><button class="btn btn-ghost" data-disposition="requires_revalidation">Requer revalidação</button><button class="btn btn-ghost" data-disposition="invalidated">Invalidada</button></div></article>`}).join(''):'<div class="eg-empty">Nenhuma aprendizagem publicada por outras missões.</div>';}
  async function handleClick(e){const b=e.target.closest?.('[data-disposition]');if(!b)return;const card=b.closest('[data-packet]'),packet=card?.dataset.packet,disposition=b.dataset.disposition,code=missionCode();if(!packet||!code)return;let rationale=prompt('Porque toma esta decisão sobre a validade desta aprendizagem?');if(!rationale)return;let context_change='';if(disposition!=='still_valid'){context_change=prompt('O que mudou no contexto?')||'';if(!context_change)return;}try{await api(`/api/pilot/learning/missions/${encodeURIComponent(code)}/candidates/${encodeURIComponent(packet)}/review`,{method:'POST',body:JSON.stringify({disposition,rationale,context_change})});await load();}catch(err){document.querySelector('#ll-status').textContent=`Erro: ${err.message}`;}}
  async function publishAcceptedLearning(nodeId){const code=missionCode();if(!code||!nodeId)return;try{await api(`/api/pilot/learning/missions/${encodeURIComponent(code)}/publish/${encodeURIComponent(nodeId)}`,{method:'POST'});return true;}catch(err){alert(`Não foi possível publicar a aprendizagem: ${err.message}`);return false;}}
  document.addEventListener('click',async e=>{const node=e.target.closest?.('.eg-node[data-type="learning"]');if(!node)return;if(e.target.closest('button'))return;const graph=window.__srisEvidenceGraph;const title=node.querySelector('strong')?.textContent||'';const candidate=(graph?.nodes||[]).find(n=>n.node_type==='learning'&&n.label===title);if(candidate&&candidate.status.match(/accepted|verified/)){if(confirm('Publicar esta aprendizagem na memória organizacional com toda a sua linhagem de evidência?')){await publishAcceptedLearning(candidate.id);}}},true);
  if(!install())document.addEventListener('DOMContentLoaded',install,{once:true});
})();