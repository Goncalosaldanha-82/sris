from pathlib import Path


INDEX = Path(__file__).resolve().parents[1] / "frontend" / "atlas-os" / "index.html"
FLAGSHIP = "M-002"
HIDDEN_MISSIONS = ["CA-AWARD-APPLICATION", "MIS-001", "M-005"]


html = INDEX.read_text(encoding="utf-8")
hidden_ids_js = ",".join(f'"{mission_id}"' for mission_id in HIDDEN_MISSIONS)


def require_replace(old: str, new: str) -> None:
    global html
    if old not in html:
        raise RuntimeError(
            f"Academic presentation patch no longer matches index.html: {old[:120]!r}"
        )
    html = html.replace(old, new)


def remove_between(start_marker: str, end_marker: str) -> None:
    global html
    start = html.find(start_marker)
    if start < 0:
        raise RuntimeError(
            f"Academic presentation start marker missing: {start_marker[:120]!r}"
        )
    end = html.find(end_marker, start)
    if end < 0:
        raise RuntimeError(
            f"Academic presentation end marker missing: {end_marker[:120]!r}"
        )
    html = html[:start] + "\n" + html[end:]


# Fresh academic session: Dragos is the flagship and withdrawn/test cases cannot persist.
require_replace(
    'const ACTIVE_KEY = "sris_active_mission_eb1";',
    'const ACTIVE_KEY = "sris_active_mission_academic_dragos_boundary_2026";\n'
    f'    const STAGING_HIDDEN_MISSION_IDS = new Set([{hidden_ids_js}]);',
)

# Remove application/test/withdrawn academic cases from every staging presentation view.
require_replace(
    'config=deepMerge(external,BRIEF_ALIGNMENT);',
    'config=deepMerge(external,BRIEF_ALIGNMENT);\n'
    '      STAGING_HIDDEN_MISSION_IDS.forEach(id=>delete config.missions?.[id]);',
)
require_replace(
    'const all=Object.values(config.missions||{}),byId=new Map(all.map(item=>[item.id,item]));',
    'const all=Object.values(config.missions||{}).filter(item=>!STAGING_HIDDEN_MISSION_IDS.has(item.id)),byId=new Map(all.map(item=>[item.id,item]));',
)

# Academic presentation: no TRL scoring in a scientific first-contact context.
remove_between(
    '\n        <div class="section-title">\n          <div class="eyebrow">Maturidade tecnológica</div>',
    '\n        <div class="two-col">',
)

# A professor is being approached for scientific collaboration, not financing.
remove_between(
    '\n        <div class="section-title">\n          <div class="eyebrow">Aplicação do investimento-piloto</div>',
    '\n        <div class="callout">',
)

# Dragos is presented as a hand-off to competent research, never as a promoter-led study.
require_replace(
    'Caso candidato para ligar memória local, património, água e ciência\n'
    '            num processo verificável. O objetivo imediato não é prometer uma\n'
    '            recuperação: é determinar que investigação, legitimidade, autorizações\n'
    '            e salvaguardas seriam necessárias antes de qualquer intervenção.',
    'Caso científico aberto onde observação física, memória local, fontes académicas,\n'
    '            hipóteses e desconhecidos permanecem separados. O promotor organiza e\n'
    '            disponibiliza o caso; não executa nem antecipa a investigação científica.\n'
    '            Método, amostragem, instrumentação, cronologia e interpretação começam\n'
    '            apenas com uma equipa de investigação competente e legitimada.',
)
require_replace(
    '<h3>Protocolo da Nascente de Dragos</h3>',
    '<h3>Fronteira de investigação formalizada</h3>',
)
require_replace(
    'Perguntas, entidades competentes, autorizações e linha de base definidos antes de qualquer intervenção.',
    'Observações, memória local, fontes académicas e lacunas ficam organizadas; o desenho científico é entregue à equipa investigadora competente.',
)

# External adoption is a validation condition, not a dated promise.
require_replace(
    '<div class="month">4–6 meses</div>\n            <h3>Primeira organização externa</h3>\n            <p>Um programa e respetivas sub-missões geridos por uma equipa que não a do promotor.</p>',
    '<div class="month">Condição de validação</div>\n            <h3>Utilização por organização externa</h3>\n            <p>Marco futuro sem prazo assumido: só existe quando uma organização externa utilizar o SRIS no seu próprio trabalho. Até lá, permanece explicitamente não demonstrado.</p>',
)

# Tighten recognition wording to claims directly supported by the documented evidence.
require_replace(
    '<p>Selecionado para a short list da edição de 2026.</p>',
    '<p>Selecionado para a Short List do Prémio Forbes Green ESG Awards 2026.</p>',
)
require_replace(
    '<p>Nomeado na categoria TECH pela inovação e desenvolvimento tecnológico aplicado ao turismo.</p>',
    '<p>Nomeado na categoria TECH dos Prémios Líderes do Turismo 2026.</p>',
)

INDEX.write_text(html, encoding="utf-8")
print(
    f"Academic presentation applied: flagship {FLAGSHIP}; "
    f"hidden: {', '.join(HIDDEN_MISSIONS)}; research boundary enforced."
)
