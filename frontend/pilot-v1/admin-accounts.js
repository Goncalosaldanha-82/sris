(()=>{
  'use strict';

  const API='/api/pilot';
  const roleLabels={
    owner:'Proprietário',
    admin:'Administrador',
    reviewer:'Revisor',
    contributor:'Colaborador',
    observer:'Observador',
  };

  function token(){
    return localStorage.getItem('sris_access_token')||sessionStorage.getItem('sris_access_token');
  }

  function escapeHtml(value){
    return String(value||'').replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  }

  function errorText(data,status){
    const detail=data?.detail;
    if(typeof detail==='string')return detail;
    return detail?.message||detail?.code||data?.message||`HTTP ${status}`;
  }

  async function api(path,options={}){
    const url=path.startsWith('/api/')?path:API+path;
    if(window.SRISApi?.request)return window.SRISApi.request(url,options);
    const headers={'Content-Type':'application/json',...(options.headers||{})};
    if(token())headers.Authorization=`Bearer ${token()}`;
    const response=await fetch(url,{...options,headers,cache:'no-store'});
    let data={};
    try{data=await response.json()}catch{}
    if(!response.ok){
      const error=new Error(errorText(data,response.status));
      error.status=response.status;
      throw error;
    }
    return data;
  }

  const client={
    status:()=>api('/ops/status'),
    list:()=>api('/admin/accounts'),
    setState:(accountId,isActive)=>api(`/admin/accounts/${accountId}/state`,{
      method:'PATCH',
      body:JSON.stringify({is_active:Boolean(isActive)}),
    }),
    setRole:(accountId,role)=>api(`/admin/accounts/${accountId}/role`,{
      method:'PATCH',
      body:JSON.stringify({role}),
    }),
    capabilities:()=>api('/api/auth/capabilities'),
    invitations:organizationId=>api(`/api/organizations/${encodeURIComponent(organizationId)}/invitations`),
    invite:(organizationId,payload)=>api(`/api/organizations/${encodeURIComponent(organizationId)}/invitations`,{method:'POST',body:JSON.stringify(payload)}),
    resend:(organizationId,invitationId)=>api(`/api/organizations/${encodeURIComponent(organizationId)}/invitations/${encodeURIComponent(invitationId)}/resend`,{method:'POST'}),
    revoke:(organizationId,invitationId)=>api(`/api/organizations/${encodeURIComponent(organizationId)}/invitations/${encodeURIComponent(invitationId)}`,{method:'DELETE'}),
  };
  window.SRISAdminAccounts=client;

  function roleOptions(current){
    return ['admin','reviewer','contributor','observer']
      .map(role=>`<option value="${role}" ${current===role?'selected':''}>${roleLabels[role]}</option>`)
      .join('');
  }

  function accountRows(accounts){
    return accounts.map(account=>{
      const owner=account.role==='owner';
      return `<div class="ledger-row" data-admin-account="${escapeHtml(account.id)}" style="align-items:center;gap:14px">
        <div style="min-width:0;flex:1">
          <strong style="display:block;overflow:hidden;text-overflow:ellipsis">${escapeHtml(account.full_name||account.email)}</strong>
          <span class="note">${escapeHtml(account.email)} · ${escapeHtml(roleLabels[account.role]||account.role)}${account.last_login_at?` · último acesso ${new Date(account.last_login_at).toLocaleString('pt-PT')}`:' · sem acesso registado'}</span>
        </div>
        <span class="pill">${account.is_active?'Ativa':'Inativa'}</span>
        ${owner?'':`<select class="admin-role" aria-label="Função no workspace">${roleOptions(account.role)}</select>`}
        ${owner?'<span class="note">Conta proprietária protegida</span>':`<button class="btn btn-secondary admin-state" data-active="${account.is_active?'1':'0'}">${account.is_active?'Desativar':'Ativar'}</button>`}
      </div>`;
    }).join('');
  }

  function invitationRows(invitations){
    const visible=(invitations||[]).filter(item=>item.status!=='accepted');
    return visible.length?visible.map(item=>`<div class="ledger-row" data-invitation="${escapeHtml(item.id)}" style="align-items:center;gap:12px">
      <div style="min-width:0;flex:1"><strong style="display:block">${escapeHtml(item.full_name)}</strong><span class="note">${escapeHtml(item.email)} · ${escapeHtml(roleLabels[item.role]||item.role)} · expira ${new Date(item.expires_at).toLocaleString('pt-PT')}</span></div>
      <span class="pill">${escapeHtml(item.status)} · ${escapeHtml(item.delivery_status)}</span>
      ${item.status==='pending'?'<button class="btn btn-secondary compact" type="button" data-invite-resend>Reenviar</button><button class="btn btn-danger compact" type="button" data-invite-revoke>Revogar</button>':''}
    </div>`).join(''):'<div class="note">Sem convites pendentes.</div>';
  }

  async function renderAdmin(){
    const accountSection=document.getElementById('account');
    if(!accountSection||document.getElementById('pilot-admin-card'))return;

    let data;
    try{
      data=await client.list();
    }catch(error){
      if(error.status===401||error.status===403)return;
      return;
    }
    const profileEmail=document.getElementById('account-email');
    if(profileEmail&&!profileEmail.value){
      const currentUserId=localStorage.getItem('sris_user_id');
      const displayedName=(document.getElementById('account-name')?.value||'').trim();
      const current=(data.accounts||[]).find(account=>account.id===currentUserId)
        ||(data.accounts||[]).find(account=>account.full_name===displayedName)
        ||(data.accounts||[]).find(account=>account.role==='owner')
        ||(data.accounts||[])[0];
      if(current?.email){profileEmail.value=current.email;localStorage.setItem('sris_user_email',current.email);}
    }

    const [capabilityResult,invitationResult]=await Promise.allSettled([
      api('/api/pilot/capabilities'),
      client.invitations(data.organization_id),
    ]);
    const capabilities=capabilityResult.status==='fulfilled'?capabilityResult.value:{invitations_enabled:false};
    const invitations=invitationResult.status==='fulfilled'?invitationResult.value:[];
    const activeAccounts=(data.accounts||[]).filter(account=>account.is_active).length;
    const totalAccounts=(data.accounts||[]).length;

    const wrapper=document.createElement('article');
    wrapper.className='card';
    wrapper.id='pilot-admin-card';
    wrapper.innerHTML=`
      <div class="card-title">
        <div><h3>Administração do workspace</h3><div class="note">Contas, funções e estado de acesso.</div></div>
        <span class="pill" id="pilot-ops-state">${activeAccounts}/${totalAccounts} contas ativas</span>
      </div>
      <div id="pilot-admin-message" class="alert hidden" role="status" aria-live="polite"></div>
      <section class="admin-section"><h4>Contas ativas no workspace</h4><div id="pilot-admin-list" class="ledger">${accountRows(data.accounts||[])||'<div class="note">Sem contas.</div>'}</div></section>
      <section class="admin-section">
        <div class="card-title"><div><h4>Convidar uma pessoa</h4><div class="note">O convite é pessoal, temporário e atribui apenas a função indicada.</div></div><span class="pill">${capabilities.invitations_enabled?'entrega validada':capabilities.transactional_email_status==='delivery-failed'?'falha de entrega':'validação necessária'}</span></div>
        ${capabilities.invitations_enabled?`<form id="pilot-invite-form" class="admin-invite-grid">
          <div class="field"><label for="pilot-invite-name">Nome completo</label><input id="pilot-invite-name" required minlength="2" maxlength="200"></div>
          <div class="field"><label for="pilot-invite-email">Email</label><input id="pilot-invite-email" type="email" required></div>
          <div class="field"><label for="pilot-invite-role">Função</label><select id="pilot-invite-role"><option value="contributor">Colaborador</option><option value="reviewer">Revisor</option><option value="observer">Observador</option></select></div>
          <button class="btn btn-primary" type="submit">Enviar convite</button>
        </form>`:`<div class="alert error">${capabilities.transactional_email_status==='delivery-failed'?'O último ensaio de email falhou.':'A entrega de email ainda não foi validada.'} As contas existentes continuam operacionais, mas os convites permanecem bloqueados até existir uma entrega confirmada.</div>`}
        <div id="pilot-invitation-list" class="ledger">${invitationRows(invitations)}</div>
      </section>`;
    accountSection.appendChild(wrapper);

    wrapper.querySelector('#pilot-invite-form')?.addEventListener('submit',async event=>{
      event.preventDefault();
      const button=event.submitter;
      button?.classList.add('loading');
      try{
        await client.invite(data.organization_id,{
          full_name:wrapper.querySelector('#pilot-invite-name').value.trim(),
          email:wrapper.querySelector('#pilot-invite-email').value.trim(),
          role:wrapper.querySelector('#pilot-invite-role').value,
        });
        event.target.reset();
        showMessage('Convite criado. O estado de entrega ficará visível nesta lista.');
        await refreshInvitations(wrapper,data.organization_id);
      }catch(error){showMessage(error.message,true)}
      finally{button?.classList.remove('loading')}
    });

    wrapper.addEventListener('change',async event=>{
      const select=event.target.closest('.admin-role');
      if(!select)return;
      const row=select.closest('[data-admin-account]');
      try{
        await client.setRole(row.dataset.adminAccount,select.value);
        showMessage('Função atualizada e registada em auditoria.');
      }catch(error){
        showMessage(error.message,true);
        await renderAdminRefresh(wrapper).catch(()=>{});
      }
    });

    wrapper.addEventListener('click',async event=>{
      const button=event.target.closest('.admin-state,[data-invite-resend],[data-invite-revoke]');
      if(!button)return;
      button.classList.add('loading');
      try{
        const invitationRow=button.closest('[data-invitation]');
        if(invitationRow){
          if(button.hasAttribute('data-invite-resend')){
            await client.resend(data.organization_id,invitationRow.dataset.invitation);
            showMessage('Convite renovado e reenviado.');
          }else{
            await client.revoke(data.organization_id,invitationRow.dataset.invitation);
            showMessage('Convite revogado. O link anterior deixou de ser válido.');
          }
          await refreshInvitations(wrapper,data.organization_id);
        }else{
          const row=button.closest('[data-admin-account]');
          const next=button.dataset.active!=='1';
          await client.setState(row.dataset.adminAccount,next);
          showMessage(next?'Conta ativada.':'Conta desativada e sessões anteriores invalidadas.');
          await renderAdminRefresh(wrapper);
        }
      }catch(error){
        showMessage(error.message,true);
      }finally{
        button.classList.remove('loading');
      }
    });
  }

  async function renderAdminRefresh(wrapper){
    const data=await client.list();
    const list=wrapper.querySelector('#pilot-admin-list');
    if(list)list.innerHTML=accountRows(data.accounts||[]);
  }

  async function refreshInvitations(wrapper,organizationId){
    const data=await client.invitations(organizationId);
    const list=wrapper.querySelector('#pilot-invitation-list');
    if(list)list.innerHTML=invitationRows(data);
  }

  function showMessage(message,isError=false){
    const node=document.getElementById('pilot-admin-message');
    if(!node)return;
    node.textContent=message;
    node.className=`alert ${isError?'error':'success'}`;
    setTimeout(()=>node.classList.add('hidden'),5000);
  }

  function boot(){
    setTimeout(renderAdmin,600);
    document.addEventListener('click',event=>{
      if(event.target.closest('[data-section="account"]'))setTimeout(renderAdmin,100);
    });
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});
  else boot();
})();
