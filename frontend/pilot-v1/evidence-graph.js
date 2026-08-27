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
    target:'Critério ou meta',
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

  const relationGuidance={
    informs:'O primeiro objeto fornece contexto ao segundo.',
    supports:'O primeiro objeto dá suporte ao segundo.',
    contradicts:'O primeiro objeto contradiz o segundo.',
    assumes:'O primeiro objeto assume o segundo como pressuposto.',
    constrained_by:'O primeiro objeto é limitado pelo segundo. Exemplo: “Hipótese é condicionada por Restrição”.',
    requires:'O primeiro objeto requer o segundo.',
    addresses:'O primeiro objeto responde ao segundo.',
    depends_on:'O primeiro objeto depende do segundo.',
    derived_from:'O primeiro objeto deriva do segundo.',
    tests:'O primeiro objeto testa o segundo.',
    leads_to:'O primeiro objeto conduz ao segundo.',
    validates:'O primeiro objeto valida o segundo.',
    invalidates:'O primeiro objeto invalida o segundo.',
    supersedes:'O primeiro objeto substitui o segundo.',
    learned_from:'O primeiro objeto é uma aprendizagem obtida a partir do segundo.',
  };

  const feminineNodeTypes=new Set(['observation','evidence','claim','assumption','constraint','gap','hypothesis','alternative','decision','action','learning']);

  const orderedTypes=['observation','evidence','assumption','constraint','gap','hypothesis','target','alternative','decision','action','outcome','learning','claim'];
  let lastConfirmedEdgeId='';
  let pendingRelationAction=null;

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
              <option value="target">Critério ou meta</option>
              <option value="alternative">Alternativa</option>
              <option value="decision">Decisão</option>
              <option value="action">Ação</option>
              <option value="outcome">Resultado</option>
              <option value="learning">Aprendizagem</option>
              <option value="claim">Afirmação</option>
            </select></div>
            <div class="field"><label for="eg-node-label">Título</label><input id="eg-node-label" required minlength="2" maxlength="300"></div>
            <div class="field"><label for="eg-node-body">Conteúdo *</label><textarea id="eg-node-body" required minlength="2" placeholder="Descreva o objeto, os critérios relevantes e os seus limites."></textarea></div>
            <div class="note"><strong>Estado inicial · Proposto.</strong> Aceitar, verificar, rejeitar ou substituir exige uma revisão humana própria.</div>
            <div class="field"><label for="eg-node-confidence">Confiança (opcional)</label><select id="eg-node-confidence"><option value="">Não avaliada</option><option value="0.25">Baixa · 25%</option><option value="0.5">Moderada · 50%</option><option value="0.75">Elevada · 75%</option><option value="1">Confirmada · 100%</option></select></div>
            <button class="btn btn-primary" type="submit">Adicionar ao grafo</button>
          </form>

          <form id="eg-edge-form" class="card eg-form">
            <div class="card-title"><h3>Criar relação</h3></div>
            <p class="eg-direction-intro">A relação é lida como uma frase, de cima para baixo: <strong>primeiro objeto + relação + segundo objeto</strong>.</p>
            <div class="field"><label for="eg-from">1. Primeiro objeto — sujeito</label><select id="eg-from"></select></div>
            <div class="field"><label for="eg-edge-type">2. Relação</label><select id="eg-edge-type">
              <option value="informs">informa</option>
              <option value="supports">suporta</option>
              <option value="contradicts">contradiz</option>
              <option value="assumes">assume</option>
              <option value="constrained_by">é condicionado/a por</option>
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
            <div class="field"><label for="eg-to">3. Segundo objeto — complemento</label><select id="eg-to"></select></div>
            <div id="eg-edge-preview" class="eg-edge-preview" aria-live="polite"></div>
            <button class="eg-swap-button" id="eg-edge-swap" type="button">⇄ Trocar a ordem dos objetos</button>
            <button class="btn btn-secondary" id="eg-edge-submit" type="submit">Criar relação</button>
            <div id="eg-edge-status" class="eg-inline-status" data-state="idle" role="status" aria-live="polite">Selecione dois objetos diferentes para criar uma relação explícita.</div>
          </form>

          <section class="card eg-relations-card" aria-labelledby="eg-relations-title">
            <div class="card-title"><h3 id="eg-relations-title">Relações guardadas</h3><span id="eg-relations-count" class="pill">0</span></div>
            <div id="eg-relations" class="eg-relations"></div>
          </section>
        </aside>
      </div>`;
    detail.appendChild(panel);

    const style=document.createElement('style');
    style.id='eg-v2-style';
    style.textContent=`
      .eg-toolbar{display:flex;justify-content:space-between;gap:18px;align-items:flex-start}.eg-toolbar h3{margin:5px 0}.eg-contract{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin:14px 0}.eg-contract>div{padding:11px 13px;border:1px solid var(--line);border-radius:12px;background:#f7faf8}.eg-contract strong,.eg-contract span{display:block}.eg-contract strong{font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:#45675b}.eg-contract span{margin-top:5px;font-size:10px;line-height:1.45;color:var(--muted)}#eg-status{min-height:20px;margin:10px 0}.eg-counts{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:7px;margin:12px 0 15px}.eg-count{border:1px solid var(--line);border-radius:12px;padding:10px;background:#f8faf8}.eg-count strong{display:block;font-size:21px;color:var(--forest)}.eg-count span{font-size:8px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted)}.eg-layout{display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:16px;align-items:start}.eg-nodes{display:grid;gap:10px}.eg-node{border:1px solid var(--line);border-radius:14px;padding:14px;background:#fff}.eg-node-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.eg-badges{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:5px}.eg-source-integrity{background:#e5f1eb;color:#285f4b}.eg-type{font-size:9px;font-weight:850;letter-spacing:.1em;text-transform:uppercase;padding:5px 8px;border-radius:999px;background:#edf4f1;color:#41685a}.eg-node[data-type="evidence"] .eg-type{background:#f6efe1;color:#8b652b}.eg-node[data-type="assumption"] .eg-type{background:#fbf0db;color:#8b6429}.eg-node[data-type="constraint"] .eg-type{background:#f8e9e6;color:#8c5047}.eg-node[data-type="gap"] .eg-type{background:#f7efe8;color:#8b6429}.eg-node[data-type="hypothesis"] .eg-type{background:#f3eafa;color:#785185}.eg-node[data-type="alternative"] .eg-type{background:#e8f1f8;color:#3d6580}.eg-node[data-type="decision"] .eg-type{background:#e5f1eb;color:#285f4b}.eg-node[data-type="learning"] .eg-type{background:#123e32;color:#fff}.eg-node p{white-space:pre-wrap;line-height:1.55;margin:9px 0;color:#364842}.eg-prov{font-size:10px;color:var(--muted);border-top:1px solid var(--line);padding-top:8px;margin-top:8px;line-height:1.45}.eg-confidence{font-weight:800;color:#46675b}.eg-node-review{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;padding-top:9px;border-top:1px solid var(--line)}.eg-node-review button{padding:7px 9px;border:1px solid #9bada6;border-radius:8px;background:#fff;color:var(--forest);font:inherit;font-size:9px;font-weight:800;cursor:pointer}.eg-node-review button[data-eg-review="verified"]{border-color:#4c806c;background:#edf7f1}.eg-node-review button[data-eg-review="rejected"]{border-color:#d5a29a;color:#8e3535}.eg-node-review button:disabled{cursor:wait;opacity:.55}.eg-edges{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}.eg-edge{font-size:9px;border-radius:999px;padding:4px 7px;background:#f0f4f2;color:#4c665e}.eg-edge.is-confirmed{background:#dcefe5;color:#205b45;box-shadow:0 0 0 2px rgba(47,116,88,.12)}.eg-side{display:grid;gap:12px;position:sticky;top:96px}.eg-form{padding:15px}.eg-form .field{margin-bottom:10px}.eg-form textarea{min-height:90px}.eg-direction-intro{margin:0 0 12px;padding:9px 10px;border-radius:10px;background:#f3f6f4;color:#52675f;font-size:10px;line-height:1.45}.eg-edge-preview{min-height:46px;margin:4px 0 8px;padding:10px 11px;border:1px solid var(--line);border-radius:11px;background:#f7faf8;color:#49615a;font-size:11px;line-height:1.45;overflow-wrap:anywhere}.eg-preview-caption{display:block;margin-bottom:5px;font-size:8px;font-weight:850;letter-spacing:.09em;text-transform:uppercase;color:#6b7d76}.eg-edge-preview strong{display:block;color:var(--forest);font-size:11px}.eg-edge-preview .eg-relation-phrase{display:block;margin:3px 0;color:#8a672d;font-weight:850}.eg-direction-help{display:block;margin-top:7px;padding-top:7px;border-top:1px solid var(--line);color:#60736b}.eg-direction-warning{display:block;margin-top:7px;padding:7px 8px;border-radius:8px;background:#fff0e7;color:#8b4b2f;font-weight:800}.eg-swap-button{width:100%;margin:0 0 8px;padding:9px 10px;border:1px solid #9bada6;border-radius:10px;background:#fff;color:var(--forest);font:inherit;font-size:10px;font-weight:800;cursor:pointer}#eg-edge-submit{width:100%}.eg-inline-status{min-height:44px;margin-top:9px;padding:10px 11px;border-radius:11px;background:#f3f5f3;color:#65736f;font-size:11px;line-height:1.45;overflow-wrap:anywhere}.eg-inline-status[data-state="pending"]{background:#f6f1e6;color:#7c642e}.eg-inline-status[data-state="success"]{background:#e8f5ed;color:#236044;font-weight:750}.eg-inline-status[data-state="error"]{background:#fff0f0;color:#8e3535;font-weight:750}.eg-relations-card{padding:15px}.eg-relations{display:grid;gap:8px}.eg-relation-row{padding:10px;border:1px solid var(--line);border-radius:11px;background:#f9fbfa;font-size:10px;line-height:1.45;color:#536660;overflow-wrap:anywhere}.eg-relation-row strong{display:block;color:var(--forest);font-size:11px;margin:2px 0}.eg-relation-row.is-confirmed{border-color:#6e9c8b;background:#edf7f1;box-shadow:0 0 0 3px rgba(47,116,88,.08)}.eg-relation-warning{margin-top:7px;padding:7px 8px;border-radius:8px;background:#fff0e7;color:#8b4b2f;font-weight:750}.eg-relation-actions{display:flex;flex-wrap:wrap;gap:6px;margin-top:9px;padding-top:8px;border-top:1px solid var(--line)}.eg-relation-action{padding:6px 8px;border:1px solid #9bada6;border-radius:8px;background:#fff;color:var(--forest);font:inherit;font-size:9px;font-weight:800;cursor:pointer}.eg-relation-action[data-edge-delete]{border-color:#d5a29a;color:#8e3535}.eg-relation-confirmation{margin-top:9px;padding:9px;border:1px solid #d8b67d;border-radius:9px;background:#fff8e9;color:#674c24}.eg-relation-confirmation strong{margin:0 0 5px;color:#674c24}.eg-relation-confirmation span{display:block;margin-top:4px}.eg-relation-confirmation .eg-relation-actions{border-top-color:#e5cfaa}.eg-relation-action[data-edge-confirm="delete"]{border-color:#c47e73;background:#fff;color:#8e3535}.eg-relation-action:disabled,.eg-swap-button:disabled{cursor:wait;opacity:.55}.eg-relations-empty{padding:13px;border:1px dashed var(--line);border-radius:11px;color:var(--muted);font-size:11px;line-height:1.45}.eg-empty{padding:28px;border:1px dashed var(--line);border-radius:14px;text-align:center;color:var(--muted)}@media(max-width:1080px){.eg-layout{grid-template-columns:1fr}.eg-side{position:static}.eg-counts{grid-template-columns:repeat(4,1fr)}}@media(max-width:700px){.eg-toolbar{display:grid}.eg-contract{grid-template-columns:1fr}.eg-counts{grid-template-columns:repeat(2,1fr)}}`;
    document.head.appendChild(style);

    button.addEventListener('click',async()=>{
      document.querySelectorAll('[data-mission-tab]').forEach(item=>item.classList.toggle('active',item===button));
      document.querySelectorAll('.mission-tab').forEach(item=>item.classList.toggle('active',item===panel));
      await loadGraph();
    });
    document.querySelector('#eg-sync')?.addEventListener('click',syncAndLoad);
    document.querySelector('#eg-node-form')?.addEventListener('submit',createNode);
    document.querySelector('#eg-edge-form')?.addEventListener('submit',createEdge);
    document.querySelector('#eg-from')?.addEventListener('change',()=>updateEdgeFormState(true));
    document.querySelector('#eg-to')?.addEventListener('change',()=>updateEdgeFormState(true));
    document.querySelector('#eg-edge-type')?.addEventListener('change',()=>updateEdgeFormState(true));
    document.querySelector('#eg-edge-swap')?.addEventListener('click',swapEdgeDirection);
    document.querySelector('#eg-relations')?.addEventListener('click',handleRelationAction);
    document.querySelector('#eg-nodes')?.addEventListener('click',handleNodeReview);
    updateEdgeFormState(false);
    return true;
  }

  function setEdgeStatus(message,state='idle'){
    const status=document.querySelector('#eg-edge-status');
    if(!status)return;
    status.textContent=message;
    status.dataset.state=state;
  }

  function nodeName(node){
    if(!node)return'Objeto indisponível';
    return `${typeLabels[node.node_type]||node.node_type} · ${node.label}`;
  }

  function relationPhrase(edgeType,source){
    if(edgeType==='constrained_by')return feminineNodeTypes.has(source?.node_type)?'é condicionada por':'é condicionado por';
    return relationLabels[edgeType]||edgeType;
  }

  function relationSentence(edgeType,source,target){
    return `${nodeName(source)} — ${relationPhrase(edgeType,source)} → ${nodeName(target)}`;
  }

  function relationDirectionWarning(edgeType,source){
    if(edgeType!=='constrained_by'||source?.node_type!=='constraint')return'';
    return 'A frase atual diz que a própria Restrição é limitada pelo segundo objeto. Se pretende que a Restrição limite esse objeto, troque a ordem.';
  }

  function updateEdgeFormState(resetStatus=false){
    const graph=window.__srisEvidenceGraph||{nodes:[]};
    const nodes=graph.nodes||[];
    const from=document.querySelector('#eg-from');
    const to=document.querySelector('#eg-to');
    const edgeType=document.querySelector('#eg-edge-type');
    const submit=document.querySelector('#eg-edge-submit');
    const preview=document.querySelector('#eg-edge-preview');
    if(!from||!to||!edgeType||!submit||!preview)return;
    const source=nodes.find(node=>node.id===from.value);
    const target=nodes.find(node=>node.id===to.value);
    const valid=Boolean(source&&target&&source.id!==target.id);
    submit.disabled=!valid||submit.dataset.saving==='true';
    if(valid){
      const guidance=relationGuidance[edgeType.value]||'Leia a frase exatamente pela ordem apresentada.';
      const warning=relationDirectionWarning(edgeType.value,source);
      preview.innerHTML=`<span class="eg-preview-caption">Frase que será guardada</span><strong>${esc(nodeName(source))}</strong><span class="eg-relation-phrase">${esc(relationPhrase(edgeType.value,source))}</span><strong>${esc(nodeName(target))}</strong><span class="eg-direction-help">${esc(guidance)}</span>${warning?`<span class="eg-direction-warning">${esc(warning)}</span>`:''}`;
      const currentStatus=document.querySelector('#eg-edge-status')?.textContent||'';
      if(resetStatus||currentStatus.startsWith('Selecione dois objetos'))setEdgeStatus('Relação pronta a guardar. A confirmação aparecerá aqui.','idle');
    }else{
      preview.textContent=nodes.length<2?'São necessários pelo menos dois objetos no grafo.':'Escolha dois objetos diferentes.';
      if(resetStatus)setEdgeStatus(preview.textContent,'error');
    }
  }

  function swapEdgeDirection(){
    const from=document.querySelector('#eg-from');
    const to=document.querySelector('#eg-to');
    if(!from||!to||!from.value||!to.value)return;
    const previousFrom=from.value;
    from.value=to.value;
    to.value=previousFrom;
    updateEdgeFormState(false);
    setEdgeStatus('Ordem trocada. Confirme a frase apresentada antes de guardar.','idle');
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
      return graph;
    }catch(error){
      if(status)status.textContent=`Não foi possível abrir o grafo: ${error.message}`;
      return null;
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
          return `<span class="eg-edge${edge.id===lastConfirmedEdgeId?' is-confirmed':''}">${esc(relationPhrase(edge.edge_type,node))} → ${esc((target?.label||edge.to_node_id).slice(0,60))}</span>`;
        }).join('');
        const confidence=node.confidence===null||node.confidence===undefined?'não avaliada':`${Math.round(Number(node.confidence)*100)}%`;
        const sourceIntegrity=(node.source_kind==='document_chunk'||node.source_kind==='visual_document')&&node.provenance?.source_integrity_verified?'<span class="pill eg-source-integrity">Fonte íntegra</span>':'';
        const verification=(node.node_type==='evidence'||node.node_type==='outcome')?`<button type="button" data-eg-node="${esc(node.id)}" data-eg-review="verified">Verificar factual</button>`:'';
        const review=node.status==='proposed'&&node.node_type!=='learning'?`<div class="eg-node-review" aria-label="Revisão humana"><button type="button" data-eg-node="${esc(node.id)}" data-eg-review="accepted">Aceitar após revisão</button>${verification}<button type="button" data-eg-node="${esc(node.id)}" data-eg-review="rejected">Rejeitar</button></div>`:'';
        return `<article class="eg-node" data-type="${esc(node.node_type)}"><div class="eg-node-head"><div><span class="eg-type">${esc(typeLabels[node.node_type]||node.node_type)}</span><strong style="display:block;margin-top:8px">${esc(node.label)}</strong></div><div class="eg-badges">${sourceIntegrity}<span class="pill">${esc(statusLabels[node.status]||node.status)}</span></div></div><p>${esc((node.body||'').slice(0,2200))}</p><div class="eg-prov">${provenanceText(node)} · <span class="eg-confidence">confiança ${confidence}</span></div>${review}${outgoing?`<div class="eg-edges">${outgoing}</div>`:''}</article>`;
      }).join(''):'<div class="eg-empty">Ainda não existem objetos no grafo. Adicione observações, evidência, pressupostos, restrições, hipóteses ou decisões — ou sincronize uma análise já realizada.</div>';
    }

    const from=document.querySelector('#eg-from');
    const to=document.querySelector('#eg-to');
    const previousFrom=from?.value||'';
    const previousTo=to?.value||'';
    const options=nodes.map(node=>`<option value="${esc(node.id)}">${esc((typeLabels[node.node_type]||node.node_type)+' · '+node.label.slice(0,70))}</option>`).join('');
    if(from)from.innerHTML=options;
    if(to)to.innerHTML=options;
    const availableIds=new Set(nodes.map(node=>node.id));
    if(from&&availableIds.has(previousFrom))from.value=previousFrom;
    if(to&&availableIds.has(previousTo))to.value=previousTo;
    if(from&&to&&from.value===to.value){
      const distinct=nodes.find(node=>node.id!==from.value);
      if(distinct)to.value=distinct.id;
    }
    renderRelations(graph);
    updateEdgeFormState(false);

    const detailCounts=document.querySelector('#detail-epistemic-counts');
    if(detailCounts){
      detailCounts.innerHTML=`<span>Pressupostos · ${Number(counts.assumption||0)}</span><span>Restrições · ${Number(counts.constraint||0)}</span><span>Lacunas · ${Number(counts.gap||0)}</span><span>Proveniência · ativa</span>`;
    }
  }

  function renderRelations(graph){
    const root=document.querySelector('#eg-relations');
    const count=document.querySelector('#eg-relations-count');
    if(!root||!count)return;
    const nodesById=Object.fromEntries((graph.nodes||[]).map(node=>[node.id,node]));
    const edges=[...(graph.edges||[])].reverse();
    count.textContent=String(edges.length);
    root.innerHTML=edges.length?edges.map(edge=>{
      const source=nodesById[edge.from_node_id];
      const target=nodesById[edge.to_node_id];
      const warning=relationDirectionWarning(edge.edge_type,source);
      const pending=pendingRelationAction?.edgeId===edge.id?pendingRelationAction:null;
      const reversedSentence=relationSentence(edge.edge_type,target,source);
      const actions=pending
        ?`<div class="eg-relation-confirmation" role="alert"><strong>${pending.action==='delete'?'Confirmar eliminação':'Confirmar inversão'}</strong>${pending.action==='delete'?'<span>A relação desaparecerá do grafo, mas a operação ficará registada na auditoria.</span>':`<span>Nova direção: ${esc(reversedSentence)}</span>`}<div class="eg-relation-actions"><button type="button" class="eg-relation-action" data-edge-confirm="${esc(pending.action)}" data-edge-id="${esc(edge.id)}">${pending.action==='delete'?'Eliminar relação':'Confirmar inversão'}</button><button type="button" class="eg-relation-action" data-edge-cancel="${esc(edge.id)}">Cancelar</button></div></div>`
        :`<div class="eg-relation-actions"><button type="button" class="eg-relation-action" data-edge-reverse="${esc(edge.id)}">⇄ Inverter direção</button><button type="button" class="eg-relation-action" data-edge-delete="${esc(edge.id)}">Eliminar</button></div>`;
      return `<article class="eg-relation-row${edge.id===lastConfirmedEdgeId?' is-confirmed':''}" data-edge-id="${esc(edge.id)}"><span>${esc(nodeName(source))}</span><strong>${esc(relationPhrase(edge.edge_type,source))} →</strong><span>${esc(nodeName(target))}</span>${warning?`<div class="eg-relation-warning">Possível direção invertida: ${esc(warning)}</div>`:''}${actions}</article>`;
    }).join(''):'<div class="eg-relations-empty">Ainda não existem relações explícitas. A primeira relação confirmada ficará visível aqui.</div>';
  }

  async function handleRelationAction(event){
    const cancelButton=event.target.closest('[data-edge-cancel]');
    if(cancelButton){
      pendingRelationAction=null;
      renderRelations(window.__srisEvidenceGraph||{nodes:[],edges:[]});
      setEdgeStatus('Operação cancelada. Nenhuma relação foi alterada.','idle');
      return;
    }
    const confirmButton=event.target.closest('[data-edge-confirm]');
    const reverseButton=event.target.closest('[data-edge-reverse]');
    const deleteButton=event.target.closest('[data-edge-delete]');
    const button=confirmButton||reverseButton||deleteButton;
    if(!button)return;
    const code=missionCode();
    const edgeId=button.dataset.edgeId||button.dataset.edgeReverse||button.dataset.edgeDelete;
    const graph=window.__srisEvidenceGraph||{nodes:[],edges:[]};
    const edge=(graph.edges||[]).find(candidate=>candidate.id===edgeId);
    if(!code||!edge){
      setEdgeStatus('Não foi possível identificar a relação selecionada. Atualize o grafo e tente novamente.','error');
      return;
    }
    const source=(graph.nodes||[]).find(node=>node.id===edge.from_node_id);
    const target=(graph.nodes||[]).find(node=>node.id===edge.to_node_id);
    const currentSentence=relationSentence(edge.edge_type,source,target);
    const status=document.querySelector('#eg-status');
    const action=confirmButton?.dataset.edgeConfirm||(deleteButton?'delete':'reverse');

    if(!confirmButton){
      pendingRelationAction={edgeId,action};
      renderRelations(graph);
      setEdgeStatus(action==='delete'?'Confirme a eliminação dentro da relação selecionada.':'Confirme a nova direção dentro da relação selecionada.','pending');
      return;
    }

    if(action==='delete'){
      button.disabled=true;
      setEdgeStatus('A eliminar e a confirmar a remoção no servidor…','pending');
      try{
        await req(`/api/pilot/evidence-graph/missions/${encodeURIComponent(code)}/edges/${encodeURIComponent(edgeId)}`,{method:'DELETE'});
        lastConfirmedEdgeId='';
        pendingRelationAction=null;
        const confirmedGraph=await loadGraph();
        if((confirmedGraph?.edges||[]).some(candidate=>candidate.id===edgeId))throw new Error('O servidor ainda devolveu a relação depois da eliminação.');
        status.textContent='Relação eliminada e ausência confirmada no grafo persistente.';
        setEdgeStatus(`Relação eliminada e confirmada: ${currentSentence}.`,'success');
      }catch(error){
        pendingRelationAction=null;
        renderRelations(window.__srisEvidenceGraph||{nodes:[],edges:[]});
        status.textContent=`Não foi possível eliminar a relação: ${error.message}`;
        setEdgeStatus(`A relação não foi eliminada: ${error.message}`,'error');
      }
      return;
    }

    const reversedSentence=relationSentence(edge.edge_type,target,source);
    button.disabled=true;
    setEdgeStatus('A inverter e a confirmar a nova direção no servidor…','pending');
    try{
      const reversed=await req(`/api/pilot/evidence-graph/missions/${encodeURIComponent(code)}/edges/${encodeURIComponent(edgeId)}/reverse`,{method:'POST'});
      lastConfirmedEdgeId=reversed.id;
      pendingRelationAction=null;
      const confirmedGraph=await loadGraph();
      const persisted=(confirmedGraph?.edges||[]).find(candidate=>candidate.id===edgeId&&candidate.from_node_id===edge.to_node_id&&candidate.to_node_id===edge.from_node_id);
      if(!persisted)throw new Error('O servidor não confirmou a relação com a direção invertida.');
      lastConfirmedEdgeId=persisted.id;
      render(confirmedGraph);
      status.textContent='Direção corrigida e confirmada no grafo persistente.';
      setEdgeStatus(`Direção corrigida e confirmada: ${reversedSentence}.`,'success');
    }catch(error){
      pendingRelationAction=null;
      renderRelations(window.__srisEvidenceGraph||{nodes:[],edges:[]});
      status.textContent=`Não foi possível inverter a relação: ${error.message}`;
      setEdgeStatus(`A direção não foi alterada: ${error.message}`,'error');
    }
  }

  async function handleNodeReview(event){
    const button=event.target.closest('[data-eg-node][data-eg-review]');
    if(!button)return;
    const code=missionCode();
    const nodeId=button.dataset.egNode;
    const nextStatus=button.dataset.egReview;
    const status=document.querySelector('#eg-status');
    if(!code||!nodeId||!nextStatus)return;
    const labels={accepted:'a aceitar',verified:'a verificar factualmente',rejected:'a rejeitar'};
    button.disabled=true;
    if(status)status.textContent=`Revisão humana ${labels[nextStatus]||'a guardar'}…`;
    try{
      await req(`/api/pilot/evidence-graph/missions/${encodeURIComponent(code)}/nodes/${encodeURIComponent(nodeId)}`,{
        method:'PATCH',
        body:JSON.stringify({status:nextStatus}),
      });
      await loadGraph();
      if(status)status.textContent=`Revisão humana guardada: ${statusLabels[nextStatus]||nextStatus}. A decisão continua sob autoridade humana.`;
    }catch(error){
      button.disabled=false;
      if(status)status.textContent=`Não foi possível guardar a revisão: ${error.message}`;
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
      status:'proposed',
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
    const form=event.currentTarget;
    const from=document.querySelector('#eg-from').value;
    const to=document.querySelector('#eg-to').value;
    const edgeType=document.querySelector('#eg-edge-type').value;
    const submit=form.querySelector('#eg-edge-submit');
    const status=document.querySelector('#eg-status');
    if(!from||!to||from===to){
      status.textContent='Escolha dois objetos diferentes.';
      setEdgeStatus('A relação não foi criada: escolha dois objetos diferentes.','error');
      updateEdgeFormState(false);
      return;
    }
    const currentGraph=window.__srisEvidenceGraph||{nodes:[],edges:[]};
    const source=currentGraph.nodes.find(node=>node.id===from);
    const target=currentGraph.nodes.find(node=>node.id===to);
    const existing=(currentGraph.edges||[]).find(edge=>edge.from_node_id===from&&edge.to_node_id===to&&edge.edge_type===edgeType);
    if(existing){
      lastConfirmedEdgeId=existing.id;
      render(currentGraph);
      const sentence=relationSentence(edgeType,source,target);
      status.textContent='A relação selecionada já estava guardada.';
      setEdgeStatus(`Relação já existente e confirmada: ${sentence}.`,'success');
      return;
    }
    const originalLabel=submit.textContent;
    form.setAttribute('aria-busy','true');
    submit.dataset.saving='true';
    submit.disabled=true;
    submit.textContent='A guardar…';
    setEdgeStatus('A guardar e a confirmar a relação no servidor…','pending');
    try{
      const savedEdge=await req(`/api/pilot/evidence-graph/missions/${encodeURIComponent(code)}/edges`,{
        method:'POST',
        body:JSON.stringify({
          from_node_id:from,
          to_node_id:to,
          edge_type:edgeType,
          provenance:{workspace:'pilot-v1',explicit:true,human_curated:true},
        }),
      });
      lastConfirmedEdgeId=savedEdge.id;
      const confirmedGraph=await loadGraph();
      const persisted=(confirmedGraph?.edges||[]).find(edge=>edge.id===savedEdge.id||(edge.from_node_id===from&&edge.to_node_id===to&&edge.edge_type===edgeType));
      if(!persisted)throw new Error('O servidor não devolveu a relação no grafo persistente.');
      lastConfirmedEdgeId=persisted.id;
      render(confirmedGraph);
      const sentence=relationSentence(edgeType,source,target);
      const outcome=savedEdge.created===false?'Relação já existente e confirmada':'Relação criada e confirmada';
      status.textContent=`${outcome} no grafo persistente.`;
      setEdgeStatus(`${outcome}: ${sentence}.`,'success');
    }catch(error){
      status.textContent=`Não foi possível guardar a relação: ${error.message}`;
      setEdgeStatus(`A relação não foi criada: ${error.message}`,'error');
    }finally{
      form.setAttribute('aria-busy','false');
      submit.dataset.saving='false';
      submit.textContent=originalLabel;
      updateEdgeFormState(false);
    }
  }

  if(!install())document.addEventListener('DOMContentLoaded',install,{once:true});
})();
