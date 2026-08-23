/* SRIS Pilot V1 - institutional home brand and editorial image alignment */
(()=>{
  'use strict';
  const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)];
  function install(){
    if($('#sris-home-brand-style'))return;
    const s=document.createElement('style');s.id='sris-home-brand-style';s.textContent=`
      .sris-site-mark{position:relative;display:inline-block;flex:0 0 auto;width:48px;height:48px;border:2px solid #d7a84c;border-radius:50%}
      .sris-site-mark:before{content:"";position:absolute;left:22px;top:9px;width:2px;height:32px;border-radius:2px;background:#d7a84c}
      .sris-site-mark:after{content:"";position:absolute;left:18px;top:8px;width:10px;height:10px;border-radius:50%;background:#d7a84c}
      .home-brand-aligned{display:flex!important;align-items:center!important;gap:14px!important}.home-brand-aligned>img,.home-brand-aligned>svg,.home-brand-aligned>.logo-mark,.home-brand-aligned>.brand-mark{display:none!important}
      .home-brand-copy{display:grid;line-height:1;color:#fff;font-weight:850;letter-spacing:.08em}.home-brand-copy small{margin-top:4px;font-size:8px;color:#e2c47f;letter-spacing:.17em}
      .sunrise-photo{display:block!important;width:100%!important;height:100%!important;object-fit:cover!important;object-position:center 55%!important;opacity:1!important}
    `;document.head.appendChild(s);
    const brand=$$('.brand,.home-brand,.login-brand,.brand-lockup').find(x=>/SRIS/i.test(x.textContent||''));
    if(brand&&!brand.dataset.aligned){brand.dataset.aligned='1';brand.classList.add('home-brand-aligned');brand.innerHTML='<span class="sris-site-mark" aria-hidden="true"></span><span class="home-brand-copy"><span>SRIS</span><small>MISSION INTELLIGENCE</small></span>'}
    const img=$('.sunrise-photo');if(img){img.removeAttribute('hidden');img.setAttribute('aria-hidden','true');img.alt=''}
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
