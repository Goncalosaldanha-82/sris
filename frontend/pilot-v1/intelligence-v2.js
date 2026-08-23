(()=>{
  const nativeFetch=window.fetch.bind(window);
  window.fetch=(input,init={})=>{
    let url=typeof input==='string'?input:input?.url;
    if(url==='/api/pilot/ai/ask'){
      url='/api/pilot/intelligence/ask';
      if(typeof input==='string')input=url;else input=new Request(url,input);
    }
    return nativeFetch(input,init);
  };
  function token(){return localStorage.getItem('sris_access_token')}
  function provenanceSummary(data){
    const ctx=data?.context||{},sources=ctx.sources||[],retrieval=ctx.retrieval||{};
    if(!sources.length)return'';
    const lines=sources.slice(0,4).map((s,i)=>`${i+1}. ${s.filename} · chars ${s.char_start}-${s.char_end} · lexical ${s.lexical_rank??'—'} · semântico ${s.semantic_rank??'—'} · hash ${String(s.content_sha256||'').slice(0,10)}…`);
    return `\n\nContexto recuperado pelo SRIS\nModo: ${retrieval.mode||ctx.retrieval_mode||'—'} · modelo semântico: ${retrieval.embedding_model||'não utilizado'}\n${lines.join('\n')}`;
  }
  async function governedMissionAnalysis(button){
    const codeNode=document.querySelector('#detail-code');
    const answer=document.querySelector('#mission-answer');
    if(!codeNode||!answer)return;
    const raw=(codeNode.textContent||'').trim();
    const parts=raw.split('/').map(x=>x.trim()).filter(Boolean);
    const missionCode=parts[parts.length-1]||raw;
    const title=(document.querySelector('#detail-title')?.textContent||'').trim();
    const objective=(document.querySelector('#detail-objective')?.textContent||'').trim();
    const question=(document.querySelector('#detail-question')?.textContent||'').trim();
    const context=(document.querySelector('#detail-context')?.textContent||'').trim();
    const message=`Analisa esta missão persistente do SRIS. Distingue rigorosamente factos confirmados, declarações, inferências, hipóteses, lacunas de evidência, riscos, alternativas e próximos passos.\n\nMissão: ${missionCode} — ${title}\nObjetivo: ${objective}\nPergunta central: ${question}`;
    answer.classList.remove('empty');answer.textContent='A recuperar contexto lexical, semântico e proveniência…';button?.classList.add('loading');
    try{
      const res=await nativeFetch('/api/pilot/intelligence/ask',{method:'POST',headers:{'Content-Type':'application/json','Authorization':`Bearer ${token()}`},body:JSON.stringify({message,context,mission_code:missionCode})});
      let data={};try{data=await res.json()}catch{}
      if(res.status===401){localStorage.removeItem('sris_access_token');location.href='/';return;}
      if(!res.ok){const detail=data?.detail;throw new Error(typeof detail==='string'?detail:(detail?.message||detail?.code||`Erro ${res.status}`));}
      answer.textContent=data.answer+provenanceSummary(data);
      const sourceCount=data?.context?.sources?.length||0;const cost=Number(data?.charged_eur||0).toFixed(4);const retrieval=data?.context?.retrieval||{};
      const history=document.querySelector('#dialogue-history');if(history){const row=document.createElement('div');row.className='timeline-row';row.innerHTML=`<span class="timeline-dot"></span><div><strong>Análise governada concluída</strong><div class="note">${sourceCount} excerto(s) · ${retrieval.mode||'retrieval'} · ${retrieval.semantic_status||'—'} · ${cost} € · ${new Date().toLocaleString('pt-PT')}</div></div>`;history.prepend(row);}
      return data;
    }catch(err){answer.textContent=`Não foi possível concluir: ${err.message}`;answer.classList.add('empty');throw err;}
    finally{button?.classList.remove('loading');}
  }
  window.SRISGovernedMissionAnalysis=governedMissionAnalysis;

  // Compatibility only. In Pilot V1 integrated mode the Mission Workspace owns
  // the primary mission CTA and opens the persistent dialogue.  The former
  // document-level capture handler stopped that CTA before the workspace could
  // receive the click, making the deployed product look like the old prototype.
  document.addEventListener('click',event=>{
    const button=event.target.closest?.('#detail-analyze-btn');if(!button)return;
    if(document.querySelector('[data-mission-tab="intelligence"]'))return;
    event.preventDefault();event.stopImmediatePropagation();governedMissionAnalysis(button).catch(()=>{});
  },true);
})();
