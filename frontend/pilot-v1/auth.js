const $=(selector,root=document)=>root.querySelector(selector);
const $$=(selector,root=document)=>[...root.querySelectorAll(selector)];
const messageBox=$('#message');
let capabilities=null;

function showMessage(text,type='success'){
  messageBox.textContent=text;
  messageBox.className=`alert ${type==='error'?'error':'success'}`;
}

function clearMessage(){
  messageBox.className='alert hidden';
  messageBox.textContent='';
}

function saveSession(data){
  localStorage.setItem('sris_access_token',data.access_token);
  localStorage.setItem('sris_refresh_token',data.refresh_token||'');
  if(data.organization_id)localStorage.setItem('sris_org_id',data.organization_id);
}

function errorText(data,status){
  const detail=data?.detail;
  if(typeof detail==='string')return detail;
  if(detail?.message)return detail.message;
  if(detail?.code)return detail.code;
  return data?.message||`Erro ${status}`;
}

async function api(path,options={}){
  const response=await fetch(path,{
    ...options,
    headers:{'Content-Type':'application/json',...(options.headers||{})},
    cache:'no-store',
  });
  let data={};
  try{data=await response.json()}catch{}
  if(!response.ok)throw new Error(errorText(data,response.status));
  return data;
}

function resetSubtitle(){
  const delivery=capabilities?.password_reset_delivery;
  if(delivery==='email')return'Introduza o email associado à conta. Receberá um endereço de utilização única, válido durante 30 minutos.';
  if(delivery==='pilot-link')return'Introduza o email associado à conta. Este ambiente de validação apresentará um endereço de utilização única.';
  return'Introduza o email associado à conta. O pedido será registado sem revelar se a conta existe.';
}

function mode(name){
  clearMessage();
  ['login-form','register-form','reset-request-form','reset-confirm-form'].forEach(id=>$('#'+id)?.classList.add('hidden'));
  $$('.auth-tab').forEach(button=>button.classList.toggle('active',button.dataset.mode===name));
  $('#auth-tabs')?.classList.toggle('hidden',!['login','register'].includes(name));
  $('#trial-box')?.classList.toggle('hidden',!['login','register'].includes(name));

  if(name==='login'){
    $('#login-form')?.classList.remove('hidden');
    $('#auth-title').textContent='Bem-vindo';
    $('#auth-subtitle').textContent='Entre no seu workspace ou crie uma conta para começar.';
  }
  if(name==='register'){
    $('#register-form')?.classList.remove('hidden');
    $('#auth-title').textContent='Criar conta';
    $('#auth-subtitle').textContent='Crie um workspace individual, seguro e pronto para estruturar a primeira missão.';
  }
  if(name==='reset-request'){
    $('#reset-request-form')?.classList.remove('hidden');
    $('#auth-title').textContent='Recuperar acesso';
    $('#auth-subtitle').textContent=resetSubtitle();
  }
  if(name==='reset-confirm'){
    $('#reset-confirm-form')?.classList.remove('hidden');
    $('#auth-title').textContent='Nova palavra-passe';
    $('#auth-subtitle').textContent='Defina uma nova credencial. A alteração invalida as sessões anteriores.';
  }
}

$$('.auth-tab').forEach(button=>button.addEventListener('click',()=>mode(button.dataset.mode)));
$('#forgot-link')?.addEventListener('click',()=>mode('reset-request'));
$$('[data-back-login]').forEach(button=>button.addEventListener('click',()=>mode('login')));

$('#login-form')?.addEventListener('submit',async event=>{
  event.preventDefault();
  clearMessage();
  event.submitter?.classList.add('loading');
  try{
    const data=await api('/api/auth/login',{
      method:'POST',
      body:JSON.stringify({
        email:$('#login-email').value.trim(),
        password:$('#login-password').value,
      }),
    });
    saveSession(data);
    location.href='/app';
  }catch(error){
    showMessage(error.message,'error');
  }finally{
    event.submitter?.classList.remove('loading');
  }
});

$('#register-form')?.addEventListener('submit',async event=>{
  event.preventDefault();
  clearMessage();
  event.submitter?.classList.add('loading');
  try{
    const data=await api('/api/pilot/register',{
      method:'POST',
      body:JSON.stringify({
        full_name:$('#reg-name').value.trim(),
        organization_name:$('#reg-org').value.trim()||null,
        email:$('#reg-email').value.trim(),
        password:$('#reg-password').value,
      }),
    });
    saveSession(data);
    location.href='/app';
  }catch(error){
    showMessage(error.message,'error');
  }finally{
    event.submitter?.classList.remove('loading');
  }
});

$('#reset-request-form')?.addEventListener('submit',async event=>{
  event.preventDefault();
  clearMessage();
  event.submitter?.classList.add('loading');
  try{
    const data=await api('/api/pilot/password-reset/request',{
      method:'POST',
      body:JSON.stringify({email:$('#reset-email').value.trim()}),
    });
    if(data.reset_token){
      $('#reset-token').value=data.reset_token;
      mode('reset-confirm');
      showMessage(`Pedido criado. O endereço de validação é válido durante ${data.expires_minutes||30} minutos.`);
    }else{
      showMessage(data.message||'Pedido aceite. Se a conta existir, receberá instruções para recuperar o acesso.');
    }
  }catch(error){
    showMessage(error.message,'error');
  }finally{
    event.submitter?.classList.remove('loading');
  }
});

$('#reset-confirm-form')?.addEventListener('submit',async event=>{
  event.preventDefault();
  clearMessage();
  if($('#new-password').value!==$('#new-password-2').value){
    showMessage('As palavras-passe não coincidem.','error');
    return;
  }
  event.submitter?.classList.add('loading');
  try{
    await api('/api/pilot/password-reset/confirm',{
      method:'POST',
      body:JSON.stringify({
        token:$('#reset-token').value,
        new_password:$('#new-password').value,
      }),
    });
    mode('login');
    showMessage('Palavra-passe atualizada. Já pode entrar.');
  }catch(error){
    showMessage(error.message,'error');
  }finally{
    event.submitter?.classList.remove('loading');
  }
});

function applyResetTokenFromURL(){
  const url=new URL(location.href);
  const resetToken=url.searchParams.get('reset_token');
  if(!resetToken)return false;
  $('#reset-token').value=resetToken;
  url.searchParams.delete('reset_token');
  history.replaceState({},document.title,url.pathname+url.search+url.hash);
  mode('reset-confirm');
  return true;
}

(async()=>{
  $('#trial-copy').textContent='A assistência deve indicar incerteza, separar facto de inferência e nunca preencher lacunas com confiança artificial.';
  try{
    capabilities=await api('/api/pilot/capabilities');
    if(!capabilities.public_signup){
      $$('[data-mode="register"]').forEach(button=>{
        button.disabled=true;
        button.title='Criação pública de conta temporariamente fechada';
      });
    }
  }catch(error){
    console.warn('Pilot capabilities unavailable on entry:',error.message);
  }

  if(applyResetTokenFromURL())return;

  const accessToken=localStorage.getItem('sris_access_token');
  if(accessToken){
    fetch('/api/pilot/profile',{headers:{Authorization:`Bearer ${accessToken}`},cache:'no-store'})
      .then(response=>{if(response.ok)location.href='/app';})
      .catch(()=>{});
  }
})();
