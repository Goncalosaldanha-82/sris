from pathlib import Path


INDEX = Path(__file__).resolve().parents[1] / "frontend" / "atlas-os" / "index.html"
FLAGSHIP = "M-002"
HIDDEN_MISSIONS = ["CA-AWARD-APPLICATION", "MIS-001", "M-005"]


html = INDEX.read_text(encoding="utf-8")
hidden_ids_js = ",".join(f'"{mission_id}"' for mission_id in HIDDEN_MISSIONS)


def require_replace(old: str, new: str) -> None:
    global html
    if old not in html:
        raise RuntimeError(f"Academic presentation patch no longer matches index.html: {old[:120]!r}")
    html = html.replace(old, new)


def remove_between(start_marker: str, end_marker: str) -> None:
    global html
    start = html.find(start_marker)
    if start < 0:
        raise RuntimeError(f"Academic presentation start marker missing: {start_marker[:120]!r}")
    end = html.find(end_marker, start)
    if end < 0:
        raise RuntimeError(f"Academic presentation end marker missing: {end_marker[:120]!r}")
    html = html[:start] + "\n" + html[end:]


# A fresh session key prevents a previous M-005 selection from surviving in the browser.
require_replace(
    'const ACTIVE_KEY = "sris_active_mission_eb1";',
    'const ACTIVE_KEY = "sris_active_mission_academic_dragos_2026";\n'
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

# Academic presentation: keep the evidence/status lists, but remove TRL scoring language.
remove_between(
    '\n        <div class="section-title">\n          <div class="eyebrow">Maturidade tecnológica</div>',
    '\n        <div class="two-col">',
)

# A professor is being approached for scientific collaboration, not funding.
remove_between(
    '\n        <div class="section-title">\n          <div class="eyebrow">Aplicação do investimento-piloto</div>',
    '\n        <div class="callout">',
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
    f"hidden: {', '.join(HIDDEN_MISSIONS)}; TRL and funding blocks removed."
)
