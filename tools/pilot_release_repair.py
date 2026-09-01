from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    (ROOT / path).write_text(content, encoding="utf-8")
    print(f"updated {path}")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    if new in text:
        print(f"already reconciled {path}")
        return
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one marker in {path}, found {count}: {old[:120]!r}")
    write(path, text.replace(old, new, 1))


def regex_once(path: str, pattern: str, replacement: str, flags: int = 0) -> None:
    text = read(path)
    updated, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        raise RuntimeError(f"Expected one regex match in {path}, found {count}: {pattern}")
    write(path, updated)


# 1. Compose the complete Pilot & Mission Intelligence runtime.
main_path = "backend/app/main.py"
main = read(main_path)
if "from app.pilot_value import router as pilot_value_router" not in main:
    main = main.replace(
        "from app.pilot_platform import router as pilot_platform_router\n",
        "from app.pilot_platform import router as pilot_platform_router\n"
        "from app.pilot_value import router as pilot_value_router\n",
        1,
    )
if "app.include_router(pilot_value_router)" not in main:
    main = main.replace(
        "app.include_router(pilot_platform_router)\n",
        "app.include_router(pilot_platform_router)\n"
        "app.include_router(pilot_value_router)\n",
        1,
    )
old_injection = """    if filename == \"index.html\":
        html = html.replace(
            \"</body>\",
            f'<script src=\"/pilot-platform-v1.js?v={PILOT_BUILD}\" defer></script>\\n</body>',
            1,
        )
"""
new_injection = """    if filename == \"index.html\":
        runtime_scripts = \"\\n\".join(
            (
                f'<script src=\"/pilot-platform-v1.js?v={PILOT_BUILD}\" defer></script>',
                f'<script src=\"/pilot-value-v1.js?v={PILOT_BUILD}\" defer></script>',
                f'<script src=\"/pilot-mission-bridge-v1.js?v={PILOT_BUILD}\" defer></script>',
            )
        )
        html = html.replace(\"</body>\", f\"{runtime_scripts}\\n</body>\", 1)
"""
if "pilot-mission-bridge-v1.js" not in main:
    if old_injection not in main:
        raise RuntimeError("main.py runtime injection marker not found")
    main = main.replace(old_injection, new_injection, 1)
write(main_path, main)

# 2. Make the direct Pilot -> Mission bridge explicit and testable.
replace_once(
    "frontend/pilot-v1/pilot-mission-bridge-v1.js",
    "form.addEventListener('submit',()=>{const pending=readPending();if(!pending)return;pending.submitted=true;pending.submittedAt=Date.now();writePending(pending);},{capture:true});",
    "form.addEventListener('submit',()=>{const pending=readPending();if(!pending)return;writePending({...pending,submitted:true,submittedAt:Date.now()});},{capture:true});",
)

# 3. Restore the six-profile universal catalog and formal programme origins.
platform_path = "backend/app/pilot_platform.py"
platform = read(platform_path)
constants_marker = 'TRANSVERSAL_CONDITIONS=["assumptions","constraints","gaps","uncertainty","provenance","confidence"]\n'
constants_block = constants_marker + '''PROFILE_CATALOG_VERSION="2026-09-01.1"\nEXPECTED_PROFILE_KEYS=("cross_sector","hospitality","public_sector","industrial_operations","territorial_lab","research_and_innovation")\nPROGRAM_SOURCES={\n"direct":{"key":"direct","label":"Piloto direto","description":"Piloto acordado diretamente com uma organização pública ou privada."},\n"tourism_advance":{"key":"tourism_advance","label":"Tourism Advance","description":"Programa de validação externa no setor do turismo e alojamento."},\n"hospitality_open_innovation":{"key":"hospitality_open_innovation","label":"Hospitality Open Innovation","description":"Programa de inovação aberta para validação em contexto hoteleiro real."},\n"public_program":{"key":"public_program","label":"Programa público","description":"Acelerador, concurso ou programa promovido por entidade pública."},\n"private_client":{"key":"private_client","label":"Cliente privado","description":"Projeto contratado por empresa ou instituição privada."},\n"academic_partnership":{"key":"academic_partnership","label":"Parceria académica","description":"Investigação aplicada, laboratório vivo ou validação metodológica."}}\n'''
if "PROFILE_CATALOG_VERSION=" not in platform:
    if constants_marker not in platform:
        raise RuntimeError("pilot_platform constants marker not found")
    platform = platform.replace(constants_marker, constants_block, 1)

territorial_line = '"territorial_lab":{"key":"territorial_lab","label":"Laboratório territorial","description":"Experimentação multientidade com condições, resultados e memória territorial.","context_labels":["território","comunidade","ecossistema","parceria","infraestrutura"],"typical_sources":["cartografia","monitorização","participação","ambiente","economia"]}}\nTEMPLATES={'
research_profiles = '"territorial_lab":{"key":"territorial_lab","label":"Laboratório territorial","description":"Experimentação multientidade com condições, resultados e memória territorial.","context_labels":["território","comunidade","ecossistema","parceria","infraestrutura"],"typical_sources":["cartografia","monitorização","participação","ambiente","economia"]},\n"research_and_innovation":{"key":"research_and_innovation","label":"Investigação e inovação","description":"Experiências, programas de I&D, consórcios, laboratórios aplicados e validação de hipóteses em contexto real.","context_labels":["programa de I&D","laboratório","consórcio","experiência","projeto"],"typical_sources":["protocolo","dataset","instrumentação","publicações","resultados"]}}\nif set(SECTOR_PROFILES)!=set(EXPECTED_PROFILE_KEYS):raise RuntimeError("O catálogo oficial de perfis SRIS foi alterado sem revisão de contrato.")\nTEMPLATES={'
if '"research_and_innovation":{"key":"research_and_innovation"' not in platform:
    if territorial_line not in platform:
        raise RuntimeError("sector profile closing marker not found")
    platform = platform.replace(territorial_line, research_profiles, 1)

if '"research_and_innovation_validation"' not in platform:
    marker = "\nDEFAULT_WORK_ITEMS="
    idx = platform.find(marker)
    if idx < 0:
        raise RuntimeError("DEFAULT_WORK_ITEMS marker not found")
    before = platform[:idx].rstrip()
    if not before.endswith("}"):
        raise RuntimeError("TEMPLATES dictionary closing brace not found")
    research_template = ''',\n"research_and_innovation_validation":{"key":"research_and_innovation_validation","label":"Investigação e inovação · Validação aplicada","sector_profile":"research_and_innovation","description":"Desenhar uma experiência, testar uma hipótese em contexto real e preservar resultados, limitações e aprendizagem.","scope_hint":"Uma hipótese explícita, um protocolo delimitado, fontes identificadas, critérios de refutação e uma decisão de continuidade.","metrics":[{"metric_key":"primary_research_outcome","label":"Resultado principal da investigação","category":"learning","unit":"","direction":"increase"},{"metric_key":"evidence_robustness","label":"Robustez da evidência","category":"governance","unit":"%","direction":"increase"},{"metric_key":"implementation_cost","label":"Custo da experiência","category":"economic","unit":"EUR","direction":"decrease"},{"metric_key":"replicability_readiness","label":"Prontidão para replicação","category":"learning","unit":"%","direction":"increase"}],"data_sources":[{"name":"Protocolo e hipótese de investigação","source_type":"document","required":True},{"name":"Dataset e instrumentação","source_type":"database","required":True},{"name":"Registos de execução e desvios","source_type":"manual","required":True},{"name":"Publicações e evidência externa","source_type":"external","required":False}]}\n}'''
    platform = before[:-1] + research_template + platform[idx:]

old_profiles_endpoint = '@router.get("/profiles")\ndef list_profiles(organization_id:str,_:Membership=Depends(require_org_role(*READ_ROLES)))->dict[str,Any]:return {"profiles":list(SECTOR_PROFILES.values()),"architecture":"universal_core_configurable_profiles","user_moments":USER_MOMENTS,"canonical_records":CANONICAL_RECORDS,"transversal_conditions":TRANSVERSAL_CONDITIONS}\n@router.get("/templates")\ndef list_templates(organization_id:str,_:Membership=Depends(require_org_role(*READ_ROLES)))->dict[str,Any]:return {"templates":list(TEMPLATES.values()),"profiles":list(SECTOR_PROFILES.values())}'
new_profiles_endpoint = '@router.get("/profiles")\ndef list_profiles(organization_id:str,_:Membership=Depends(require_org_role(*READ_ROLES)))->dict[str,Any]:return {"profiles":list(SECTOR_PROFILES.values()),"profile_catalog_version":PROFILE_CATALOG_VERSION,"profile_count":len(SECTOR_PROFILES),"program_sources":list(PROGRAM_SOURCES.values()),"architecture":"universal_core_configurable_profiles","user_moments":USER_MOMENTS,"canonical_records":CANONICAL_RECORDS,"transversal_conditions":TRANSVERSAL_CONDITIONS}\n@router.get("/templates")\ndef list_templates(organization_id:str,_:Membership=Depends(require_org_role(*READ_ROLES)))->dict[str,Any]:return {"templates":list(TEMPLATES.values()),"profiles":list(SECTOR_PROFILES.values()),"profile_catalog_version":PROFILE_CATALOG_VERSION,"program_sources":list(PROGRAM_SOURCES.values())}'
if '"profile_catalog_version":PROFILE_CATALOG_VERSION' not in platform:
    if old_profiles_endpoint not in platform:
        raise RuntimeError("profile endpoints marker not found")
    platform = platform.replace(old_profiles_endpoint, new_profiles_endpoint, 1)
write(platform_path, platform)

# 4. Make release identity and database revision inspectable without exposing secrets.
capabilities_path = "backend/app/pilot_capabilities.py"
capabilities = read(capabilities_path)
capabilities = capabilities.replace(
    "import os\n\nfrom fastapi import APIRouter\n",
    "import os\nfrom pathlib import Path\n\nfrom alembic.config import Config\nfrom alembic.script import ScriptDirectory\nfrom fastapi import APIRouter, Depends\nfrom sqlalchemy import text\nfrom sqlalchemy.orm import Session\n",
    1,
)
capabilities = capabilities.replace(
    "from app.atlas_platform.auth_delivery import auth_email_delivery_ready\n",
    "from app.atlas_platform.auth_delivery import auth_email_delivery_ready\n"
    "from app.atlas_platform.database import get_db\n"
    "from app.pilot_platform import (\n"
    "    PROFILE_CATALOG_VERSION,\n"
    "    PROGRAM_SOURCES,\n"
    "    SECTOR_PROFILES,\n"
    ")\n",
    1,
)
capabilities = capabilities.replace(
    'PILOT_BUILD = "20260901-pilot-mission-platform-v31"',
    'PILOT_BUILD = "20260901-pilot-mission-intelligence-rc1"',
    1,
)
old_profile_list = '''        "configurable_sector_profiles": [
            "cross_sector",
            "hospitality",
            "public_sector",
            "industrial_operations",
            "territorial_lab",
        ],'''
new_profile_list = '''        "configurable_sector_profiles": list(SECTOR_PROFILES),
        "profile_catalog_version": PROFILE_CATALOG_VERSION,
        "profile_count": len(SECTOR_PROFILES),
        "program_sources": list(PROGRAM_SOURCES),'''
if old_profile_list in capabilities:
    capabilities = capabilities.replace(old_profile_list, new_profile_list, 1)
if '"pilot_value_case": True' not in capabilities:
    capabilities = capabilities.replace(
        '        "pilot_scale_recommendation": True,\n',
        '        "pilot_scale_recommendation": True,\n'
        '        "pilot_value_case": True,\n'
        '        "pilot_collaboration": True,\n'
        '        "pilot_report_suite": True,\n'
        '        "direct_pilot_to_mission_creation": True,\n',
        1,
    )
old_build_endpoint = '''@router.get("/build")
def pilot_build() -> dict[str, str]:
    return {"build": PILOT_BUILD, "product": "SRIS Pilot & Mission Intelligence"}
'''
new_build_endpoint = '''PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _migration_heads() -> list[str]:
    configuration = Config(str(PROJECT_ROOT / "alembic.ini"))
    return sorted(ScriptDirectory.from_config(configuration).get_heads())


@router.get("/build")
def pilot_build() -> dict[str, str]:
    return {
        "build": PILOT_BUILD,
        "product": "SRIS Pilot & Mission Intelligence",
        "branch": os.getenv("RAILWAY_GIT_BRANCH", "local"),
        "commit_sha": os.getenv("RAILWAY_GIT_COMMIT_SHA", "local"),
    }


@router.get("/release-state")
def pilot_release_state(db: Session = Depends(get_db)) -> dict:
    database_revisions = list(
        db.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num"))
        .scalars()
        .all()
    )
    return {
        "build": PILOT_BUILD,
        "service": os.getenv("RAILWAY_SERVICE_NAME", "local"),
        "environment": os.getenv("RAILWAY_ENVIRONMENT_NAME", "local"),
        "branch": os.getenv("RAILWAY_GIT_BRANCH", "local"),
        "commit_sha": os.getenv("RAILWAY_GIT_COMMIT_SHA", "local"),
        "database_revisions": database_revisions,
        "migration_heads": _migration_heads(),
        "database_at_head": sorted(database_revisions) == _migration_heads(),
        "profile_catalog_version": PROFILE_CATALOG_VERSION,
        "profile_count": len(SECTOR_PROFILES),
        "profile_keys": list(SECTOR_PROFILES),
        "program_source_keys": list(PROGRAM_SOURCES),
    }
'''
if "def pilot_release_state" not in capabilities:
    if old_build_endpoint not in capabilities:
        raise RuntimeError("pilot_capabilities build endpoint marker not found")
    capabilities = capabilities.replace(old_build_endpoint, new_build_endpoint, 1)
write(capabilities_path, capabilities)

# 5. Present five navigable moments while preserving eight canonical records.
app_path = "frontend/pilot-v1/app.js"
app = read(app_path)
cycle_pattern = r"const CANONICAL_MISSION_CHAIN_PT=.*?\n\];"
cycle_replacement = """const CANONICAL_MISSION_CHAIN_PT='Observação → Evidência → Hipótese → Alternativa → Decisão → Ação → Resultado → Aprendizagem';
const MISSION_CYCLE_STEPS=[
  {label:'Contexto',description:'Enquadrar o problema, o objetivo, o decisor, os pressupostos e as restrições.',tab:'summary'},
  {label:'Evidência',description:'Reunir Observação, Evidência e Hipótese sem confundir facto, explicação e lacuna.',tab:'graph'},
  {label:'Decisão',description:'Comparar Alternativas e registar a Decisão humana, o fundamento, o risco e a reversibilidade.',tab:'comparison'},
  {label:'Medição',description:'Executar a Ação, observar o Resultado e comparar baseline, objetivo, efeitos e limitações.',tab:'validation'},
  {label:'Memória',description:'Rever e publicar a Aprendizagem, preservando validade, contexto e condições de revalidação.',tab:'memory'},
];"""
app, count = re.subn(cycle_pattern, cycle_replacement, app, count=1, flags=re.S)
if count != 1:
    raise RuntimeError(f"Expected one mission cycle declaration, found {count}")
app = app.replace("`ETAPA ${activeIndex+1} DE ${MISSION_CYCLE_STEPS.length}`", "`MOMENTO ${activeIndex+1} DE ${MISSION_CYCLE_STEPS.length}`")
app = app.replace("trabalhar esta etapa", "trabalhar este momento")
write(app_path, app)

index_path = "frontend/pilot-v1/index.html"
index = read(index_path)
old_tabs = '''            <div class="decision-chain" role="tablist" aria-label="Etapas da cadeia canónica de missão do SRIS">
              <button class="active" type="button" role="tab" aria-selected="true" aria-controls="cycle-step-panel" tabindex="0" data-cycle-step="0">Contexto</button>
              <button type="button" role="tab" aria-selected="false" aria-controls="cycle-step-panel" tabindex="-1" data-cycle-step="1">Observação</button>
              <button type="button" role="tab" aria-selected="false" aria-controls="cycle-step-panel" tabindex="-1" data-cycle-step="2">Evidência</button>
              <button type="button" role="tab" aria-selected="false" aria-controls="cycle-step-panel" tabindex="-1" data-cycle-step="3">Hipótese</button>
              <button type="button" role="tab" aria-selected="false" aria-controls="cycle-step-panel" tabindex="-1" data-cycle-step="4">Alternativas</button>
              <button type="button" role="tab" aria-selected="false" aria-controls="cycle-step-panel" tabindex="-1" data-cycle-step="5">Decisão</button>
              <button type="button" role="tab" aria-selected="false" aria-controls="cycle-step-panel" tabindex="-1" data-cycle-step="6">Ação</button>
              <button type="button" role="tab" aria-selected="false" aria-controls="cycle-step-panel" tabindex="-1" data-cycle-step="7">Medição</button>
              <button type="button" role="tab" aria-selected="false" aria-controls="cycle-step-panel" tabindex="-1" data-cycle-step="8">Resultado</button>
              <button type="button" role="tab" aria-selected="false" aria-controls="cycle-step-panel" tabindex="-1" data-cycle-step="9">Aprendizagem</button>
              <button type="button" role="tab" aria-selected="false" aria-controls="cycle-step-panel" tabindex="-1" data-cycle-step="10">Memória</button>
            </div>'''
new_tabs = '''            <div class="decision-chain" role="tablist" aria-label="Cinco momentos do percurso de missão do SRIS">
              <button class="active" type="button" role="tab" aria-selected="true" aria-controls="cycle-step-panel" tabindex="0" data-cycle-step="0">Contexto</button>
              <button type="button" role="tab" aria-selected="false" aria-controls="cycle-step-panel" tabindex="-1" data-cycle-step="1">Evidência</button>
              <button type="button" role="tab" aria-selected="false" aria-controls="cycle-step-panel" tabindex="-1" data-cycle-step="2">Decisão</button>
              <button type="button" role="tab" aria-selected="false" aria-controls="cycle-step-panel" tabindex="-1" data-cycle-step="3">Medição</button>
              <button type="button" role="tab" aria-selected="false" aria-controls="cycle-step-panel" tabindex="-1" data-cycle-step="4">Memória</button>
            </div>'''
if old_tabs not in index:
    raise RuntimeError("index.html eleven-step navigation marker not found")
index = index.replace(old_tabs, new_tabs, 1)
index = index.replace('id="cycle-position">ETAPA 1 DE 11', 'id="cycle-position">MOMENTO 1 DE 5', 1)
index = index.replace('id="cycle-open-step" type="button">Abrir esta etapa', 'id="cycle-open-step" type="button">Abrir este momento', 1)
write(index_path, index)

# 6. Update contracts so they protect the corrected product rather than the obsolete eleven-step UI.
release_test = "frontend/tests/pilot_release_hardening_contract.test.js"
release = read(release_test)
release = release.replace('data-cycle-step="7">Medição', 'data-cycle-step="3">Medição')
release = release.replace('data-cycle-step="10">Memória', 'data-cycle-step="4">Memória')
write(release_test, release)

decision_test = "frontend/tests/pilot_decision_first_contract.test.js"
decision = read(decision_test)
decision = decision.replace('length,11);', 'length,5);')
decision = decision.replace('role="tablist" aria-label="Etapas da cadeia canónica', 'role="tablist" aria-label="Cinco momentos do percurso de missão')
write(decision_test, decision)

platform_test = "frontend/tests/pilot_platform_contract.test.js"
platform_contract = read(platform_test)
platform_contract = platform_contract.replace(
    "['cross_sector','hospitality','public_sector','industrial_operations','territorial_lab']",
    "['cross_sector','hospitality','public_sector','industrial_operations','territorial_lab','research_and_innovation']",
)
platform_contract = platform_contract.replace(
    "['hospitality_resource_efficiency','hospitality_operational_intelligence','public_service_improvement','investment_validation']",
    "['hospitality_resource_efficiency','hospitality_operational_intelligence','public_service_improvement','investment_validation','research_and_innovation_validation']",
)
if "PROFILE_CATALOG_VERSION" not in platform_contract:
    platform_contract = platform_contract.replace(
        "  assert.match(domain,/program_source/);\n",
        "  assert.match(domain,/PROFILE_CATALOG_VERSION/);\n"
        "  assert.match(domain,/EXPECTED_PROFILE_KEYS/);\n"
        "  assert.match(domain,/program_source/);\n",
        1,
    )
write(platform_test, platform_contract)

backend_platform_test = "backend/tests/test_pilot_platform.py"
backend_test = read(backend_platform_test)
if 'assert payload["profile_count"] == 6' not in backend_test:
    backend_test = backend_test.replace(
        '    assert payload["pilot_portfolio"] is True\n',
        '    assert payload["pilot_portfolio"] is True\n'
        '    assert payload["profile_count"] == 6\n'
        '    assert "research_and_innovation" in payload["configurable_sector_profiles"]\n'
        '    assert "tourism_advance" in payload["program_sources"]\n',
        1,
    )
backend_test = backend_test.replace(
    '        "investment_validation",\n    } <= keys',
    '        "investment_validation",\n        "research_and_innovation_validation",\n    } <= keys',
    1,
)
write(backend_platform_test, backend_test)

# 7. Reproduce the real staging path: an existing 0022 database upgraded to the current head.
migration_test = "backend/tests/test_alembic_migrations.py"
migration = read(migration_test)
for table in (
    '            "sris_pilots",\n',
    '            "sris_pilot_missions",\n',
    '            "sris_pilot_metrics",\n',
    '            "sris_pilot_data_sources",\n',
    '            "sris_pilot_work_items",\n',
    '            "sris_pilot_value_items",\n',
    '            "sris_pilot_collaborators",\n',
):
    if table.strip() not in migration:
        migration = migration.replace('            "pilot_mission_module_reviews",\n', '            "pilot_mission_module_reviews",\n' + table, 1)
if "def test_existing_0022_staging_schema_upgrades_to_current_head" not in migration:
    migration += '''\n\ndef test_existing_0022_staging_schema_upgrades_to_current_head() -> None:\n    repo_root = Path(__file__).resolve().parents[2]\n    revision_files = {path.name for path in (repo_root / "migrations" / "versions").glob("*.py")}\n    assert not any("20260831_0023" in name for name in revision_files)\n    assert "20260901_0023_pilot_mission_platform.py" in revision_files\n    assert "20260901_0024_pilot_value_collaboration_reports.py" in revision_files\n\n    with TemporaryDirectory(prefix="atlas-staging-0022-upgrade-") as tmp:\n        database_path = Path(tmp) / "staging-at-0022.db"\n        database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"\n        run_alembic(repo_root, "upgrade", "20260827_0022", database_url=database_url)\n\n        engine = create_engine(database_url)\n        try:\n            with engine.connect() as connection:\n                assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20260827_0022"\n        finally:\n            engine.dispose()\n\n        run_alembic(repo_root, "upgrade", "head", database_url=database_url)\n        engine = create_engine(database_url)\n        try:\n            with engine.connect() as connection:\n                assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20260901_0024"\n        finally:\n            engine.dispose()\n\n        assert {\n            "sris_pilots",\n            "sris_pilot_missions",\n            "sris_pilot_metrics",\n            "sris_pilot_data_sources",\n            "sris_pilot_work_items",\n            "sris_pilot_value_items",\n            "sris_pilot_collaborators",\n        }.issubset(table_names(database_url))\n'''
write(migration_test, migration)

# 8. Make the permanent CI exercise the complete candidate.
workflow_path = ".github/workflows/atlas-core-ci.yml"
workflow = read(workflow_path)
if "Run Pilot value, collaboration and report tests" not in workflow:
    workflow = workflow.replace(
        "      - name: Run Pilot and Mission Intelligence platform tests\n        run: python -m pytest backend/tests/test_pilot_platform.py\n",
        "      - name: Run Pilot and Mission Intelligence platform tests\n"
        "        run: python -m pytest backend/tests/test_pilot_platform.py\n\n"
        "      - name: Run Pilot value, collaboration and report tests\n"
        "        run: python -m pytest backend/tests/test_pilot_value.py\n\n"
        "      - name: Run negative tenant-isolation tests\n"
        "        run: python -m pytest backend/tests/test_pilot_tenant_isolation.py\n",
        1,
    )
write(workflow_path, workflow)

# 9. Keep test-only dependencies out of the deployed runtime image.
docker_path = "Dockerfile"
docker = read(docker_path)
docker = docker.replace('python -m pip install --no-cache-dir -e ".[test]"', 'python -m pip install --no-cache-dir -e "."')
write(docker_path, docker)

# 10. Final static guards before tests run.
for path in (app_path, index_path):
    source = read(path)
    if "ETAPA 1 DE 11" in source or 'data-cycle-step="10"' in source:
        raise RuntimeError(f"Obsolete eleven-step navigation remains in {path}")

print("Pilot release candidate reconciliation completed.")
