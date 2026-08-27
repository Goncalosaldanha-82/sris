(function () {
  "use strict";

  const TAB = "economics";
  let state = null;
  let currentMissionCode = "";
  let loadSequence = 0;
  let editingItemId = "";
  let pendingRetirementId = "";
  let saving = false;

  const KIND_TREATMENT = {
    monetary_cost: "cost",
    monetary_benefit: "benefit",
    non_monetary_benefit: "none",
    financial_resource: "none",
  };
  const FLEXIBLE_KIND_DEFAULT = {
    human_resource: "none",
    material_resource: "none",
    equipment_resource: "none",
  };
  const KIND_LABELS = {
    monetary_cost: "Custo monetário",
    monetary_benefit: "Benefício monetário",
    non_monetary_benefit: "Benefício não monetizado",
    human_resource: "Recurso humano",
    material_resource: "Material ou consumível",
    equipment_resource: "Equipamento ou capacidade",
    financial_resource: "Financiamento disponível",
  };
  const PHASE_LABELS = {
    planning: "Planeamento",
    execution: "Execução",
    post_mission: "Após a missão",
  };
  const RECURRENCE_LABELS = {
    one_off: "Uma vez",
    monthly: "Mensal",
    quarterly: "Trimestral",
    annual: "Anual",
  };
  const EVENT_LABELS = {
    case_created: "Business case criado",
    case_updated: "Configuração atualizada",
    item_created: "Linha criada",
    item_updated: "Linha atualizada",
    item_retired: "Linha retirada",
    case_reviewed: "Revisão humana concluída",
  };

  const esc = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  async function api(path, options = {}) {
    if (window.SRISApi?.request) return window.SRISApi.request(path, options);
    const headers = { ...(options.headers || {}) };
    if (!(options.body instanceof FormData)) headers["Content-Type"] = "application/json";
    const accessToken = localStorage.getItem("sris_access_token") || sessionStorage.getItem("sris_access_token");
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
    const response = await fetch(path, { ...options, headers, cache: "no-store", credentials: "same-origin" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = payload?.detail;
      throw new Error(typeof detail === "string" ? detail : detail?.message || `Pedido recusado (${response.status}).`);
    }
    return payload;
  }

  function root() {
    return document.querySelector("#business-case-root");
  }

  function missionCode() {
    return currentMissionCode || String(document.querySelector("#detail-code")?.textContent || "").split("/").pop().trim();
  }

  function installTab() {
    const tabs = document.querySelector("#mission-detail .mission-tabs");
    const detail = document.querySelector("#mission-detail");
    if (!tabs || !detail || tabs.querySelector(`[data-mission-tab="${TAB}"]`)) return;
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.missionTab = TAB;
    button.textContent = "Economia e recursos";
    const anchor = tabs.querySelector('[data-mission-tab="validation"]');
    tabs.insertBefore(button, anchor || null);
    const panel = document.createElement("div");
    panel.className = "mission-tab";
    panel.id = `mission-tab-${TAB}`;
    panel.innerHTML = '<div id="business-case-root" class="business-case-root"><div class="note">A sincronizar o business case vivo…</div></div>';
    const validation = detail.querySelector("#mission-tab-validation");
    detail.insertBefore(panel, validation || detail.querySelector("#mission-tab-history") || null);
  }

  function installStyles() {
    if (document.querySelector("#business-case-styles")) return;
    const style = document.createElement("style");
    style.id = "business-case-styles";
    style.textContent = `
      .business-case-root{display:grid;gap:18px;color:#12352c}.business-case-root *{box-sizing:border-box}.bc-hero{background:linear-gradient(135deg,#092f28,#17644f 68%,#a47822);color:#fff;border-radius:24px;padding:28px;display:flex;justify-content:space-between;gap:22px}.bc-hero h3{font-size:clamp(29px,4vw,46px);line-height:1.02;margin:8px 0;color:#fff!important}.bc-hero .product-index{color:#c9e4da}.bc-hero p{max-width:780px;color:#e5f0eb;margin:0}.bc-revision{align-self:flex-start;border:1px solid rgba(255,255,255,.5);border-radius:999px;background:rgba(4,34,27,.24);color:#fff;padding:9px 13px;white-space:nowrap;font-weight:800}.bc-card{background:#fff;border:1px solid #cfdbd6;border-radius:20px;padding:20px}.bc-card h4{margin:0 0 7px}.bc-kpis{display:grid;grid-template-columns:repeat(5,minmax(130px,1fr));gap:10px}.bc-kpi{background:#f4f7f5;border:1px solid #d6dfdb;border-radius:16px;padding:14px;min-height:96px}.bc-kpi strong{display:block;font-size:clamp(20px,2.4vw,30px);line-height:1.05;overflow-wrap:anywhere}.bc-kpi span{display:block;color:#5d7169;font-size:12px;margin-top:8px}.bc-status{min-height:23px;color:#536a61}.bc-status.success{color:#176a4d}.bc-status.error{color:#a22b23}.bc-status.warning{color:#8a6515}.bc-warnings{display:grid;gap:8px}.bc-warning{border-left:4px solid #c59639;background:#fff9e9;border-radius:10px;padding:11px 13px}.bc-warning.high{border-left-color:#a64036;background:#fff2f0}.bc-warning.info{border-left-color:#4e7d91;background:#f0f7fa}.bc-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.bc-grid.two{grid-template-columns:repeat(2,minmax(0,1fr))}.bc-field{display:grid;gap:6px}.bc-field.full{grid-column:1/-1}.bc-field label{font-weight:800;font-size:13px}.bc-field small{color:#60746c}.business-case-root input,.business-case-root textarea,.business-case-root select{width:100%;border:1px solid #c9d5d0;border-radius:11px;background:#fff;color:#0b3026;padding:10px 11px;font:inherit;font-size:16px}.business-case-root textarea{min-height:94px;resize:vertical}.bc-actions{display:flex;gap:9px;flex-wrap:wrap;align-items:center;margin-top:14px}.bc-scenarios{overflow-x:auto}.bc-table{width:100%;border-collapse:separate;border-spacing:0;min-width:720px}.bc-table th,.bc-table td{padding:11px;border-right:1px solid #d9e1de;border-bottom:1px solid #d9e1de;text-align:right}.bc-table th:first-child,.bc-table td:first-child{text-align:left;border-left:1px solid #d9e1de}.bc-table thead th{background:#f3f6f4;border-top:1px solid #d9e1de}.bc-alt-gaps{display:block;color:#92621b;font-size:11px;margin-top:5px}.bc-ledger{display:grid;gap:10px}.bc-line{border:1px solid #d4dfda;border-radius:15px;padding:14px;display:grid;grid-template-columns:minmax(0,1.6fr) repeat(3,minmax(100px,.65fr)) auto;gap:11px;align-items:center}.bc-line small{display:block;color:#62766e;margin-top:4px}.bc-line-value strong{display:block}.bc-line-value span{font-size:11px;color:#667970}.bc-line-actions{display:flex;gap:6px;flex-wrap:wrap}.bc-line-actions button{white-space:nowrap}.bc-kind{display:inline-flex;border-radius:999px;background:#e9f2ee;color:#18513f;padding:4px 8px;font-size:11px;font-weight:800}.bc-scope{display:inline-flex;border-radius:999px;background:#fff4d8;color:#755316;padding:4px 8px;font-size:11px;font-weight:800;margin-left:5px}.bc-form-shell{background:#f7f9f8;border:1px solid #d8e1dd;border-radius:17px;padding:16px}.bc-form-shell summary{cursor:pointer;font-weight:900}.bc-form-body{margin-top:15px}.bc-check{display:flex;gap:9px;align-items:flex-start}.bc-check input{width:auto;margin-top:4px}.bc-quality{display:grid;grid-template-columns:150px 1fr;gap:17px;align-items:center}.bc-quality-score{border-radius:50%;width:128px;height:128px;display:grid;place-content:center;background:conic-gradient(#17644f calc(var(--score)*1%),#e1e8e5 0);position:relative}.bc-quality-score:before{content:"";position:absolute;inset:12px;background:#fff;border-radius:50%}.bc-quality-score strong,.bc-quality-score span{position:relative;text-align:center}.bc-quality-score strong{font-size:28px}.bc-readiness{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.bc-check-row{border:1px solid #d9e1de;border-radius:11px;padding:9px;display:flex;gap:8px}.bc-check-row.passed{background:#edf6f1}.bc-history{display:grid;gap:8px}.bc-history-row{display:flex;justify-content:space-between;gap:12px;border-top:1px solid #e0e7e4;padding-top:9px}.bc-empty{border:1px dashed #b9c8c2;border-radius:14px;padding:17px;color:#5b7068}.bc-danger-confirm{border:1px solid #e2b1aa;background:#fff1ef;border-radius:10px;padding:8px}.bc-muted{color:#62766e}.bc-review{border-color:#d5b56f;background:#fffcf4}.bc-review textarea{min-height:78px}.bc-integrity{font-size:12px;color:#63766f;overflow-wrap:anywhere}.business-case-root button:disabled{opacity:.55;cursor:not-allowed}
      .business-case-root .bc-conclusion{border-left:5px solid #b98620;background:#fff9e9;border-radius:13px;padding:14px 16px;margin-top:14px;font-size:16px;line-height:1.55}
      .bc-advanced{margin-top:12px}.bc-advanced>summary,.bc-metric-details>summary{cursor:pointer;font-weight:850;color:#315d50;padding:8px 0}.bc-metric-details{margin-top:12px}.bc-metric-details .bc-kpis{margin-top:10px}
      .bc-prefill{margin:12px 0;border:1px solid #c8ddd4;border-radius:13px;background:#f2f8f5;padding:11px 13px}.bc-prefill summary{cursor:pointer;font-weight:850}.bc-prefill-list{display:grid;gap:7px;margin-top:10px}.bc-prefill-row{border-top:1px solid #d8e6e0;padding-top:7px}.bc-prefill-row strong,.bc-prefill-row small{display:block}.bc-prefill-row small{color:#60746c;overflow-wrap:anywhere}
      @media(max-width:1100px){.bc-kpis{grid-template-columns:repeat(3,1fr)}.bc-line{grid-template-columns:1fr repeat(2,minmax(100px,.55fr))}.bc-line-actions{grid-column:1/-1}}
      @media(max-width:760px){.bc-hero{display:block;padding:22px 18px;border-radius:18px}.bc-revision{display:inline-block;margin-top:15px}.bc-card{padding:15px}.bc-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.bc-grid,.bc-grid.two{grid-template-columns:1fr}.bc-field.full{grid-column:auto}.bc-line{grid-template-columns:1fr 1fr}.bc-line-main,.bc-line-actions{grid-column:1/-1}.bc-quality{grid-template-columns:1fr}.bc-quality-score{margin:auto}.bc-readiness{grid-template-columns:1fr}.bc-history-row{display:grid}.bc-actions .btn{flex:1 1 150px}}
      @media(max-width:430px){.bc-kpis{grid-template-columns:1fr 1fr}.bc-kpi{padding:11px;min-height:91px}.bc-kpi strong{font-size:20px}.bc-line{grid-template-columns:1fr}.bc-line-value{display:flex;justify-content:space-between;gap:8px}.bc-line-main,.bc-line-actions{grid-column:auto}}
    `;
    document.head.appendChild(style);
  }

  function setStatus(message, tone = "") {
    const node = document.querySelector("#business-case-status");
    if (!node) return;
    node.className = `bc-status ${tone}`.trim();
    node.textContent = message || "";
  }

  function money(value) {
    if (value === null || value === undefined || value === "") return "—";
    const currency = state?.case?.currency || "EUR";
    return Number(value).toLocaleString("pt-PT", { style: "currency", currency, maximumFractionDigits: 0 });
  }

  function metricState(group = "any_lines") {
    return state?.metric_states?.[group] || state?.metrics_state || "unknown_not_zero";
  }

  function stateValue(value, valueState, formatter) {
    if (!valueState || valueState === "unknown_not_zero") return "—";
    const formatted = formatter(value);
    if (formatted === "—") return formatted;
    return valueState === "partial_observed_or_estimated" ? `Parcial · ${formatted}` : formatted;
  }

  function metricKnown(group = "any_lines") {
    return metricState(group) !== "unknown_not_zero";
  }

  function metricMoney(value, group = "financial") {
    return stateValue(value, metricState(group), money);
  }

  function metricNumber(value, digits = 1, group = "any_lines") {
    return stateValue(value, metricState(group), amount => number(amount, digits));
  }

  function number(value, digits = 1) {
    if (value === null || value === undefined || value === "") return "—";
    return Number(value).toLocaleString("pt-PT", { maximumFractionDigits: digits });
  }

  function dateValue(value) {
    return value ? String(value).slice(0, 10) : "";
  }

  function inputValue(value) {
    return value === null || value === undefined ? "" : String(value);
  }

  function kpi(label, value, detail = "") {
    return `<div class="bc-kpi"><strong>${esc(value)}</strong><span>${esc(label)}${detail ? ` · ${esc(detail)}` : ""}</span></div>`;
  }

  function scenarioTable() {
    const scenarios = state?.metrics?.scenarios || {};
    const labels = { conservative: "Conservador", base: "Base", favorable: "Favorável" };
    const rows = ["conservative", "base", "favorable"].map((key) => {
      const row = scenarios[key] || {};
      const financialGroup = `scenario_${key}_financial`;
      return `<tr><th scope="row">${labels[key]}</th><td>${metricMoney(row.total_cost,`scenario_${key}_costs`)}</td><td>${metricMoney(row.gross_benefit,`scenario_${key}_benefits`)}</td><td>${metricMoney(row.net_benefit,financialGroup)}</td><td>${row.roi_pct == null?"—":`${metricNumber(row.roi_pct,2,financialGroup)}%`}</td><td>${row.payback_months == null?"—":`${metricNumber(row.payback_months,0,financialGroup)} meses`}</td><td>${metricMoney(row.npv,financialGroup)}</td></tr>`;
    }).join("");
    return `<div class="bc-scenarios"><table class="bc-table"><thead><tr><th>Cenário</th><th>Custo total</th><th>Benefício bruto</th><th>Benefício líquido</th><th>ROI</th><th>Payback</th><th>VAL</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  }

  function alternativeTable() {
    const comparison = state?.alternative_comparison || {};
    const profiles = comparison.profiles || [];
    if (!profiles.length) return '<div class="bc-empty">Crie alternativas na área Comparação para modelar o custo total, os recursos, o benefício provável e o retorno de cada opção.</div>';
    const rows = profiles.map((profile) => {
      const profileStates = profile.metric_states || {};
      const financialState = profileStates.scenario_base_financial || profileStates.financial;
      const costsState = profileStates.scenario_base_costs || profileStates.costs;
      const benefitsState = profileStates.scenario_base_benefits || profileStates.benefits;
      const resourcesKnown = Boolean(profileStates.resources) && profileStates.resources !== "unknown_not_zero";
      const qualityKnown = Number(profile.quality?.monetary_line_count || 0) > 0;
      const value = (amount) => stateValue(amount, financialState, money);
      const resources = profile.resources || {};
      const plannedHoursState = profileStates.planned_human_hours || "unknown_not_zero";
      const resourceText = !resourcesKnown ? "—" : [
        resources.human_roles ? `${resources.human_roles} ${resources.human_roles === 1 ? "função" : "funções"} · ${stateValue(resources.planned_human_hours,plannedHoursState,amount=>number(amount,1))} h previstas` : "",
        resources.material_lines ? `${resources.material_lines} materiais` : "",
        resources.equipment_lines ? `${resources.equipment_lines} equipamentos` : "",
        resources.funding_lines ? `${resources.funding_lines} fontes de financiamento` : "",
      ].filter(Boolean).join(" · ") || "—";
      const gaps = profile.gaps?.length ? `<span class="bc-alt-gaps">Falta: ${esc(profile.gaps.join(", "))}</span>` : "";
      return `<tr><th scope="row"><strong>${esc(profile.alternative_label)}</strong>${gaps}</th><td>${stateValue(profile.total_cost,costsState,money)}</td><td>${esc(resourceText)}</td><td>${stateValue(profile.probable_gross_benefit,benefitsState,money)}</td><td>${value(profile.probable_net_benefit)}</td><td>${!financialState||financialState==='unknown_not_zero'||profile.roi_pct == null ? "—" : `${stateValue(profile.roi_pct,financialState,amount=>number(amount,2))}%`}</td><td>${!financialState||financialState==='unknown_not_zero'||profile.payback_months == null ? "—" : `${stateValue(profile.payback_months,financialState,amount=>number(amount,0))} meses`}</td><td>${qualityKnown ? `${number(profile.quality?.overall_score || 0, 0)}%` : "—"}</td></tr>`;
    }).join("");
    return `<div class="bc-scenarios"><table class="bc-table"><thead><tr><th>Alternativa</th><th>Custo total</th><th>Recursos</th><th>Benefício provável</th><th>Benefício líquido</th><th>ROI</th><th>Payback</th><th>Qualidade</th></tr></thead><tbody>${rows}</tbody></table></div><p class="bc-muted">Cada alternativa é calculada isoladamente. As respetivas linhas não entram nos totais da missão e não são somadas entre si.</p>`;
  }

  function caseForm() {
    const item = state.case || {};
    return `<form id="bc-case-form">
      <div class="bc-grid">
        <div class="bc-field"><label for="bc-case-kind">Lógica de valor</label><select id="bc-case-kind" name="case_kind"><option value="commercial" ${item.case_kind === "commercial" ? "selected" : ""}>Retorno comercial</option><option value="public_value" ${item.case_kind === "public_value" ? "selected" : ""}>Valor público, social ou ambiental</option><option value="cost_effectiveness" ${item.case_kind === "cost_effectiveness" ? "selected" : ""}>Custo-eficácia</option><option value="hybrid" ${item.case_kind === "hybrid" ? "selected" : ""}>Valor híbrido</option></select></div>
        <div class="bc-field"><label for="bc-horizon">Horizonte de análise</label><input id="bc-horizon" name="horizon_months" type="number" min="1" max="600" step="1" value="${esc(item.horizon_months || 60)}" required><small>meses, incluindo efeitos posteriores${item.id ? "" : "; proposta inicial a confirmar"}</small></div>
        <div class="bc-field"><label for="bc-discount">Taxa anual de desconto</label><input id="bc-discount" name="discount_rate_pct" type="number" min="0" max="100" step="0.01" value="${esc(inputValue(item.discount_rate_pct ?? 8))}" required><small>% usada no VAL${item.id ? "" : "; proposta inicial a confirmar"}</small></div>
        <div class="bc-field full"><label for="bc-context">Decisão económica em causa</label><textarea id="bc-context" name="decision_context" maxlength="5000" placeholder="O que se pretende decidir, financiar, evitar ou criar?">${esc(item.decision_context || "")}</textarea></div>
      </div>
      <details class="bc-form-shell bc-advanced"><summary>Contexto, datas, resultado e limites</summary><div class="bc-form-body"><div class="bc-grid">
        <div class="bc-field full"><label for="bc-baseline">Situação de partida</label><textarea id="bc-baseline" name="baseline" maxlength="5000" placeholder="Custos, desempenho e recursos antes da missão.">${esc(item.baseline || "")}</textarea></div>
        <div class="bc-field full"><label for="bc-counterfactual">O que acontece se nada for feito?</label><textarea id="bc-counterfactual" name="counterfactual" maxlength="5000" placeholder="Custo de não agir, perdas prováveis e riscos mantidos.">${esc(item.counterfactual || "")}</textarea></div>
        <div class="bc-field"><label for="bc-planned-start">Início previsto</label><input id="bc-planned-start" name="planned_start_date" type="date" value="${esc(dateValue(item.planned_start_date))}"></div>
        <div class="bc-field"><label for="bc-planned-end">Conclusão prevista</label><input id="bc-planned-end" name="planned_end_date" type="date" value="${esc(dateValue(item.planned_end_date))}"></div>
        <div class="bc-field"><label for="bc-forecast-end">Conclusão agora projetada</label><input id="bc-forecast-end" name="forecast_end_date" type="date" value="${esc(dateValue(item.forecast_end_date))}"></div>
        <div class="bc-field"><label for="bc-actual-start">Início real</label><input id="bc-actual-start" name="actual_start_date" type="date" value="${esc(dateValue(item.actual_start_date))}"></div>
        <div class="bc-field"><label for="bc-actual-end">Conclusão real</label><input id="bc-actual-end" name="actual_end_date" type="date" value="${esc(dateValue(item.actual_end_date))}"></div>
        <div class="bc-field"><label for="bc-currency">Moeda</label><input id="bc-currency" name="currency" value="${esc(item.currency || "EUR")}" pattern="[A-Z]{3}" maxlength="3" required></div>
        <div class="bc-field"><label for="bc-outcome-name">Indicador de resultado</label><input id="bc-outcome-name" name="outcome_name" maxlength="300" value="${esc(item.outcome_name || "")}" placeholder="Ex.: emissões evitadas"></div>
        <div class="bc-field"><label for="bc-outcome-unit">Unidade de medição</label><input id="bc-outcome-unit" name="outcome_unit" maxlength="80" value="${esc(item.outcome_unit || "")}" placeholder="Ex.: tCO₂e"></div>
        <div class="bc-field"><label for="bc-outcome-plan">Resultado previsto</label><input id="bc-outcome-plan" name="planned_outcome_quantity" type="number" min="0" step="any" value="${esc(inputValue(item.planned_outcome_quantity))}"></div>
        <div class="bc-field"><label for="bc-outcome-actual">Resultado realizado</label><input id="bc-outcome-actual" name="actual_outcome_quantity" type="number" min="0" step="any" value="${esc(inputValue(item.actual_outcome_quantity))}"></div>
        <div class="bc-field full"><label for="bc-notes">Notas e limites</label><textarea id="bc-notes" name="notes" maxlength="8000" placeholder="Dependências, exclusões, limites de inferência e regras de contabilização.">${esc(item.notes || "")}</textarea></div>
      </div></div></details>
      <div class="bc-actions">${!item.id ? '<button class="btn btn-secondary" type="button" data-bc-apply-prefill>Usar propostas da missão</button>' : ''}<button class="btn btn-primary" type="submit" ${saving ? "disabled" : ""}>${item.id ? "Guardar nova revisão" : "Criar business case"}</button><span class="bc-muted">As propostas nunca são gravadas sem confirmação humana.</span></div>
    </form>`;
  }

  function governedPrefillSummary() {
    const proposal = state?.governed_prefill || {};
    const labels = {
      decision_context: "Decisão económica",
      baseline: "Situação de partida",
      planned_start_date: "Início previsto",
      planned_end_date: "Conclusão prevista",
      outcome_name: "Indicador de resultado",
      outcome_unit: "Unidade de medição",
      planned_outcome_quantity: "Resultado previsto",
      actual_outcome_quantity: "Resultado observado",
      counterfactual: "Cenário de não agir",
      discount_rate_pct: "Taxa de desconto",
      economic_line_items: "Custos, benefícios e recursos",
    };
    const rows = Object.entries(proposal.fields || {}).filter(([, field]) => field?.value !== null && field?.value !== undefined && field?.value !== "");
    if (!rows.length) return '<div class="bc-empty">A missão ainda não contém campos governados suficientes para propor uma fundação. O utilizador mantém controlo integral do preenchimento.</div>';
    const proposalLabel = rows.length === 1 ? "proposta rastreável disponível" : "propostas rastreáveis disponíveis";
    const unresolved = (proposal.unresolved_fields || []).map(key => labels[key] || key);
    return `<details class="bc-prefill"><summary>${rows.length} ${proposalLabel}</summary><div class="bc-prefill-list">${rows.map(([key, field]) => `<div class="bc-prefill-row"><strong>${esc(labels[key] || key)}</strong><span>${esc(String(field.value).slice(0, 260))}</span><small>Fonte${(field.source_ids || []).length === 1 ? "" : "s"}: ${esc((field.source_ids || []).join(" · ") || "não identificada")}</small></div>`).join("")}<div class="bc-prefill-row"><strong>Dados que continuam em falta</strong><span>${esc(unresolved.join(" · ") || "Nenhum identificado")}</span><small>Nada é persistido sem confirmação humana.</small></div></div></details>`;
  }

  function evidenceOptions(selected) {
    return ['<option value="">Sem evidência ligada</option>'].concat((state.evidence || []).map((item) => `<option value="${esc(item.id)}" ${item.id === selected ? "selected" : ""}>${esc(item.label)}</option>`)).join("");
  }

  function alternativeOptions(selected) {
    return ['<option value="">Missão em execução · inclui nos cartões executivos</option>'].concat((state.alternatives || []).map((item) => `<option value="${esc(item.id)}" ${item.id === selected ? "selected" : ""}>Alternativa · ${esc(item.label)}</option>`)).join("");
  }

  function itemForm() {
    const existing = (state.items || []).find((item) => item.id === editingItemId);
    const item = existing || {
      kind: "monetary_cost",
      financial_treatment: "cost",
      phase: "execution",
      amount_basis: "total",
      recurrence: "one_off",
      start_month: 0,
      operational_status: "planned",
      confidence: "moderate",
      include_in_totals: true,
    };
    const title = existing ? `Editar · ${item.label}` : "Adicionar custo, benefício ou recurso";
    return `<details class="bc-form-shell" ${existing || !(state.items || []).length ? "open" : ""}><summary>${esc(title)}</summary><div class="bc-form-body"><form id="bc-item-form" data-item-id="${esc(existing?.id || "")}">
      <div class="bc-grid">
        <div class="bc-field"><label for="bc-item-kind">Tipo de registo</label><select id="bc-item-kind" name="kind">${Object.entries(KIND_LABELS).map(([key, label]) => `<option value="${key}" ${item.kind === key ? "selected" : ""}>${esc(label)}</option>`).join("")}</select></div>
        <div class="bc-field"><label for="bc-treatment">Tratamento no cálculo</label><select id="bc-treatment" name="financial_treatment" ${KIND_TREATMENT[item.kind] ? "disabled" : ""}><option value="cost" ${item.financial_treatment === "cost" ? "selected" : ""}>Somar aos custos</option><option value="benefit" ${item.financial_treatment === "benefit" ? "selected" : ""}>Somar aos benefícios</option><option value="none" ${item.financial_treatment === "none" ? "selected" : ""}>Quantificar sem monetizar</option></select><small>Custos, benefícios e financiamento usam o tratamento coerente com o tipo.</small></div>
        <div class="bc-field"><label for="bc-phase">Fase</label><select id="bc-phase" name="phase">${Object.entries(PHASE_LABELS).map(([key, label]) => `<option value="${key}" ${item.phase === key ? "selected" : ""}>${label}</option>`).join("")}</select></div>
        <div class="bc-field full"><label for="bc-alternative">Âmbito da linha</label><select id="bc-alternative" name="alternative_node_id">${alternativeOptions(item.alternative_node_id || "")}</select><small>Escolha uma alternativa para comparar opções sem inflacionar o total da missão.</small></div>
        <div class="bc-field"><label for="bc-amount-basis">Base do valor</label><select id="bc-amount-basis" name="amount_basis"><option value="total" ${item.amount_basis !== "per_unit" ? "selected" : ""}>Valor total por ocorrência</option><option value="per_unit" ${item.amount_basis === "per_unit" ? "selected" : ""}>Valor unitário × quantidade prevista</option></select></div>
        <div class="bc-field"><label for="bc-operational-status">Estado operacional</label><select id="bc-operational-status" name="operational_status"><option value="planned" ${item.operational_status === "planned" ? "selected" : ""}>Planeado</option><option value="committed" ${item.operational_status === "committed" ? "selected" : ""}>Comprometido</option><option value="active" ${item.operational_status === "active" ? "selected" : ""}>Em utilização</option><option value="completed" ${item.operational_status === "completed" ? "selected" : ""}>Concluído</option><option value="blocked" ${item.operational_status === "blocked" ? "selected" : ""}>Bloqueado</option></select></div>
        <div class="bc-field"><label for="bc-item-label">Designação</label><input id="bc-item-label" name="label" required minlength="2" maxlength="300" value="${esc(item.label || "")}" placeholder="Ex.: Equipa técnica interna"></div>
        <div class="bc-field"><label for="bc-category">Categoria</label><input id="bc-category" name="category" maxlength="120" value="${esc(item.category || "")}" placeholder="Ex.: pessoal, CAPEX, poupança"></div>
        <div class="bc-field"><label for="bc-responsible">Responsável / entidade</label><input id="bc-responsible" name="responsible" maxlength="300" value="${esc(item.responsible || "")}"></div>
        <div class="bc-field full"><label for="bc-description">Descrição</label><textarea id="bc-description" name="description" maxlength="5000" placeholder="O que inclui e o que exclui esta linha?">${esc(item.description || "")}</textarea></div>
      </div>
      <div class="bc-grid" style="margin-top:12px">
        <div class="bc-field"><label for="bc-conservative">Valor conservador</label><input id="bc-conservative" name="conservative_amount" type="number" min="0" step="any" value="${esc(inputValue(item.conservative_amount))}"><small>por ocorrência</small></div>
        <div class="bc-field"><label for="bc-base">Valor base</label><input id="bc-base" name="base_amount" type="number" min="0" step="any" value="${esc(inputValue(item.base_amount))}"><small>por ocorrência</small></div>
        <div class="bc-field"><label for="bc-favorable">Valor favorável</label><input id="bc-favorable" name="favorable_amount" type="number" min="0" step="any" value="${esc(inputValue(item.favorable_amount))}"><small>por ocorrência</small></div>
        <div class="bc-field"><label for="bc-committed">Comprometido</label><input id="bc-committed" name="committed_amount" type="number" min="0" step="any" value="${esc(inputValue(item.committed_amount))}"><small>acumulado e ainda não realizado</small></div>
        <div class="bc-field"><label for="bc-realized">Realizado</label><input id="bc-realized" name="realized_amount" type="number" min="0" step="any" value="${esc(inputValue(item.realized_amount))}"><small>acumulado observado</small></div>
        <div class="bc-field"><label for="bc-forecast">Projeção à conclusão</label><input id="bc-forecast" name="forecast_amount" type="number" min="0" step="any" value="${esc(inputValue(item.forecast_amount))}"><small>por ocorrência</small></div>
        <div class="bc-field"><label for="bc-planned-quantity">Quantidade prevista</label><input id="bc-planned-quantity" name="planned_quantity" type="number" min="0" step="any" value="${esc(inputValue(item.planned_quantity))}" ${item.amount_basis === "per_unit" ? "required" : ""}></div>
        <div class="bc-field"><label for="bc-actual-quantity">Quantidade realizada</label><input id="bc-actual-quantity" name="actual_quantity" type="number" min="0" step="any" value="${esc(inputValue(item.actual_quantity))}"></div>
        <div class="bc-field"><label for="bc-unit">Unidade desta linha</label><input id="bc-unit" name="unit" maxlength="80" value="${esc(item.unit || "")}" placeholder="Ex.: horas, unidades, kg"></div>
        <div class="bc-field"><label for="bc-recurrence">Periodicidade</label><select id="bc-recurrence" name="recurrence">${Object.entries(RECURRENCE_LABELS).map(([key, label]) => `<option value="${key}" ${item.recurrence === key ? "selected" : ""}>${label}</option>`).join("")}</select></div>
        <div class="bc-field"><label for="bc-start-month">Mês inicial</label><input id="bc-start-month" name="start_month" type="number" min="0" max="599" step="1" value="${esc(inputValue(item.start_month ?? 0))}"><small>0 = início da missão</small></div>
        <div class="bc-field"><label for="bc-end-month">Mês final</label><input id="bc-end-month" name="end_month" type="number" min="0" max="599" step="1" value="${esc(inputValue(item.end_month))}"><small>vazio = até ao horizonte</small></div>
        <div class="bc-field"><label for="bc-confidence">Confiança</label><select id="bc-confidence" name="confidence"><option value="low" ${item.confidence === "low" ? "selected" : ""}>Baixa</option><option value="moderate" ${item.confidence === "moderate" ? "selected" : ""}>Moderada</option><option value="high" ${item.confidence === "high" ? "selected" : ""}>Alta</option></select></div>
        <div class="bc-field full"><label for="bc-source">Origem do valor</label><input id="bc-source" name="source_label" maxlength="500" value="${esc(item.source_label || "")}" placeholder="Ex.: orçamento do fornecedor de 12/08/2026; estimativa da direção"></div>
        <div class="bc-field full"><label for="bc-evidence">Evidência da missão</label><select id="bc-evidence" name="evidence_node_id">${evidenceOptions(item.evidence_node_id || "")}</select></div>
        <div class="bc-field full"><label for="bc-assumption">Pressuposto ou limite</label><textarea id="bc-assumption" name="assumption" maxlength="3000" placeholder="Que hipótese sustenta este valor e em que condições deixa de ser válido?">${esc(item.assumption || "")}</textarea></div>
        <div class="bc-field full"><label for="bc-blocker">Bloqueio operacional</label><textarea id="bc-blocker" name="blocker" maxlength="3000" ${item.operational_status === "blocked" ? "required" : ""} placeholder="Obrigatório quando o recurso está bloqueado: o que falta, quem desbloqueia e que efeito pode ter?">${esc(item.blocker || "")}</textarea></div>
        <label class="bc-check bc-field full"><input name="include_in_totals" type="checkbox" ${item.include_in_totals ? "checked" : ""}><span><strong>Incluir nos totais monetários</strong><small>Desative se esta linha apenas descreve um recurso já contabilizado noutro custo, evitando dupla contagem.</small></span></label>
      </div>
      <div class="bc-actions"><button class="btn btn-primary" type="submit" ${saving ? "disabled" : ""}>${existing ? "Guardar alteração" : "Adicionar ao business case"}</button>${existing ? '<button class="btn btn-secondary" type="button" data-bc-cancel-edit>Cancelar edição</button>' : ""}</div>
    </form></div></details>`;
  }

  function lineRows() {
    const items = state.items || [];
    if (!items.length) return '<div class="bc-empty">Ainda não existem custos, benefícios ou recursos. A configuração por si só não produz um business case.</div>';
    return `<div class="bc-ledger">${items.map((item) => {
      const retirement = pendingRetirementId === item.id
        ? `<div class="bc-danger-confirm"><strong>Retirar esta linha?</strong><small>A revisão atual será invalidada, mas o registo permanece nas revisões históricas.</small><div class="bc-line-actions"><button class="btn btn-danger compact" type="button" data-bc-retire-confirm="${esc(item.id)}">Sim, retirar</button><button class="btn btn-secondary compact" type="button" data-bc-retire-cancel>Cancelar</button></div></div>`
        : `<div class="bc-line-actions"><button class="btn btn-secondary compact" type="button" data-bc-edit="${esc(item.id)}">Editar</button><button class="btn btn-secondary compact" type="button" data-bc-retire="${esc(item.id)}">Retirar</button></div>`;
      const scope = item.alternative_node_id ? `<span class="bc-scope">Alternativa · ${esc(item.alternative_label || "indisponível")}</span>` : '<span class="bc-scope">Missão</span>';
      const status = { planned: "planeado", committed: "comprometido", active: "em utilização", completed: "concluído", blocked: "bloqueado" }[item.operational_status] || item.operational_status;
      const blocked = item.operational_status === "blocked" ? `<small style="color:#a22b23"><strong>Bloqueio:</strong> ${esc(item.blocker || "não descrito")}</small>` : "";
      const confidence = { low: "baixa", moderate: "moderada", high: "alta" }[item.confidence] || item.confidence;
      return `<article class="bc-line"><div class="bc-line-main"><span class="bc-kind">${esc(KIND_LABELS[item.kind] || item.kind)}</span>${scope}<strong>${esc(item.label)}</strong><small>${esc(PHASE_LABELS[item.phase] || item.phase)} · ${esc(RECURRENCE_LABELS[item.recurrence] || item.recurrence)} · ${esc(status)} · confiança ${esc(confidence)}</small><small>${esc(item.source_label || item.evidence_label || "origem não declarada")}</small>${blocked}</div><div class="bc-line-value"><strong>${money(item.base_amount)}</strong><span>${item.amount_basis === "per_unit" ? "base / unidade" : "base / ocorrência"}</span></div><div class="bc-line-value"><strong>${money(item.realized_amount)}</strong><span>realizado acumulado</span></div><div class="bc-line-value"><strong>${item.kind === "human_resource" ? `${number(item.actual_quantity)} ${esc(item.unit || "")}` : money(item.forecast_amount)}</strong><span>${item.kind === "human_resource" ? "esforço observado" : "projeção"}</span></div>${retirement}</article>`;
    }).join("")}</div>`;
  }

  function reviewCard() {
    const readiness = state.readiness || {};
    const checks = (readiness.checks || []).map((check) => `<div class="bc-check-row ${check.passed ? "passed" : ""}"><span>${check.passed ? "✓" : "○"}</span><div><strong>${esc(check.label)}</strong>${check.blocking && !check.passed ? "<small>Obrigatório para revisão</small>" : ""}</div></div>`).join("");
    return `<section class="bc-card bc-review"><div class="card-head"><div><h4>Revisão humana e integridade</h4><p class="bc-muted">Qualquer alteração posterior retira automaticamente o estado revisto.</p></div><span class="pill">${readiness.completed_checks || 0}/${readiness.total_checks || 0}</span></div><div class="bc-readiness">${checks}</div><form id="bc-review-form" style="margin-top:14px"><div class="bc-field"><label for="bc-review-rationale">Racional da revisão</label><textarea id="bc-review-rationale" name="rationale" minlength="5" maxlength="5000" required placeholder="Explique por que os pressupostos, fontes, horizonte e limites são adequados para esta decisão.">${esc(state.case.review_rationale || "")}</textarea></div><div class="bc-actions"><button class="btn btn-primary" type="submit" ${!readiness.ready_for_review || saving ? "disabled" : ""}>Confirmar revisão humana</button><span class="bc-muted">${readiness.ready_for_review ? "A revisão confirma o modelo; não garante que as previsões se concretizem." : "Complete os requisitos obrigatórios antes de rever."}</span></div></form><p class="bc-integrity">${state.integrity_verified ? "Integridade da revisão atual verificada" : "Revisão atual ainda sem integridade confirmada"} · revisão ${Number(state.case.revision || 0)} · SHA-256 ${esc(state.case.content_hash || "a sincronizar")}</p></section>`;
  }

  function render() {
    const node = root();
    if (!node || !state) return;
    const current = state.case || {};
    const metrics = state.metrics || {};
    const quality = state.quality || {};
    const qualityKnown = Number(quality.monetary_line_count || 0) > 0;
    const qualityScore = qualityKnown ? Number(quality.overall_score || 0) : 0;
    const economicDataPresent = metricKnown("any_lines");
    const profitLabel = metrics.profit_applicable ? "Lucro projetado" : "Benefício líquido projetado";
    const revision = current.id ? `Revisão ${current.revision} · ${current.status === "reviewed" ? "revista" : "viva / por rever"}` : "Ainda não iniciado";
    const warnings = (state.warnings || []).length
      ? `<div class="bc-warnings">${state.warnings.map((item) => `<div class="bc-warning ${esc(item.severity)}">${esc(item.message)}</div>`).join("")}</div>`
      : '<div class="bc-warning info">Sem alertas materiais no estado atual. Isto não substitui revisão financeira ou contabilística.</div>';
    const history = (state.history || []).length
      ? state.history.map((item) => `<div class="bc-history-row"><span><strong>Revisão ${item.revision}</strong> · ${esc(EVENT_LABELS[item.event_type] || item.event_type)}</span><span class="bc-muted">${item.created_at ? new Date(item.created_at).toLocaleString("pt-PT") : ""} · ${esc(String(item.content_hash || "").slice(0, 12))}…</span></div>`).join("")
      : '<div class="bc-muted">Ainda não existem revisões económicas.</div>';
    const roi = !metricKnown("forecast_financial") || metrics.forecast_roi_pct == null ? "—" : `${metricNumber(metrics.forecast_roi_pct,2,"forecast_financial")}%`;
    const payback = !metricKnown("forecast_financial") || metrics.forecast_payback_months == null ? "—" : `${metricNumber(metrics.forecast_payback_months,0,"forecast_financial")} meses`;
    const schedule = !metricKnown("schedule") || metrics.schedule_variance_days == null ? "—" : `${metrics.schedule_variance_days > 0 ? "+" : ""}${number(metrics.schedule_variance_days, 0)} dias`;
    const executiveKpiList = [
      kpi("Orçamento base", metricMoney(metrics.budget_base, "budget_base")),
      kpi("Custo comprometido", metricMoney(metrics.committed_cost, "committed_cost")),
      kpi("Custo realizado", metricMoney(metrics.realized_cost, "realized_cost")),
      kpi("Custo previsto à conclusão", metricMoney(metrics.forecast_cost_at_completion, "forecast_cost")),
      kpi("Desvio de custo", metricMoney(metrics.cost_variance, "cost_variance"), !metricKnown("cost_variance") || metrics.cost_variance_pct == null ? "" : `${number(metrics.cost_variance_pct, 1)}%`),
      kpi("Benefício esperado", metricMoney(metrics.expected_gross_benefit, "expected_benefit")),
      kpi("Benefício realizado", metricMoney(metrics.realized_benefit, "realized_benefit")),
      kpi("Benefício com evidência revista", metricMoney(metrics.reviewed_evidence_realized_benefit, "reviewed_evidence_realized_benefit"), !metricKnown("reviewed_evidence_realized_benefit") ? "ainda não apurado" : "fonte aceite ou verificada"),
      kpi(profitLabel, metricMoney(metrics.forecast_net_benefit, "forecast_financial")),
      kpi("ROI projetado", roi),
      kpi("Prazo de recuperação", payback),
      kpi("Lacuna para equilíbrio", metricMoney(metrics.break_even_gap, "break_even_gap")),
      kpi("Horas humanas", metricNumber(metrics.actual_human_hours, 1, "actual_human_hours"), !metricKnown("planned_human_hours") ? "planeamento por determinar" : `${metricNumber(metrics.planned_human_hours,1,"planned_human_hours")} previstas`),
      kpi("Recursos bloqueados", metricNumber(metrics.blocked_resource_count, 0, "resources")),
      kpi("Custo por resultado", metricMoney(metrics.cost_per_actual_outcome ?? metrics.cost_per_planned_outcome, "cost_per_outcome"), current.outcome_unit || "unidade por definir"),
      kpi("Desvio de prazo", schedule, !metricKnown("schedule") || metrics.schedule_variance_pct == null ? "" : `${number(metrics.schedule_variance_pct, 1)}%`),
      kpi("Encargo anual posterior", metricMoney(metrics.annual_post_mission_burden, "post_mission_costs")),
      kpi("Financiamento identificado", metricMoney(metrics.funding_available, "funding")),
      kpi("Lacuna de financiamento", metricMoney(metrics.funding_gap, "funding_gap")),
    ];
    const primaryKpiIndexes = new Set([2, 3, 5, 6, 8, 9]);
    const executiveKpis = executiveKpiList.filter((_, index) => primaryKpiIndexes.has(index)).join("");
    const secondaryKpis = executiveKpiList.filter((_, index) => !primaryKpiIndexes.has(index)).join("");
    const executiveReading = economicDataPresent
      ? `<div class="bc-kpis">${executiveKpis}</div><details class="bc-metric-details"><summary>Ver indicadores complementares (${executiveKpiList.length-primaryKpiIndexes.size})</summary><div class="bc-kpis">${secondaryKpis}</div></details>`
      : '<div class="bc-empty">Ainda não existem linhas económicas ou de recursos para apurar indicadores. Os valores permanecem por determinar — não são zero.</div>';
    const caseBadge = current.id
      ? `${esc(current.currency || "EUR")} · ${Number(current.horizon_months)} meses`
      : "Configuração por confirmar";
    const qualitySummary = qualityKnown
      ? `<p>Confiança declarada ${number(quality.confidence_score, 0)}% · origem ${number(quality.source_coverage_pct, 0)}% · evidência ${number(quality.evidence_coverage_pct, 0)}%.</p>`
      : "<p>A qualidade ainda não é avaliável porque não existem valores monetários. Ausência de dados não corresponde a 0%.</p>";
    const configuredSections = current.id ? [
      `<section class="bc-card"><div class="card-head"><div><h4>Livro económico e de recursos</h4><p class="bc-muted">Uma linha pode representar dinheiro, esforço humano, materiais, equipamento ou valor não monetizado.</p></div><span class="pill">${state.mission_item_count || 0} missão · ${state.alternative_item_count || 0} alternativas</span></div>${itemForm()}<div style="margin-top:16px">${lineRows()}</div></section>`,
      economicDataPresent ? `<section class="bc-card"><div class="card-head"><div><h4>Cenários e retorno da missão</h4><p class="bc-muted">O valor base é usado apenas quando uma linha não explicita o cenário conservador ou favorável.</p></div></div>${scenarioTable()}</section>` : "",
      (state.alternative_comparison?.profiles || []).length ? `<section class="bc-card"><div class="card-head"><div><h4>Economia comparada das alternativas</h4><p class="bc-muted">Custo total, recursos, benefício provável e retorno calculados sob o mesmo horizonte.</p></div><span class="pill">${state.alternative_comparison?.complete_profile_count || 0}/${state.alternative_comparison.profiles.length} completos</span></div>${alternativeTable()}</section>` : "",
      `<section class="bc-card"><div class="bc-quality"><div class="bc-quality-score" style="--score:${qualityScore}"><strong>${qualityKnown ? `${number(qualityScore, 0)}%` : "—"}</strong><span>qualidade</span></div><div><h4>Qualidade dos dados económicos da missão</h4>${qualitySummary}<p class="bc-muted">A pontuação mede completude e rastreabilidade; não transforma estimativas em factos.</p></div></div></section>`,
      reviewCard(),
      `<section class="bc-card"><h4>Histórico económico preservado</h4><div class="bc-history">${history}</div></section>`,
    ].filter(Boolean).join("") : "";
    node.innerHTML = `
      <section class="bc-hero"><div><span class="product-index">BUSINESS CASE VIVO · CÁLCULO DETERMINÍSTICO</span><h3>Quanto custa. Que valor cria. O que permanece.</h3><p>Custos, benefícios, tempo, pessoas, financiamento e materiais acompanhados antes, durante e depois da missão. Valores não monetizáveis permanecem quantificados sem receber um preço artificial.</p></div><span class="bc-revision">${esc(revision)}</span></section>
      <div id="business-case-status" class="bc-status" role="status" aria-live="polite"></div>
      <section class="bc-card"><div class="card-head"><div><h4>Leitura executiva</h4><p class="bc-muted">Previsto, comprometido, realizado e projetado não são misturados. “—” significa não apurado, nunca zero.</p></div><span class="pill">${caseBadge}</span></div>${executiveReading}<div class="bc-conclusion"><strong>Conclusão automática auditável</strong><br>${esc(state.executive_conclusion || "Ainda sem dados suficientes.")}</div></section>
      ${warnings}
      <section class="bc-card"><div class="card-head"><div><h4>Fundação do business case</h4><p class="bc-muted">A situação de partida e o cenário de não agir impedem que qualquer benefício seja atribuído automaticamente à missão.</p></div></div>${current.id ? "" : governedPrefillSummary()}${caseForm()}</section>
      ${configuredSections}
    `;
  }

  function nullableNumber(form, name) {
    const raw = form.elements.namedItem(name)?.value?.trim();
    return raw === "" || raw == null ? null : Number(raw);
  }

  function nullableDate(form, name) {
    return form.elements.namedItem(name)?.value || null;
  }

  function casePayload(form) {
    return {
      expected_revision: Number(state.case?.revision || 0),
      case_kind: form.case_kind.value,
      currency: form.currency.value.trim().toUpperCase(),
      horizon_months: Number(form.horizon_months.value),
      discount_rate_pct: Number(form.discount_rate_pct.value),
      decision_context: form.decision_context.value.trim(),
      baseline: form.baseline.value.trim(),
      counterfactual: form.counterfactual.value.trim(),
      planned_start_date: nullableDate(form, "planned_start_date"),
      planned_end_date: nullableDate(form, "planned_end_date"),
      forecast_end_date: nullableDate(form, "forecast_end_date"),
      actual_start_date: nullableDate(form, "actual_start_date"),
      actual_end_date: nullableDate(form, "actual_end_date"),
      outcome_name: form.outcome_name.value.trim(),
      outcome_unit: form.outcome_unit.value.trim(),
      planned_outcome_quantity: nullableNumber(form, "planned_outcome_quantity"),
      actual_outcome_quantity: nullableNumber(form, "actual_outcome_quantity"),
      notes: form.notes.value.trim(),
    };
  }

  function itemPayload(form) {
    return {
      expected_revision: Number(state.case.revision),
      kind: form.kind.value,
      financial_treatment: form.financial_treatment.value,
      category: form.category.value.trim(),
      label: form.label.value.trim(),
      description: form.description.value.trim(),
      phase: form.phase.value,
      unit: form.unit.value.trim(),
      amount_basis: form.amount_basis.value,
      planned_quantity: nullableNumber(form, "planned_quantity"),
      actual_quantity: nullableNumber(form, "actual_quantity"),
      conservative_amount: nullableNumber(form, "conservative_amount"),
      base_amount: nullableNumber(form, "base_amount"),
      favorable_amount: nullableNumber(form, "favorable_amount"),
      committed_amount: nullableNumber(form, "committed_amount"),
      realized_amount: nullableNumber(form, "realized_amount"),
      forecast_amount: nullableNumber(form, "forecast_amount"),
      start_month: Number(form.start_month.value || 0),
      end_month: nullableNumber(form, "end_month"),
      recurrence: form.recurrence.value,
      source_label: form.source_label.value.trim(),
      evidence_node_id: form.evidence_node_id.value || null,
      alternative_node_id: form.alternative_node_id.value || null,
      responsible: form.responsible.value.trim(),
      operational_status: form.operational_status.value,
      blocker: form.blocker.value.trim(),
      assumption: form.assumption.value.trim(),
      confidence: form.confidence.value,
      include_in_totals: form.include_in_totals.checked,
    };
  }

  function acceptResponse(payload, message) {
    state = payload;
    editingItemId = "";
    pendingRetirementId = "";
    // Successful responses are rendered immediately.  Clear the busy flag
    // first so the freshly rendered controls do not remain disabled until a
    // full page reload.
    saving = false;
    render();
    setStatus(message, "success");
    document.dispatchEvent(new CustomEvent("sris:business-case-updated", { detail: state }));
  }

  function applyGovernedPrefill() {
    const form = document.querySelector("#bc-case-form");
    const fields = state?.governed_prefill?.fields || {};
    if (!form) return;
    let applied = 0;
    Object.entries(fields).forEach(([name, proposal]) => {
      const control = form.elements.namedItem(name);
      const value = proposal?.value;
      if (!control || value === null || value === undefined || value === "") return;
      if (String(control.value || "").trim()) return;
      control.value = /_date$/.test(name) ? String(value).slice(0, 10) : String(value);
      applied += 1;
    });
    if (applied) {
      const advanced = form.querySelector(".bc-advanced");
      if (advanced) advanced.open = true;
    }
    setStatus(
      applied
        ? `${applied} proposta${applied === 1 ? "" : "s"} aplicada${applied === 1 ? "" : "s"} ao formulário. Reveja antes de guardar; nada foi persistido.`
        : "Não existem novas propostas governadas para aplicar. Complete os campos em falta com fontes e pressupostos explícitos.",
      applied ? "warning" : "",
    );
  }

  async function load(code) {
    const requested = String(code || "").trim();
    if (!requested) return;
    const sequence = ++loadSequence;
    currentMissionCode = requested;
    state = null;
    editingItemId = "";
    pendingRetirementId = "";
    if (root()) root().innerHTML = '<div class="note">A sincronizar o business case vivo…</div>';
    try {
      const payload = await api(`/api/pilot/business-cases/missions/${encodeURIComponent(requested)}`);
      if (sequence !== loadSequence || requested !== currentMissionCode) return;
      state = payload;
      render();
    } catch (error) {
      if (sequence !== loadSequence) return;
      if (root()) root().innerHTML = `<div class="alert error">Não foi possível carregar o business case: ${esc(error.message)}</div>`;
    }
  }

  document.addEventListener("submit", async (event) => {
    if (event.target.id === "bc-case-form") {
      event.preventDefault();
      if (saving) return;
      saving = true;
      setStatus("A guardar a configuração e a recalcular o business case…");
      try {
        const payload = await api(`/api/pilot/business-cases/missions/${encodeURIComponent(missionCode())}`, { method: "PUT", body: JSON.stringify(casePayload(event.target)) });
        acceptResponse(payload, "Configuração guardada e indicadores recalculados no servidor.");
      } catch (error) {
        setStatus(error.message, "error");
      } finally {
        saving = false;
      }
    }
    if (event.target.id === "bc-item-form") {
      event.preventDefault();
      if (saving) return;
      saving = true;
      const itemId = event.target.dataset.itemId;
      setStatus(itemId ? "A atualizar a linha económica…" : "A adicionar a linha económica…");
      try {
        const url = itemId ? `/api/pilot/business-cases/missions/${encodeURIComponent(missionCode())}/items/${encodeURIComponent(itemId)}` : `/api/pilot/business-cases/missions/${encodeURIComponent(missionCode())}/items`;
        const payload = await api(url, { method: itemId ? "PATCH" : "POST", body: JSON.stringify(itemPayload(event.target)) });
        acceptResponse(payload, itemId ? "Linha atualizada; a revisão anterior foi invalidada." : "Linha adicionada e business case recalculado.");
      } catch (error) {
        setStatus(error.message, "error");
      } finally {
        saving = false;
      }
    }
    if (event.target.id === "bc-review-form") {
      event.preventDefault();
      if (saving) return;
      saving = true;
      setStatus("A registar a revisão humana e a calcular a nova assinatura…");
      try {
        const payload = await api(`/api/pilot/business-cases/missions/${encodeURIComponent(missionCode())}/review`, { method: "POST", body: JSON.stringify({ expected_revision: Number(state.case.revision), rationale: event.target.rationale.value.trim() }) });
        acceptResponse(payload, "Business case revisto e integridade confirmada.");
      } catch (error) {
        setStatus(error.message, "error");
      } finally {
        saving = false;
      }
    }
  });

  document.addEventListener("change", (event) => {
    if (event.target.id === "bc-item-kind") {
      const treatment = document.querySelector("#bc-treatment");
      const forced = KIND_TREATMENT[event.target.value];
      if (treatment) {
        treatment.value = forced || FLEXIBLE_KIND_DEFAULT[event.target.value] || "none";
        treatment.disabled = Boolean(forced);
      }
    }
    if (event.target.id === "bc-amount-basis") {
      const quantity = document.querySelector("#bc-planned-quantity");
      if (quantity) quantity.required = event.target.value === "per_unit";
    }
    if (event.target.id === "bc-operational-status") {
      const blocker = document.querySelector("#bc-blocker");
      if (blocker) blocker.required = event.target.value === "blocked";
    }
  });

  document.addEventListener("click", async (event) => {
    if (event.target.closest("[data-bc-apply-prefill]")) {
      applyGovernedPrefill();
      return;
    }
    const edit = event.target.closest("[data-bc-edit]");
    if (edit) {
      editingItemId = edit.dataset.bcEdit;
      pendingRetirementId = "";
      render();
      document.querySelector("#bc-item-form")?.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    if (event.target.closest("[data-bc-cancel-edit]")) {
      editingItemId = "";
      render();
      return;
    }
    const retire = event.target.closest("[data-bc-retire]");
    if (retire) {
      pendingRetirementId = retire.dataset.bcRetire;
      render();
      return;
    }
    if (event.target.closest("[data-bc-retire-cancel]")) {
      pendingRetirementId = "";
      render();
      return;
    }
    const confirmRetire = event.target.closest("[data-bc-retire-confirm]");
    if (confirmRetire && !saving) {
      saving = true;
      const itemId = confirmRetire.dataset.bcRetireConfirm;
      setStatus("A retirar a linha e a preservar a versão anterior no histórico…");
      try {
        const payload = await api(`/api/pilot/business-cases/missions/${encodeURIComponent(missionCode())}/items/${encodeURIComponent(itemId)}?expected_revision=${encodeURIComponent(state.case.revision)}`, { method: "DELETE" });
        acceptResponse(payload, "Linha retirada; a versão anterior permanece no histórico auditável.");
      } catch (error) {
        setStatus(error.message, "error");
      } finally {
        saving = false;
      }
    }
  });

  document.addEventListener("sris:mission-opened", (event) => {
    const code = event.detail?.mission?.code;
    if (code) void load(code);
  });

  document.addEventListener("sris:alternative-matrix-updated", () => {
    if (currentMissionCode) void load(currentMissionCode);
  });

  document.addEventListener("sris:evidence-graph-updated", () => {
    if (currentMissionCode && document.querySelector(`#mission-tab-${TAB}`)?.classList.contains("active")) {
      void load(currentMissionCode);
    }
  });

  document.addEventListener("sris:validation-updated", () => {
    if (currentMissionCode) void load(currentMissionCode);
  });

  document.addEventListener("click", (event) => {
    const opener = event.target.closest('[data-open-mission-tab="economics"], [data-mission-tab="economics"]');
    if (opener) window.setTimeout(() => load(missionCode()), 0);
  });

  installStyles();
  installTab();
  document.addEventListener("DOMContentLoaded", () => {
    installStyles();
    installTab();
    const code = missionCode();
    if (code) void load(code);
  }, { once: true });
})();
