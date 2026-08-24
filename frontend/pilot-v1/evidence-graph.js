(()=>{
  'use strict';

  const token=()=>localStorage.getItem('sris_access_token')||sessionStorage.getItem('sris_access_token');
  const headers=()=>({'Content-Type':'application/json','Authorization':`Bearer ${token()||''}`});
  const esc=(value='')=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const missionCode=()=>{
    const raw=(document.querySelector('#detail-code')?.textContent||'').trim();
    const parts=raw.split('/').map(value=>value.trim()).filter(Boolean);
    return parts[parts.length-1]||raw;
  };

  const typeLabels={
    observation:'Observação',
    evidence:'Evidência',
    claim:'Afirmação',
    assumption:'Pressuposto',
    constraint:'Restrição',
    gap:'Lacuna',
    hypothesis:'Hipótese',
    alternative:'Alternativa',
    decision:'Decisão',
    action:'Ação',
    outcome:'Resultado',
    learning:'Aprendizagem',
  };

  const statusLabels={
    proposed:'Proposto',
    verified:'Verificado',
    accepted:'Aceite',
    rejected:'Rejeitado',
    superseded:'Substituído',
  };

  const relationLabels={
    supports:'suporta',
    contradicts:'contradiz',
    informs:'informa',
    derived_from:'deriva de',
    tests:'testa',
    leads_to:'conduz a',
    validates:'valida',
    invalidates:'invalida',
    supersedes:'substitui',
    learned_from:'é aprendido de',
    depends_on:'depende de',
    constrained_by:'é condicionado por',
    assumes:'assume',
    requires:'requer',
    addresses:'responde a',
  };

  const orderedTypes=['observation','evidence','assumption','constraint','gap','hypothesis','alternative','decision','action','outcome','learning','claim'];

  async function req(url,options={}){
    if(window.SRISApi?.request)return window.SRISApi.request(url,options);
    const response=await fetch(url,{...options,headers:{...headers(),...(options.headers||{})},cache:'no-store'});
    let data={};
    try{data=await response.json()}catch{}
    if(response.status===401){
      localStorage.removeItem('sris_access_token');
      location.href='/';
      throw new Error('Sessão expirada.');
    }
    if(!response.ok){
      const detail=data?.detail;
      throw new Error(typeof detail==='string'?detail:(detail?.message||detail?.code||data?.message||`Erro ${response.status}`));
    }
    return data;
  }

  function install(){
    const tabs=document.querySelector('.mission-tabs');
    const detail=document.querySelector('#mission-detail');
    if(!tabs||!detail||document.querySelector('[data-mission-tab="graph"]'))return false;

    const button=document.createElement('button');
    button.type='button';
    button.dataset.missionTab='graph';
    button.textContent='Evidência';
    tabs.appendChild(button);

    const panel=document.createElement('div');
    panel.className='mission-tab';
    panel.id='mission-tab-graph';
    panel.innerHTML=`
      <div class="eg-toolbar">
        <div>
          <div class="eyebrow">GRAFO DE EVIDÊNCIA</div>
          <h3>Raciocínio com proveniência explícita</h3>
          <div class="note">A recuperação documental apenas <strong>informa</strong>. <strong>Fonte íntegra não significa conteúdo verdadeiro.</strong> Suporte, contradição, validação e decisão exigem curadoria explícita.</div>
        </div>
        <button class="btn btn-primary" id="eg-sync" type="button">Sincronizar evidência</button>
      </div>
      <div class="eg-contract">
        <div><strong>Cadeia principal</strong><span>Observação → Evidência → Hipótese → Alternativa → Decisão → Ação → Resultado → Aprendizagem</span></div>
        <div><strong>Camada transversal</strong><span>Pressupostos · Restrições · Lacunas · Incerteza · Proveniência · Confiança</span></div>
      </div>
      <div id="eg-status" class="note" role="status" aria-live="polite"></div>
      <div id="eg-counts" class="eg-counts"></div>
      <div class="eg-layout">
        <div><div id="eg-nodes" class="eg-nodes"></div></div>
        <aside class="eg-side">
          <form id="eg-node-form" class="card eg-form">
            <div class="card-title"><h3>Adicionar objeto</h3></div>
            <div class="field"><label for="eg-node-type">Tipo canónico</label><select id="eg-node-type">
              <option value="observation">Observação</option>
              <option value="evidence">Evidência manual</option>
              <option value="assumption">Pressuposto</option>
              <option value="constraint">Restrição</option>
              <option value="gap">Lacuna de informação</option>
              <option value="hypothesis">Hipótese</option>
              <option value="alternative">Alternativa</option>
              <option value="decision">Decisão</option>
              <option value="action">Ação</option>
              <option value="outcome">Resultado</option>
              <option value="learning">Aprendizagem</option>
              <option value="claim">Afirmação</option>
            </select></div>
            <div class="field"><label for="eg-node-label">Título</label><input id="eg-node-label" required minlength="2" maxlength="300"></div>
            <div class="field"><label for="eg-node-body">Conteúdo *</label><textarea id="eg-node-body" required minlength="2" placeholder="Descreva o objeto, os critérios relevantes e os seus limites."></textarea></div>
            <div class="field"><label for="eg-node-status">Estado</label><select id="eg-node-status"><option value="proposed">Proposto</option><option value="verified">Verificado</option><option value="accepted">Aceite</option><option value="rejected">Rejeitado</option><option value="superseded">Substituído</option></select></div>
            <div class="field"><label for="eg-node-confidence">Confiança (opcional)</label><select id="eg-node-confidence"><option value="">Não avaliada</option><option value="0.25">Baixa · 25%</option><option value="0.5">Moderada · 50%</option><option value="0.75">Elevada · 75%</option><option value="1">Confirmada · 100%</option></select></div>
            <button class="btn btn-primary" type="submit">Adicionar ao grafo</button>
          </form>

          <form id="eg-edge-form" class="card eg-form">
            <div class="card-title"><h3>Criar relação</h3></div>
            <div class="field"><label for="eg-from">De</label><select id="eg-from"></select></div>
            <div class="field"><label for="eg-edge-type">Relação</label><select id="eg-edge-type">
              <option value="informs">informa</option>
              <option value="supports">suporta</option>
              <option value="contradicts">contradiz</option>
              <option value="assumes">assume</option>
              <option value="constrained_by">é condicionado por</option>
              <option value="requires">requer</option>
              <option value="addresses">responde a</option>
              <option value="depends_on">depende de</option>
              <option value="derived_from">deriva de</option>
              <option value="tests">testa</option>
              <option value="leads_to">conduz a</option>
              <option value="validates">valida</option>
              <option value="invalidates">invalida</option>
              <option value="supersedes">substitui</option>
              <option value="learned_from">é aprendido de</option>
            </select></div>
            <div class="field"><label for="eg-to">Para</label><select id="eg-to"></select></div>
            <button class="btn btn-secondary" type="submit">Criar relação</button>
          </form>
        </aside>
      </div>`;
    detail.appendChild(panel);

    const style=document.createElement('style');
    style.id='eg-v2-style';
    style.textContent=`
      .eg-toolbar{display:flex;justify-content:space-between;gap:18px;align-items:flex-start}.eg-toolbar h3{margin:5px 0}.eg-contract{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin:14px 0}.eg-contract>div{padding:11px 13px;border:1px solid var(--line);border-radius:12px;background:#f7faf8}.eg-contract strong,.eg-contract span{display:block}.eg-contract strong{font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:#45675b}.eg-contract span{margin-top:5px;font-size:10px;line-height:1.45;color:var(--muted)}#eg-status{min-height:20px;margin:10px 0}.eg-counts{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:7px;margin:12px 0 15px}.eg-count{border:1px solid var(--line);border-radius:12px;padding:10px;background:#f8faf8}.eg-count strong{display:block;font-size:21px;color:var(--forest)}.eg-count span{font-size:8px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted)}.eg-layout{display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:16px;align-items:start}.eg-nodes{display:grid;gap:10px}.eg-node{border:1px solid var(--line);border-radius:14px;padding:14px;background:#fff}.eg-node-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.eg-badges{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:5px}.eg-source-integrity{background:#e5f1eb;color:#285f4b}.eg-type{font-size:9px;font-weight:850;letter-spacing:.1em;text-transform:uppercase;padding:5px 8px;border-radius:999px;background:#edf4f1;color:#41685a}.eg-node[data-type="evidence"] .eg-type{background:#f6efe1;color:#8b652b}.eg-node[data-type="assumption"] .eg-type{background:#fbf0db;color:#8b6429}.eg-node[data-type="constraint"] .eg-type{background:#f8e9e6;color:#8c5047}.eg-node[data-type="gap"] .eg-type{background:#f7efe8;color:#8b6429}.eg-node[data-type="hypothesis"] .eg-type{background:#f3eafa;color:#785185}.eg-node[data-type="alternative"] .eg-type{background:#e8f1f8;color:#3d6580}.eg-node[data-type="decision"] .eg-type{background:#e5f1eb;color:#285f4b}.eg-node[data-type="learning"] .eg-type{background:#123e32;color:#fff}.eg-node p{white-space:pre-wrap;line-height:1.55;margin:9px 0;color:#364842}.eg-prov{font-size:10px;color:var(--muted);border-top:1px solid var(--line);padding-top:8px;margin-top:8px;line-height:1.45}.eg-confidence{font-weight:800;color:#46675b}.eg-edges{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}.eg-edge{font-size:9px;border-radius:999px;padding:4px 7px;background:#f0f4f2;color:#4c665e}.eg-side{display:grid;gap:12px;position:sticky;top:96px}.eg-form{padding:15px}.eg-form .field{margin-bottom:10px}.eg-form textarea{min-height:90px}.eg-empty{padding:28px;border:1px dashed var(--line);border-radius:14px;text-align:center;color:var(--muted)}@media(max-width:1080px){.eg-layout{grid-template-columns:1fr}.eg-side{position:static}.eg-counts{grid-template-columns:repeat(4,1fr)}}@media(max-width:700px){.eg-toolbar{display:grid}.eg-contract{grid-template-columns:1fr}.eg-counts{grid-template-columns:repeat(2,1fr)}}`;
    document.head.appendChild(style);

    button.addEventListener('click',async()=>{
      document.querySelectorAll('[data-mission-tab]').forEach(item=>item.classList.toggle('active',item===button));
      document.querySelectorAll('.mission-tab').forEach(item=>item.classList.toggle('active',item===panel));
      await loadGraph();
    });
    document.querySelector('#eg-sync')?.addEventListener('click',syncAndLoad);
    document.querySelector('#eg-node-form')?.addEventListener('submit',createNode);
    document.querySelector('#eg-edge-form')?.addEventListener('submit',createEdge);
    return true;
  }

  async function syncAndLoad(){
    const code=missionCode();
    if(!code)return;
    const status=document.querySelector('#eg-status');
    status.textContent='A sincronizar interações, excertos recuperados e proveniência…';
    try{
      const sync=await req(`/api/pilot/evidence-graph/missions/${encodeURIComponent(code)}/sync`,{method:'POST'});
      status.textContent=`${sync.interactions_scanned} interação(ões) analisada(s) · ${sync.nodes_created} objeto(s) novo(s) · ${sync.edges_created} relação(ões) nova(s).`;
      await loadGraph();
    }catch(error){
      status.textContent=`Não foi possível sincronizar: ${error.message}`;
    }
  }

  async function loadGraph(){
    const code=missionCode();
    if(!code)return;
    const status=document.querySelector('#eg-status');
    try{
      const graph=await req(`/api/pilot/evidence-graph/missions/${encodeURIComponent(code)}`);
      window.__srisEvidenceGraph=graph;
      render(graph);
      document.dispatchEvent(new CustomEvent('sris:evidence-graph-updated',{detail:graph}));
      if(status&&!status.textContent)status.textContent='Grafo sincronizado com o estado persistente da missão.';
    }catch(error){
      if(status)status.textContent=`Não foi possível abrir o grafo: ${error.message}`;
    }
  }

  function provenanceText(node){
    const provenance=node.provenance||{};
    if(node.source_kind==='document_chunk'){
      const filename=provenance.filename||node.label||'Documento';
      const hash=(node.source_sha256||provenance.content_sha256||'').slice(0,12);
      const ranks=[
        provenance.lexical_rank?`lexical #${provenance.lexical_rank}`:null,
        provenance.semantic_rank?`semântico #${provenance.semantic_rank}`:null,
        provenance.hybrid_score!==undefined?`híbrido ${Number(provenance.hybrid_score||0).toFixed(3)}`:null,
      ].filter(Boolean).join(' · ');
      const integrity=provenance.source_integrity_verified?'integridade da fonte verificada':'integridade da fonte não confirmada';
      const factual=provenance.factual_validation==='verified'?'conteúdo revisto factual':'validade factual não avaliada';
      return `${esc(filename)} · ${integrity} · ${factual} · posição ${node.char_start??'—'}–${node.char_end??'—'}${hash?` · hash ${esc(hash)}…`:''}${ranks?` · ${esc(ranks)}`:''}`;
    }
    if(node.source_kind==='visual_document'){
      const integrity=provenance.source_integrity_verified?'integridade da fonte verificada':'integridade da fonte não confirmada';
      return `Observação humana ligada à fonte visual · ${integrity} · validade factual não avaliada`;
    }
    if(node.source_kind==='ai_interaction')return'Candidato assistido · revisão humana obrigatória · não constitui facto confirmado';
    if(provenance.source==='mission_onboarding')return'Entrada humana · criada no início da missão · proveniência preservada';
    return'Entrada humana curada no workspace';
  }

  function render(graph){
    const counts=graph.counts||{};
    const countRoot=document.querySelector('#eg-counts');
    if(countRoot)countRoot.innerHTML=orderedTypes.map(type=>`<div class="eg-count"><strong>${Number(counts[type]||0)}</strong><span>${esc(typeLabels[type]||type)}</span></div>`).join('');

    const edgesByNode={};
    for(const edge of graph.edges||[])(edgesByNode[edge.from_node_id]??=[]).push(edge);
    const nodes=graph.nodes||[];
    const nodeRoot=document.querySelector('#eg-nodes');
    if(nodeRoot){
      nodeRoot.innerHTML=nodes.length?nodes.map(node=>{
        const outgoing=(edgesByNode[node.id]||[]).map(edge=>{
          const target=nodes.find(candidate=>candidate.id===edge.to_node_id);
          return `<span class="eg-edge">${esc(relationLabels[edge.edge_type]||edge.edge_type)} → ${esc((target?.label||edge.to_node_id).slice(0,60))}</span>`;
        }).join('');
        const confidence=node.confidence===null||node.confidence===undefined?'não avaliada':`${Math.round(Number(node.confidence)*100)}%`;
        const sourceIntegrity=(node.source_kind==='document_chunk'||node.source_kind==='visual_document')&&node.provenance?.source_integrity_verified?'<span class="pill eg-source-integrity">Fonte íntegra</span>':'';
        return `<article class="eg-node" data-type="${esc(node.node_type)}"><div class="eg-node-head"><div><span class="eg-type">${esc(typeLabels[node.node_type]||node.node_type)}</span><strong style="display:block;margin-top:8px">${esc(node.label)}</strong></div><div class="eg-badges">${sourceIntegrity}<span class="pill">${esc(statusLabels[node.status]||node.status)}</span></div></div><p>${esc((node.body||'').slice(0,2200))}</p><div class="eg-prov">${provenanceText(node)} · <span class="eg-confidence">confiança ${confidence}</span></div>${outgoing?`<div class="eg-edges">${outgoing}</div>`:''}</article>`;
      }).join(''):'<div class="eg-empty">Ainda não existem objetos no grafo. Adicione observações, evidência, pressupostos, restrições, hipóteses ou decisões — ou sincronize uma análise já realizada.</div>';
    }

    const options=nodes.map(node=>`<option value="${esc(node.id)}">${esc((typeLabels[node.node_type]||node.node_type)+' · '+node.label.slice(0,70))}</option>`).join('');
    const from=document.querySelector('#eg-from');
    const to=document.querySelector('#eg-to');
    if(from)from.innerHTML=options;
    if(to)to.innerHTML=options;

    const detailCounts=document.querySelector('#detail-epistemic-counts');
    if(detailCounts){
      detailCounts.innerHTML=`<span>Pressupostos · ${Number(counts.assumption||0)}</span><span>Restrições · ${Number(counts.constraint||0)}</span><span>Lacunas · ${Number(counts.gap||0)}</span><span>Proveniência · ativa</span>`;
    }
  }

  async function createNode(event){
    event.preventDefault();
    const code=missionCode();
    if(!code)return;
    const confidenceValue=document.querySelector('#eg-node-confidence').value;
    const payload={
      node_type:document.querySelector('#eg-node-type').value,
      label:document.querySelector('#eg-node-label').value.trim(),
      body:document.querySelector('#eg-node-body').value.trim(),
      status:document.querySelector('#eg-node-status').value,
      confidence:confidenceValue===''?null:Number(confidenceValue),
      provenance:{workspace:'pilot-v1',human_authored:true,review:'human'},
    };
    const status=document.querySelector('#eg-status');
    try{
      await req(`/api/pilot/evidence-graph/missions/${encodeURIComponent(code)}/nodes`,{method:'POST',body:JSON.stringify(payload)});
      event.target.reset();
      status.textContent='Objeto guardado com autoria humana e proveniência explícita.';
      await loadGraph();
    }catch(error){
      status.textContent=`Não foi possível guardar o objeto: ${error.message}`;
    }
  }

  async function createEdge(event){
    event.preventDefault();
    const code=missionCode();
    if(!code)return;
    const from=document.querySelector('#eg-from').value;
    const to=document.querySelector('#eg-to').value;
    const status=document.querySelector('#eg-status');
    if(!from||!to||from===to){status.textContent='Escolha dois objetos diferentes.';return;}
    try{
      await req(`/api/pilot/evidence-graph/missions/${encodeURIComponent(code)}/edges`,{
        method:'POST',
        body:JSON.stringify({
          from_node_id:from,
          to_node_id:to,
          edge_type:document.querySelector('#eg-edge-type').value,
          provenance:{workspace:'pilot-v1',explicit:true,human_curated:true},
        }),
      });
      status.textContent='Relação guardada com curadoria humana.';
      await loadGraph();
    }catch(error){
      status.textContent=`Não foi possível guardar a relação: ${error.message}`;
    }
  }

  if(!install())document.addEventListener('DOMContentLoaded',install,{once:true});
})();
