(()=>{
  'use strict';
  const build=document.querySelector('meta[name="sris-pilot-build"]')?.content||'pilot';
  ['/admin-workspace-core.js','/commercial-access-admin.js'].forEach(src=>{
    const script=document.createElement('script');
    script.src=`${src}?v=${encodeURIComponent(build)}`;
    script.defer=true;
    document.head.appendChild(script);
  });
})();
