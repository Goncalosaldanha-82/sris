const $=(s)=>document.querySelector(s);
const $$=(s)=>[...document.querySelectorAll(s)];
const msg=$('#message');

function showMessage(text,type='success'){
  msg.textContent=text;
  msg.className=`alert ${type==='error'?'error':'success'}`;
}
function clearMessage(){msg.className='alert hidden';msg.textContent='';}
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
  const res=await fetch(path,{headers:{'Content-Type':'application/json',...(options.headers||{})},...options});
  let data={};
  try{data=await res.json()}catch{}
  if(!res.ok)throw new Error(errorText(data,res.status));
  return data;
}
function mode(name){
  clearMessage();
  ['login-form','register-form','reset-request-form','reset-confirm-form'].forEach(id=>$('#'+id).classList.add('hidden'));
  $$('.auth-tab').forEach(b=>b.classList.toggle('active',b.dataset.mode===name));
  $('#auth-tabs').classList.toggle('hidden',!['login','register'].includes(name));
  $('#trial-box').classList.toggle('hidden',!['login','register'].includes(name));
  if(name==='login'){
    $('#login-form').classList.remove('hidden');
    $('#auth-title').textContent='Bem-vindo';
    $('#auth-subtitle').textContent='Entre no seu workspace ou crie uma conta para começar.';
  }
  if(name==='register'){
    $('#register-form').classList.remove('hidden');
    $('#auth-title').textContent='Criar conta';
    $('#auth-subtitle').textContent='Um workspace individual, seguro e pronto para estruturar a primeira missão.';
  }
  if(name==='reset-request'){
    $('#reset-request-form').classList.remove('hidden');
    $('#auth-title').textContent='Recuperar acesso';
    $('#auth-subtitle').textContent='Crie um pedido de recuperação de palavra-passe.';
  }
  if(name==='reset-confirm'){
    $('#reset-confirm-form').classList.remove('hidden');
    $('#auth-title').textContent='Nova palavra-passe';
    $('#auth-subtitle').textContent='Defina uma nova credencial para a sua conta.';
  }
}

$$('.auth-tab').forEach(b=>b.addEventListener('click',()=>mode(b.dataset.mode)));
$('#forgot-link').addEventListener('click',()=>mode('reset-request'));
$$('[data-back-login]').forEach(b=>b.addEventListener('click',()=>mode('login')));

$('#login-form').addEventListener('submit',async e=>{
  e.preventDefault();clearMessage();
  try{
    const data=await api('/api/auth/login',{method:'POST',body:JSON.stringify({email:$('#login-email').value.trim(),password:$('#login-password').value})});
    saveSession(data);location.href='/app';
  }catch(err){showMessage(err.message,'error');}
});
$('#register-form').addEventListener('submit',async e=>{
  e.preventDefault();clearMessage();
  try{
    const data=await api('/api/pilot/register',{method:'POST',body:JSON.stringify({full_name:$('#reg-name').value.trim(),organization_name:$('#reg-org').value.trim()||null,email:$('#reg-email').value.trim(),password:$('#reg-password').value})});
    saveSession(data);location.href='/app';
  }catch(err){showMessage(err.message,'error');}
});
$('#reset-request-form').addEventListener('submit',async e=>{
  e.preventDefault();clearMessage();
  try{
    const data=await api('/api/pilot/password-reset/request',{method:'POST',body:JSON.stringify({email:$('#reset-email').value.trim()})});
    if(data.reset_token){
      $('#reset-token').value=data.reset_token;mode('reset-confirm');
      showMessage(`Pedido criado. Link de teste válido durante ${data.expires_minutes||30} minutos.`);
    }else showMessage(data.message||'Pedido aceite. Verifique o seu email.');
  }catch(err){showMessage(err.message,'error');}
});
$('#reset-confirm-form').addEventListener('submit',async e=>{
  e.preventDefault();clearMessage();
  if($('#new-password').value!==$('#new-password-2').value){showMessage('As palavras-passe não coincidem.','error');return;}
  try{
    await api('/api/pilot/password-reset/confirm',{method:'POST',body:JSON.stringify({token:$('#reset-token').value,new_password:$('#new-password').value})});
    mode('login');showMessage('Palavra-passe atualizada. Já pode entrar.');
  }catch(err){showMessage(err.message,'error');}
});

(async()=>{
  const copy='Missões persistentes, evidência, histórico e memória organizacional num único espaço de trabalho.';
  $('#trial-copy').textContent=copy;
  try{
    const c=await api('/api/pilot/capabilities');
    if(!c.public_signup){
      $$('[data-mode="register"]').forEach(b=>{b.disabled=true;b.title='Criação pública de conta temporariamente fechada';});
    }
  }catch(err){
    console.warn('Pilot capabilities unavailable on entry:',err.message);
  }
})();

if(localStorage.getItem('sris_access_token')){
  fetch('/api/pilot/profile',{headers:{Authorization:`Bearer ${localStorage.getItem('sris_access_token')}`}})
    .then(r=>{if(r.ok)location.href='/app';})
    .catch(()=>{});
}
