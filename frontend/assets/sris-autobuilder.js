(() => {
  "use strict";

  const CONFIG_URL = "/assets/sris-platform-content.json";
  const DEFAULT_MISSION = "M-001";
  const BUILD = "1.2.0";

  let config = null;
  let activeMissionId =
    sessionStorage.getItem("sris_active_mission") || DEFAULT_MISSION;

  const esc = (value) =>
    String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");

  const qs = (selector, root = document) => root.querySelector(selector);
  const qsa = (selector, root = document) => [...root.querySelectorAll(selector)];

  function missionById(id) {
    return config?.missions?.[id] || null;
  }

  function missionOptions({ includeAll = false } = {}) {
    const items = Object.values(config?.missions || {});
    return `${includeAll ? '<option value="all">Todas as missões</option>' : ""}${items
      .map((m) => `<option value="${esc(m.id)}">${esc(m.id)} — ${esc(m.title)}</option>`)
      .join("")}`;
  }

  function injectStyles() {
    document.getElementById("sris-stabilization-styles")?.remove();

    const style = document.createElement("style");
    style.id = "sris-consolidation-styles";
    style.textContent = `
      .sris-mission-context{
        margin:0 0 22px;padding:16px 18px;display:flex;align-items:end;
        justify-content:space-between;gap:18px;border:1px solid var(--border);
        border-radius:var(--radius-small);background:rgba(255,255,255,.72)
      }
      .sris-mission-context .field{margin:0;min-width:min(520px,100%)}
      .sris-mission-context-copy{
        color:var(--ink-soft);font-size:12px;line-height:1.55;max-width:650px
      }
      .sris-impact-block{margin-top:34px}
      .sris-impact-block:first-of-type{margin-top:0}
      .sris-impact-grid{
        display:grid;grid-template-columns:repeat(3,minmax(0,1fr));
        gap:16px;margin-top:18px
      }
      .sris-impact-card{
        min-height:150px;padding:20px;border:1px solid var(--border);
        border-radius:var(--radius);background:var(--surface);box-shadow:var(--shadow)
      }
      .sris-impact-index{
        margin-bottom:18px;font-size:10px;font-weight:800;
        letter-spacing:.14em;color:var(--gold)
      }
      .sris-impact-card h3{
        margin:0 0 10px;font-family:Georgia,serif;font-weight:400;font-size:22px
      }
      .sris-impact-card p{
        margin:0;color:var(--ink-soft);line-height:1.6;font-size:13px
      }

      .sris-recognition-grid{
        display:grid;grid-template-columns:repeat(3,minmax(0,1fr));
        gap:16px;margin-top:18px
      }
      .sris-recognition-card{
        overflow:hidden;border:1px solid var(--border);border-radius:var(--radius);
        background:var(--surface);box-shadow:var(--shadow)
      }
      .sris-recognition-status{
        padding:16px 18px 0;font-size:9px;font-weight:800;
        letter-spacing:.14em;color:var(--ink-muted)
      }
      .sris-recognition-media{
        width:calc(100% - 36px);height:210px;margin:12px 18px 0;padding:0;
        display:grid;place-items:center;border:1px solid var(--border);
        border-radius:12px;background:#fff;cursor:zoom-in;overflow:hidden
      }
      .sris-recognition-media img{
        display:block;width:100%;height:100%;object-fit:contain;padding:8px
      }
      .sris-recognition-copy{padding:18px}
      .sris-recognition-copy h3{
        margin:0 0 8px;font-family:Georgia,serif;font-weight:400;font-size:21px
      }
      .sris-recognition-copy p{
        margin:0;color:var(--ink-soft);font-size:12px;line-height:1.6
      }

      .sris-lightbox{
        position:fixed;inset:0;z-index:9999;display:grid;place-items:center;
        padding:28px;background:rgba(8,14,11,.84);backdrop-filter:blur(10px)
      }
      .sris-lightbox.hidden{display:none!important}
      .sris-lightbox-panel{
        position:relative;width:min(1040px,94vw);max-height:92vh;padding:18px;
        display:grid;place-items:center;border-radius:18px;background:#fff;
        box-shadow:0 30px 100px rgba(0,0,0,.35)
      }
      .sris-lightbox-panel img{max-width:100%;max-height:78vh;object-fit:contain}
      .sris-lightbox-caption{
        width:100%;padding:12px 6px 2px;text-align:center;color:var(--ink);
        font-weight:700
      }
      .sris-lightbox-close{
        position:absolute;top:10px;right:10px;width:38px;height:38px;border:0;
        border-radius:50%;background:rgba(24,34,29,.92);color:#fff;
        font-size:24px;line-height:1;z-index:2
      }

      .sris-filterbar{
        margin:0 0 18px;padding:14px 16px;display:flex;align-items:center;gap:14px;
        border:1px solid var(--border);border-radius:var(--radius-small);
        background:rgba(255,255,255,.7)
      }
      .sris-filterbar label{
        font-size:11px;font-weight:800;color:var(--ink-soft)
      }
      .sris-filterbar select{
        min-width:280px;height:40px;padding:0 12px;border:1px solid var(--border-strong);
        border-radius:10px;background:#fff
      }
      .sris-mission-tag{
        display:inline-block;margin-bottom:8px;padding:4px 7px;border-radius:999px;
        background:var(--sage-soft);color:var(--forest);font-size:9px;
        font-weight:800;letter-spacing:.08em
      }
      .sris-empty{
        padding:38px 24px;border:1px dashed var(--border-strong);
        border-radius:var(--radius);text-align:center;color:var(--ink-muted)
      }

      @media(max-width:900px){
        .sris-impact-grid,.sris-recognition-grid{grid-template-columns:1fr}
        .sris-mission-context{align-items:stretch;flex-direction:column}
        .sris-filterbar{align-items:stretch;flex-direction:column}
        .sris-filterbar select{width:100%;min-width:0}
      }
    `;
    document.head.appendChild(style);
  }

  function consolidateLegacyShell() {
    const positioning = config?.platform?.positioning || {};

    const loginEyebrow = qs("#loginScreen .login-statement .eyebrow");
    if (loginEyebrow) {
      loginEyebrow.textContent =
        positioning.eyebrow || "Inteligência para decisões complexas";
    }

    const loginHeadline = qs("#loginScreen .login-statement h1");
    if (loginHeadline && positioning.headline) {
      loginHeadline.textContent = positioning.headline;
    }

    const loginDescription = qs("#loginScreen .login-statement p");
    if (loginDescription && positioning.description) {
      loginDescription.textContent = positioning.description;
    }

    qsa('option[value="CA-AWARDS-APPLICATION"]').forEach((option) => {
      option.value = "CA-AWARD-APPLICATION";
    });

    // Any legacy impact/recognition block is never allowed outside page-impact.
    qsa(".recognition-section").forEach((el) => el.remove());
    qsa("#sris-differentiation,#sris-market,#sris-sustainability").forEach((el) =>
      el.remove()
    );

    const statusVersion = qs(".system-status-top strong");
    if (statusVersion) statusVersion.textContent = "v1.2";
  }

  function ensureImpactNavigation() {
    const nav = qs(".sidebar nav");
    if (!nav) return;

    if (!qs('[data-page="impact"]', nav)) {
      const label = document.createElement("div");
      label.className = "nav-group-label";
      label.textContent = "Produto";

      const button = document.createElement("button");
      button.className = "nav-item";
      button.dataset.page = "impact";
      button.innerHTML = '<span class="nav-icon">◆</span><span>Impacto</span>';

      nav.append(label, button);
    }
  }

  function ensureImpactPage() {
    let page = qs("#page-impact");

    if (!page) {
      const main = qs(".main-area");
      if (!main) return;

      page = document.createElement("section");
      page.id = "page-impact";
      page.className = "page";
      page.innerHTML = `
        <div class="hero">
          <div class="hero-copy">
            <div class="eyebrow">Produto e impacto</div>
            <h1>${esc(config.platform.impact.headline)}</h1>
            <p>${esc(config.platform.impact.description)}</p>
          </div>
        </div>
        <div id="sris-impact-content"></div>
      `;
      main.appendChild(page);
    }

    if (!qs("#sris-impact-content", page)) {
      page.insertAdjacentHTML("beforeend", '<div id="sris-impact-content"></div>');
    }

    renderImpact();
  }

  function renderImpactCards(cards = []) {
    return `<div class="sris-impact-grid">${cards
      .map(
        (card) => `
          <article class="sris-impact-card">
            <div class="sris-impact-index">${esc(card.index)}</div>
            <h3>${esc(card.title)}</h3>
            <p>${esc(card.description)}</p>
          </article>`
      )
      .join("")}</div>`;
  }

  function renderImpact() {
    const root = qs("#sris-impact-content");
    const impact = config?.platform?.impact;
    if (!root || !impact) return;

    const recognition = impact.recognition || {};

    root.innerHTML = `
      <section class="sris-impact-block">
        <div class="page-section-title">
          <div class="eyebrow">Diferenciação</div>
          <h2>${esc(impact.differentiation.headline)}</h2>
          <p>${esc(impact.differentiation.description)}</p>
        </div>
      </section>

      <section class="sris-impact-block">
        <div class="page-section-title">
          <div class="eyebrow">Escalabilidade</div>
          <h2>${esc(impact.market.headline)}</h2>
          <p>${esc(impact.market.description)}</p>
        </div>
        ${renderImpactCards(impact.market.cards)}
      </section>

      <section class="sris-impact-block">
        <div class="page-section-title">
          <div class="eyebrow">Impacto e sustentabilidade</div>
          <h2>${esc(impact.sustainability.headline)}</h2>
          <p>${esc(impact.sustainability.description)}</p>
        </div>
        ${renderImpactCards(impact.sustainability.cards)}
      </section>

      <section class="sris-impact-block">
        <div class="page-section-title">
          <div class="eyebrow">Reconhecimento externo</div>
          <h2>${esc(recognition.headline)}</h2>
          <p>${esc(recognition.description)}</p>
        </div>

        <div class="sris-recognition-grid">
          ${(recognition.items || [])
            .map(
              (item) => `
                <article class="sris-recognition-card">
                  <div class="sris-recognition-status">${esc(item.status)}</div>
                  <button
                    class="sris-recognition-media"
                    type="button"
                    data-lightbox-src="${esc(item.image)}"
                    data-lightbox-alt="${esc(item.alt)}"
                    data-lightbox-title="${esc(item.title)}"
                    aria-label="Ampliar ${esc(item.title)}"
                  >
                    <img src="${esc(item.image)}" alt="${esc(item.alt)}" />
                  </button>
                  <div class="sris-recognition-copy">
                    <h3>${esc(item.title)}</h3>
                    <p>${esc(item.description)}</p>
                  </div>
                </article>`
            )
            .join("")}
        </div>
      </section>
    `;
  }

  function ensureLightbox() {
    if (qs("#sris-lightbox")) return;

    const box = document.createElement("div");
    box.id = "sris-lightbox";
    box.className = "sris-lightbox hidden";
    box.setAttribute("aria-hidden", "true");
    box.innerHTML = `
      <div class="sris-lightbox-panel" role="dialog" aria-modal="true">
        <button class="sris-lightbox-close" type="button" aria-label="Fechar">×</button>
        <img id="sris-lightbox-image" alt="" />
        <div id="sris-lightbox-caption" class="sris-lightbox-caption"></div>
      </div>
    `;
    document.body.appendChild(box);

    const close = () => {
      box.classList.add("hidden");
      box.setAttribute("aria-hidden", "true");
      document.body.style.overflow = "";
    };

    box.addEventListener("click", (event) => {
      if (event.target === box || event.target.closest(".sris-lightbox-close")) {
        close();
      }
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !box.classList.contains("hidden")) close();
    });
  }

  function openLightbox(trigger) {
    const box = qs("#sris-lightbox");
    if (!box) return;

    const img = qs("#sris-lightbox-image");
    const caption = qs("#sris-lightbox-caption");

    img.src = trigger.dataset.lightboxSrc;
    img.alt =
      trigger.dataset.lightboxAlt || trigger.dataset.lightboxTitle || "";
    caption.textContent = trigger.dataset.lightboxTitle || "";

    box.classList.remove("hidden");
    box.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
  }

  function navigate(pageName) {
    const target = qs(`#page-${pageName}`);
    if (!target) return;

    qsa(".page").forEach((page) => {
      page.classList.toggle("active", page === target);
    });

    qsa(".nav-item").forEach((item) => {
      item.classList.toggle("active", item.dataset.page === pageName);
    });

    const labels = config?.platform?.positioning?.topbar || {};
    const current = labels[pageName] || ["SRIS", "Mission Intelligence"];

    if (qs("#topbarTitle")) qs("#topbarTitle").textContent = current[0];
    if (qs("#topbarSubtitle")) qs("#topbarSubtitle").textContent = current[1];

    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function ensureSituationSelector() {
    const page = qs("#page-overview");
    const chain = qs(".decision-chain", page);
    if (!page || !chain || qs("#srisSituationMission")) return;

    const wrap = document.createElement("div");
    wrap.className = "sris-mission-context";
    wrap.innerHTML = `
      <div class="field">
        <label for="srisSituationMission">Missão ativa</label>
        <select id="srisSituationMission">${missionOptions()}</select>
      </div>
      <div id="srisSituationSummary" class="sris-mission-context-copy"></div>
    `;
    chain.before(wrap);
  }

  function renderSituation() {
    const mission = missionById(activeMissionId);
    const page = qs("#page-overview");
    if (!mission || !page) return;

    ensureSituationSelector();

    if (qs("#srisSituationMission")) {
      qs("#srisSituationMission").value = activeMissionId;
    }

    if (qs("#srisSituationSummary")) {
      qs("#srisSituationSummary").textContent = mission.situation?.summary || "";
    }

    const chain = qs(".decision-chain", page);
    if (chain) {
      chain.innerHTML = (mission.situation?.chain || [])
        .map(
          (item) => `
            <article class="chain-card ${esc(item.state || "")}">
              <div class="chain-number">${esc(item.number)}</div>
              <div class="chain-label">${esc(item.label)}</div>
              <div class="chain-value">${esc(item.value)}</div>
              <div class="chain-note">${esc(item.note)}</div>
            </article>`
        )
        .join("");
    }

    const attention = qs(".attention-list", page);
    if (attention) {
      attention.innerHTML = (mission.situation?.attention || [])
        .map(
          (item) => `
            <div class="attention-item">
              <strong>${esc(item.title)}</strong>
              <p>${esc(item.description)}</p>
              <div class="attention-level">${esc(item.level)}</div>
            </div>`
        )
        .join("");
    }
  }

  function statusClass(status = "") {
    const s = status.toLowerCase();
    if (s.includes("preparação") || s.includes("avaliação")) {
      return "status-attention";
    }
    if (s.includes("identificada") || s.includes("conclu")) {
      return "status-stable";
    }
    return "status-stable";
  }

  function confidenceClass(confidence = "") {
    const c = confidence.toLowerCase();
    if (c.includes("elev")) return "trend-improving";
    if (c.includes("moder")) return "trend-stable";
    return "trend-deteriorating";
  }

  function renderMissionLists() {
    const missions = Object.values(config?.missions || {});

    qsa(".mission-list").forEach((list) => {
      list.innerHTML = missions
        .map(
          (m) => `
            <button
              class="mission-row mission-open"
              type="button"
              data-mission-id="${esc(m.id)}"
            >
              <div>
                <div class="mission-title">${esc(m.title)}</div>
                <div class="mission-meta">${esc(m.id)} · ${esc(
            m.meta || m.subtitle
          )}</div>
              </div>
              <div>
                <span class="status-badge ${statusClass(m.status)}">${esc(
            m.status
          )}</span>
              </div>
              <div>
                <strong class="${confidenceClass(
                  m.confidence
                )}">Confiança ${esc(String(m.confidence).toLowerCase())}</strong>
              </div>
              <div class="row-arrow">›</div>
            </button>`
        )
        .join("");
    });
  }

  function renderMissionModal(mission) {
    const modal = qs("#missionModal");
    if (!modal || !mission) return;

    const result = mission.analysis?.result;

    if (qs("#missionModalEyebrow")) {
      qs("#missionModalEyebrow").textContent = `Missão ${mission.id}`;
    }
    if (qs("#missionModalTitle")) {
      qs("#missionModalTitle").textContent = mission.title;
    }
    if (qs("#missionModalSubtitle")) {
      qs("#missionModalSubtitle").textContent = mission.subtitle;
    }
    if (qs("#missionModalContent")) {
      qs("#missionModalContent").innerHTML = `
        <div class="mission-detail-status">
          <article><span>Estado</span><strong>${esc(mission.status)}</strong></article>
          <article><span>Confiança</span><strong>${esc(
            mission.confidence
          )}</strong></article>
          <article><span>Decisão</span><strong>${esc(
            mission.decision
          )}</strong></article>
        </div>

        <section class="mission-detail-section">
          <h3>Contexto</h3>
          <p>${esc(mission.analysis?.context || "")}</p>
        </section>

        <section class="mission-detail-section">
          <h3>Questão central</h3>
          <p>${esc(mission.analysis?.central_question || "")}</p>
        </section>

        <section class="mission-detail-section">
          <h3>Próxima decisão</h3>
          <p>${esc(result?.next_decision || mission.decision)}</p>
        </section>
      `;
    }

    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
  }

  function populateWorkspaceSelect() {
    const select = qs("#analysisMission");
    if (!select) return;

    select.innerHTML = missionOptions();
    select.value = missionById(activeMissionId)
      ? activeMissionId
      : DEFAULT_MISSION;
  }

  function setField(id, value) {
    const el = document.getElementById(id);
    if (el) el.value = value ?? "";
  }

  function renderResult(result) {
    const root = qs("#resultBlock");
    if (!root || !result) return;

    const alternatives = (result.alternatives || [])
      .map(
        (a) => `
          <li>
            <strong>${esc(a.id)} — ${esc(a.title)}</strong><br>
            ${esc(a.description)}
          </li>`
      )
      .join("");

    root.innerHTML = `
      <div class="result-hero">
        <small>Resultado reconstruído</small>
        <h3>${esc(result.headline)}</h3>
        <p>${esc(result.summary)}</p>
      </div>

      <div class="result-section">
        <strong>Situação</strong>
        <p>${esc(result.situation)}</p>
      </div>

      <div class="result-section">
        <strong>Risco principal</strong>
        <p>${esc(result.principal_risk)}</p>
      </div>

      <div class="result-section">
        <strong>Pressupostos a testar</strong>
        <ul>${(result.assumptions || [])
          .map((x) => `<li>${esc(x)}</li>`)
          .join("")}</ul>
      </div>

      <div class="result-section">
        <strong>Alternativas</strong>
        <ul>${alternatives}</ul>
      </div>

      <div class="result-section">
        <strong>Próxima decisão</strong>
        <p>${esc(result.next_decision)}</p>
      </div>

      <div class="result-section">
        <strong>Confiança atual</strong>
        <p>${esc(result.confidence)}</p>
      </div>
    `;
  }

  function renderWorkspace(id = activeMissionId) {
    const mission = missionById(id);
    if (!mission) return;

    activeMissionId = id;
    sessionStorage.setItem("sris_active_mission", id);

    const a = mission.analysis || {};

    setField("analysisTitle", a.title);
    setField("analysisContext", a.context);
    setField("analysisDecision", a.central_question);
    setField("analysisEvidence", a.available_evidence);
    setField("analysisUnknowns", a.unknowns);

    if (qs("#analysisMission")) qs("#analysisMission").value = id;

    if (qs("#outputPlaceholder")) {
      qs("#outputPlaceholder").classList.remove("hidden");
    }
    if (qs("#resultBlock")) {
      qs("#resultBlock").classList.remove("visible");
    }

    renderResult(a.result);
    renderSituation();
    syncFilters(id);
  }

  function setActiveMission(id, { syncWorkspace = true } = {}) {
    if (!missionById(id)) return;

    activeMissionId = id;
    sessionStorage.setItem("sris_active_mission", id);

    renderSituation();
    if (syncWorkspace) renderWorkspace(id);
    syncFilters(id);
  }

  function processActiveAnalysis() {
    const mission = missionById(
      qs("#analysisMission")?.value || activeMissionId
    );
    if (!mission) return;

    renderResult(mission.analysis?.result);

    if (qs("#outputPlaceholder")) {
      qs("#outputPlaceholder").classList.add("hidden");
    }
    if (qs("#resultBlock")) {
      qs("#resultBlock").classList.add("visible");
      qs("#resultBlock").scrollIntoView({
        behavior: "smooth",
        block: "start"
      });
    }
  }

  function ensureFilter(pageId, selectId, labelText) {
    const page = qs(pageId);
    const hero = qs(".hero", page);
    if (!page || !hero || qs(`#${selectId}`)) return;

    const bar = document.createElement("div");
    bar.className = "sris-filterbar";
    bar.innerHTML = `
      <label for="${selectId}">${esc(labelText)}</label>
      <select id="${selectId}">${missionOptions({ includeAll: true })}</select>
    `;
    hero.after(bar);
  }

  function renderEvidence(filter = activeMissionId) {
    const page = qs("#page-evidence");
    if (!page) return;

    ensureFilter(
      "#page-evidence",
      "srisEvidenceMission",
      "Filtrar evidência por missão"
    );

    const existing = qs(
      ".knowledge-grid,.empty-state,.sris-evidence-root",
      page
    );
    const root = existing?.classList.contains("sris-evidence-root")
      ? existing
      : document.createElement("div");

    if (!root.classList.contains("sris-evidence-root")) {
      root.className = "sris-evidence-root";
      existing?.replaceWith(root);
      if (!existing) page.appendChild(root);
    }

    const missions = Object.values(config.missions).filter(
      (m) => filter === "all" || m.id === filter
    );
    const items = missions.flatMap((m) =>
      (m.evidence || []).map((e) => ({ ...e, missionId: m.id }))
    );

    root.innerHTML = items.length
      ? `<div class="knowledge-grid">${items
          .map(
            (e) => `
              <article class="knowledge-card">
                <span class="sris-mission-tag">${esc(e.missionId)}</span>
                <div class="knowledge-type">${esc(e.id)} · ${esc(e.type)}</div>
                <h3>${esc(e.title)}</h3>
                <p>${esc(e.description)}</p>
                <div class="knowledge-footer">
                  <span>${esc(e.status)} · Confiança ${esc(e.confidence)}</span>
                  <span>${esc(e.source)}</span>
                </div>
              </article>`
          )
          .join("")}</div>`
      : '<div class="sris-empty">Não existem registos de evidência para este filtro.</div>';

    if (qs("#srisEvidenceMission")) {
      qs("#srisEvidenceMission").value = filter;
    }
  }

  function renderLearning(filter = activeMissionId) {
    const page = qs("#page-learning");
    if (!page) return;

    ensureFilter(
      "#page-learning",
      "srisLearningMission",
      "Filtrar aprendizagem por missão"
    );

    const existing = qs(
      ".knowledge-grid,.empty-state,.sris-learning-root",
      page
    );
    const root = existing?.classList.contains("sris-learning-root")
      ? existing
      : document.createElement("div");

    if (!root.classList.contains("sris-learning-root")) {
      root.className = "sris-learning-root";
      existing?.replaceWith(root);
      if (!existing) page.appendChild(root);
    }

    const missions = Object.values(config.missions).filter(
      (m) => filter === "all" || m.id === filter
    );
    const items = missions.flatMap((m) =>
      (m.learning || []).map((e) => ({ ...e, missionId: m.id }))
    );

    root.innerHTML = items.length
      ? `<div class="knowledge-grid">${items
          .map(
            (e) => `
              <article class="knowledge-card">
                <span class="sris-mission-tag">${esc(e.missionId)}</span>
                <div class="knowledge-type">${esc(
                  e.id
                )} · Aprendizagem institucional</div>
                <h3>${esc(e.title)}</h3>
                <p>${esc(e.description)}</p>
                <div class="knowledge-footer">
                  <span>Preservada</span>
                  <span>SRIS</span>
                </div>
              </article>`
          )
          .join("")}</div>`
      : '<div class="sris-empty">Não existem registos de aprendizagem para este filtro.</div>';

    if (qs("#srisLearningMission")) {
      qs("#srisLearningMission").value = filter;
    }
  }

  function syncFilters(id) {
    const e = qs("#srisEvidenceMission");
    const l = qs("#srisLearningMission");

    if (e && e.value !== "all") {
      e.value = id;
      renderEvidence(id);
    }
    if (l && l.value !== "all") {
      l.value = id;
      renderLearning(id);
    }
  }

  function exportMission(mission) {
    const blob = new Blob([JSON.stringify(mission, null, 2)], {
      type: "application/json"
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");

    link.href = url;
    link.download = `${mission.id}-SRIS.json`;

    document.body.appendChild(link);
    link.click();
    link.remove();

    URL.revokeObjectURL(url);
  }

  function bindEvents() {
    // Capture phase deliberately neutralizes the legacy navigation and mission
    // handlers still present in old index.html versions.
    document.addEventListener(
      "click",
      (event) => {
        const nav = event.target.closest(".nav-item");
        if (nav?.dataset.page) {
          event.preventDefault();
          event.stopImmediatePropagation();
          navigate(nav.dataset.page);
          return;
        }

        const go = event.target.closest("[data-go]");
        if (go?.dataset.go) {
          event.preventDefault();
          event.stopImmediatePropagation();
          navigate(go.dataset.go);
          return;
        }

        if (event.target.closest("#newAnalysisButton")) {
          event.preventDefault();
          event.stopImmediatePropagation();
          navigate("workspace");
          return;
        }

        const lightbox = event.target.closest("[data-lightbox-src]");
        if (lightbox) {
          event.preventDefault();
          event.stopImmediatePropagation();
          openLightbox(lightbox);
          return;
        }

        const missionRow = event.target.closest(".mission-open");
        if (missionRow) {
          const mission = missionById(missionRow.dataset.missionId);
          if (mission) {
            event.preventDefault();
            event.stopImmediatePropagation();
            setActiveMission(mission.id, { syncWorkspace: false });
            renderMissionModal(mission);
          }
        }
      },
      true
    );

    qs("#srisSituationMission")?.addEventListener("change", (event) => {
      setActiveMission(event.target.value, { syncWorkspace: true });
    });

    qs("#analysisMission")?.addEventListener("change", (event) => {
      setActiveMission(event.target.value, { syncWorkspace: true });
    });

    qs("#analysisForm")?.addEventListener(
      "submit",
      (event) => {
        event.preventDefault();
        event.stopImmediatePropagation();
        processActiveAnalysis();
      },
      true
    );

    qs("#srisEvidenceMission")?.addEventListener("change", (event) => {
      renderEvidence(event.target.value);
    });

    qs("#srisLearningMission")?.addEventListener("change", (event) => {
      renderLearning(event.target.value);
    });

    qs("#missionExportButton")?.addEventListener(
      "click",
      (event) => {
        const mission = missionById(activeMissionId);
        if (!mission) return;

        event.preventDefault();
        event.stopImmediatePropagation();
        exportMission(mission);
      },
      true
    );
  }

  async function loadConfig() {
    const response = await fetch(`${CONFIG_URL}?v=${Date.now()}`, {
      cache: "no-store"
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  async function boot() {
    try {
      config = await loadConfig();

      if (!config?.missions || !config?.platform?.impact) {
        throw new Error("Estrutura de conteúdo SRIS incompleta.");
      }

      if (!missionById(activeMissionId)) {
        activeMissionId = DEFAULT_MISSION;
      }

      injectStyles();
      consolidateLegacyShell();
      ensureImpactNavigation();
      ensureImpactPage();
      ensureLightbox();
      ensureSituationSelector();
      populateWorkspaceSelect();
      renderMissionLists();
      renderSituation();
      renderWorkspace(activeMissionId);
      renderEvidence(activeMissionId);
      renderLearning(activeMissionId);
      bindEvents();

      document.documentElement.dataset.srisAutobuilder = BUILD;
      console.info(`SRIS Consolidation Patch ${BUILD} carregado.`);
    } catch (error) {
      console.error("SRIS Consolidation Patch falhou:", error);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
