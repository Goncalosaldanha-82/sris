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

  const contactForm = document.querySelector("[data-contact-form]");
  const formStatus = document.querySelector("[data-form-status]");

  if (contactForm) {
    const submitButton = contactForm.querySelector('button[type="submit"]');
    const loadedAt = Date.now();

    contactForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!contactForm.reportValidity()) return;

      const data = new FormData(contactForm);
      const payload = {
        name: String(data.get("name") || "").trim(),
        email: String(data.get("email") || "").trim(),
        organization: String(data.get("organization") || "").trim(),
        purpose: String(data.get("purpose") || "").trim(),
        message: String(data.get("message") || "").trim(),
        website: String(data.get("website") || "").trim(),
        privacy: data.get("privacy") === "on",
        elapsed_ms: Date.now() - loadedAt
      };

      submitButton.disabled = true;
      submitButton.textContent = "A enviar…";
      contactForm.setAttribute("aria-busy", "true");
      formStatus.className = "form-status";
      formStatus.textContent = "A enviar o contacto em segurança.";

      try {
        const response = await fetch("/api/contact", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(result.error || "Não foi possível enviar o pedido.");

        contactForm.reset();
        formStatus.classList.add("success");
        formStatus.textContent = "Contacto enviado. Obrigado — responderemos para avaliar o enquadramento e os próximos passos.";
      } catch (error) {
        formStatus.classList.add("error");
        formStatus.textContent = error.message || "Não foi possível enviar agora. Tente novamente dentro de alguns minutos.";
      } finally {
        submitButton.disabled = false;
        submitButton.textContent = "Solicitar contacto";
        contactForm.removeAttribute("aria-busy");
      }
    });
  }
})();
