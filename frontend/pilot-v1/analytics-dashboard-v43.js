(()=>{
  'use strict';
  const el=document.getElementById('content');
  const token=()=>localStorage.getItem('sris_access_token')||'';
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let generation=0,controller=null,lastToken=token(),period=30;
  function clear(text='Área reservada ao proprietário da plataforma SRIS.'){
    generation+=1;controller?.abort();controller=null;el.textContent=text;
  }
  function render(d){
    const rows=(d.daily||[]).map(x=>`<tr>${['date','site','demo','app','login','pilots'].map(k=>`<td>${esc(x[k])}</td>`).join('')}</tr>`).reverse().join('');
    const src=(d.sources||[]).map(x=>`<tr><td>${esc(x.source)}</td><td>${esc(x.views)}</td></tr>`).join('');
    const cards=[['Site',d.views.site],['Demonstração',d.views.demo],['Aplicação',d.views.app]].map(([label,value])=>`<div class="card"><div class="eyebrow">${label}</div><div class="value">${esc(value)}</div><div class="muted">visualizações</div></div>`).join('');
    el.innerHTML=`<section class="cards">${cards}</section><section class="grid"><div class="panel"><div class="eyebrow">Evolução diária</div><table><thead><tr><th>Data</th><th>Site</th><th>Demo</th><th>App</th><th>Login</th><th>Pilotos</th></tr></thead><tbody>${rows||'<tr><td colspan="6">Sem dados ainda.</td></tr>'}</tbody></table></div><div class="panel"><div class="eyebrow">Funil observado</div><div class="funnel"><div class="step"><span>Site → Demo</span><br><b>${esc(d.funnel.site_to_demo_events)}</b> <span class="muted">eventos · ${esc(d.funnel.site_to_demo_rate_pct)}%</span></div><div class="step"><span>Demo → App</span><br><b>${esc(d.funnel.demo_to_app_events)}</b> <span class="muted">eventos · ${esc(d.funnel.demo_to_app_rate_pct)}%</span></div></div><div class="eyebrow" style="margin-top:24px">Origem</div><table><tbody>${src||'<tr><td>Sem dados</td></tr>'}</tbody></table></div></section><div class="privacy">Período: ${esc(d.period_days)} dias · eventos agregados: ${esc(d.total_events)} · telemetria própria do SRIS.</div>`;
  }
  async function load(days=period){
    period=days;clear();lastToken=token();const credentials=lastToken,sequence=generation;
    if(!credentials||document.hidden)return;
    const active=new AbortController();controller=active;const timer=setTimeout(()=>active.abort(),15000);
    const current=()=>sequence===generation&&credentials===token()&&!document.hidden;
    try{
      const response=await fetch(`/api/internal-analytics/summary?days=${days}`,{headers:{Authorization:`Bearer ${credentials}`},cache:'no-store',signal:active.signal});
      if(!response.ok||!current())return;
      const data=await response.json();if(current())render(data);
    }catch{if(current())clear('Analytics indisponível. A autorização será novamente verificada ao atualizar.');}
    finally{clearTimeout(timer);if(controller===active)controller=null;}
  }
  document.querySelectorAll('[data-days]').forEach(button=>button.addEventListener('click',()=>void load(Number(button.dataset.days))));
  window.addEventListener('pagehide',()=>clear());
  window.addEventListener('pageshow',()=>void load());
  window.addEventListener('storage',event=>{if(event.key===null||event.key==='sris_access_token')void load();});
  document.addEventListener('visibilitychange',()=>document.hidden?clear():void load());
  setInterval(()=>{if(token()!==lastToken){clear();lastToken=token();if(!document.hidden)void load();}},500);
  clear();void load();
})();
