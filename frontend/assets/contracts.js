(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.SRISContracts = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  function asArray(value) {
    return Array.isArray(value) ? value : [];
  }

  function normalizeMe(payload) {
    const envelope = payload && typeof payload === 'object' ? payload : {};
    const data = envelope.data && typeof envelope.data === 'object' ? envelope.data : envelope;
    const rawUser = data.user && typeof data.user === 'object' ? data.user : data;
    const memberships = asArray(data.memberships ?? rawUser.memberships);
    const email = typeof rawUser.email === 'string' ? rawUser.email : '';
    const fullName = [rawUser.full_name, rawUser.name, rawUser.display_name, email, 'Utilizador']
      .find(value => typeof value === 'string' && value.trim())
      .trim();

    return {
      user: {
        id: rawUser.id ?? null,
        email,
        full_name: fullName,
        is_platform_admin: Boolean(rawUser.is_platform_admin),
      },
      memberships: memberships
        .filter(item => item && typeof item === 'object')
        .map(item => ({
          organization_id: item.organization_id ?? item.org_id ?? item.organization?.id ?? null,
          organization_name: item.organization_name ?? item.organization?.name ?? '',
          role: item.role ?? 'member',
        }))
        .filter(item => item.organization_id),
    };
  }

  function identityLabel(me) {
    return me?.user?.full_name || me?.user?.email || 'Utilizador';
  }

  function applyExperienceSnapshot(state, snapshot) {
    if (!state || !snapshot || typeof snapshot !== 'object') return false;
    if (!snapshot.entry || !snapshot.map || !snapshot.timeline) return false;
    state.entry = snapshot.entry;
    state.map = snapshot.map;
    state.timeline = snapshot.timeline;
    if (state.workspace && typeof state.workspace === 'object') {
      state.workspace.graph = snapshot.map;
      state.workspace.audit = snapshot.entry.attention || state.workspace.audit || [];
    }
    state.last_experience_refresh = snapshot.generated_at || null;
    return true;
  }

  return { normalizeMe, identityLabel, applyExperienceSnapshot };
});
