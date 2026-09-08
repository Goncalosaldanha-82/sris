(()=>{
  'use strict';
  const $=selector=>document.querySelector(selector);
  const roles={owner:'Proprietário',admin:'Administrador',reviewer:'Revisor',contributor:'Colaborador',observer:'Observador'};
  let inviteToken='',resetToken='',invitation=null,proofId='',useCurrent=false,busy=false;
  function message(selector,text,error=false){const node=$(selector);node.textContent=text;node.className='activation-message '+(error?'error':'success');}
  function show(id){['invite-view','request-view','reset-view'].forEach(key=>$('#'+key).classList.toggle('hidden',key!==id));}
  async function api(path,payload){
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),30000);
    try{
      const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),cache:'no-store',signal:controller.signal});
      const data=await response.json().catch(()=>({}));
      if(!response.ok){const detail=data.detail;const text=typeof detail==='string'?detail:detail?.message||'Não foi possível concluir a operação.';throw new Error(text);}
      return data;
    }catch(error){if(error.name==='AbortError')throw new Error('O serviço demorou demasiado. Não volte a submeter sem confirmar o estado.');if(error instanceof TypeError)throw new Error('Não foi possível contactar o SRIS. Verifique a ligação.');throw error;}
    finally{clearTimeout(timer);}
  }
  function date(value){return value?new Date(value).toLocaleString('pt-PT',{dateStyle:'long',timeStyle:'short'}):'não definida';}
  function termsView(terms){
    const node=$('#invite-terms');node.replaceChildren();
    const title=document.createElement('strong');title.textContent='Condições do acesso';node.appendChild(title);
    if(!terms.present){const p=document.createElement('p');p.textContent='Não existe licença comercial atribuída a este workspace. Contacte o SRIS.';node.appendChild(p);node.classList.remove('hidden');return;}
    const lines=[`Plano: ${terms.plan_code||'não definido'}.`,terms.expires_at?`Acesso válido até ${date(terms.expires_at)}.`:'Este workspace tem uma autorização sem prazo definido. Não representa uma subscrição paga.',
      'Sem renovação automática e sem cobrança automática. A palavra-passe não prolonga o prazo.',
      terms.expires_at?'Após a expiração, a utilização deste workspace fica bloqueada até o SRIS autorizar a renovação. Os dados são preservados.':'A autorização sem prazo deve ser regularizada pelo SRIS antes de utilização comercial.'];
    if(terms.enforced===false)lines.push('Ambiente de teste: o bloqueio comercial não está ativo.');
    if(terms.status!=='active')lines.unshift('Acesso comercial não ativo. Contacte o SRIS antes de continuar.');
    lines.forEach(text=>{const p=document.createElement('p');p.textContent=text;node.appendChild(p);});node.classList.remove('hidden');
  }
  function configureForm(){
    const existing=Boolean(invitation?.existing_account),recover=existing&&!useCurrent;
    $('#mailbox-proof').classList.toggle('hidden',!recover);
    $('#code-field').classList.toggle('hidden',!recover);
    $('#activation-code').required=recover;
    $('#invite-name-field').classList.toggle('hidden',existing);$('#invite-name').required=!existing;
    $('#invite-confirm-field').classList.toggle('hidden',useCurrent);$('#invite-confirm').required=!useCurrent;
    $('#replace-confirm').classList.toggle('hidden',!recover);$('#replace-password').required=recover;
    $('#invite-password-label').textContent=useCurrent?'Palavra-passe atual':'Criar palavra-passe';
    $('#invite-password').autocomplete=useCurrent?'current-password':'new-password';
    $('#invite-title').textContent=useCurrent?'Aceitar convite e entrar':'Definir palavra-passe e entrar';
    $('#activate-submit').textContent=useCurrent?'Aceitar convite e entrar':'Criar palavra-passe e entrar';
    $('#activate-submit').disabled=(recover&&!proofId)||(invitation?.commercial_access?.enforced&&invitation.commercial_access.status!=='active');
    $('#use-existing').classList.toggle('hidden',!existing);
    $('#use-existing').textContent=useCurrent?'Não sei a palavra-passe — criar uma nova':'Já sei a palavra-passe — usar a atual';
  }
  async function inspect(){
    show('invite-view');
    try{
      invitation=await api('/api/auth/invitations/activation/inspect',{token:inviteToken});
      $('#invite-intro').textContent='Defina a sua credencial do SRIS e consulte abaixo o prazo de utilização do workspace.';
      const node=$('#invite-summary');node.replaceChildren();const org=document.createElement('strong'),meta=document.createElement('span');
      org.textContent=invitation.organization_name;meta.textContent=invitation.email+' · '+(roles[invitation.role]||invitation.role);node.append(org,meta);node.classList.remove('hidden');
      $('#invite-name').value=invitation.full_name||'';
      termsView(invitation.commercial_access);configureForm();$('#invite-form').classList.remove('hidden');
    }catch(error){$('#invite-intro').textContent='Não foi possível validar este convite.';message('#invite-message',error.message,true);}
  }
  $('#send-code').addEventListener('click',async()=>{
    if(busy)return;busy=true;$('#send-code').disabled=true;
    message('#code-message','A enviar código de confirmação…');
    try{
      const data=await api('/api/auth/invitations/activation/send-code',{token:inviteToken});
      proofId=data.proof_id||'';message('#code-message',data.message);configureForm();$('#activation-code').focus();
    }catch(error){message('#code-message',error.message,true);}
    finally{busy=false;$('#send-code').disabled=false;}
  });
  $('#use-existing').addEventListener('click',()=>{if(busy)return;useCurrent=!useCurrent;$('#invite-password').value='';$('#invite-confirm').value='';configureForm();});
  $('#invite-form').addEventListener('submit',async event=>{
    event.preventDefault();const form=event.currentTarget;
    if(busy||!form.reportValidity())return;
    if(!useCurrent&&$('#invite-password').value!==$('#invite-confirm').value){message('#invite-message','As duas palavras-passe não coincidem.',true);return;}
    if(invitation.existing_account&&!useCurrent&&!proofId){message('#invite-message','Peça primeiro o código de confirmação por email.',true);return;}
    busy=true;$('#activate-submit').disabled=true;message('#invite-message','A criar a credencial e aceitar o workspace…');
    try{
      const data=await api('/api/auth/invitations/activation/complete',{token:inviteToken,password:$('#invite-password').value,
        full_name:invitation.existing_account?null:$('#invite-name').value.trim(),proof_id:proofId||null,
        code:invitation.existing_account&&!useCurrent?$('#activation-code').value.trim():null,use_current_password:useCurrent});
      localStorage.setItem('sris_access_token',data.access_token);localStorage.setItem('sris_refresh_token',data.refresh_token);
      localStorage.setItem('sris_org_id',data.organization_id);localStorage.setItem('sris_workspace_selection','manual');
      localStorage.setItem('sris_user_email',invitation.email.toLowerCase());localStorage.removeItem('sris_user_id');
      $('#invite-password').value='';$('#invite-confirm').value='';$('#activation-code').value='';
      message('#invite-message','Acesso ativado. A abrir o workspace atribuído…');location.replace('/app');
    }catch(error){message('#invite-message',error.message,true);busy=false;configureForm();}
  });
  $('#request-form').addEventListener('submit',async event=>{
    event.preventDefault();const form=event.currentTarget,button=form.querySelector('button');if(busy)return;busy=true;button.disabled=true;
    try{const data=await api('/api/auth/password-reset/request',{email:$('#request-email').value.trim()});form.reset();message('#request-message',data.message);}
    catch(error){message('#request-message',error.message,true);}finally{busy=false;button.disabled=false;}
  });
  $('#reset-form').addEventListener('submit',async event=>{
    event.preventDefault();const form=event.currentTarget,button=form.querySelector('button');if(busy)return;
    if($('#reset-password').value!==$('#reset-confirm').value){message('#reset-message','As duas palavras-passe não coincidem.',true);return;}
    busy=true;button.disabled=true;
    try{await api('/api/auth/password-reset/confirm',{token:resetToken,new_password:$('#reset-password').value});form.reset();form.classList.add('hidden');message('#reset-message','Palavra-passe alterada. Entre com a nova credencial. A validade comercial mantém-se.');}
    catch(error){message('#reset-message',error.message,true);}finally{busy=false;button.disabled=false;}
  });
  const params=new URLSearchParams(location.hash.replace(/^#/,''));inviteToken=params.get('invite')||'';resetToken=params.get('reset')||'';
  if(location.hash)history.replaceState(null,'',location.pathname+location.search);
  if(inviteToken)inspect();else if(resetToken)show('reset-view');else show('request-view');
})();
