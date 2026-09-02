from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one {label} marker, found {count}")
    return source.replace(old, new, 1)


def update(path: str, transform) -> None:
    target = ROOT / path
    source = target.read_text(encoding="utf-8")
    revised = transform(source)
    if revised == source:
        raise RuntimeError(f"No change produced for {path}")
    target.write_text(revised, encoding="utf-8")
    print(f"updated {path}")


def demonstration_html(source: str) -> str:
    source = replace_once(
        source,
        '<a href="/" aria-label="SRIS — início"><img src="/sris-logo-compact-light.svg?v=__PILOT_BUILD__" alt="SRIS — Mission Intelligence"></a>',
        '<a href="https://www.sris.io/" aria-label="Voltar ao site SRIS"><img src="/sris-logo-compact-light.svg?v=__PILOT_BUILD__" alt="SRIS — Mission Intelligence"></a>',
        "demonstration logo link",
    )
    source = replace_once(
        source,
        '<nav><span class="readonly">Só de leitura</span><a href="/">Acesso institucional</a></nav>',
        '<nav><span class="readonly">Só de leitura</span><a class="site-return" href="https://www.sris.io/">Voltar ao site SRIS</a><a href="/">Entrar na aplicação</a></nav>',
        "demonstration navigation",
    )
    if 'href="https://sris-mission-intelligence.up.railway.app/#contacto"' not in source:
        raise RuntimeError("Tourism Advance Railway site link is no longer present")
    return source


def demonstration_css(source: str) -> str:
    marker = '.demo-header a{color:#fff;text-decoration:none;font-weight:700}'
    source = replace_once(
        source,
        marker,
        marker + '.demo-header .site-return{display:inline-flex;align-items:center;min-height:38px;padding:8px 12px;border:1px solid rgba(255,255,255,.34);border-radius:10px;background:rgba(255,255,255,.08)}.demo-header .site-return:hover,.demo-header .site-return:focus-visible{background:#fff;color:var(--forest);outline:0}',
        "demonstration site-return style",
    )
    return replace_once(
        source,
        '@media(max-width:760px){.demo-header{height:auto;padding:15px 18px}.demo-header img{width:150px}.readonly{display:none}',
        '@media(max-width:760px){.demo-header{height:auto;padding:15px 18px;gap:14px}.demo-header img{width:150px}.demo-header nav{justify-content:flex-end;gap:9px;flex-wrap:wrap}.demo-header nav a{font-size:.84rem}.readonly{display:none}',
        "demonstration mobile header",
    )


def app_index(source: str) -> str:
    source = replace_once(
        source,
        '<button data-mission-area="cycle">✓ <span>Decisões e resultados</span></button>\n        <button data-mission-area="learning">↻ <span>Memória</span></button>',
        '<button data-mission-area="cycle">✓ <span>Decisões e resultados</span></button>\n        <button data-mission-area="economics">€ <span>Economia e recursos</span></button>\n        <button data-mission-area="learning">↻ <span>Memória</span></button>',
        "main economics navigation",
    )
    source = replace_once(
        source,
        '<div class="card-head"><div><h2>Missões</h2><div class="note">Portefólio persistente</div></div><button class="btn btn-primary compact" id="new-mission-btn">+ Nova</button></div>\n          <input id="mission-search" class="input" placeholder="Pesquisar missões…" autocomplete="off">',
        '<div class="card-head"><div><h2>Missões</h2><div class="note">Histórico persistente deste workspace</div></div><button class="btn btn-primary compact" id="new-mission-btn">+ Nova</button></div>\n          <input id="mission-search" class="input" placeholder="Pesquisar missões…" autocomplete="off">\n          <div class="note mission-continuity-note">As missões anteriores permanecem preservadas. Só pertencem a um piloto quando são ligadas explicitamente.</div>',
        "mission continuity note",
    )
    source = replace_once(
        source,
        '<div class="mission-tabs" aria-label="Áreas da missão"><button class="active" type="button" data-mission-tab="summary">Resumo</button><button type="button" data-mission-tab="documents">Documentos</button><button type="button" data-mission-tab="validation">Medição</button><button type="button" data-mission-tab="history">Auditoria</button></div>',
        '<div class="mission-tabs" aria-label="Áreas da missão"><button class="active" type="button" data-mission-tab="summary">Resumo</button><button type="button" data-mission-tab="documents">Documentos</button><button type="button" data-mission-tab="economics">Economia e recursos</button><button type="button" data-mission-tab="validation">Medição</button><button type="button" data-mission-tab="history">Auditoria</button></div>',
        "mission economics tab",
    )
    return replace_once(
        source,
        '            </div>\n            <div class="mission-tab" id="mission-tab-validation">\n              <div id="validation-root" class="validation-root"><div class="note">A sincronizar o protocolo mensurável da missão…</div></div>\n            </div>',
        '            </div>\n            <div class="mission-tab" id="mission-tab-economics">\n              <div id="business-case-root" class="business-case-root"><div class="note">A sincronizar o Business Case Vivo…</div></div>\n            </div>\n            <div class="mission-tab" id="mission-tab-validation">\n              <div id="validation-root" class="validation-root"><div class="note">A sincronizar o protocolo mensurável da missão…</div></div>\n            </div>',
        "mission economics panel",
    )


def pilot_platform(source: str) -> str:
    source = replace_once(
        source,
        "const BUILD='20260901-pilot-mission-platform-v31';",
        "const BUILD=document.querySelector('meta[name=\"sris-pilot-build\"]')?.content||'integrated';",
        "platform build identity",
    )
    source = replace_once(
        source,
        "const state={pilots:[],selected:null,templates:[],profiles:[],missions:[],activeTab:'charter',loading:false,installed:false};",
        "const state={pilots:[],selected:null,templates:[],profiles:[],programSources:[],missions:[],activeTab:'charter',loading:false,installed:false};",
        "platform catalog state",
    )
    source = replace_once(
        source,
        "const profileLabels={cross_sector:'Transversal',hospitality:'Hospitality',public_sector:'Setor público',industrial_operations:'Operações industriais',territorial_lab:'Laboratório territorial'};",
        "const profileLabels={cross_sector:'Transversal',hospitality:'Hospitality',public_sector:'Setor público',industrial_operations:'Operações industriais',territorial_lab:'Laboratório territorial',research_and_innovation:'Investigação e inovação'};\n  const legacyProgramLabels={corporate_program:'Programa corporate',other:'Outro'};\n  const profileLabel=key=>state.profiles.find(item=>item.key===key)?.label||profileLabels[key]||key||'Transversal';\n  const programLabel=key=>state.programSources.find(item=>item.key===key)?.label||legacyProgramLabels[key]||key||'Piloto direto';\n  function programSourceOptions(selected='direct'){\n    const rows=[...state.programSources];\n    if(selected&&!rows.some(item=>item.key===selected))rows.push({key:selected,label:legacyProgramLabels[selected]||`Outro / legado · ${selected}`});\n    return rows.map(item=>`<option value=\"${esc(item.key)}\" ${item.key===selected?'selected':''}>${esc(item.label)}</option>`).join('');\n  }",
        "profile and programme catalog helpers",
    )
    source = replace_once(
        source,
        "state.templates=catalog.templates||[];state.profiles=catalog.profiles||[];state.pilots=pilots||[];state.missions=missions||[];",
        "state.templates=catalog.templates||[];state.profiles=catalog.profiles||[];state.programSources=catalog.program_sources||[];state.pilots=pilots||[];state.missions=missions||[];",
        "catalog synchronization",
    )
    source = source.replace("(state.templates||[]).slice(0,4)", "(state.templates||[])")
    replacements = {
        "profileLabels[template.sector_profile]||template.sector_profile": "profileLabel(template.sector_profile)",
        "profileLabels[row.sector_profile]||'Contexto por definir'": "profileLabel(row.sector_profile)||'Contexto por definir'",
        "profileLabels[item.sector_profile]||item.sector_profile": "profileLabel(item.sector_profile)",
        "profileLabels[pilot.sector_profile]||pilot.sector_profile": "profileLabel(pilot.sector_profile)",
        "row.program_source||'direto'": "programLabel(row.program_source)",
        "pilot.program_source||'direto'": "programLabel(pilot.program_source)",
    }
    for old, new in replacements.items():
        if old not in source:
            raise RuntimeError(f"Platform marker missing: {old}")
        source = source.replace(old, new)
    return replace_once(
        source,
        '<div class="field"><label>Origem / programa</label><select name="program_source"><option value="direct">Relação direta</option><option value="tourism_advance">Tourism Advance</option><option value="hospitality_open_innovation">Hospitality Open Innovation</option><option value="public_program">Programa público</option><option value="corporate_program">Programa corporate</option><option value="academic_partnership">Parceria académica</option><option value="other">Outro</option></select></div>',
        '<div class="field"><label>Origem / programa</label><select name="program_source">${programSourceOptions(pilot?.program_source||\'direct\')}</select></div>',
        "programme source selector",
    )


def pilot_value(source: str) -> str:
    source = replace_once(source, "valueButton.textContent='Value Case';", "valueButton.textContent='Valor do piloto';", "pilot value tab label")
    source = replace_once(source, "A sincronizar o Value Case…", "A sincronizar o valor do piloto…", "pilot value loading label")
    return replace_once(source, "PILOT VALUE CASE", "VALOR DO PILOTO", "pilot value heading")


def capabilities(source: str) -> str:
    source = replace_once(
        source,
        'PILOT_BUILD = "20260901-pilot-mission-intelligence-rc1"',
        'PILOT_BUILD = "20260902-pilot-navigation-economics-v35"',
        "pilot build bump",
    )
    return replace_once(
        source,
        '        "product": "SRIS Pilot & Mission Intelligence",\n        "architecture": "universal_core_configurable_profiles",',
        '        "product": "SRIS Pilot & Mission Intelligence",\n        "site_urls": [\n            "https://www.sris.io/",\n            "https://sris-mission-intelligence.up.railway.app/",\n        ],\n        "architecture": "universal_core_configurable_profiles",',
        "dual site URL capability",
    )


def public_demo_test(source: str) -> str:
    return replace_once(
        source,
        '  assert.match(css,/\\.fictional-banner/);',
        '  assert.match(css,/\\.fictional-banner/);\n  assert.match(html,/Voltar ao site SRIS/);\n  assert.match(html,/https:\\/\\/www\\.sris\\.io\\//);\n  assert.match(html,/https:\\/\\/sris-mission-intelligence\\.up\\.railway\\.app\\/#contacto/);\n  assert.match(html,/Entrar na aplicação/);',
        "dual site regression assertions",
    )


def release_test(source: str) -> str:
    return replace_once(
        source,
        "  assert.match(app,/setAttribute\\('aria-expanded'/);",
        "  assert.match(app,/setAttribute\\('aria-expanded'/);\n  assert.match(index,/data-mission-area=\"economics\"/);\n  assert.match(index,/data-mission-tab=\"economics\"/);\n  assert.match(index,/id=\"business-case-root\"/);\n  assert.match(index,/missões anteriores permanecem preservadas/i);",
        "economics navigation assertions",
    )


def platform_test(source: str) -> str:
    return replace_once(
        source,
        '  assert.match(platform,/hospitality_open_innovation/);',
        '  assert.match(platform,/hospitality_open_innovation/);\n  assert.match(platform,/research_and_innovation:\'Investigação e inovação\'/);\n  assert.match(platform,/catalog\\.program_sources/);\n  assert.match(platform,/programSourceOptions/);\n  assert.doesNotMatch(platform,/\\.slice\\(0,4\\)/);',
        "catalog consumption assertions",
    )


def value_test(source: str) -> str:
    return replace_once(
        source,
        '  assert.match(ui,/PILOT VALUE CASE/);',
        '  assert.match(ui,/VALOR DO PILOTO/);\n  assert.match(ui,/Valor do piloto/);',
        "pilot value Portuguese label assertion",
    )


update("frontend/pilot-v1/demonstracao.html", demonstration_html)
update("frontend/pilot-v1/demonstracao.css", demonstration_css)
update("frontend/pilot-v1/index.html", app_index)
update("frontend/pilot-v1/pilot-platform-v1.js", pilot_platform)
update("frontend/pilot-v1/pilot-value-v1.js", pilot_value)
update("backend/app/pilot_capabilities.py", capabilities)
update("frontend/tests/public_demonstration_contract.test.js", public_demo_test)
update("frontend/tests/pilot_release_hardening_contract.test.js", release_test)
update("frontend/tests/pilot_platform_contract.test.js", platform_test)
update("frontend/tests/pilot_value_contract.test.js", value_test)

print("Approved Pilot V1 UX alignment applied.")
