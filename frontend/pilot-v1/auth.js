(()=>{
  'use strict';

  const $=(selector,root=document)=>root.querySelector(selector);
  const $$=(selector,root=document)=>[...root.querySelectorAll(selector)];
  const messageBox=$('#message');
  let capabilities=null;

  function translateError(message,status){
    const value=String(message||'').trim();
    if(status===401||/invalid credentials/i.test(value))return'Email ou palavra-passe incorretos.';
    if(status===409&&/email|conta/i.test(value))return'Já existe uma conta com este email.';
    if(status===403)return value||'Esta operação não está disponível neste momento.';
    if(status===429)return'Demasiadas tentativas. Aguarde um pouco antes de repetir.';
    if(status>=500)return'O serviço não conseguiu concluir o pedido. Tente novamente dentro de instantes.';
    return value||`Não foi possível concluir o pedido (erro ${status}).`;
  }

  function errorText(data,status){
    const detail=data?.detail;
    const raw=typeof detail==='string'?detail:(detail?.message||detail?.code||data?.message||'');
    return translateError(raw,status);
  }

  function showMessage(text,type='success'){
    messageBox.textContent=text;
    messageBox.className=`alert ${type==='error'?'error':'success'}`;
    requestAnimationFrame(()=>messageBox.scrollIntoView({block:'nearest',behavior:'smooth'}));
  }

  function clearMessage(){
    messageBox.className='alert hidden';
    messageBox.textContent='';
  }

  function saveSession(data,email=''){
    localStorage.setItem('sris_access_token',data.access_token||'');
    localStorage.setItem('sris_refresh_token',data.refresh_token||'');
    if(data.organization_id)localStorage.setItem('sris_org_id',data.organization_id);
    if(email)localStorage.setItem('sris_user_email',String(email).trim().toLowerCase());
  }

  function clearSession(){
    ['sris_access_token','sris_refresh_token','sris_org_id','sris_user_id','sris_user_email'].forEach(key=>localStorage.removeItem(key));
  }

  async function api(path,options={}){
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),20000);
    try{
      const response=await fetch(path,{
        ...options,
        headers:{'Content-Type':'application/json',...(options.headers||{})},
        cache:'no-store',
        signal:controller.signal,
      });
      let data={};
      try{data=await response.json();}catch{}
      if(!response.ok){
        const error=new Error(errorText(data,response.status));
        error.status=response.status;
        throw error;
      }
      return data;
    }catch(error){
      if(error.name==='AbortError')throw new Error('O serviço demorou demasiado a responder. Verifique a ligação e tente novamente.');
      if(error instanceof TypeError)throw new Error('Não foi possível contactar o serviço. Verifique a ligação e tente novamente.');
      throw error;
    }finally{
      clearTimeout(timeout);
    }
  }

  function setBusy(form,busy,label){
    if(!form)return;
    form.setAttribute('aria-busy',busy?'true':'false');
    $$('button,input',form).forEach(control=>control.disabled=busy);
    const submit=$('[type="submit"]',form);
    if(!submit)return;
    if(busy){
      submit.dataset.idleLabel=submit.textContent;
      submit.textContent=label;
      submit.classList.add('loading');
    }else{
      submit.textContent=submit.dataset.idleLabel||submit.textContent;
      submit.classList.remove('loading');
    }
  }

  function validate(form){
    if(form.checkValidity())return true;
    form.reportValidity();
    const invalid=$(':invalid',form);
    invalid?.focus({preventScroll:true});
    invalid?.scrollIntoView({block:'center',behavior:'smooth'});
    return false;
  }

  function resetSubtitle(){
    const delivery=capabilities?.password_reset_delivery;
    if(delivery==='email')return'Introduza o email associado à conta. Receberá um endereço de utilização única, válido durante 30 minutos.';
    if(delivery==='pilot-link')return'Introduza o email associado à conta. Neste ambiente controlado será criado um endereço de utilização única.';
    return'Introduza o email associado à conta. O pedido será registado sem revelar se a conta existe.';
  }

  function mode(name){
    clearMessage();
    ['login-form','register-form','reset-request-form','reset-confirm-form'].forEach(id=>$('#'+id)?.classList.add('hidden'));
    $$('.auth-tab').forEach(button=>{
      const active=button.dataset.mode===name;
      button.classList.toggle('active',active);
      button.setAttribute('aria-selected',active?'true':'false');
    });
    $('#auth-tabs')?.classList.toggle('hidden',!['login','register'].includes(name));
    $('#trial-box')?.classList.toggle('hidden',!['login','register'].includes(name));

    const copy={
      login:['Bem-vindo','Entre no espaço da sua organização. As contas institucionais são criadas por convite.','login-form'],
      register:['Criar conta','Crie um workspace individual e comece pela primeira decisão real.','register-form'],
      'reset-request':['Recuperar acesso',resetSubtitle(),'reset-request-form'],
      'reset-confirm':['Nova palavra-passe','Defina uma nova credencial. A alteração invalida as sessões anteriores.','reset-confirm-form'],
    }[name];
    if(!copy)return;
    $('#auth-title').textContent=copy[0];
    $('#auth-subtitle').textContent=copy[1];
    $('#'+copy[2])?.classList.remove('hidden');
    document.body.dataset.authMode=name;
    window.scrollTo({top:0,behavior:'smooth'});
  }

  async function submit(form,label,task){
    if(!validate(form))return;
    clearMessage();
    setBusy(form,true,label);
    try{await task();}
    catch(error){showMessage(error.message,'error');}
    finally{setBusy(form,false,label);}
  }

  $$('.auth-tab').forEach(button=>button.addEventListener('click',()=>mode(button.dataset.mode)));
  $('#forgot-link')?.addEventListener('click',()=>mode('reset-request'));
  $$('[data-back-login]').forEach(button=>button.addEventListener('click',()=>mode('login')));

  $('#login-form')?.addEventListener('submit',event=>{
    event.preventDefault();
    submit(event.currentTarget,'A entrar…',async()=>{
      const data=await api('/api/auth/login',{
        method:'POST',
        body:JSON.stringify({email:$('#login-email').value.trim(),password:$('#login-password').value}),
      });
      saveSession(data,$('#login-email').value);
      location.assign('/app');
    });
  });

  $('#register-form')?.addEventListener('submit',event=>{
    event.preventDefault();
    submit(event.currentTarget,'A criar workspace…',async()=>{
      const data=await api('/api/pilot/register',{
        method:'POST',
        body:JSON.stringify({
          full_name:$('#reg-name').value.trim(),
          organization_name:$('#reg-org').value.trim()||null,
          email:$('#reg-email').value.trim(),
          password:$('#reg-password').value,
        }),
      });
      saveSession(data,$('#reg-email').value);
      location.assign('/app');
    });
  });

  $('#reset-request-form')?.addEventListener('submit',event=>{
    event.preventDefault();
    submit(event.currentTarget,'A criar pedido…',async()=>{
      const data=await api('/api/auth/password-reset/request',{
        method:'POST',body:JSON.stringify({email:$('#reset-email').value.trim()}),
      });
      if(data.reset_token){
        $('#reset-token').value=data.reset_token;
        mode('reset-confirm');
        showMessage(`Pedido criado. O endereço é válido durante ${data.expires_minutes||30} minutos.`);
      }else{
        showMessage(data.message||'Pedido aceite. Se a conta existir, receberá instruções para recuperar o acesso.');
      }
    });
  });

  $('#reset-confirm-form')?.addEventListener('submit',event=>{
    event.preventDefault();
    if($('#new-password').value!==$('#new-password-2').value){
      showMessage('As palavras-passe não coincidem.','error');
      $('#new-password-2').focus();
      return;
    }
    submit(event.currentTarget,'A atualizar…',async()=>{
      await api('/api/pilot/password-reset/confirm',{
        method:'POST',
        body:JSON.stringify({token:$('#reset-token').value,new_password:$('#new-password').value}),
      });
      mode('login');
      showMessage('Palavra-passe atualizada. Já pode entrar.');
    });
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

  async function restoreSession(){
    let accessToken=localStorage.getItem('sris_access_token');
    const refreshToken=localStorage.getItem('sris_refresh_token');
    if(!accessToken&&!refreshToken)return;

    const profile=async tokenValue=>fetch('/api/pilot/profile',{
      headers:{Authorization:`Bearer ${tokenValue}`},cache:'no-store',
    });
    try{
      if(accessToken){
        const current=await profile(accessToken);
        if(current.ok){location.assign('/app');return;}
        if(current.status!==401)return;
      }
      if(!refreshToken){clearSession();return;}
      const renewed=await api('/api/auth/refresh',{method:'POST',body:JSON.stringify({refresh_token:refreshToken})});
      saveSession(renewed);
      accessToken=renewed.access_token;
      const current=await profile(accessToken);
      if(current.ok)location.assign('/app');
      else clearSession();
    }catch{clearSession();}
  }

  function updateKeyboardState(){
    const viewport=window.visualViewport;
    const keyboardLikely=Boolean(viewport&&viewport.height<window.innerHeight*0.78&&$('input:focus,textarea:focus'));
    document.body.classList.toggle('keyboard-open',keyboardLikely);
  }

  window.visualViewport?.addEventListener('resize',updateKeyboardState);
  window.visualViewport?.addEventListener('scroll',updateKeyboardState);
  document.addEventListener('focusin',event=>{
    if(!event.target.matches('input,textarea'))return;
    setTimeout(()=>{
      updateKeyboardState();
      event.target.scrollIntoView({block:'center',behavior:'smooth'});
    },180);
  });
  document.addEventListener('focusout',()=>setTimeout(updateKeyboardState,120));

  (async()=>{
    $('#trial-copy').textContent='Facto, inferência e incerteza permanecem distintos; a decisão continua a exigir revisão humana.';
    try{
      capabilities=await api('/api/pilot/capabilities');
      if(!capabilities.public_signup){
        $('#register-tab').classList.add('hidden');
        $('#register-tab').disabled=true;
        $('#register-tab').title='Criação pública de conta fechada; acesso por convite';
      }else{
        $('#register-tab').classList.remove('hidden');
      }
    }catch(error){console.warn('Pilot capabilities unavailable on entry:',error.message);}
    if(applyResetTokenFromURL())return;
    await restoreSession();
  })();
})();
