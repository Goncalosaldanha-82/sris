(() => {
  "use strict";

  const CONFIG_URL = "/assets/sris-platform-content.json";

  const escapeHtml = (value) =>
    String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");

  const setText = (selector, value) => {
    const el = document.querySelector(selector);
    if (el && value !== undefined && value !== null) {
      el.textContent = value;
    }
  };

  const setValue = (id, value) => {
    const el = document.getElementById(id);
    if (el && value !== undefined && value !== null) {
      el.value = value;
    }
  };

  const renderList = (items = []) => {
    return `
      <ul>
        ${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
      </ul>
    `;
  };

  function renderCapabilities(items = []) {
    const grid = document.querySelector(".intelligence-grid");

    if (!grid || !Array.isArray(items) || !items.length) {
      return;
    }

    grid.innerHTML = items
      .map(
        (item) => `
          <article class="intelligence-card">
            <div class="card-index">${escapeHtml(item.index)}</div>
            <h3>${escapeHtml(item.title)}</h3>
            <p>${escapeHtml(item.description)}</p>
          </article>
        `
      )
      .join("");
  }

  function renderEvidence(items = []) {
    const page = document.getElementById("page-evidence");

    if (!page || !Array.isArray(items) || !items.length) {
      return;
    }

    const emptyState = page.querySelector(".empty-state");

    const html = `
      <div class="knowledge-grid">
        ${items
          .map(
            (item) => `
              <article class="knowledge-card">
                <div class="knowledge-type">
                  ${escapeHtml(item.id)} · ${escapeHtml(item.type)}
                </div>

                <h3>${escapeHtml(item.title)}</h3>

                <p>${escapeHtml(item.description)}</p>

                <div class="knowledge-footer">
                  <span>
                    ${escapeHtml(item.status)} · Confiança ${escapeHtml(
              item.confidence
            )}
                  </span>

                  <span>${escapeHtml(item.source)}</span>
                </div>
              </article>
            `
          )
          .join("")}
      </div>
    `;

    if (emptyState) {
      emptyState.outerHTML = html;
    }
  }

  function renderLearning(items = []) {
    const page = document.getElementById("page-learning");

    if (!page || !Array.isArray(items) || !items.length) {
      return;
    }

    const emptyState = page.querySelector(".empty-state");

    const html = `
      <div class="knowledge-grid">
        ${items
          .map(
            (item) => `
              <article class="knowledge-card">
                <div class="knowledge-type">
                  ${escapeHtml(item.id)} · Aprendizagem institucional
                </div>

                <h3>${escapeHtml(item.title)}</h3>

                <p>${escapeHtml(item.description)}</p>

                <div class="knowledge-footer">
                  <span>Reutilizável</span>
                  <span>SRIS</span>
                </div>
              </article>
            `
          )
          .join("")}
      </div>
    `;

    if (emptyState) {
      emptyState.outerHTML = html;
    }
  }

  function renderWorkspace(workspace, result) {
    if (!workspace) {
      return;
    }

    setText("#page-workspace .eyebrow", workspace.eyebrow);
    setText("#page-workspace h1", workspace.headline);
    setText("#page-workspace .hero p", workspace.description);

    setValue("analysisTitle", workspace.analysis_title);
    setValue("analysisContext", workspace.context);
    setValue("analysisDecision", workspace.central_question);
    setValue("analysisEvidence", workspace.available_evidence);
    setValue("analysisUnknowns", workspace.unknowns);

    const missionSelect = document.getElementById("analysisMission");

    if (missionSelect && workspace.mission_id) {
      missionSelect.value = workspace.mission_id;
    }

    if (!result) {
      return;
    }

    const resultBlock =
      document.getElementById("resultBlock") ||
      document.querySelector(".result-block");

    if (!resultBlock) {
      return;
    }

    const alternatives = Array.isArray(result.alternatives)
      ? result.alternatives
          .map(
            (item) => `
              <li>
                <strong>${escapeHtml(item.id)} — ${escapeHtml(
              item.title
            )}</strong><br>
                ${escapeHtml(item.description)}
              </li>
            `
          )
          .join("")
      : "";

    resultBlock.innerHTML = `
      <div class="result-highlight">
        <div class="result-label">Resultado reconstruído</div>
        <h2>${escapeHtml(result.headline)}</h2>
        <p>${escapeHtml(result.summary)}</p>
      </div>

      <div class="result-section">
        <strong>Situação</strong>
        <p>${escapeHtml(result.situation)}</p>
      </div>

      <div class="result-section">
        <strong>Risco principal</strong>
        <p>${escapeHtml(result.principal_risk)}</p>
      </div>

      <div class="result-section">
        <strong>Pressupostos a testar</strong>
        ${renderList(result.assumptions)}
      </div>

      <div class="result-section">
        <strong>Alternativas</strong>
        <ul>${alternatives}</ul>
      </div>

      <div class="result-section">
        <strong>Próxima decisão</strong>
        <p>${escapeHtml(result.next_decision)}</p>
      </div>

      <div class="result-section">
        <strong>Confiança atual</strong>
        <p>${escapeHtml(result.confidence)}</p>
      </div>
    `;
  }

  function updateCandidacyMission(missions = {}) {
    const mission = missions["CA-AWARD-APPLICATION"];

    if (!mission) {
      return;
    }

    document
      .querySelectorAll('[data-mission-id="CA-AWARD-APPLICATION"]')
      .forEach((button) => {
        const title = button.querySelector(".mission-title");

        if (title) {
          title.textContent = mission.title;
        }

        const meta = button.querySelector(".mission-meta");

        if (meta) {
          meta.textContent = `${mission.id} · ${mission.status}`;
        }

        const status = button.querySelector(".status-badge");

        if (status) {
          status.textContent = mission.status;
        }

        const confidence = button.querySelector(".trend-improving");

        if (confidence) {
          confidence.textContent = `Confiança ${mission.confidence.toLowerCase()}`;
        }
      });
  }

  function renderDifferentiation(data) {
    if (!data) {
      return;
    }

    const target = document.querySelector(".recognition-section");

    if (!target || document.getElementById("sris-differentiation")) {
      return;
    }

    const section = document.createElement("section");

    section.id = "sris-differentiation";
    section.className = "recognition-section";

    section.innerHTML = `
      <div class="page-section-title">
        <div class="eyebrow">DIFERENCIAÇÃO</div>
        <h2>${escapeHtml(data.headline)}</h2>
        <p>${escapeHtml(data.description)}</p>
      </div>
    `;

    target.parentNode.insertBefore(section, target);
  }

  function renderMarket(data) {
    if (!data) {
      return;
    }

    const target = document.querySelector(".recognition-section");

    if (!target || document.getElementById("sris-market")) {
      return;
    }

    const section = document.createElement("section");

    section.id = "sris-market";
    section.className = "recognition-section";

    section.innerHTML = `
      <div class="page-section-title">
        <div class="eyebrow">ESCALABILIDADE</div>
        <h2>${escapeHtml(data.headline)}</h2>
        <p>${escapeHtml(data.description)}</p>
      </div>

      <div class="intelligence-grid">
        <article class="intelligence-card">
          <div class="card-index">01</div>
          <h3>Mercado inicial</h3>
          <p>${escapeHtml((data.initial_domains || []).join(" · "))}</p>
        </article>

        <article class="intelligence-card">
          <div class="card-index">02</div>
          <h3>Modelo de escala</h3>
          <p>${escapeHtml(data.scalability)}</p>
        </article>

        <article class="intelligence-card">
          <div class="card-index">03</div>
          <h3>Expansão</h3>
          <p>${escapeHtml((data.expansion_domains || []).join(" · "))}</p>
        </article>
      </div>
    `;

    target.parentNode.insertBefore(section, target);
  }

  function renderSustainability(data) {
    if (!data) {
      return;
    }

    const target = document.querySelector(".recognition-section");

    if (!target || document.getElementById("sris-sustainability")) {
      return;
    }

    const section = document.createElement("section");

    section.id = "sris-sustainability";
    section.className = "recognition-section";

    section.innerHTML = `
      <div class="page-section-title">
        <div class="eyebrow">IMPACTO E SUSTENTABILIDADE</div>
        <h2>${escapeHtml(data.headline)}</h2>
        <p>${escapeHtml(data.description)}</p>
      </div>

      <div class="intelligence-grid">
        ${(data.dimensions || [])
          .map(
            (item, index) => `
              <article class="intelligence-card">
                <div class="card-index">0${index + 1}</div>
                <h3>${escapeHtml(item.title)}</h3>
                <p>${escapeHtml(item.description)}</p>
              </article>
            `
          )
          .join("")}
      </div>
    `;

    target.parentNode.insertBefore(section, target);
  }

  async function loadContent() {
    try {
      const response = await fetch(`${CONFIG_URL}?v=${Date.now()}`, {
        cache: "no-store"
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error(
        "SRIS AutoBuilder: não foi possível carregar o conteúdo mestre.",
        error
      );

      return null;
    }
  }

  async function boot() {
    const config = await loadContent();

    if (!config || !config.platform) {
      return;
    }

    const platform = config.platform;

    renderCapabilities(platform.capabilities);
    renderWorkspace(platform.workspace, platform.analysis_result);
    renderEvidence(platform.evidence);
    renderLearning(platform.learning);

    renderDifferentiation(platform.differentiation);
    renderMarket(platform.market);
    renderSustainability(platform.sustainability);

    updateCandidacyMission(config.missions);

    document.documentElement.dataset.srisAutobuilder =
      config.version || "1.0.0";

    console.info(
      `SRIS AutoBuilder ${config.version || "1.0.0"} carregado com sucesso.`
    );
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
