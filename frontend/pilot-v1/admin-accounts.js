(() => {
  const API = '/api/pilot';

  function token() {
    return window.localStorage.getItem('sris_access_token') || window.sessionStorage.getItem('sris_access_token');
  }

  async function api(path, options = {}) {
    const headers = Object.assign({'Content-Type': 'application/json'}, options.headers || {});
    if (token()) headers.Authorization = `Bearer ${token()}`;
    const response = await fetch(API + path, Object.assign({}, options, {headers}));
    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try { detail = (await response.json()).detail || detail; } catch (_) {}
      const error = new Error(detail);
      error.status = response.status;
      throw error;
    }
    return response.json();
  }

  const client = {
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
  window.SRISAdminAccounts = client;

  function accountRows(accounts) {
    return accounts.map(account => `
      <div class="ledger-row" data-admin-account="${account.id}" style="align-items:center;gap:14px">
        <div style="min-width:0;flex:1">
          <strong style="display:block;overflow:hidden;text-overflow:ellipsis">${escapeHtml(account.full_name || account.email)}</strong>
          <span class="note">${escapeHtml(account.email)} · ${escapeHtml(account.role)}</span>
        </div>
        <span class="pill">${account.is_active ? 'Ativa' : 'Inativa'}</span>
        ${account.role === 'owner' ? '' : `<select class="admin-role" aria-label="Função">
          ${['admin','reviewer','contributor','observer'].map(role => `<option value="${role}" ${account.role === role ? 'selected' : ''}>${role}</option>`).join('')}
        </select>`}
        <button class="btn btn-ghost admin-state" data-active="${account.is_active ? '1' : '0'}">${account.is_active ? 'Desativar' : 'Ativar'}</button>
      </div>`).join('');
  }

  function escapeHtml(value) {
    return String(value || '').replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
  }

  async function renderAdmin() {
    const accountSection = document.getElementById('account');
    if (!accountSection || document.getElementById('pilot-admin-card')) return;
    let data;
    try {
      data = await client.list();
    } catch (error) {
      if (error.status === 401 || error.status === 403) return;
      return;
    }

    const wrapper = document.createElement('article');
    wrapper.className = 'card';
    wrapper.id = 'pilot-admin-card';
    wrapper.style.marginTop = '18px';
    wrapper.innerHTML = `
      <div class="card-title">
        <div><h3>Administração do workspace</h3><div class="note">Contas, funções e estado de acesso com registo de auditoria.</div></div>
        <span class="pill" id="pilot-ops-state">Operacional</span>
      </div>
      <div id="pilot-admin-message" class="alert hidden"></div>
      <div id="pilot-admin-list" class="ledger">${accountRows(data.accounts || []) || '<div class="note">Sem contas.</div>'}</div>`;
    accountSection.appendChild(wrapper);

    try {
      const status = await client.status();
      const pill = document.getElementById('pilot-ops-state');
      if (pill) pill.textContent = `${status.active_members}/${status.members} ativas · ${status.audit_events} eventos`;
    } catch (_) {}

    wrapper.addEventListener('change', async event => {
      const select = event.target.closest('.admin-role');
      if (!select) return;
      const row = select.closest('[data-admin-account]');
      try {
        await client.setRole(row.dataset.adminAccount, select.value);
        showMessage('Função atualizada e registada em auditoria.');
      } catch (error) {
        showMessage(error.message, true);
        renderAdminRefresh(wrapper);
      }
    });

    wrapper.addEventListener('click', async event => {
      const button = event.target.closest('.admin-state');
      if (!button) return;
      const row = button.closest('[data-admin-account]');
      const next = button.dataset.active !== '1';
      try {
        await client.setState(row.dataset.adminAccount, next);
        showMessage(next ? 'Conta ativada.' : 'Conta desativada e sessões anteriores invalidadas.');
        await renderAdminRefresh(wrapper);
      } catch (error) {
        showMessage(error.message, true);
      }
    });
  }

  async function renderAdminRefresh(wrapper) {
    const data = await client.list();
    const list = wrapper.querySelector('#pilot-admin-list');
    if (list) list.innerHTML = accountRows(data.accounts || []);
  }

  function showMessage(message, isError = false) {
    const node = document.getElementById('pilot-admin-message');
    if (!node) return;
    node.textContent = message;
    node.classList.remove('hidden');
    node.style.borderColor = isError ? '#a45b4d' : '';
    window.setTimeout(() => node.classList.add('hidden'), 5000);
  }

  function boot() {
    window.setTimeout(renderAdmin, 600);
    document.addEventListener('click', event => {
      const nav = event.target.closest('[data-section="account"]');
      if (nav) window.setTimeout(renderAdmin, 100);
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
