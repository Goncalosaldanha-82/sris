(()=>{
  const token=()=>localStorage.getItem('sris_access_token');
  const headers=()=>({'Content-Type':'application/json','Authorization':`Bearer ${token()}`});
  const esc=(v='')=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const missionCode=()=>{
    const raw=(document.querySelector('#detail-code')?.textContent||'').trim();
    const parts=raw.split('/').map(x=>x.trim()).filter(Boolean);
    return parts[parts.length-1]||raw;
  };
  async function req(url,options={}){
    const res=await fetch(url,{...options,headers:{...headers(),...(options.headers||{})}});
    let data={};try{data=await res.json()}catch{}
    if(res.status===401){localStorage.removeItem('sris_access_token');location.href='/';throw new Error('Sessão expirada.');}
    if(!res.ok){const d=data?.detail;throw new Error(typeof d==='string'?d:(d?.message||d?.code||`Erro ${res.status}`));}
    return data;
  }
  function install(){
    const tabs=document.querySelector('.mission-tabs');
    const detail=document.querySelector('#mission-detail');
    if(!tabs||!detail||document.querySelector('[data-mission-tab="graph"]'))return false;
    const btn=document.createElement('button');btn.type='button';btn.dataset.missionTab='graph';btn.textContent='Evidence Graph';tabs.appendChild(btn);
    const panel=document.createElement('div');panel.className='mission-tab';panel.id='mission-tab-graph';panel.innerHTML=`
      <div class="eg-toolbar">
        <div><div class="eyebrow">EVIDENCE GRAPH</div><h3>Raciocínio com proveniência explícita</h3><div class="note">A recuperação documental apenas <strong>informa</strong>. Relações de suporte, contradição ou validação exigem curadoria explícita.</div></div>
        <button class="btn btn-primary" id="eg-sync">Sincronizar evidência</button>
      </div>
      <div id="eg-status" class="note" style="margin:12px 0"></div>
      <div id="eg-counts" class="eg-counts"></div>
      <div class="eg-layout">
        <div><div id="eg-nodes" class="eg-nodes"></div></div>
        <aside class="eg-side">
          <form id="eg-node-form" class="card eg-form">
            <div class="card-title"><h3>Adicionar nó</h3></div>
            <div class="field"><label>Tipo</label><select id="eg-node-type"><option value="claim">Claim</option><option value="hypothesis">Hipótese</option><option value="decision">Decisão</option><option value="outcome">Outcome</option><option value="learning">Aprendizagem</option><option value="evidence">Evidência manual</option></select></div>
            <div class="field"><label>Título</label><input id="eg-node-label" required maxlength="300"></div>
            <div class="field"><label>Conteúdo</label><textarea id="eg-node-body" placeholder="Descreva o nó e o seu contexto."></textarea></div>
            <button class="btn btn-primary" type="submit">Adicionar ao grafo</button>
          </form>
          <form id="eg-edge-form" class="card eg-form">
            <div class="card-title"><h3>Criar relação</h3></div>
            <div class="field"><label>De</label><select id="eg-from"></select></div>
            <div class="field"><label>Relação</label><select id="eg-edge-type"><option value="supports">suporta</option><option value="contradicts">contradiz</option><option value="informs">informa</option><option value="derived_from">deriva de</option><option value="tests">testa</option><option value="leads_to">leva a</option><option value="validates">valida</option><option value="invalidates">invalida</option><option value="supersedes">substitui</option><option value="learned_from">aprendido de</option></select></div>
            <div class="field"><label>Para</label><select id="eg-to"></select></div>
            <button class="btn btn-ghost" type="submit">Criar relação</button>
          </form>
        </aside>
      </div>`;
    detail.appendChild(panel);
    const style=document.createElement('style');style.textContent=`
      .eg-toolbar{display:flex;justify-content:space-between;gap:18px;align-items:flex-start}.eg-toolbar h3{margin:5px 0}.eg-counts{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px;margin:14px 0}.eg-count{border:1px solid var(--line);border-radius:12px;padding:11px;background:#f8faf8}.eg-count strong{display:block;font-size:23px;color:var(--forest)}.eg-count span{font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}.eg-layout{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:16px;align-items:start}.eg-nodes{display:grid;gap:10px}.eg-node{border:1px solid var(--line);border-radius:14px;padding:14px;background:#fff}.eg-node-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.eg-type{font-size:9px;font-weight:850;letter-spacing:.1em;text-transform:uppercase;padding:5px 8px;border-radius:999px;background:#edf4f1;color:#41685a}.eg-node[data-type="evidence"] .eg-type{background:#f6efe1;color:#8b652b}.eg-node[data-type="claim"] .eg-type{background:#edf0f8;color:#445e90}.eg-node[data-type="hypothesis"] .eg-type{background:#f7eefa;color:#785185}.eg-node p{white-space:pre-wrap;line-height:1.55;margin:9px 0;color:#364842}.eg-prov{font-size:10px;color:var(--muted);border-top:1px solid var(--line);padding-top:8px;margin-top:8px}.eg-edges{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}.eg-edge{font-size:9px;border-radius:999px;padding:4px 7px;background:#f0f4f2;color:#4c665e}.eg-side{display:grid;gap:12px;position:sticky;top:96px}.eg-form{padding:15px}.eg-form .field{margin-bottom:10px}.eg-form textarea{min-height:90px}.eg-empty{padding:28px;border:1px dashed var(--line);border-radius:14px;text-align:center;color:var(--muted)}@media(max-width:1000px){.eg-layout{grid-template-columns:1fr}.eg-side{position:static}.eg-counts{grid-template-columns:repeat(3,1fr)}}@media(max-width:650px){.eg-toolbar{display:grid}.eg-counts{grid-template-columns:repeat(2,1fr)}}`;
    document.head.appendChild(style);
    btn.addEventListener('click',async()=>{document.querySelectorAll('[data-mission-tab]').forEach(x=>x.classList.toggle('active',x===btn));document.querySelectorAll('.mission-tab').forEach(x=>x.classList.toggle('active',x===panel));await syncAndLoad();});
    document.querySelector('#eg-sync').addEventListener('click',syncAndLoad);
    document.querySelector('#eg-node-form').addEventListener('submit',createNode);
    document.querySelector('#eg-edge-form').addEventListener('submit',createEdge);
    return true;
  }
  async function syncAndLoad(){
    const code=missionCode();if(!code)return;
    const status=document.querySelector('#eg-status');status.textContent='A sincronizar interações, chunks recuperados e proveniência…';
    try{const sync=await req(`/api/pilot/evidence-graph/missions/${encodeURIComponent(code)}/sync`,{method:'POST'});status.textContent=`${sync.interactions_scanned} interação(ões) analisada(s) · ${sync.nodes_created} nó(s) novo(s) · ${sync.edges_created} relação(ões) nova(s).`;await loadGraph();}catch(err){status.textContent=`Não foi possível sincronizar: ${err.message}`;}
  }
  async function loadGraph(){
    const code=missionCode();if(!code)return;
    const graph=await req(`/api/pilot/evidence-graph/missions/${encodeURIComponent(code)}`);window.__srisEvidenceGraph=graph;render(graph);
  }
  function render(graph){
    const types=['evidence','claim','hypothesis','decision','outcome','learning'];
    const labels={evidence:'Evidência',claim:'Claims',hypothesis:'Hipóteses',decision:'Decisões',outcome:'Outcomes',learning:'Aprendizagens'};
    document.querySelector('#eg-counts').innerHTML=types.map(t=>`<div class="eg-count"><strong>${graph.counts?.[t]||0}</strong><span>${labels[t]}</span></div>`).join('');
    const edgesByNode={};for(const e of graph.edges||[]){(edgesByNode[e.from_node_id]??=[]).push(e);}
    const nodes=graph.nodes||[];
    document.querySelector('#eg-nodes').innerHTML=nodes.length?nodes.map(n=>{
      const p=n.provenance||{};const prov=n.source_kind==='document_chunk'?`${esc(p.filename||n.label)} · chars ${n.char_start??'—'}–${n.char_end??'—'} · hash ${esc((n.source_sha256||'').slice(0,10))}…${p.lexical_rank?` · lexical #${p.lexical_rank}`:''}${p.semantic_rank?` · semântico #${p.semantic_rank}`:''}`:n.source_kind==='ai_interaction'?`Candidato gerado por IA · revisão humana obrigatória${p.model?` · ${esc(p.model)}`:''}`:'Entrada curada pelo utilizador';
      const outgoing=(edgesByNode[n.id]||[]).map(e=>`<span class="eg-edge">${esc(e.edge_type)} → ${esc((nodes.find(x=>x.id===e.to_node_id)?.label||e.to_node_id).slice(0,55))}</span>`).join('');
      return `<article class="eg-node" data-type="${esc(n.node_type)}"><div class="eg-node-head"><div><span class="eg-type">${esc(labels[n.node_type]||n.node_type)}</span><strong style="display:block;margin-top:8px">${esc(n.label)}</strong></div><span class="pill">${esc(n.status)}</span></div><p>${esc((n.body||'').slice(0,1800))}</p><div class="eg-prov">${prov}</div>${outgoing?`<div class="eg-edges">${outgoing}</div>`:''}</article>`;
    }).join(''):'<div class="eg-empty">Ainda não existem nós. Execute uma análise da missão ou adicione um claim, hipótese ou decisão manualmente.</div>';
    const options=nodes.map(n=>`<option value="${esc(n.id)}">${esc((labels[n.node_type]||n.node_type)+' · '+n.label.slice(0,70))}</option>`).join('');
    document.querySelector('#eg-from').innerHTML=options;document.querySelector('#eg-to').innerHTML=options;
  }
  async function createNode(e){e.preventDefault();const code=missionCode();if(!code)return;const payload={node_type:document.querySelector('#eg-node-type').value,label:document.querySelector('#eg-node-label').value.trim(),body:document.querySelector('#eg-node-body').value.trim(),status:'proposed',provenance:{workspace:'pilot-v1'}};try{await req(`/api/pilot/evidence-graph/missions/${encodeURIComponent(code)}/nodes`,{method:'POST',body:JSON.stringify(payload)});e.target.reset();await loadGraph();}catch(err){document.querySelector('#eg-status').textContent=`Erro: ${err.message}`;}}
  async function createEdge(e){e.preventDefault();const code=missionCode();if(!code)return;const from=document.querySelector('#eg-from').value,to=document.querySelector('#eg-to').value;if(!from||!to||from===to){document.querySelector('#eg-status').textContent='Escolha dois nós diferentes.';return;}try{await req(`/api/pilot/evidence-graph/missions/${encodeURIComponent(code)}/edges`,{method:'POST',body:JSON.stringify({from_node_id:from,to_node_id:to,edge_type:document.querySelector('#eg-edge-type').value,provenance:{workspace:'pilot-v1',explicit:true}})});await loadGraph();}catch(err){document.querySelector('#eg-status').textContent=`Erro: ${err.message}`;}}
  if(!install())document.addEventListener('DOMContentLoaded',install,{once:true});
})();
