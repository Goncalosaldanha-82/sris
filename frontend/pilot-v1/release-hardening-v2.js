/* SRIS Pilot V1 — release hardening V2
   Mission Intelligence remains the product centre; assisted analysis is optional.
*/
(()=>{
  'use strict';

  if(window.__srisReleaseHardeningV2)return;
  window.__srisReleaseHardeningV2=true;

  const BUILD='20260823-release-hardening-v2';
  const $=(selector,root=document)=>root.querySelector(selector);
  const $$=(selector,root=document)=>[...root.querySelectorAll(selector)];
  const token=()=>localStorage.getItem('sris_access_token');
  const organizationId=()=>localStorage.getItem('sris_org_id')||'';
  const baseFetch=window.fetch.bind(window);
  let attachmentSignature='';
  let attachmentLoading=false;
  let refreshTimer=null;

  window.__srisReleaseHardeningBuild=BUILD;
  document.documentElement.dataset.releaseHardening=BUILD;

  function ensureStyles(){
    if($('link[data-sris-release-hardening]'))return;
    const link=document.createElement('link');
    link.rel='stylesheet';
    link.href='/release-hardening-v2.css?v=20260823-release-hardening-v2';
    link.dataset.srisReleaseHardening='true';
    document.head.appendChild(link);
  }

  function escapeHtml(value=''){
    return String(value??'').replace(/[&<>"']/g,char=>({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    }[char]));
  }

  function slug(value='missao-sris'){
    return String(value||'missao-sris')
      .normalize('NFD').replace(/[\u0300-\u036f]/g,'')
      .toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'')||'missao-sris';
  }

  function currentMissionCode(){
    const raw=($('#detail-code')?.textContent||'').trim();
    const parts=raw.split('/').map(part=>part.trim()).filter(Boolean);
    return parts[parts.length-1]||'';
  }

  function missionBase(){
    const org=organizationId();
    return org?`/api/organizations/${encodeURIComponent(org)}/mission-intelligence`:'';
  }

  async function authorizedFetch(url,options={}){
    const headers={...(options.headers||{})};
    if(token())headers.Authorization=`Bearer ${token()}`;
    const response=await baseFetch(url,{...options,headers,cache:'no-store'});
    if(!response.ok){
      let message=`Erro ${response.status}`;
      try{
        const data=await response.json();
        const detail=data?.detail;
        message=typeof detail==='string'?detail:(detail?.message||detail?.code||data?.message||message);
      }catch{}
      throw new Error(message);
    }
    return response;
  }

  function downloadBlob(blob,filename){
    const url=URL.createObjectURL(blob);
    const anchor=document.createElement('a');
    anchor.href=url;
    anchor.download=filename;
    anchor.style.display='none';
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(()=>URL.revokeObjectURL(url),1200);
  }

  function installInstitutionalBrand(){
    $$('.brand-emblem').forEach(current=>{
      if(current.classList.contains('sris-mark-v2'))return;
      const mark=document.createElement('span');
      const extra=[...current.classList].filter(name=>name!=='brand-emblem');
      mark.className=['sris-mark-v2',...extra].join(' ');
      mark.setAttribute('aria-hidden','true');
      mark.title='SRIS — Mission Intelligence';
      current.replaceWith(mark);
    });
    $$('.brand-copy').forEach(copy=>{
      const strong=$('strong',copy);
      const small=$('small',copy);
      if(strong)strong.textContent='SRIS';
      if(small)small.textContent='MISSION INTELLIGENCE';
      copy.setAttribute('aria-label','SRIS — Mission Intelligence');
    });
  }

  function setMenuState(open){
    const sidebar=$('#sidebar');
    const toggle=$('#menu-btn');
    sidebar?.classList.toggle('open',open);
    document.documentElement.classList.toggle('sris-sidebar-open',open);
    toggle?.setAttribute('aria-expanded',String(open));
  }

  function installMenu(){
    const sidebar=$('#sidebar');
    const toggle=$('#menu-btn');
    if(!sidebar||!toggle)return;
    toggle.classList.add('sris-menu-toggle');
    toggle.setAttribute('aria-controls','sidebar');
    toggle.setAttribute('aria-expanded','false');
    toggle.title='Abrir ou recolher a navegação';

    let overlay=$('.sris-menu-overlay');
    if(!overlay){
      overlay=document.createElement('button');
      overlay.type='button';
      overlay.className='sris-menu-overlay';
      overlay.setAttribute('aria-label','Fechar navegação');
      document.body.appendChild(overlay);
      overlay.addEventListener('click',()=>setMenuState(false));
    }

    if(matchMedia('(min-width:901px)').matches)setMenuState(true);
    else setMenuState(false);

    toggle.addEventListener('click',()=>{
      // app.js performs the canonical sidebar toggle; synchronize the release shell afterwards.
      setTimeout(()=>setMenuState(sidebar.classList.contains('open')),0);
    });

    $$('.nav button',sidebar).forEach(button=>button.addEventListener('click',()=>{
      if(matchMedia('(max-width:900px)').matches)setMenuState(false);
    }));

    window.addEventListener('resize',()=>{
      if(matchMedia('(min-width:901px)').matches&&!document.documentElement.classList.contains('sris-sidebar-open'))return;
      setMenuState(sidebar.classList.contains('open'));
    },{passive:true});
  }

  function installEditorialPhotography(){
    const overview=$('#overview');
    if(!overview||$('#sris-editorial-panel'))return;
    const anchor=$('.decision-chain',overview)||$('.hero-card',overview);
    if(!anchor)return;
    const panel=document.createElement('article');
    panel.id='sris-editorial-panel';
    panel.className='sris-editorial-panel';
    // Keep the exact asset contract auditable: url('/sunrise.svg')
    panel.innerHTML=`<div class="sris-editorial-panel__content">
      <div class="eyebrow">DISCIPLINA ANTES DA AÇÃO</div>
      <h3>Compreender antes de intervir.</h3>
      <p>O SRIS mantém explícito o que é facto, inferência, pressuposto, restrição ou lacuna. A assistência deve indicar incerteza e nunca preencher lacunas com confiança artificial.</p>
    </div>`;
    anchor.insertAdjacentElement('afterend',panel);
  }

  function installUploadZone(){
    const tab=$('#mission-tab-documents');
    const row=$('.upload-row',tab||document);
    if(!tab||!row||$('#sris-upload-zone'))return;

    const heading=$('h3',tab);
    if(heading)heading.textContent='Documentos e fontes';

    const zone=document.createElement('section');
    zone.id='sris-upload-zone';
    zone.className='sris-upload-zone';
    zone.innerHTML=`<div class="sris-upload-zone__head"><div><h4>Carregar documentos</h4><p>PDF, Word, Excel, PowerPoint, imagens e texto. Cada ficheiro fica associado à missão, com extração e proveniência.</p></div><span class="pill">Inteligência documental</span></div>`;
    row.parentNode.insertBefore(zone,row);
    zone.appendChild(row);

    const input=$('#mission-file');
    const button=$('#upload-file-btn');
    if(button)button.textContent='Selecionar e carregar';

    ['dragenter','dragover'].forEach(type=>zone.addEventListener(type,event=>{
      event.preventDefault();
      zone.classList.add('dragover');
    }));
    ['dragleave','drop'].forEach(type=>zone.addEventListener(type,event=>{
      event.preventDefault();
      zone.classList.remove('dragover');
    }));
    zone.addEventListener('drop',event=>{
      const files=event.dataTransfer?.files;
      if(!input||!files?.length)return;
      try{input.files=files;}catch{}
      button?.click();
    });
  }

  async function downloadAttachment(id,filename,button){
    const code=currentMissionCode();
    const base=missionBase();
    if(!base||!code||!id)return;
    button?.classList.add('loading');
    try{
      const response=await authorizedFetch(`${base}/missions/${encodeURIComponent(code)}/attachments/${encodeURIComponent(id)}/download`);
      downloadBlob(await response.blob(),filename||'documento');
    }catch(error){
      alert(`Não foi possível descarregar o documento: ${error.message}`);
    }finally{
      button?.classList.remove('loading');
    }
  }

  async function renderAttachmentActions(force=false){
    const root=$('#attachment-list');
    const code=currentMissionCode();
    const base=missionBase();
    if(!root||!code||!base||attachmentLoading)return;
    if(root.closest('.mission-tab')&&!root.closest('.mission-tab').classList.contains('active')&&!force)return;

    attachmentLoading=true;
    try{
      const response=await authorizedFetch(`${base}/missions/${encodeURIComponent(code)}/attachments`);
      const rows=await response.json();
      const signature=JSON.stringify((rows||[]).map(item=>[item.id,item.extraction_status,item.byte_size]));
      if(!force&&signature===attachmentSignature&&root.dataset.releaseEnhanced==='true')return;
      attachmentSignature=signature;
      root.dataset.releaseEnhanced='true';
      root.innerHTML=rows.length?rows.map(item=>`
        <div class="attachment-row" data-attachment-id="${escapeHtml(item.id)}">
          <span><strong>${escapeHtml(item.original_filename||item.filename||'Documento')}</strong><small>${escapeHtml(item.extraction_status||'registado')}${item.byte_size?` · ${Math.ceil(Number(item.byte_size)/1024)} KB`:''}</small></span>
          <span class="sris-attachment-actions"><span class="pill">${escapeHtml(item.extension||'ficheiro')}</span><button type="button" data-download-attachment="${escapeHtml(item.id)}" data-filename="${escapeHtml(item.original_filename||item.filename||'documento')}">Descarregar</button></span>
        </div>`).join(''):'<div class="note">Sem documentos carregados. Use “Carregar documentos” para fundamentar a missão.</div>';
      $$('[data-download-attachment]',root).forEach(button=>button.addEventListener('click',()=>downloadAttachment(button.dataset.downloadAttachment,button.dataset.filename,button)));
    }catch(error){
      if(!root.children.length)root.innerHTML=`<div class="note">Documentos temporariamente indisponíveis: ${escapeHtml(error.message)}</div>`;
    }finally{
      attachmentLoading=false;
    }
  }

  function reportSnapshot(){
    const title=($('#detail-title')?.textContent||'Missão SRIS').trim();
    const code=currentMissionCode()||'MISSÃO';
    const objective=($('#detail-objective')?.textContent||'').trim();
    const question=($('#detail-question')?.textContent||'').trim();
    const context=($('#detail-context')?.textContent||'').trim();
    const meta=($('#detail-meta')?.innerText||'').trim();
    const activeTab=$('.mission-tab.active');
    const sectionTitle=($('.mission-tabs button.active')?.textContent||'Secção atual').trim();
    const sectionText=(activeTab?.innerText||'').trim();
    return {title,code,objective,question,context,meta,sectionTitle,sectionText,generatedAt:new Date()};
  }

  function completeReportHtml(snapshot=reportSnapshot()){
    const generated=snapshot.generatedAt.toLocaleString('pt-PT');
    return `<!doctype html><html lang="pt-PT"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escapeHtml(snapshot.code)} — ${escapeHtml(snapshot.title)}</title><style>
      :root{--ink:#0d201a;--green:#123f34;--gold:#c7963e;--paper:#f7f4ec}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.65 Arial,sans-serif}main{max-width:920px;margin:auto;padding:54px}header{padding-bottom:28px;border-bottom:2px solid var(--gold)}.brand{font-weight:800;letter-spacing:.12em;color:var(--green)}h1,h2{font-family:Georgia,serif;font-weight:500}h1{font-size:42px;line-height:1.04;margin:20px 0 8px}h2{font-size:25px;margin:30px 0 10px}section{padding:0 0 18px;border-bottom:1px solid #d9dfda;white-space:pre-wrap}.meta{color:#61716a}.stamp{margin-top:34px;color:#708078;font-size:12px}@media print{body{background:#fff}main{padding:20mm}.no-print{display:none}}</style></head><body><main><header><div class="brand">SRIS · MISSION INTELLIGENCE</div><h1>${escapeHtml(snapshot.title)}</h1><div class="meta">${escapeHtml(snapshot.code)}${snapshot.meta?` · ${escapeHtml(snapshot.meta)}`:''}</div></header><section><h2>Objetivo</h2>${escapeHtml(snapshot.objective||'Não registado')}</section><section><h2>Pergunta central</h2>${escapeHtml(snapshot.question||'Não registada')}</section><section><h2>Contexto</h2>${escapeHtml(snapshot.context||'Não registado')}</section><section><h2>${escapeHtml(snapshot.sectionTitle)}</h2>${escapeHtml(snapshot.sectionText||'Sem conteúdo registado nesta secção.')}</section><div class="stamp">Relatório gerado em ${escapeHtml(generated)}. Documento de trabalho SRIS sujeito a revisão humana.</div></main></body></html>`;
  }

  function makePdf(){
    const snapshot=reportSnapshot();
    const popup=window.open('','_blank','noopener,noreferrer');
    if(!popup){alert('Permita janelas adicionais para gerar o relatório em PDF.');return;}
    popup.document.open();
    popup.document.write(completeReportHtml(snapshot));
    popup.document.close();
    popup.addEventListener('load',()=>setTimeout(()=>popup.print(),250),{once:true});
  }
  window.makePdf=makePdf;

  function downloadFullHtml(){
    const snapshot=reportSnapshot();
    const blob=new Blob([completeReportHtml(snapshot)],{type:'text/html;charset=utf-8'});
    downloadBlob(blob,`${slug(snapshot.code+'-'+snapshot.title)}-relatorio.html`);
  }

  function downloadCurrentMarkdown(){
    const snapshot=reportSnapshot();
    const markdown=`# ${snapshot.title}\n\n**Missão:** ${snapshot.code}\n\n## ${snapshot.sectionTitle}\n\n${snapshot.sectionText||'Sem conteúdo registado nesta secção.'}\n\n---\nGerado pelo SRIS Mission Intelligence em ${snapshot.generatedAt.toLocaleString('pt-PT')}.\n`;
    downloadBlob(new Blob([markdown],{type:'text/markdown;charset=utf-8'}),`${slug(snapshot.code+'-'+snapshot.sectionTitle)}.md`);
  }

  function installReportActions(){
    const detail=$('#mission-detail');
    const head=$('.detail-head',detail||document);
    if(!detail||!head||$('#sris-report-actions'))return;
    const actions=document.createElement('div');
    actions.id='sris-report-actions';
    actions.className='sris-report-actions';
    actions.innerHTML=`<button type="button" data-report="pdf">Relatório completo (.pdf)</button><button type="button" data-report="html">Relatório completo (.html)</button><button type="button" data-report="md">Secção atual (.md)</button>`;
    head.appendChild(actions);
    $('[data-report="pdf"]',actions)?.addEventListener('click',makePdf);
    $('[data-report="html"]',actions)?.addEventListener('click',downloadFullHtml);
    $('[data-report="md"]',actions)?.addEventListener('click',downloadCurrentMarkdown);
  }

  async function syncAssistanceTruth(){
    const submit=$('#copilot-form button[type="submit"]');
    const card=$('#copilot .card');
    if(!submit||!card||!token())return;
    let note=$('#sris-ai-runtime-truth');
    if(!note){
      note=document.createElement('div');
      note.id='sris-ai-runtime-truth';
      note.className='sris-runtime-truth';
      card.insertBefore(note,$('#copilot-quick-actions')||$('#copilot-form'));
    }
    let ready=false;
    try{
      const response=await authorizedFetch('/api/pilot/profile');
      const profile=await response.json();
      const ai=profile?.ai||{};
      ready=Boolean(ai.provider_configured&&ai.runtime_enabled&&ai.organization_enabled!==false);
    }catch{}
    submit.disabled=!ready;
    note.dataset.ready=String(ready);
    if(ready){
      note.innerHTML='<strong>Análise assistida disponível</strong>O motor está configurado para apoiar a missão ativa. A resposta permanece sujeita a revisão humana.';
    }else{
      note.innerHTML='<strong>Análise assistida indisponível</strong>O Mission Workspace continua operacional sem IA. Missões, documentos, decisões, resultados e memória permanecem disponíveis.';
    }
    const availability=$('#copilot-availability');
    if(availability)availability.textContent=ready?'Disponível':'Indisponível';
  }

  function scheduleAttachmentRefresh(force=false){
    clearTimeout(refreshTimer);
    refreshTimer=setTimeout(()=>renderAttachmentActions(force),180);
  }

  function installObservers(){
    const observer=new MutationObserver(mutations=>{
      let missionChanged=false;
      let attachmentChanged=false;
      for(const mutation of mutations){
        if(mutation.target?.id==='detail-code'||mutation.target?.closest?.('#mission-detail'))missionChanged=true;
        if(mutation.target?.id==='attachment-list'||mutation.target?.closest?.('#attachment-list'))attachmentChanged=true;
      }
      installInstitutionalBrand();
      installUploadZone();
      installReportActions();
      if(missionChanged||attachmentChanged)scheduleAttachmentRefresh(missionChanged);
    });
    observer.observe(document.body,{subtree:true,childList:true,characterData:true});

    $$('[data-mission-tab]').forEach(button=>button.addEventListener('click',()=>{
      if(button.dataset.missionTab==='documents')scheduleAttachmentRefresh(true);
    }));
  }

  function boot(){
    ensureStyles();
    installInstitutionalBrand();
    installMenu();
    installEditorialPhotography();
    installUploadZone();
    installReportActions();
    installObservers();
    syncAssistanceTruth();
    setTimeout(()=>{
      installInstitutionalBrand();
      installUploadZone();
      installReportActions();
      scheduleAttachmentRefresh(true);
      syncAssistanceTruth();
    },1100);
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});
  else boot();
})();
