(()=>{
  'use strict';
  const build=document.querySelector('meta[name="sris-pilot-build"]')?.content||'pilot';
  ['/commercial-entitlement-ui.js','/commercial-requests-ui.js'].forEach(src=>{
    const script=document.createElement('script');
    script.src=`${src}?v=${encodeURIComponent(build)}`;
    script.defer=true;
    document.head.appendChild(script);
  });
})();
