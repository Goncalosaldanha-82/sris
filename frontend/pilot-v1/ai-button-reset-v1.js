/* Removes legacy generic analysis handlers before the governed mission-scoped handler is attached. */
(()=>{
 'use strict';
 const selectors=['#copilot-analyze-btn','#analyze-btn','button[data-action="analyze"]'];
 function reset(){for(const selector of selectors){const button=document.querySelector(selector);if(!button||button.dataset.aiHandlerReset)return;const clean=button.cloneNode(true);clean.dataset.aiHandlerReset='1';button.replaceWith(clean)}}
 let timer;const observer=new MutationObserver(()=>{clearTimeout(timer);timer=setTimeout(reset,40)});
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>{reset();observer.observe(document.body,{childList:true,subtree:true})},{once:true});else{reset();observer.observe(document.body,{childList:true,subtree:true})}
})();
