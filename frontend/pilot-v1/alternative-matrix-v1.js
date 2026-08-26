(function () {
  "use strict";

  const TAB = "comparison";
  const CRITERION_ORDER = [
    "efficacy",
    "cost",
    "risk",
    "reversibility",
    "guest_experience",
    "evidence_robustness",
  ];
  const CRITERION_FALLBACKS = {
    efficacy: {
      key: "efficacy",
      label: "Eficácia",
      description: "Capacidade esperada para produzir o resultado definido.",
      scale_hint: "1 = eficácia muito baixa · 5 = eficácia muito alta",
    },
    cost: {
      key: "cost",
      label: "Custo",
      description: "Custo total de adoção, operação e manutenção.",
      scale_hint: "1 = custo muito elevado · 5 = custo muito favorável",
    },
    risk: {
      key: "risk",
      label: "Risco",
      description: "Exposição operacional, financeira, legal e reputacional.",
      scale_hint: "1 = risco muito elevado · 5 = risco muito controlado",
    },
    reversibility: {
      key: "reversibility",
      label: "Reversibilidade",
      description: "Facilidade de interromper, corrigir ou reverter a alternativa.",
      scale_hint: "1 = dificilmente reversível · 5 = facilmente reversível",
    },
    guest_experience: {
      key: "guest_experience",
      label: "Impacto no utilizador / beneficiário",
      description: "Efeito previsível nas pessoas, entidades ou comunidades que recebem o resultado.",
      scale_hint: "1 = impacto muito negativo · 5 = impacto muito positivo",
    },
    evidence_robustness: {
      key: "evidence_robustness",
      label: "Robustez da evidência",
      description: "Qualidade, proveniência e suficiência da evidência disponível.",
      scale_hint: "1 = evidência muito frágil · 5 = evidência muito robusta",
    },
  };
  let state = null;
  let currentMissionCode = "";
  let loading = false;
  let addingAlternative = false;
  let removingAlternative = false;
  let pendingRemovalId = "";

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
    const currentToken = localStorage.getItem("sris_access_token")
      || sessionStorage.getItem("sris_access_token");
    if (currentToken) headers.Authorization = `Bearer ${currentToken}`;
    const response = await fetch(path, {
      ...options,
      credentials: "same-origin",
      headers,
      cache: "no-store",
    });
    const payload = await response.json().catch(() => ({}));
    if (response.status === 401) {
      [localStorage, sessionStorage].forEach((storage) => {
        storage.removeItem("sris_access_token");
        storage.removeItem("sris_refresh_token");
      });
      location.href = "/";
      throw new Error("Sessão expirada.");
    }
    if (!response.ok) {
      const detail = payload && payload.detail;
      const message = typeof detail === "string"
        ? detail
        : (detail && (detail.message || detail.code)) || `Pedido recusado (${response.status}).`;
      throw new Error(message);
    }
    return payload;
  }

  function missionCode() {
    const raw = (document.querySelector("#detail-code")?.textContent || "").trim();
    const parts = raw.split("/").map((item) => item.trim()).filter(Boolean);
    return parts[parts.length - 1] || raw;
  }

  function root() {
    return document.querySelector("#alternative-matrix-root");
  }

  function setStatus(message, tone) {
    const node = document.querySelector("#alternative-matrix-status");
    if (!node) return;
    node.className = `alternative-matrix-status ${tone || ""}`.trim();
    node.textContent = message || "";
  }

  function installStyles() {
    if (document.querySelector("#alternative-matrix-styles")) return;
    const style = document.createElement("style");
    style.id = "alternative-matrix-styles";
    style.textContent = `
      .alternative-matrix-root .sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
      .alternative-matrix-root{display:grid;gap:18px}.alternative-matrix-hero{background:linear-gradient(135deg,#073d31,#17644f);color:#fff;border-radius:24px;padding:28px;display:flex;justify-content:space-between;gap:20px;align-items:flex-start}.alternative-matrix-hero h3{font-family:inherit;font-size:clamp(28px,4vw,46px);line-height:1.02;margin:8px 0}.alternative-matrix-hero p{max-width:780px;color:#e6f0ec;margin:0}.alternative-matrix-revision{border:1px solid rgba(255,255,255,.38);border-radius:999px;padding:10px 14px;white-space:nowrap;font-weight:800}.alternative-matrix-card{border:1px solid #cfdbd6;border-radius:20px;padding:20px;background:#fff}.alternative-matrix-card h4{margin:0 0 8px}.alternative-matrix-status{min-height:24px;color:#4e645c}.alternative-matrix-status.success{color:#176a4d}.alternative-matrix-status.error{color:#a22b23}.alternative-matrix-status.warning{color:#886516}.alternative-matrix-controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center}.alternative-matrix-controls .btn{margin:0}.alternative-matrix-weights{display:grid;grid-template-columns:repeat(6,minmax(118px,1fr));gap:10px;margin-top:14px}.alternative-matrix-weight{border:1px solid #d6dfdb;border-radius:14px;padding:10px}.alternative-matrix-weight label{display:block;font-size:12px;font-weight:800;min-height:32px}.alternative-matrix-weight input{width:100%;margin-top:6px}.alternative-matrix-weight-total{font-weight:800}.alternative-matrix-weight-total.invalid{color:#a22b23}.alternative-matrix-scroller{overflow-x:auto;padding-bottom:5px}.alternative-matrix-table{border-collapse:separate;border-spacing:0;width:100%;min-width:760px}.alternative-matrix-table th,.alternative-matrix-table td{border-right:1px solid #d9e1de;border-bottom:1px solid #d9e1de;padding:12px;vertical-align:top}.alternative-matrix-table th{background:#f4f7f5;text-align:left}.alternative-matrix-table tr:first-child th{border-top:1px solid #d9e1de}.alternative-matrix-table th:first-child,.alternative-matrix-table td:first-child{border-left:1px solid #d9e1de;position:sticky;left:0;background:#fff;z-index:1;min-width:180px}.alternative-matrix-table tr:first-child th:first-child{background:#f4f7f5;z-index:2;border-top-left-radius:12px}.alternative-matrix-table tr:first-child th:last-child{border-top-right-radius:12px}.alternative-matrix-table select{min-width:118px;width:100%}.alternative-matrix-scale{display:block;font-size:11px;color:#667a72;margin-top:5px}.alternative-matrix-contribution{display:block;font-size:11px;color:#a07617;margin-top:6px}.alternative-matrix-rationales{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:16px}.alternative-matrix-rationales details{border:1px solid #d5dfdb;border-radius:16px;padding:14px}.alternative-matrix-rationales summary{cursor:pointer;font-weight:800}.alternative-matrix-rationale{padding:14px 0;border-top:1px solid #e2e8e5}.alternative-matrix-rationale:first-of-type{margin-top:12px}.alternative-matrix-rationale textarea,.alternative-matrix-rationale select{width:100%;margin-top:7px}.alternative-matrix-rationale textarea{min-height:92px}.alternative-matrix-ranking{display:grid;gap:10px}.alternative-matrix-rank{display:grid;grid-template-columns:48px 1fr auto;gap:12px;align-items:center;border:1px solid #d4dfda;border-radius:14px;padding:12px}.alternative-matrix-rank strong:first-child{font-size:24px;color:#b98620}.alternative-matrix-rank-score{font-size:22px;font-weight:900}.alternative-matrix-criterion-chips{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}.alternative-matrix-criterion-chips span{font-size:11px;background:#eef4f1;border-radius:999px;padding:4px 7px}.alternative-matrix-add{display:grid;grid-template-columns:minmax(180px,1fr) minmax(240px,2fr) auto;gap:10px;align-items:end}.alternative-matrix-history{display:grid;gap:8px}.alternative-matrix-history-row{display:flex;justify-content:space-between;gap:12px;border-top:1px solid #e1e7e4;padding-top:10px}.alternative-matrix-empty{border:1px dashed #bdcbc5;border-radius:14px;padding:18px;color:#5b7068}.alternative-matrix-explanation{background:#f5f8f6;border-radius:14px;padding:12px;margin-top:12px;color:#52665e}.alternative-matrix-root input,.alternative-matrix-root textarea,.alternative-matrix-root select{border:1px solid #cbd7d2;border-radius:10px;padding:10px;background:#fff;color:#092c23}.alternative-matrix-root textarea{resize:vertical}.alternative-matrix-root label{color:#183d32}.alternative-matrix-root .product-index{color:#d5a844}.alternative-matrix-root .note{color:#62766e}.alternative-matrix-root .eyebrow{letter-spacing:.18em}.alternative-matrix-root button:disabled{opacity:.55;cursor:not-allowed}.alternative-matrix-duplicate{display:grid;gap:7px;margin-top:10px;padding:9px;border:1px solid #e4c989;border-radius:10px;background:#fff9e9}.alternative-matrix-duplicate-actions{display:flex;flex-wrap:wrap;gap:6px}.alternative-matrix-duplicate button{font:inherit;border-radius:8px;padding:6px 9px;cursor:pointer}.alternative-matrix-remove{border:1px solid #a94b42;background:#fff;color:#842c25}.alternative-matrix-cancel{border:1px solid #b9c8c2;background:#fff;color:#244b40}
      .alternative-matrix-total-row th,.alternative-matrix-total-row td{background:#edf4f1;font-weight:900}.alternative-matrix-live-total{font-size:20px;color:#17644f}.alternative-matrix-economic-status{border-left:4px solid #b98620;background:#fff9e9;border-radius:10px;padding:10px 12px;margin-top:12px}.alternative-matrix-economic-status.current{border-left-color:#17644f;background:#edf6f1}.alternative-matrix-economic-gaps{display:block;color:#93651c;font-size:11px;margin-top:5px}
      @media(max-width:980px){.alternative-matrix-weights{grid-template-columns:repeat(3,1fr)}.alternative-matrix-rationales{grid-template-columns:1fr}.alternative-matrix-add{grid-template-columns:1fr}.alternative-matrix-hero{display:block}.alternative-matrix-revision{display:inline-block;margin-top:16px}}
      @media(max-width:620px){.alternative-matrix-card{padding:15px}.alternative-matrix-hero{padding:22px 18px;border-radius:18px}.alternative-matrix-weights{grid-template-columns:repeat(2,1fr)}.alternative-matrix-rank{grid-template-columns:38px 1fr}.alternative-matrix-rank-score{grid-column:2}.alternative-matrix-table th:first-child,.alternative-matrix-table td:first-child{min-width:142px}.alternative-matrix-history-row{display:grid}}
    `;
    document.head.appendChild(style);
  }

  function installTab() {
    const tabs = document.querySelector("#mission-detail .mission-tabs");
    const detail = document.querySelector("#mission-detail");
    if (!tabs || !detail || tabs.querySelector(`[data-mission-tab="${TAB}"]`)) return;
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.missionTab = TAB;
    button.textContent = "Comparação";
    const anchor = tabs.querySelector('[data-mission-tab="validation"], [data-mission-tab="history"]');
    tabs.insertBefore(button, anchor || null);
    const panel = document.createElement("div");
    panel.className = "mission-tab";
    panel.id = `mission-tab-${TAB}`;
    panel.innerHTML = '<div id="alternative-matrix-root" class="alternative-matrix-root"><div class="note">A sincronizar a matriz de alternativas…</div></div>';
    const history = detail.querySelector("#mission-tab-history");
    detail.insertBefore(panel, history || null);
  }

  function criteria() {
    const byKey = new Map((state?.criteria || []).map((item) => [item.key, item]));
    return CRITERION_ORDER.map((key) => byKey.get(key) || CRITERION_FALLBACKS[key]);
  }

  function assessmentIndex() {
    const index = new Map();
    for (const evaluation of state?.matrix?.evaluations || []) {
      const scoreIndex = new Map((evaluation.scores || []).map((item) => [item.criterion, item]));
      index.set(evaluation.alternative_node_id, scoreIndex);
    }
    return index;
  }

  function weightValue(key) {
    const value = state?.matrix?.weights?.[key] ?? state?.default_weights?.[key] ?? 0;
    return Number(value) || 0;
  }

  function evidenceOptions(selected) {
    return ['<option value="">Sem evidência específica</option>'].concat(
      (state?.evidence || []).map((item) => `<option value="${esc(item.id)}" ${item.id === selected ? "selected" : ""}>${esc(item.label)}</option>`)
    ).join("");
  }

  function scoreOptions(selected) {
    return [1, 2, 3, 4, 5].map((score) => `<option value="${score}" ${Number(selected) === score ? "selected" : ""}>${score}</option>`).join("");
  }

  function economicMoney(value) {
    if (value === null || value === undefined || value === "") return "—";
    const currency = state?.economic_comparison?.currency || "EUR";
    return Number(value).toLocaleString("pt-PT", { style: "currency", currency, maximumFractionDigits: 0 });
  }

  function economicComparisonTable() {
    const economics = state?.economic_comparison || {};
    if (!economics.configured) {
      return '<div class="alternative-matrix-empty">O Business Case Vivo ainda não foi iniciado. A pontuação de custo pode ser justificada qualitativamente, mas ainda não existe comparação económica por alternativa.</div>';
    }
    const profiles = economics.profiles || [];
    if (!profiles.length) {
      return '<div class="alternative-matrix-empty">Ainda não existem alternativas económicas para comparar.</div>';
    }
    const rows = profiles.map((profile) => {
      const resources = profile.resources || {};
      const resourceText = [
        resources.planned_human_hours ? `${Number(resources.planned_human_hours).toLocaleString("pt-PT")} h` : "",
        resources.material_lines ? `${resources.material_lines} materiais` : "",
        resources.equipment_lines ? `${resources.equipment_lines} equipamentos` : "",
      ].filter(Boolean).join(" · ") || "—";
      const gaps = profile.gaps?.length ? `<span class="alternative-matrix-economic-gaps">Falta: ${esc(profile.gaps.join(", "))}</span>` : "";
      return `<tr><th scope="row"><strong>${esc(profile.alternative_label)}</strong>${gaps}</th><td>${economicMoney(profile.total_cost)}</td><td>${esc(resourceText)}</td><td>${economicMoney(profile.probable_gross_benefit)}</td><td>${economicMoney(profile.probable_net_benefit)}</td><td>${profile.roi_pct == null ? "—" : `${Number(profile.roi_pct).toLocaleString("pt-PT", { maximumFractionDigits: 2 })}%`}</td><td>${profile.payback_months == null ? "—" : `${Number(profile.payback_months).toLocaleString("pt-PT")} meses`}</td><td>${Number(profile.quality?.overall_score || 0).toLocaleString("pt-PT", { maximumFractionDigits: 0 })}%</td></tr>`;
    }).join("");
    return `<div class="alternative-matrix-scroller"><table class="alternative-matrix-table"><thead><tr><th>Alternativa</th><th>Custo total</th><th>Recursos</th><th>Benefício provável</th><th>Benefício líquido</th><th>ROI</th><th>Payback</th><th>Qualidade</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  }

  function render() {
    const node = root();
    if (!node || !state) return;
    const criterionList = criteria();
    const alternatives = state.alternatives || [];
    const existing = assessmentIndex();
    const revision = state.matrix
      ? `Revisão ${state.matrix.revision} · ${state.matrix.status === "reviewed" ? "revista" : "rascunho"}${state.matrix.integrity_verified ? "" : " · integridade inválida"}`
      : "Sem revisão guardada";
    const tableHead = alternatives.map((alternative) => {
      const duplicateControl = alternative.duplicate_of_id
        ? `<div class="alternative-matrix-duplicate"><span>Duplicado exato detetado.</span>${pendingRemovalId === alternative.id ? `<span class="alternative-matrix-scale">Confirmar retirada? A cópia original permanece ativa e esta fica preservada no histórico.</span><div class="alternative-matrix-duplicate-actions"><button class="alternative-matrix-remove" type="button" data-acm-remove-confirm="${esc(alternative.id)}" ${removingAlternative ? "disabled" : ""}>Sim, retirar duplicado</button><button class="alternative-matrix-cancel" type="button" data-acm-remove-cancel>Cancelar</button></div>` : `<button class="alternative-matrix-remove" type="button" data-acm-remove="${esc(alternative.id)}">Retirar duplicado</button>`}</div>`
        : "";
      return `<th scope="col"><strong>${esc(alternative.label)}</strong><span class="alternative-matrix-scale">${esc(alternative.body || "Sem descrição")}</span>${duplicateControl}</th>`;
    }).join("");
    const tableRows = criterionList.map((criterion) => {
      const cells = alternatives.map((alternative) => {
        const saved = existing.get(alternative.id)?.get(criterion.key);
        const selected = saved?.score || 3;
        return `<td><label class="sr-only" for="acm-score-${esc(alternative.id)}-${esc(criterion.key)}">${esc(criterion.label)} · ${esc(alternative.label)}</label><select id="acm-score-${esc(alternative.id)}-${esc(criterion.key)}" data-acm-score data-alt="${esc(alternative.id)}" data-criterion="${esc(criterion.key)}">${scoreOptions(selected)}</select><span class="alternative-matrix-contribution" data-acm-contribution data-alt="${esc(alternative.id)}" data-criterion="${esc(criterion.key)}"></span></td>`;
      }).join("");
      return `<tr><th scope="row"><strong>${esc(criterion.label)}</strong><span class="alternative-matrix-scale">${esc(criterion.scale_hint)}</span></th>${cells}</tr>`;
    }).join("");
    const totalCells = alternatives.map((alternative) => `<td><span class="alternative-matrix-live-total" data-acm-live-total data-alt="${esc(alternative.id)}">—</span><span class="alternative-matrix-scale">pontos ponderados</span></td>`).join("");
    const rationaleEditors = alternatives.map((alternative, altIndex) => {
      const blocks = criterionList.map((criterion) => {
        const saved = existing.get(alternative.id)?.get(criterion.key);
        return `<div class="alternative-matrix-rationale"><label for="acm-rationale-${esc(alternative.id)}-${esc(criterion.key)}"><strong>${esc(criterion.label)}</strong></label><span class="alternative-matrix-scale">${esc(criterion.description)}</span><textarea id="acm-rationale-${esc(alternative.id)}-${esc(criterion.key)}" data-acm-rationale data-alt="${esc(alternative.id)}" data-criterion="${esc(criterion.key)}" maxlength="3000" placeholder="Justifique a pontuação com limites, pressupostos e factos relevantes.">${esc(saved?.rationale || "")}</textarea><label for="acm-evidence-${esc(alternative.id)}-${esc(criterion.key)}" class="alternative-matrix-scale">Evidência que sustenta esta avaliação (opcional)</label><select id="acm-evidence-${esc(alternative.id)}-${esc(criterion.key)}" data-acm-evidence data-alt="${esc(alternative.id)}" data-criterion="${esc(criterion.key)}">${evidenceOptions(saved?.evidence_node_id || "")}</select></div>`;
      }).join("");
      return `<details ${altIndex === 0 ? "open" : ""}><summary>${esc(alternative.label)} · justificações e evidência</summary>${blocks}</details>`;
    }).join("");
    const weightEditors = criterionList.map((criterion) => `<div class="alternative-matrix-weight"><label for="acm-weight-${esc(criterion.key)}">${esc(criterion.label)}</label><input id="acm-weight-${esc(criterion.key)}" data-acm-weight data-criterion="${esc(criterion.key)}" type="number" min="0" max="100" step="1" value="${weightValue(criterion.key)}"><span class="alternative-matrix-scale">peso %</span></div>`).join("");
    const ranking = (state.ranking || []).length
      ? (state.ranking || []).map((item) => `<div class="alternative-matrix-rank"><strong>${item.position}</strong><div><strong>${esc(item.alternative_label)}</strong><div class="alternative-matrix-criterion-chips">${criterionList.map((criterion) => `<span>${esc(criterion.label)} ${esc(item.scores[criterion.key])}/5</span>`).join("")}</div></div><span class="alternative-matrix-rank-score">${Number(item.weighted_score).toFixed(1)}</span></div>`).join("")
      : '<div class="alternative-matrix-empty">Guarde uma revisão completa para obter a ordenação determinística. A ordenação informa; não decide.</div>';
    const history = (state.history || []).length
      ? state.history.map((item) => `<div class="alternative-matrix-history-row"><span><strong>Revisão ${item.revision}</strong> · ${esc(item.status === "reviewed" ? "revista" : "rascunho")} · ${item.alternative_count} alternativas</span><span class="note">hash ${esc(String(item.content_hash || "").slice(0, 12))}… · ${item.integrity_verified ? "verificado" : "inválido"}</span></div>`).join("")
      : '<div class="note">Ainda não existem revisões.</div>';
    const economicAlignment = state.economic_alignment || {};
    const economicAlignmentTone = economicAlignment.up_to_date ? "current" : "";
    node.innerHTML = `
      <section class="alternative-matrix-hero"><div><span class="product-index">COMPARAÇÃO MULTICRITÉRIO · SEM IA</span><h3>Comparar antes de decidir.</h3><p>Seis critérios canónicos, pesos explícitos, justificação humana e evidência por avaliação. O cálculo é reproduzível e a decisão continua a pertencer à pessoa responsável.</p></div><span class="alternative-matrix-revision">${esc(revision)}</span></section>
      <div id="alternative-matrix-status" class="alternative-matrix-status ${state.matrix && !state.matrix.integrity_verified ? "error" : ""}" role="status" aria-live="polite">${state.matrix && !state.matrix.integrity_verified ? "A revisão persistida não coincide com o respetivo snapshot e hash. A ordenação foi bloqueada; guarde uma nova revisão íntegra." : ""}</div>
      <section class="alternative-matrix-card"><div class="card-head"><div><h4>Alternativas da missão</h4><p class="note">As alternativas pertencem ao grafo canónico da missão; não são cópias locais da matriz. Duplicados exatos podem ser retirados sem apagar o histórico.</p></div><span class="pill">${alternatives.length} disponíveis</span></div><form id="alternative-matrix-add" class="alternative-matrix-add"><div class="field"><label for="acm-new-title">Título</label><input id="acm-new-title" required minlength="3" placeholder="Ex.: Redutores de caudal reguláveis"></div><div class="field"><label for="acm-new-body">Descrição</label><input id="acm-new-body" required minlength="5" placeholder="Âmbito, diferença material e condição de aplicação"></div><button id="alternative-matrix-add-submit" class="btn btn-secondary" type="submit" ${addingAlternative ? "disabled" : ""}>${addingAlternative ? "A adicionar…" : "Adicionar alternativa"}</button></form></section>
      <section class="alternative-matrix-card"><div class="card-head"><div><h4>Economia e recursos por alternativa</h4><p class="note">Valores vivos do business case: custo total, recursos necessários, benefício provável e retorno. Não substituem a avaliação multicritério.</p></div><span class="pill">${state.economic_comparison?.complete_profile_count || 0}/${state.economic_comparison?.profiles?.length || 0} completos</span></div>${economicComparisonTable()}<div class="alternative-matrix-economic-status ${economicAlignmentTone}">${esc(economicAlignment.message || "A sincronizar a revisão económica usada pela matriz.")}</div><div class="alternative-matrix-controls" style="margin-top:12px"><button class="btn btn-secondary" type="button" data-open-mission-tab="economics">Abrir Business Case Vivo</button></div></section>
      <section class="alternative-matrix-card"><div class="card-head"><div><h4>Pesos da decisão</h4><p class="note">A soma tem de ser 100%. Os pesos fazem parte de cada revisão e ficam sujeitos a auditoria.</p></div><span id="alternative-matrix-weight-total" class="alternative-matrix-weight-total"></span></div><div class="alternative-matrix-weights">${weightEditors}</div></section>
      <section class="alternative-matrix-card"><div class="card-head"><div><h4>Matriz de pontuação</h4><p class="note">Escala 1–5 orientada para valor. Em custo e risco, 5 representa a condição mais favorável.</p></div><span class="pill">20–100 pontos</span></div>${alternatives.length ? `<div class="alternative-matrix-scroller"><table class="alternative-matrix-table"><thead><tr><th scope="col">Critério</th>${tableHead}</tr></thead><tbody>${tableRows}<tr class="alternative-matrix-total-row"><th scope="row">Pontuação total</th>${totalCells}</tr></tbody></table></div><div class="alternative-matrix-rationales">${rationaleEditors}</div>` : '<div class="alternative-matrix-empty">Adicione pelo menos duas alternativas para iniciar a comparação.</div>'}<div class="alternative-matrix-explanation">Fórmula: soma(pontuação × peso) ÷ 5. Como a escala começa em 1, o resultado final varia entre 20 e 100 pontos. Desempate: robustez da evidência, eficácia e título. Nenhuma alternativa é selecionada automaticamente.</div><div class="alternative-matrix-controls" style="margin-top:14px"><button id="alternative-matrix-save" class="btn btn-primary" type="button" ${alternatives.length < 2 ? "disabled" : ""}>Guardar nova revisão</button><button id="alternative-matrix-review" class="btn btn-secondary" type="button" ${!state.matrix || !state.readiness?.passed || state.matrix.status === "reviewed" ? "disabled" : ""}>Confirmar revisão humana</button></div></section>
      <section class="alternative-matrix-card"><div class="card-head"><div><h4>Ordenação transparente</h4><p class="note">Resultado da última revisão guardada.</p></div><span class="pill">${state.readiness?.passed ? "comparação completa" : "incompleta"}</span></div><div class="alternative-matrix-ranking">${ranking}</div></section>
      <details class="alternative-matrix-card"><summary><strong>Histórico imutável e hashes</strong></summary><div class="alternative-matrix-history" style="margin-top:14px">${history}</div></details>
    `;
    bind();
    updateLiveCalculations();
  }

  function findField(kind, alternativeId, criterionKey) {
    return Array.from(document.querySelectorAll(`[data-acm-${kind}]`)).find((item) => item.dataset.alt === alternativeId && item.dataset.criterion === criterionKey);
  }

  function weightsFromForm() {
    const weights = {};
    document.querySelectorAll("[data-acm-weight]").forEach((input) => {
      weights[input.dataset.criterion] = input.value === "" ? 0 : Number(input.value);
    });
    return weights;
  }

  function updateLiveCalculations() {
    const weights = weightsFromForm();
    const total = Object.values(weights).reduce((sum, value) => sum + value, 0);
    const totalNode = document.querySelector("#alternative-matrix-weight-total");
    if (totalNode) {
      totalNode.textContent = `${total}%`;
      totalNode.classList.toggle("invalid", total !== 100);
    }
    for (const alternative of state?.alternatives || []) {
      let weightedTotal = 0;
      for (const criterion of criteria()) {
        const scoreNode = findField("score", alternative.id, criterion.key);
        const contributionNode = findField("contribution", alternative.id, criterion.key);
        if (scoreNode && contributionNode) {
          const contribution = (Number(scoreNode.value) * (weights[criterion.key] || 0)) / 5;
          weightedTotal += contribution;
          contributionNode.textContent = `${contribution.toFixed(1)} pontos ponderados`;
        }
      }
      const liveTotal = Array.from(document.querySelectorAll("[data-acm-live-total]"))
        .find((item) => item.dataset.alt === alternative.id);
      if (liveTotal) liveTotal.textContent = weightedTotal.toFixed(1);
    }
  }

  function buildPayload() {
    const weights = weightsFromForm();
    if (Object.values(weights).some((value) => !Number.isInteger(value) || value < 0 || value > 100)) {
      throw new Error("Cada peso deve ser um número inteiro entre 0 e 100%.");
    }
    if (Object.values(weights).reduce((sum, value) => sum + value, 0) !== 100) {
      throw new Error("A soma dos seis pesos tem de ser exatamente 100%.");
    }
    if ((state?.alternatives || []).length < 2) {
      throw new Error("Adicione pelo menos duas alternativas comparáveis.");
    }
    const evaluations = (state.alternatives || []).map((alternative) => ({
      alternative_node_id: alternative.id,
      scores: criteria().map((criterion) => {
        const score = findField("score", alternative.id, criterion.key);
        const rationale = findField("rationale", alternative.id, criterion.key);
        const evidence = findField("evidence", alternative.id, criterion.key);
        const rationaleValue = (rationale?.value || "").trim();
        if (rationaleValue.length < 2) {
          throw new Error(`Justifique ${criterion.label.toLowerCase()} para “${alternative.label}”.`);
        }
        return {
          criterion: criterion.key,
          score: Number(score?.value || 0),
          rationale: rationaleValue,
          evidence_node_id: evidence?.value || null,
        };
      }),
    }));
    return { weights, evaluations };
  }

  async function save() {
    try {
      const payload = buildPayload();
      setStatus("A guardar uma revisão imutável da matriz…", "");
      state = await api(`/api/pilot/alternative-matrices/missions/${encodeURIComponent(currentMissionCode)}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      render();
      setStatus(`Revisão ${state.matrix.revision} guardada com hash ${String(state.matrix.content_hash).slice(0, 12)}…`, "success");
      document.dispatchEvent(new CustomEvent("sris:alternative-matrix-updated", { detail: state }));
    } catch (error) {
      setStatus(error.message, "error");
    }
  }

  async function review() {
    try {
      setStatus("A registar a revisão humana…", "");
      state = await api(`/api/pilot/alternative-matrices/missions/${encodeURIComponent(currentMissionCode)}/review`, { method: "POST" });
      render();
      setStatus(`Revisão ${state.matrix.revision} confirmada por uma pessoa autorizada.`, "success");
      document.dispatchEvent(new CustomEvent("sris:alternative-matrix-updated", { detail: state }));
    } catch (error) {
      setStatus(error.message, "error");
    }
  }

  async function addAlternative(event) {
    event.preventDefault();
    if (addingAlternative) return;
    const title = (document.querySelector("#acm-new-title")?.value || "").trim();
    const body = (document.querySelector("#acm-new-body")?.value || "").trim();
    if (title.length < 3 || body.length < 5) {
      setStatus("Indique um título e uma descrição material para a alternativa.", "error");
      return;
    }
    addingAlternative = true;
    const submit = document.querySelector("#alternative-matrix-add-submit");
    if (submit) {
      submit.disabled = true;
      submit.textContent = "A adicionar…";
    }
    try {
      setStatus("A adicionar a alternativa ao grafo da missão…", "");
      state = await api(`/api/pilot/alternative-matrices/missions/${encodeURIComponent(currentMissionCode)}/alternatives`, {
        method: "POST",
        body: JSON.stringify({ title, body }),
      });
      const created = state.alternative_change?.created !== false;
      addingAlternative = false;
      render();
      setStatus(created ? `Alternativa “${title}” adicionada.` : `A alternativa “${title}” já existia e não foi duplicada.`, created ? "success" : "warning");
      if (created) document.dispatchEvent(new CustomEvent("sris:evidence-graph-updated"));
    } catch (error) {
      addingAlternative = false;
      if (submit) {
        submit.disabled = false;
        submit.textContent = "Adicionar alternativa";
      }
      setStatus(error.message, "error");
    }
  }

  function requestDuplicateRemoval(alternativeId) {
    pendingRemovalId = alternativeId;
    render();
    setStatus("Confirme a retirada da cópia duplicada. A alternativa original será mantida.", "warning");
  }

  function cancelDuplicateRemoval() {
    pendingRemovalId = "";
    render();
    setStatus("Retirada cancelada.", "");
  }

  async function removeDuplicate(alternativeId) {
    if (removingAlternative || pendingRemovalId !== alternativeId) return;
    removingAlternative = true;
    render();
    setStatus("A retirar a cópia duplicada e a preservar o registo histórico…", "");
    try {
      state = await api(`/api/pilot/alternative-matrices/missions/${encodeURIComponent(currentMissionCode)}/alternatives/${encodeURIComponent(alternativeId)}/duplicate`, { method: "DELETE" });
      pendingRemovalId = "";
      removingAlternative = false;
      render();
      setStatus("Duplicado retirado. A alternativa original permanece ativa e o histórico foi preservado.", "success");
      document.dispatchEvent(new CustomEvent("sris:evidence-graph-updated"));
      document.dispatchEvent(new CustomEvent("sris:alternative-matrix-updated", { detail: state }));
    } catch (error) {
      removingAlternative = false;
      render();
      setStatus(error.message, "error");
    }
  }

  function bind() {
    document.querySelector("#alternative-matrix-add")?.addEventListener("submit", addAlternative);
    document.querySelectorAll("[data-acm-remove]").forEach((button) => button.addEventListener("click", () => requestDuplicateRemoval(button.dataset.acmRemove)));
    document.querySelectorAll("[data-acm-remove-confirm]").forEach((button) => button.addEventListener("click", () => removeDuplicate(button.dataset.acmRemoveConfirm)));
    document.querySelectorAll("[data-acm-remove-cancel]").forEach((button) => button.addEventListener("click", cancelDuplicateRemoval));
    document.querySelector("#alternative-matrix-save")?.addEventListener("click", save);
    document.querySelector("#alternative-matrix-review")?.addEventListener("click", review);
    document.querySelectorAll("[data-acm-score], [data-acm-weight]").forEach((node) => node.addEventListener("input", updateLiveCalculations));
  }

  async function load(code, force) {
    const resolved = code || missionCode();
    if (!resolved || resolved === "MISSÃO" || loading) return;
    if (!force && state && resolved === currentMissionCode) {
      render();
      return;
    }
    currentMissionCode = resolved;
    loading = true;
    if (root()) root().innerHTML = '<div class="note">A sincronizar alternativas, critérios, pesos e revisões…</div>';
    try {
      state = await api(`/api/pilot/alternative-matrices/missions/${encodeURIComponent(resolved)}`);
      render();
    } catch (error) {
      if (root()) root().innerHTML = `<div class="alternative-matrix-status error">${esc(error.message)}</div>`;
    } finally {
      loading = false;
    }
  }

  function activate() {
    installTab();
    document.querySelectorAll("#mission-detail .mission-tabs [data-mission-tab]").forEach((item) => item.classList.toggle("active", item.dataset.missionTab === TAB));
    document.querySelectorAll("#mission-detail .mission-tab").forEach((item) => item.classList.toggle("active", item.id === `mission-tab-${TAB}`));
    load(missionCode(), true);
  }

  document.addEventListener("DOMContentLoaded", () => {
    installStyles();
    installTab();
  });
  document.addEventListener("click", (event) => {
    const opener = event.target.closest('[data-open-mission-tab="comparison"]');
    if (opener) {
      event.preventDefault();
      activate();
      return;
    }
    const tab = event.target.closest('[data-mission-tab="comparison"]');
    if (tab) window.setTimeout(() => load(missionCode(), true), 0);
  });
  document.addEventListener("sris:mission-opened", () => {
    state = null;
    currentMissionCode = missionCode();
    installTab();
  });
  document.addEventListener("sris:evidence-graph-updated", () => {
    if (document.querySelector(`#mission-tab-${TAB}`)?.classList.contains("active")) load(missionCode(), true);
  });
  document.addEventListener("sris:business-case-updated", () => {
    if (document.querySelector(`#mission-tab-${TAB}`)?.classList.contains("active")) load(missionCode(), true);
  });

  window.__srisAlternativeMatrix = { load, activate, get state() { return state; } };
})();
