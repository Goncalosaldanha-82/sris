from pathlib import Path


INDEX = Path(__file__).resolve().parents[1] / "frontend" / "atlas-os" / "index.html"
FLAGSHIP = "M-005"
TITLE = "Resiliência do Solo e da Paisagem Rural — Penela 2035"


html = INDEX.read_text(encoding="utf-8")

replacements = {
    'const ACTIVE_KEY = "sris_active_mission_eb1";':
        'const ACTIVE_KEY = "sris_active_mission_academic_2026";',
    'sessionStorage.getItem(ACTIVE_KEY) || "M-002"':
        f'sessionStorage.getItem(ACTIVE_KEY) || "{FLAGSHIP}"',
    'config.missions["M-002"]?"M-002":Object.keys(config.missions)[0]':
        f'config.missions["{FLAGSHIP}"]?"{FLAGSHIP}":Object.keys(config.missions)[0]',
    '<strong>Missão-farol — Nascente de Dragos.</strong>\n'
    '          Um caso onde água, património, arqueologia, memória local e governação\n'
    '          se encontram. As fontes justificam investigação, mas não provam a\n'
    '          ligação funcional entre a nascente e os vestígios romanos, nem\n'
    '          propriedades medicinais. O SRIS torna precisamente essa fronteira útil\n'
    '          para decidir o que investigar, com quem e em que ordem.':
        '<strong>Missão-farol — Resiliência do Solo e da Paisagem Rural — Penela 2035.</strong>\n'
        '          Solo, água, biodiversidade, clima, fogo e comunidades rurais são tratados\n'
        '          como um único sistema de decisão. A missão começa pelo que ainda falta\n'
        '          medir: linha de base, comparadores, trade-offs, atores legitimados e\n'
        '          condições de revisão. O objetivo não é declarar impacto, mas tornar\n'
        '          verificável o caminho entre evidência, intervenção e aprendizagem.',
    '<h2>M-002 · Nascente de Dragos</h2>':
        f'<h2>{FLAGSHIP} · {TITLE}</h2>',
    'Caso candidato para ligar memória local, património, água e ciência\n'
    '            num processo verificável. O objetivo imediato não é prometer uma\n'
    '            recuperação: é determinar que investigação, legitimidade, autorizações\n'
    '            e salvaguardas seriam necessárias antes de qualquer intervenção.':
        'Missão demonstrativa para ligar solo, água, biodiversidade, clima e gestão rural\n'
        '            num processo verificável. O objetivo imediato não é prescrever uma\n'
        '            intervenção: é definir o baseline Ano 0, os comparadores, a governação\n'
        '            dos dados e os critérios que permitam avaliar resultados sem confundir\n'
        '            correlação, urgência operacional e atribuição causal.',
    '<h3>Protocolo da Nascente de Dragos</h3>':
        '<h3>Protocolo Ano 0 · solo e paisagem</h3>',
    'Perguntas, entidades competentes, autorizações e linha de base definidos antes de qualquer intervenção.':
        'Parcelas, indicadores, fontes, comparadores, responsabilidades e regras de revisão definidos antes de qualquer atribuição de impacto.',
}

missing = [old for old in replacements if old not in html]
if missing:
    raise RuntimeError(
        "Academic flagship patch no longer matches index.html: "
        + "; ".join(repr(item[:90]) for item in missing)
    )

for old, new in replacements.items():
    html = html.replace(old, new)

INDEX.write_text(html, encoding="utf-8")
print(f"Academic flagship applied: {FLAGSHIP} — {TITLE}")
