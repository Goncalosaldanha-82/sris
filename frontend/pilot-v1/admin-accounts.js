(() => {
  const API = '/api/pilot';

  async function api(path, options = {}) {
    const token = window.localStorage.getItem('sris_access_token') || window.sessionStorage.getItem('sris_access_token');
    const headers = Object.assign({'Content-Type': 'application/json'}, options.headers || {});
    if (token) headers.Authorization = `Bearer ${token}`;
    const response = await fetch(API + path, Object.assign({}, options, {headers}));
    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try { detail = (await response.json()).detail || detail; } catch (_) {}
      throw new Error(detail);
    }
    return response.json();
  }

  window.SRISAdminAccounts = {
    status: () => api('/ops/status'),
    list: () => api('/admin/accounts'),
    setState: (accountId, isActive) => api(`/admin/accounts/${accountId}/state`, {
      method: 'PATCH',
      body: JSON.stringify({is_active: !!isActive})
    }),
    setRole: (accountId, role) => api(`/admin/accounts/${accountId}/role`, {
      method: 'PATCH',
      body: JSON.stringify({role})
    })
  };
})();
