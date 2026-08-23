(() => {
  window.SRISOpsStatus = async function () {
    const token = window.localStorage.getItem('sris_access_token') || window.sessionStorage.getItem('sris_access_token');
    const response = await fetch('/api/pilot/ops/status', {
      headers: token ? {Authorization: `Bearer ${token}`} : {}
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  };
})();
