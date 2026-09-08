(()=>{
  'use strict';
  const $=(s,r=document)=>r.querySelector(s);
  const esc=v=>String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const api=(p,o={})=>window.SRISApi.request(p,o);
  let loading=false;
  function view(e,org){
    const status={active:'Ativo',expired:'Expirado',missing:'Sem licença',suspended:'Suspenso',cancelled:'Cancelado'}[e?.status]||e?.status||'Indisponível';
    return`<h4>${esc(org.name)} · ${esc(status)}</h4><p>Plano: <strong>${esc(e?.plan_code||'não atribuído')}</strong></p><p>${!e?.present?'Sem licença comercial atribuída.':e?.expires_at?`Válido até <strong>${new Date(e.expires_at).toLocaleString('pt-PT')}</strong>.`:'<strong>Autorização sem prazo definido.</strong> Exceção de acesso existente; não é prova de pagamento nem uma subscrição comercial.'}</p><p class="note">Sem renovação automática e sem cobrança automática. A palavra-passe identifica a pessoa, mas não prolonga o acesso. Na expiração, as operações deste workspace ficam bloqueadas até renovação autorizada pelo SRIS; os dados são preservados.</p>${e?.enforced===false?'<p class="alert error">Bloqueio comercial desativado neste ambiente de teste.</p>':''}`;
  }
  async function render(force=false){
    const section=document.getElementById('account');
    if(loading||!section||!window.SRISApi?.raw)return;
    if(!force&&!section.classList.contains('active'))return;
    loading=true;
    try{
      const selected=localStorage.getItem('sris_org_id');
      const p=await api('/api/pilot/profile'+(selected?'?organization_id='+encodeURIComponent(selected):''));
      const org=p.organization||{};if(!org.id)return;
      const response=await window.SRISApi.raw('/api/admin/access-requests/summary',{skipWorkspace:true});
      const platform=response.ok;
      if(selected!==localStorage.getItem('sris_org_id'))return;
      let card=document.getElementById('commercial-entitlement-card');
      if(card?.dataset.org===org.id&&card.contains(document.activeElement))return;
      if(!card){card=document.createElement('article');card.className='card';card.id='commercial-entitlement-card';section.prepend(card);}
      card.dataset.org=org.id;
      card.innerHTML=`<div class="card-title"><div><h3>Entitlement comercial · prazo do acesso</h3><div class="note">Cada workspace tem a sua própria autorização.</div></div></div><div data-entitlement>${view(p.commercial_access,org)}</div><div data-msg class="alert hidden" role="status"></div>${platform?'<form data-renew-form><div class="field"><label>Plano a renovar</label><select data-plan><option value="pilot">Pilot</option><option value="professional">Professional</option><option value="organization">Organization</option></select></div><div class="field"><label>Período de renovação (dias)</label><input data-days type="number" min="1" max="3650" value="365" required></div><div class="field"><label>Referência comercial (opcional)</label><input data-reference maxlength="200" placeholder="Contrato ou acordo autorizado"></div><button class="btn btn-secondary" type="submit">Autorizar renovação</button><p class="note">Esta operação concede mais tempo de utilização. Não cobra dinheiro nem confirma pagamentos.</p></form>':''}`;
      if(!platform)return;
      $('[data-plan]',card).value=p.commercial_access?.plan_code||'pilot';
      $('[data-renew-form]',card).addEventListener('submit',async event=>{
        event.preventDefault();const form=event.currentTarget,button=form.querySelector('button'),m=$('[data-msg]',card);
        if(!form.reportValidity())return;
        const days=Number($('[data-days]',card).value);
        if(!Number.isInteger(days)||days<1||days>3650)return;
        if(!confirm('Autorizar mais '+days+' dias para '+org.name+'? Esta ação não efetua qualquer cobrança.'))return;
        button.disabled=true;
        try{
          const d=await api(`/api/admin/organizations/${encodeURIComponent(org.id)}/commercial-entitlement/renew`,{method:'POST',body:JSON.stringify({term_days:days,plan_code:$('[data-plan]',card).value,commercial_reference:$('[data-reference]',card).value.trim()||null})});
          $('[data-entitlement]',card).innerHTML=view(d.entitlement,org);m.textContent='Prazo renovado por decisão SRIS. Nenhuma cobrança foi efetuada.';m.className='alert success';
        }catch(error){m.textContent=error.message;m.className='alert error';}finally{button.disabled=false;}
      });
    }catch(error){console.warn('SRIS commercial terms could not be loaded.');}
    finally{loading=false;}
  }
  const boot=()=>setTimeout(()=>render(true),900);
  document.readyState==='loading'?document.addEventListener('DOMContentLoaded',boot,{once:true}):boot();
  document.addEventListener('click',event=>{if(event.target.closest('[data-section="account"]'))setTimeout(()=>render(true),100);});
  setInterval(()=>{if(!document.hidden)render();},15000);
})();
