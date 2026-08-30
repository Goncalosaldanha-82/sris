(() => {
  "use strict";

  const steps = [
    {
      title: "Contexto",
      kicker: "Enquadrar antes de interpretar",
      description: "Define o problema, o objetivo, o âmbito, os intervenientes e as restrições em que a decisão existe.",
      guardrail: "O Contexto enquadra a missão; não acrescenta um nono registo à cadeia canónica."
    },
    {
      title: "Evidência",
      kicker: "Distinguir o que se observa do que se infere",
      description: "Reúne Observação, Evidência e Hipótese, preservando a origem dos dados e mantendo a interpretação como proposição testável.",
      guardrail: "Três registos canónicos: Observação → Evidência → Hipótese."
    },
    {
      title: "Decisão",
      kicker: "Comparar antes de escolher",
      description: "Liga Alternativa e Decisão para tornar visíveis as opções consideradas, os critérios usados, o fundamento e a responsabilidade humana.",
      guardrail: "Dois registos canónicos: Alternativa → Decisão."
    },
    {
      title: "Medição",
      kicker: "Executar e medir sem confundir",
      description: "Liga Ação e Resultado, com baseline, indicador, período e condições suficientes para comparar o esperado com o que aconteceu.",
      guardrail: "Dois registos canónicos: Ação → Resultado."
    },
    {
      title: "Memória",
      kicker: "Aprender sem congelar",
      description: "Preserva a Aprendizagem revista, a sua linhagem, validade e condições de aplicabilidade para apoiar missões futuras.",
      guardrail: "Um registo canónico: Aprendizagem. Só regressa a um novo Contexto depois de revalidada."
    }
  ];

  const cycle = document.querySelector("[data-cycle]");
  if (cycle) {
    const tabs = [...cycle.querySelectorAll("[data-cycle-step]")];
    const panel = cycle.querySelector('[role="tabpanel"]');
    const position = cycle.querySelector("[data-cycle-position]");
    const kicker = cycle.querySelector("[data-cycle-kicker]");
    const title = cycle.querySelector("[data-cycle-title]");
    const description = cycle.querySelector("[data-cycle-description]");
    const guardrail = cycle.querySelector("[data-cycle-guardrail]");
    const previous = cycle.querySelector("[data-cycle-prev]");
    const next = cycle.querySelector("[data-cycle-next]");
    let activeIndex = 0;

    const activate = (index, focusTab = false, scrollTab = true) => {
      activeIndex = (index + steps.length) % steps.length;
      const step = steps[activeIndex];

      tabs.forEach((tab, tabIndex) => {
        const isActive = tabIndex === activeIndex;
        tab.classList.toggle("active", isActive);
        tab.setAttribute("aria-selected", String(isActive));
        tab.tabIndex = isActive ? 0 : -1;
      });

      position.textContent = String(activeIndex + 1).padStart(2, "0");
      kicker.textContent = step.kicker;
      title.textContent = step.title;
      description.textContent = step.description;
      guardrail.textContent = step.guardrail;

      const activeTab = tabs[activeIndex];
      panel?.setAttribute("aria-labelledby", activeTab.id);
      if (scrollTab) {
        const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        activeTab.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "nearest", inline: "center" });
      }
      if (focusTab) activeTab.focus();
    };

    tabs.forEach((tab, index) => {
      tab.id = `cycle-tab-${index + 1}`;
      tab.setAttribute("aria-controls", "cycle-panel");
      tab.addEventListener("click", () => activate(index));
      tab.addEventListener("keydown", (event) => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        if (event.key === "Home") activate(0, true);
        else if (event.key === "End") activate(steps.length - 1, true);
        else activate(activeIndex + (event.key === "ArrowRight" ? 1 : -1), true);
      });
    });

    previous?.addEventListener("click", () => activate(activeIndex - 1));
    next?.addEventListener("click", () => activate(activeIndex + 1));
    if (panel) panel.id = "cycle-panel";
    activate(0, false, false);
  }

  const mobileMenu = document.querySelector(".mobile-menu");
  mobileMenu?.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => {
      mobileMenu.open = false;
    });
  });

  const copyEmailButton = document.querySelector("[data-copy-email]");
  const copyFeedback = document.querySelector("[data-copy-feedback]");

  if (copyEmailButton) {
    const initialLabel = copyEmailButton.textContent;
    let resetTimer;

    copyEmailButton.addEventListener("click", async () => {
      const email = copyEmailButton.dataset.copyEmail;
      let copied = false;

      try {
        if (navigator.clipboard && window.isSecureContext) {
          await navigator.clipboard.writeText(email);
          copied = true;
        } else {
          const field = document.createElement("textarea");
          field.value = email;
          field.setAttribute("readonly", "");
          field.style.position = "fixed";
          field.style.opacity = "0";
          document.body.appendChild(field);
          field.select();
          copied = document.execCommand("copy");
          field.remove();
        }
      } catch {
        copied = false;
      }

      window.clearTimeout(resetTimer);
      copyEmailButton.textContent = copied ? "Copiado" : initialLabel;
      if (copyFeedback) {
        copyFeedback.textContent = copied
          ? "Endereço copiado para a área de transferência."
          : "Não foi possível copiar. Selecione o endereço apresentado acima.";
      }

      resetTimer = window.setTimeout(() => {
        copyEmailButton.textContent = initialLabel;
        if (copyFeedback) copyFeedback.textContent = "";
      }, 3000);
    });
  }
})();
