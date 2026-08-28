(() => {
  "use strict";

  const steps = [
    {
      title: "Contexto",
      kicker: "Delimitar antes de interpretar",
      description: "Define o problema, o objetivo, o âmbito, os intervenientes e as restrições em que a decisão existe.",
      guardrail: "Impede que um indicador seja interpretado fora das condições que lhe dão significado."
    },
    {
      title: "Observação",
      kicker: "Registar sem concluir",
      description: "Preserva aquilo que foi observado, com tempo, origem e condições, sem o converter prematuramente numa explicação causal.",
      guardrail: "Mantém separados o sinal observado e a interpretação proposta para esse sinal."
    },
    {
      title: "Evidência",
      kicker: "Ligar cada afirmação à origem",
      description: "Associa documentos, dados e registos à missão, preservando título, proveniência, estatuto de revisão e relações.",
      guardrail: "Evita decisões sustentadas por referências opacas, identificadores técnicos ou fontes impossíveis de reconstruir."
    },
    {
      title: "Hipótese",
      kicker: "Explicar sem fingir certeza",
      description: "Formula causas ou mecanismos possíveis como proposições testáveis, com confiança, pressupostos e incerteza explícita.",
      guardrail: "Uma explicação plausível permanece hipótese até existir evidência suficiente para a rever."
    },
    {
      title: "Alternativas",
      kicker: "Comparar opções reais",
      description: "Mantém opções materialmente diferentes, incluindo condições de aplicação, riscos e a possibilidade de não intervir.",
      guardrail: "Impede que a primeira solução imaginada seja tratada como a única solução disponível."
    },
    {
      title: "Decisão",
      kicker: "Escolher com fundamento",
      description: "Regista a opção escolhida, a fundamentação, o responsável, a confiança, as condições e o momento em que deve ser revista.",
      guardrail: "A plataforma apoia a decisão; não substitui o ato humano de decidir e assumir responsabilidade."
    },
    {
      title: "Ação",
      kicker: "Transformar decisão em execução",
      description: "Define o que será executado, por quem, com que recursos, em que prazo e sob que autorização.",
      guardrail: "Separa uma intenção aprovada de uma ação efetivamente realizada."
    },
    {
      title: "Medição",
      kicker: "Medir antes e depois",
      description: "Estrutura indicador, baseline, meta, fonte, período, normalização e condições necessárias para avaliar o efeito.",
      guardrail: "Evita atribuir à intervenção uma variação que pode resultar de ocupação, clima, sazonalidade ou outros fatores."
    },
    {
      title: "Resultado",
      kicker: "Distinguir esperado de observado",
      description: "Regista o efeito realmente observado e liga-o a evidência posterior à ação, incluindo desvios e efeitos não previstos.",
      guardrail: "Um resultado não é confirmado apenas porque coincide com a expectativa inicial."
    },
    {
      title: "Aprendizagem",
      kicker: "Rever o que a missão demonstrou",
      description: "Explicita o que foi confirmado, refutado ou permaneceu incerto, antes de qualquer reutilização futura.",
      guardrail: "Só a aprendizagem sujeita a revisão humana pode avançar para memória organizacional."
    },
    {
      title: "Memória",
      kicker: "Preservar sem congelar",
      description: "Publica aprendizagem com linhagem, contexto, validade e condições de aplicabilidade para apoiar missões futuras.",
      guardrail: "Memória não é verdade eterna: regressa sempre a um novo contexto para ser revalidada."
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
})();
