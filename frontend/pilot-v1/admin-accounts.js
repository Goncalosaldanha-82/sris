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
    const headers={'Content-Type':'application/json',...(options.headers||{})};
    if(token())headers.Authorization=`Bearer ${token()}`;
    const response=await fetch(API+path,{...options,headers,cache:'no-store'});
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
          <span class="note">${escapeHtml(account.email)} · ${escapeHtml(roleLabels[account.role]||account.role)}</span>
        </div>
        <span class="pill">${account.is_active?'Ativa':'Inativa'}</span>
        ${owner?'':`<select class="admin-role" aria-label="Função no workspace">${roleOptions(account.role)}</select>`}
        ${owner?'<span class="note">Conta proprietária protegida</span>':`<button class="btn btn-secondary admin-state" data-active="${account.is_active?'1':'0'}">${account.is_active?'Desativar':'Ativar'}</button>`}
      </div>`;
    }).join('');
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

    const wrapper=document.createElement('article');
    wrapper.className='card';
    wrapper.id='pilot-admin-card';
    wrapper.innerHTML=`
      <div class="card-title">
        <div><h3>Administração do workspace</h3><div class="note">Contas, funções e estado de acesso com registo de auditoria.</div></div>
        <span class="pill" id="pilot-ops-state">A sincronizar</span>
      </div>
      <div id="pilot-admin-message" class="alert hidden" role="status" aria-live="polite"></div>
      <div id="pilot-admin-list" class="ledger">${accountRows(data.accounts||[])||'<div class="note">Sem contas.</div>'}</div>`;
    accountSection.appendChild(wrapper);

    try{
      const status=await client.status();
      const pill=document.getElementById('pilot-ops-state');
      if(pill)pill.textContent=`${status.active_members}/${status.members} ativas · ${status.audit_events} eventos`;
    }catch{}

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
      const button=event.target.closest('.admin-state');
      if(!button)return;
      const row=button.closest('[data-admin-account]');
      const next=button.dataset.active!=='1';
      button.classList.add('loading');
      try{
        await client.setState(row.dataset.adminAccount,next);
        showMessage(next?'Conta ativada.':'Conta desativada e sessões anteriores invalidadas.');
        await renderAdminRefresh(wrapper);
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
