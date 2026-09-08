(()=>{
  'use strict';
  // The inbox has its own URL; it is no longer buried below the account cards.
  const path='/admin/access-requests';let authorized=false,busy=false;
  function remove(){document.querySelectorAll('[data-sris-access-inbox]').forEach(n=>n.remove());authorized=false;}
  async function refresh(){
    if(busy||document.hidden||!window.SRISApi?.raw)return;busy=true;
    try{
      const response=await window.SRISApi.raw('/api/admin/access-requests/summary',{skipWorkspace:true});
      if([401,403].includes(response.status)){remove();return;}
      if(!response.ok)throw new Error('Não foi possível atualizar os pedidos de acesso.');
      const data=await response.json();authorized=true;const count=Number(data.counts?.pending||0);
      const nav=document.querySelector('.nav');
      if(nav&&!document.getElementById('access-inbox-nav')){
        const group=document.createElement('div');group.className='nav-group';group.dataset.srisAccessInbox='nav';
        group.innerHTML='<div class="nav-group-label">Gestão SRIS</div><button type="button" id="access-inbox-nav"><span>Pedidos de acesso</span> <strong data-access-count></strong></button>';
        group.querySelector('button').addEventListener('click',()=>location.assign(path));nav.prepend(group);
      }
      for(const id of ['overview','account']){
        const section=document.getElementById(id);if(!section||section.querySelector('[data-sris-access-inbox]'))continue;
        const card=document.createElement('article');card.className='card';card.dataset.srisAccessInbox=id;
        const title=document.createElement('h3');title.textContent='Pedidos de acesso';const info=document.createElement('p');info.dataset.accessSummary='';
        const button=document.createElement('a');button.href=path;button.className='btn btn-primary';button.textContent='Abrir pedidos e decidir';
        card.append(title,info,button);section.prepend(card);
      }
      document.querySelectorAll('[data-access-count]').forEach(n=>n.textContent=String(count));
      document.querySelectorAll('[data-access-summary]').forEach(n=>n.textContent=count?`${count} ${count===1?'pedido aguarda':'pedidos aguardam'} a sua aprovação. Pode aprovar ou recusar nesta área.`:'Não há pedidos pendentes. Consulte o histórico de decisões nesta área.');
    }catch(error){if(authorized)document.querySelectorAll('[data-access-summary]').forEach(n=>n.textContent='Não foi possível atualizar o contador. Abra a área para consultar o estado.');}
    finally{busy=false;}
  }
  function boot(){refresh();setInterval(refresh,30000);document.addEventListener('visibilitychange',refresh);window.addEventListener('focus',refresh);}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
  // App boot and token refresh may finish after this dynamic module loads.
  setTimeout(refresh,1500);
})();
