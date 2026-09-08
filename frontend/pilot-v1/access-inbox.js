(()=>{
  'use strict';
  const $=s=>document.querySelector(s);
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const labels={pending:'Pendente',approved:'Aprovado',rejected:'Recusado',cancelled:'Cancelado',accepted:'Aceite',expired:'Expirado',revoked:'Revogado'};
  let refreshing=null, loading=false, deciding=false, items=[], refusalId=null;
  function message(text,error=false){$('#message').textContent=text;$('#message').className='message'+(error?' error':'');}
  function needLogin(text){$('#inbox').classList.add('hidden');$('#access-login').classList.remove('hidden');$('#actor').textContent='Área reservada à aprovação SRIS.';message(text,true);}
  function detail(data,status){if(status===401)return'Email ou palavra-passe incorretos, ou sessão expirada.';if(status===403)return'Esta conta não está autorizada a aprovar pedidos SRIS. Entre com a conta de administração da plataforma.';if(status>=500)return'O serviço não conseguiu concluir a operação. O estado deve ser confirmado antes de repetir.';return typeof data?.detail==='string'?data.detail:data?.detail?.message||'Não foi possível concluir a operação.';}
  async function request(path,options={},retry=true){
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),25000);
    try{
      const access=localStorage.getItem('sris_access_token');
      const response=await fetch(path,{...options,headers:{'Content-Type':'application/json',...(access?{Authorization:`Bearer ${access}`}:{})},cache:'no-store',signal:controller.signal});
      if(response.status===401&&retry&&localStorage.getItem('sris_refresh_token')&&!path.startsWith('/api/auth/')){
        if(!refreshing)refreshing=request('/api/auth/refresh',{method:'POST',body:JSON.stringify({refresh_token:localStorage.getItem('sris_refresh_token')})},false).then(saveTokens).finally(()=>refreshing=null);
        await refreshing;return request(path,options,false);
      }
      const data=await response.json().catch(()=>({}));
      if(!response.ok){const error=new Error(detail(data,response.status));error.status=response.status;throw error;}
      return data;
    }catch(error){if(error.name==='AbortError')throw new Error('O pedido demorou demasiado. Atualize a lista para confirmar o estado.');if(error instanceof TypeError)throw new Error('Não foi possível contactar o serviço. Verifique a ligação.');throw error;}
    finally{clearTimeout(timer);}
  }
  function saveTokens(data){if(data.access_token)localStorage.setItem('sris_access_token',data.access_token);if(data.refresh_token)localStorage.setItem('sris_refresh_token',data.refresh_token);return data;}
  const date=value=>value?new Date(value).toLocaleString('pt-PT'):'—';
  function invitationDelivery(invite){
    if(invite.status==='accepted')return'<p class="message">Convite aceite. A conta já está associada ao workspace.</p>';
    if(invite.status==='revoked')return'<p class="message error">Convite revogado. Este link já não permite ativar o acesso.</p>';
    if(invite.status==='expired')return'<p class="message error">O convite expirou. Reenvie-o para a pessoa poder ativar o acesso.</p>';
    if(invite.delivery_status==='failed')return'<p class="message error">Aprovação registada, mas o email do convite falhou. A pessoa ainda não recebeu deste envio o link para criar a palavra-passe. Use «Reenviar convite».</p>';
    if(invite.delivery_status==='sent')return'<p class="message">Convite aceite pelo serviço de email'+(invite.last_sent_at?' em '+date(invite.last_sent_at):'')+'. A pessoa deve abrir «Ativar conta no SRIS» para definir a palavra-passe e entrar. A entrega na caixa de correio ainda não foi confirmada pela aplicação.</p>';
    return'<p class="message">Aprovação registada. Convite em processamento; o envio ainda não está confirmado.</p>';
  }
  function notices(row){
    return(row.notifications||[]).map(n=>{const channel=n.kind==='admin_new'?'Aviso à gestão':'Resposta ao requerente';const status={provider_accepted:'aceite pelo serviço de email',queued:'em fila de envio',failed:'envio falhou',cancelled:'cancelado'}[n.status]||n.status;return`<div>${esc(channel)}: ${esc(status)}${n.status==='failed'?' — nova tentativa automática ou manual':''}.</div>`;}).join('')||'Aviso à gestão a aguardar processamento.';
  }
  function rowView(row){
    const pending=row.status==='pending';
    const invite=row.invitation;
    const failed=(row.notifications||[]).some(n=>n.status==='failed');
    return`<article class="request" data-id="${esc(row.id)}"><div class="request-head"><div><h2>${esc(row.organization_name)}</h2><strong>${esc(row.full_name)}</strong><div><a href="mailto:${esc(row.email)}">${esc(row.email)}</a></div><div class="muted">Recebido ${date(row.requested_at)}</div></div><span class="pill">${esc(labels[row.status]||row.status)}</span></div>${pending?`<details><summary>Analisar e decidir</summary><p class="muted">Ao aprovar será criado um novo workspace e preparado o envio de um convite pessoal. A conta só fica associada quando o convite for aceite.</p><div class="grid"><div class="field"><label>Nome do novo workspace</label><input data-workspace value="${esc(row.organization_name)}" minlength="2" maxlength="200" required></div><div class="field"><label>Plano</label><select data-plan><option value="pilot">Pilot</option><option value="professional">Professional</option><option value="organization">Organization</option></select></div><div class="field"><label>Validade (dias)</label><input data-days type="number" value="90" min="1" max="3650" required></div></div><div class="field"><label>Nota interna da decisão (não enviada por email)</label><textarea data-note maxlength="2000"></textarea></div><div class="actions" style="margin-top:16px"><button data-approve class="primary">Aprovar e enviar convite</button><button data-reject class="danger">Recusar pedido</button></div></details>`:`<div class="muted">Decidido ${date(row.reviewed_at)}</div>${row.workspace?`<p>Workspace: <strong>${esc(row.workspace.name)}</strong> · Plano: ${esc(row.entitlement?.plan_code||row.plan_code)}</p>`:''}${invite?`${invitationDelivery(invite)}${!['accepted','revoked'].includes(invite.status)?'<button data-resend>Reenviar convite</button>':''}`:''}` }<div class="notice muted">${notices(row)}${failed?'<p><button data-retry>Repetir notificação falhada</button></p>':''}</div></article>`;
  }
  async function load(){
    if(loading)return;loading=true;$('#refresh').disabled=true;
    try{
      const data=await request('/api/admin/access-requests/inbox?status='+encodeURIComponent($('#filter').value));
      items=data.requests||[];$('#access-login').classList.add('hidden');$('#inbox').classList.remove('hidden');
      $('#actor').textContent='Sessão de aprovação: '+data.actor_email;
      ['pending','approved','rejected'].forEach(k=>$('#'+k+'-count').textContent=data.counts[k]);
      $('#notification-info').textContent=data.notifications_enabled?'Destino dos avisos de novos pedidos: '+data.notification_recipients.join(', ')+'. Consulte o estado de envio em cada pedido.':'O envio automático de avisos está desativado. Os pedidos continuam disponíveis para decisão.';
      $('#requests').innerHTML=items.length?items.map(rowView).join(''):'<div class="card empty">Não há pedidos neste estado.</div>';
      $('#updated-at').textContent='Atualizado '+new Date().toLocaleTimeString('pt-PT')+'. São apresentados até 200 pedidos por estado.';
    }catch(error){if([401,403].includes(error.status))needLogin(error.message);else message(error.message,true);}
    finally{loading=false;$('#refresh').disabled=false;}
  }
  async function followInvitation(id){
    // Do not leave the just-approved person hidden in the pending filter.
    $('#filter').value='approved';
    for(let attempt=0;attempt<5;attempt++){
      await load();
      const row=items.find(item=>item.id===id),invite=row?.invitation;
      if(invite?.delivery_status==='failed'){message('Aprovação registada, mas o envio do convite falhou. O pedido está visível abaixo; use «Reenviar convite».',true);return;}
      if(invite?.status==='accepted'){message('O convite já foi aceite e a conta está associada ao workspace.');return;}
      if(invite?.delivery_status==='sent'){message('Aprovação registada. O serviço de email aceitou o convite para '+row.email+'. A pessoa deverá abrir o link e definir a palavra-passe.');return;}
      if(attempt<4)await new Promise(resolve=>setTimeout(resolve,750));
    }
    message('Aprovação registada. O convite continua em processamento; o envio ainda não está confirmado.');
  }
  async function action(button,task){if(deciding)return;deciding=true;button.disabled=true;try{await task();await load();}catch(error){message(error.message,true);}finally{deciding=false;button.disabled=false;}}
  $('#login-form').addEventListener('submit',event=>{
    event.preventDefault();const form=event.currentTarget,button=form.querySelector('button');
    action(button,async()=>{const data=await request('/api/auth/login',{method:'POST',body:JSON.stringify({email:$('#login-email').value.trim(),password:$('#login-password').value})},false);saveTokens(data);['sris_org_id','sris_workspace_selection','sris_user_id'].forEach(k=>localStorage.removeItem(k));localStorage.setItem('sris_user_email',$('#login-email').value.trim().toLowerCase());$('#login-password').value='';$('#message').classList.add('hidden');});
  });
  $('#refresh').addEventListener('click',()=>load());$('#filter').addEventListener('change',()=>load());
  $('#switch-account').addEventListener('click',()=>{$('#inbox').classList.add('hidden');$('#access-login').classList.remove('hidden');$('#login-email').focus();});
  $('#requests').addEventListener('click',event=>{
    const button=event.target.closest('button'),element=button?.closest('[data-id]');if(!button||!element)return;
    const row=items.find(x=>x.id===element.dataset.id);if(!row)return;
    const base='/api/admin/access-requests/'+encodeURIComponent(row.id);
    if(button.hasAttribute('data-approve')){
      const name=element.querySelector('[data-workspace]'),days=element.querySelector('[data-days]');
      if(!name.reportValidity()||!days.reportValidity())return;
      const payload={workspace_name:name.value.trim(),plan_code:element.querySelector('[data-plan]').value,entitlement_days:Number(days.value),decision_note:element.querySelector('[data-note]').value.trim()||null};
      if(payload.workspace_name.length<2){message('Indique um nome de workspace com pelo menos dois caracteres.',true);return;}
      if(!confirm(`Aprovar ${row.full_name} (${row.email})?\nNovo workspace: ${payload.workspace_name}\nPlano: ${payload.plan_code} · ${payload.entitlement_days} dias\nSerá preparado o envio de um convite pessoal.`))return;
      action(button,async()=>{await request(base+'/approve',{method:'POST',body:JSON.stringify(payload)});await followInvitation(row.id);});
    }else if(button.hasAttribute('data-reject')){refusalId=row.id;$('#refusal-person').textContent=row.full_name+' · '+row.email;$('#refusal-dialog').showModal();}
    else if(button.hasAttribute('data-resend')){if(!confirm('Reenviar o convite para '+row.email+'? O endereço anterior deixará de ser válido.'))return;action(button,async()=>{await request(base+'/resend-invitation',{method:'POST'});await followInvitation(row.id);});}
    else if(button.hasAttribute('data-retry'))action(button,async()=>{await request(base+'/retry-notification',{method:'POST'});message('Notificação colocada novamente em fila.');});
  });
  $('#cancel-refusal').addEventListener('click',()=>$('#refusal-dialog').close());
  $('#refusal-form').addEventListener('submit',event=>{event.preventDefault();if(!refusalId)return;const id=refusalId,button=event.currentTarget.querySelector('[type="submit"]');const element=[...document.querySelectorAll('[data-id]')].find(x=>x.dataset.id===id);action(button,async()=>{await request('/api/admin/access-requests/'+encodeURIComponent(id)+'/reject',{method:'POST',body:JSON.stringify({response_message:$('#response-message').value,decision_note:element?.querySelector('[data-note]')?.value||null})});$('#refusal-dialog').close();message('Pedido recusado. A resposta por email ficou em fila de envio.');});});
  setInterval(()=>{if(!deciding&&!document.hidden&&!$('#inbox').classList.contains('hidden')&&!$('#refusal-dialog').open&&!document.querySelector('details[open]'))load();},30000);
  if(localStorage.getItem('sris_access_token')||localStorage.getItem('sris_refresh_token'))load();else needLogin('Entre com a conta de aprovação SRIS para consultar e decidir os pedidos.');
})();
