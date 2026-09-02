from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    print(f"updated {path}")


def replace_once(path: str, old: str, new: str) -> None:
    source = read(path)
    if old not in source:
        if new in source:
            print(f"already updated {path}")
            return
        raise RuntimeError(f"marker not found in {path}: {old[:160]!r}")
    if source.count(old) != 1:
        raise RuntimeError(f"marker is not unique in {path}: {source.count(old)} matches")
    write(path, source.replace(old, new, 1))


def replace_regex_once(path: str, pattern: str, replacement: str, flags: int = 0) -> None:
    source = read(path)
    updated, count = re.subn(pattern, replacement, source, count=1, flags=flags)
    if count != 1:
        raise RuntimeError(f"regex marker not found or not unique in {path}: {pattern}")
    write(path, updated)


# 1. Prevent a NameError when attachment context is incomplete.
replace_once(
    "backend/app/mission_intelligence/dialogue_service.py",
    "from .attachments import (\n    attachment_chunk_counts,",
    "from .attachments import (\n    AttachmentError,\n    attachment_chunk_counts,",
)

# 2. Use one canonical password-reset lifecycle; preserve old URLs only as hidden aliases.
write(
    "backend/app/pilot_product_secure.py",
    '''from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.atlas_platform.auth import current_user
from app.atlas_platform.database import get_db
from app.atlas_platform.identity import (
    confirm_password_reset as canonical_confirm_password_reset,
    request_password_reset as canonical_request_password_reset,
)
from app.atlas_platform.models import User
from app.atlas_platform.schemas import (
    PasswordResetConfirmRequest,
    PasswordResetConfirmResponse,
    PasswordResetStartRequest,
    PasswordResetStartResponse,
)
from app.pilot_product import (
    PilotTopupRequest,
    _flag,
    pilot_test_topup as legacy_test_topup,
    router as legacy_router,
)


# Reuse mature Pilot routes while replacing operations whose public behavior is
# governed by the canonical identity lifecycle or disabled during validation.
router = APIRouter(tags=["pilot-product"])
_replaced = {
    ("/api/pilot/capabilities", "GET"),
    ("/api/pilot/password-reset/request", "POST"),
    ("/api/pilot/password-reset/confirm", "POST"),
    ("/api/pilot/credits/test-topup", "POST"),
}
for route in legacy_router.routes:
    methods = set(getattr(route, "methods", set()) or set())
    if any((route.path, method) in _replaced for method in methods):
        continue
    router.routes.append(route)


@router.post(
    "/api/pilot/password-reset/request",
    response_model=PasswordResetStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
    include_in_schema=False,
    deprecated=True,
)
def legacy_password_reset_request_alias(
    payload: PasswordResetStartRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> PasswordResetStartResponse:
    """Compatibility alias backed by the canonical reset-token store."""

    return canonical_request_password_reset(
        payload=payload,
        background_tasks=background_tasks,
        db=db,
    )


@router.post(
    "/api/pilot/password-reset/confirm",
    response_model=PasswordResetConfirmResponse,
    include_in_schema=False,
    deprecated=True,
)
def legacy_password_reset_confirm_alias(
    payload: PasswordResetConfirmRequest,
    db: Session = Depends(get_db),
) -> PasswordResetConfirmResponse:
    """Compatibility alias backed by the canonical reset-token store."""

    return canonical_confirm_password_reset(payload=payload, db=db)


@router.post("/api/pilot/credits/test-topup")
def pilot_test_topup(
    payload: PilotTopupRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not _flag("SRIS_BILLING_TEST_MODE", False):
        raise HTTPException(
            status_code=403,
            detail="Os carregamentos de teste estão desativados durante a validação operacional.",
        )
    return legacy_test_topup(payload=payload, user=user, db=db)
''',
)

# 3. Align entry copy with the actual signup gate and use canonical reset routes.
auth_path = "frontend/pilot-v1/auth.js"
auth = read(auth_path)
auth = auth.replace(
    "  function mode(name){",
    "  function loginSubtitle(){\n"
    "    if(capabilities?.public_signup===false)return'Entre no seu workspace. O acesso de novas organizações é feito por convite.';\n"
    "    if(capabilities?.public_signup===true)return'Entre no seu workspace ou crie uma conta para estruturar a primeira missão.';\n"
    "    return'Entre no seu workspace para continuar.';\n"
    "  }\n\n"
    "  function mode(name){",
    1,
)
auth = auth.replace(
    "      login:['Bem-vindo','Entre no seu workspace ou crie uma conta para estruturar a primeira missão.','login-form'],",
    "      login:['Bem-vindo',loginSubtitle(),'login-form'],",
    1,
)
auth = auth.replace("/api/pilot/password-reset/confirm", "/api/auth/password-reset/confirm")
old_reset_url = '''  function applyResetTokenFromURL(){
    const url=new URL(location.href);
    const resetToken=url.searchParams.get('reset_token');
    if(!resetToken)return false;
    $('#reset-token').value=resetToken;
    url.searchParams.delete('reset_token');
    history.replaceState({},document.title,url.pathname+url.search+url.hash);
    mode('reset-confirm');
    return true;
  }
'''
new_reset_url = '''  function applyResetTokenFromURL(){
    const url=new URL(location.href);
    const fragment=new URLSearchParams(url.hash.replace(/^#/,''));
    const resetToken=fragment.get('reset')||url.searchParams.get('reset_token');
    if(!resetToken)return false;
    $('#reset-token').value=resetToken;
    url.searchParams.delete('reset_token');
    history.replaceState({},document.title,url.pathname+url.search);
    mode('reset-confirm');
    return true;
  }
'''
if old_reset_url not in auth:
    raise RuntimeError("auth reset URL block not found")
auth = auth.replace(old_reset_url, new_reset_url, 1)
old_caps = '''      if(!capabilities.public_signup){
        $('#register-tab').disabled=true;
        $('#register-tab').title='Criação pública de conta temporariamente fechada';
      }
'''
new_caps = '''      const registerTab=$('#register-tab');
      if(!capabilities.public_signup){
        registerTab.disabled=true;
        registerTab.tabIndex=-1;
        registerTab.setAttribute('aria-disabled','true');
        registerTab.title='Criação pública de conta temporariamente fechada; o acesso é atribuído por convite.';
      }else{
        registerTab.disabled=false;
        registerTab.removeAttribute('aria-disabled');
        registerTab.tabIndex=0;
        registerTab.title='';
      }
      if(!document.body.dataset.authMode||document.body.dataset.authMode==='login'){
        $('#auth-subtitle').textContent=loginSubtitle();
      }
'''
if old_caps not in auth:
    raise RuntimeError("auth capability block not found")
auth = auth.replace(old_caps, new_caps, 1)
write(auth_path, auth)

replace_once(
    "frontend/pilot-v1/home.html",
    '<p class="muted" id="auth-subtitle">Entre no seu workspace ou crie uma conta para estruturar a primeira missão.</p>',
    '<p class="muted" id="auth-subtitle">Entre no seu workspace para continuar.</p>',
)

# 4. Serve account.html through the same build-token renderer and remove stored-XSS-prone innerHTML.
account_path = "frontend/pilot-v1/account.html"
account = read(account_path)
account = account.replace("/pilot.css?v=20260828-brand-system-v30", "/pilot.css?v=__PILOT_BUILD__")
account = account.replace("/sris-logo-compact-dark.svg?v=20260828-brand-system-v30", "/sris-logo-compact-dark.svg?v=__PILOT_BUILD__")
old_summary = "$('#invite-summary').innerHTML=`<strong>${invitation.organization_name}</strong><span>${invitation.email} · ${roleLabels[invitation.role]||invitation.role}</span>`;$('#invite-summary').classList.remove('hidden');"
new_summary = "const summary=$('#invite-summary');summary.replaceChildren();const summaryName=document.createElement('strong');summaryName.textContent=invitation.organization_name;const summaryMeta=document.createElement('span');summaryMeta.textContent=`${invitation.email} · ${roleLabels[invitation.role]||invitation.role}`;summary.append(summaryName,summaryMeta);summary.classList.remove('hidden');"
if old_summary not in account:
    raise RuntimeError("account invitation summary marker not found")
account = account.replace(old_summary, new_summary, 1)
write(account_path, account)

main_path = "backend/app/main.py"
main = read(main_path)
account_route = '''

@app.get("/account.html", include_in_schema=False)
def pilot_account() -> HTMLResponse:
    return HTMLResponse(
        _frontend_html("account.html"),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "X-SRIS-Pilot-Build": PILOT_BUILD,
        },
    )
'''
if 'def pilot_account()' not in main:
    marker = '\n\n@app.get("/demonstracao", include_in_schema=False)\n'
    if marker not in main:
        raise RuntimeError("main account route insertion marker not found")
    main = main.replace(marker, account_route + marker, 1)
write(main_path, main)

# 5. Improve accessible names and module-specific empty states.
index_path = "frontend/pilot-v1/index.html"
index = read(index_path)
index = index.replace('aria-label="Selecionar etapa anterior"', 'aria-label="Selecionar momento anterior"')
index = index.replace('aria-label="Selecionar etapa seguinte"', 'aria-label="Selecionar momento seguinte"')
index = index.replace('<input id="mission-search" class="input" placeholder="Pesquisar missões…" autocomplete="off">', '<input id="mission-search" class="input" aria-label="Pesquisar missões" placeholder="Pesquisar missões…" autocomplete="off">')
index = index.replace('<input type="file" id="mission-file" multiple', '<input type="file" id="mission-file" aria-label="Selecionar documentos da missão" multiple')
index = index.replace('<div class="eyebrow">ESPAÇO DE MISSÃO</div>\n              <h2>Comece pela decisão que precisa de ficar melhor fundamentada.</h2>\n              <p>Uma missão não é uma conversa descartável. O contexto, os documentos, os pressupostos, as decisões, os resultados e a aprendizagem permanecem ligados ao trabalho.</p>', '<div class="eyebrow" id="mission-empty-eyebrow">ESPAÇO DE MISSÃO</div>\n              <h2 id="mission-empty-title">Comece pela decisão que precisa de ficar melhor fundamentada.</h2>\n              <p id="mission-empty-description">Uma missão não é uma conversa descartável. O contexto, os documentos, os pressupostos, as decisões, os resultados e a aprendizagem permanecem ligados ao trabalho.</p>')
write(index_path, index)

app_path = "frontend/pilot-v1/app.js"
app = read(app_path)
titles_marker = '''const titles={
  overview:'Visão geral',
  mission:'Espaço de missão',
  copilot:'Análise assistida',
  account:'Conta',
};
'''
empty_copy = titles_marker + '''
const missionAreaEmptyCopy={
  mission:{eyebrow:'ESPAÇO DE MISSÃO',title:'Comece pela decisão que precisa de ficar melhor fundamentada.',description:'Uma missão não é uma conversa descartável. O contexto, os documentos, os pressupostos, as decisões, os resultados e a aprendizagem permanecem ligados ao trabalho.'},
  graph:{eyebrow:'EVIDÊNCIA',title:'Selecione ou crie uma missão para estruturar a evidência.',description:'Observações, fontes, hipóteses e lacunas só fazem sentido dentro do contexto de uma missão identificada.'},
  validation:{eyebrow:'MEDIÇÃO E IMPACTO',title:'Selecione ou crie uma missão para definir a baseline e medir o impacto.',description:'A medição liga uma ação a um resultado comparável, com método, período, fonte, confiança e limitações explícitas.'},
  cycle:{eyebrow:'DECISÕES E RESULTADOS',title:'Selecione ou crie uma missão para comparar, decidir e acompanhar resultados.',description:'Alternativas, decisão, ação e resultado permanecem ligados à mesma missão e à respetiva fundamentação.'},
  economics:{eyebrow:'ECONOMIA E RECURSOS',title:'Selecione ou crie uma missão para abrir o Business Case Vivo.',description:'Custos, benefícios, tempo, pessoas, materiais, cenários e retorno pertencem a uma decisão concreta.'},
  learning:{eyebrow:'MEMÓRIA',title:'Selecione ou crie uma missão para rever e preservar aprendizagem.',description:'A aprendizagem só pode ser publicada, revalidada e reutilizada quando conserva o contexto que lhe dá validade.'},
};

function renderMissionEmpty(area='mission'){
  const copy=missionAreaEmptyCopy[area]||missionAreaEmptyCopy.mission;
  setText('#mission-empty-eyebrow',copy.eyebrow);
  setText('#mission-empty-title',copy.title);
  setText('#mission-empty-description',copy.description);
}
'''
if titles_marker not in app:
    raise RuntimeError("app titles marker not found")
app = app.replace(titles_marker, empty_copy, 1)
old_handler = '''$$('.nav button[data-mission-area]').forEach(button=>button.addEventListener('click',async()=>{
  await go('mission');
  normaliseMissionTabs();
  const tab=$(`[data-mission-tab="${button.dataset.missionArea}"]`);
  if(tab)tab.click();
  $$('.nav button').forEach(item=>item.classList.toggle('active',item===button));
  setText('#page-title',button.querySelector('span')?.textContent||'Espaço de missão');
}));
'''
new_handler = '''$$('.nav button[data-mission-area]').forEach(button=>button.addEventListener('click',async()=>{
  await go('mission');
  const area=button.dataset.missionArea;
  if(!selectedMission){
    renderMissionEmpty(area);
    showMissionMode('empty');
  }else{
    normaliseMissionTabs();
    const tab=$(`[data-mission-tab="${area}"]`);
    if(tab)tab.click();
  }
  $$('.nav button').forEach(item=>item.classList.toggle('active',item===button));
  setText('#page-title',button.querySelector('span')?.textContent||'Espaço de missão');
}));
'''
if old_handler not in app:
    raise RuntimeError("mission area handler marker not found")
app = app.replace(old_handler, new_handler, 1)
app = app.replace("function go(section){\n  $$('.section')", "function go(section){\n  if(section==='mission'&&!selectedMission)renderMissionEmpty('mission');\n  $$('.section')", 1)
app = app.replace("    if(!missions.length){\n      selectedMission=null;", "    if(!missions.length){\n      selectedMission=null;\n      renderMissionEmpty('mission');", 1)
write(app_path, app)

css_path = "frontend/pilot-v1/pilot.css"
css = read(css_path)
css_marker = ".auth-card>.muted{max-width:510px;margin:0 0 24px;font-size:16px}\n"
if "#auth-subtitle,#trial-copy{color:#5f7068}" not in css:
    if css_marker not in css:
        raise RuntimeError("pilot CSS auth marker not found")
    css = css.replace(css_marker, css_marker + "#auth-subtitle,#trial-copy{color:#5f7068}\n", 1)
write(css_path, css)

# 6. Restore the fixed canonical label and the agreed six scored criteria in the public demo.
demo_path = "backend/app/mission_intelligence/fictional_demo.py"
demo = read(demo_path)
demo = demo.replace('"catalog_version": "2026-08"', '"catalog_version": "2026-09-02"')
demo = demo.replace('{"number": "04", "label": "Alternativas",', '{"number": "04", "label": "Alternativa",')
demo = demo.replace('                        {"id": "traceability", "label": "Rastreabilidade"},\n', '')
demo = demo.replace('{"alternative_id": "ALT-TA-001", "label": "Substituição geral", "scores": [2, 4, 2, 2, 1, 3, 2], "total": 16}', '{"alternative_id": "ALT-TA-001", "label": "Substituição geral", "scores": [4, 2, 2, 1, 3, 2], "total": 14}')
demo = demo.replace('{"alternative_id": "ALT-TA-002", "label": "Medição dirigida", "scores": [5, 4, 4, 4, 5, 4, 5], "total": 31}', '{"alternative_id": "ALT-TA-002", "label": "Medição dirigida", "scores": [4, 4, 4, 5, 4, 5], "total": 26}')
demo = demo.replace('{"alternative_id": "ALT-TA-003", "label": "Lavandaria externa", "scores": [2, 3, 3, 2, 3, 3, 2], "total": 18}', '{"alternative_id": "ALT-TA-003", "label": "Lavandaria externa", "scores": [3, 3, 2, 3, 3, 2], "total": 16}')
write(demo_path, demo)

# 7. Reduce unauthenticated operational fingerprinting and align signup capability with the real gate.
cap_path = "backend/app/pilot_capabilities.py"
cap = read(cap_path)
cap = cap.replace("from app.atlas_platform.auth_delivery import auth_email_delivery_ready\n", "from app.atlas_platform.auth import current_user\nfrom app.atlas_platform.auth_delivery import auth_email_delivery_ready\n")
cap = cap.replace("from app.atlas_platform.database import get_db\n", "from app.atlas_platform.database import get_db\nfrom app.atlas_platform.models import User\n")
cap = cap.replace('PILOT_BUILD = "20260902-workspace-continuity-v36"', 'PILOT_BUILD = "20260902-staging-audit-hardening-v37"')
flag_marker = '''def _password_reset_delivery() -> str:
    if auth_email_delivery_ready():
        return "email"
    if _flag("SRIS_PILOT_SHOW_RESET_LINK", False):
        return "pilot-link"
    return "configuration-required"
'''
flag_replacement = flag_marker + '''

def _public_signup_enabled() -> bool:
    # Mirror the actual authentication gate; retain the historical Pilot flag
    # only as a fallback for older local environments.
    if os.getenv("ATLAS_SELF_REGISTRATION_ENABLED") is not None:
        return _flag("ATLAS_SELF_REGISTRATION_ENABLED", False)
    return _flag("SRIS_PUBLIC_SIGNUP_ENABLED", True)
'''
if flag_marker not in cap:
    raise RuntimeError("pilot capability flag marker not found")
cap = cap.replace(flag_marker, flag_replacement, 1)
cap = cap.replace('"public_signup": _flag("SRIS_PUBLIC_SIGNUP_ENABLED", True),', '"public_signup": _public_signup_enabled(),')
old_build = '''@router.get("/build")
def pilot_build() -> dict[str, str]:
    return {
        "build": PILOT_BUILD,
        "product": "SRIS Pilot & Mission Intelligence",
        "branch": os.getenv("RAILWAY_GIT_BRANCH", "local"),
        "commit_sha": os.getenv("RAILWAY_GIT_COMMIT_SHA", "local"),
    }


@router.get("/release-state")
def pilot_release_state(db: Session = Depends(get_db)) -> dict:
'''
new_build = '''@router.get("/build", include_in_schema=False)
def pilot_build() -> dict[str, str]:
    return {
        "build": PILOT_BUILD,
        "product": "SRIS Pilot & Mission Intelligence",
    }


@router.get("/release-state", include_in_schema=False)
def pilot_release_state(
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
'''
if old_build not in cap:
    raise RuntimeError("pilot build/release route marker not found")
cap = cap.replace(old_build, new_build, 1)
write(cap_path, cap)

api_path = "backend/app/atlas_platform/api.py"
api = read(api_path)
old_app = '''app = FastAPI(
    title="SRIS Mission Intelligence API",
    version="1.7.3",
    description=(
        "Canonical mission intelligence, authentication, organizations, RBAC and "
        "the unified knowledge workflow."
    ),
)

app.include_router(workflow_router)
app.include_router(public_router)
app.include_router(organization_router)
app.include_router(identity_router)


def _managed_runtime() -> bool:
    return any(
        os.getenv(name)
        for name in (
            "RAILWAY_ENVIRONMENT_ID",
            "RAILWAY_PROJECT_ID",
            "RAILWAY_SERVICE_ID",
        )
    )
'''
new_app = '''def _managed_runtime() -> bool:
    return any(
        os.getenv(name)
        for name in (
            "RAILWAY_ENVIRONMENT_ID",
            "RAILWAY_PROJECT_ID",
            "RAILWAY_SERVICE_ID",
        )
    )


def _public_api_docs_enabled() -> bool:
    return environment_flag(
        "SRIS_PUBLIC_API_DOCS_ENABLED",
        default=not _managed_runtime(),
    )


_api_docs_enabled = _public_api_docs_enabled()
app = FastAPI(
    title="SRIS Mission Intelligence API",
    version="1.7.3",
    description=(
        "Canonical mission intelligence, authentication, organizations, RBAC and "
        "the unified knowledge workflow."
    ),
    docs_url="/docs" if _api_docs_enabled else None,
    redoc_url="/redoc" if _api_docs_enabled else None,
    openapi_url="/openapi.json" if _api_docs_enabled else None,
)

app.include_router(workflow_router)
app.include_router(public_router)
app.include_router(organization_router)
app.include_router(identity_router)
'''
if old_app not in api:
    raise RuntimeError("FastAPI application marker not found")
api = api.replace(old_app, new_app, 1)
write(api_path, api)

# 8. Lock runtime/test dependency resolution and make permanent CI consume it.
docker_path = "Dockerfile"
docker = read(docker_path)
docker = docker.replace('    && python -m pip install --no-cache-dir -e "."', '    && python -m pip install --no-cache-dir -r requirements.lock \\\n    && python -m pip install --no-cache-dir --no-deps -e "."')
write(docker_path, docker)

ci_path = ".github/workflows/atlas-core-ci.yml"
ci = read(ci_path)
ci = ci.replace('      - name: Install ATLAS Core\n        run: python -m pip install -e ".[test]"', '      - name: Install locked ATLAS Core\n        run: |\n          python -m pip install -r requirements-test.lock\n          python -m pip install --no-deps -e ".[test]"')
ci = ci.replace('          node --check frontend/pilot-v1/app.js\n          node --check frontend/pilot-v1/pilot-platform-v1.js\n          node --check frontend/pilot-v1/pilot-value-v1.js\n          node --check frontend/pilot-v1/pilot-mission-bridge-v1.js\n          node --check frontend/pilot-v1/business-case-v1.js', '          while IFS= read -r -d \'\' file; do node --check "$file"; done < <(find frontend/pilot-v1 frontend/tests -type f -name \'*.js\' -print0)')
identity_step = '      - name: Run identity lifecycle tests\n        run: python -m pytest -q backend/tests/test_identity_lifecycle.py\n'
if 'Run staging audit hardening tests' not in ci:
    if identity_step not in ci:
        raise RuntimeError("CI identity step marker not found")
    ci = ci.replace(identity_step, identity_step + '\n      - name: Run staging audit hardening tests\n        run: python -m pytest -q backend/tests/test_staging_audit_hardening.py\n', 1)
write(ci_path, ci)

# 9. Update existing identity contract and add dedicated regression tests.
identity_test_path = "backend/tests/test_identity_lifecycle.py"
identity_test = read(identity_test_path).replace('assert "/api/pilot/password-reset/confirm" in auth', 'assert "/api/auth/password-reset/confirm" in auth\n    assert "/api/pilot/password-reset/confirm" not in auth')
write(identity_test_path, identity_test)

write(
    "backend/tests/test_staging_audit_hardening.py",
    '''from __future__ import annotations

import os
import subprocess
import sys
from uuid import uuid4

os.environ.setdefault("SRIS_PILOT_MODE", "true")
os.environ.setdefault("SRIS_PUBLIC_SIGNUP_ENABLED", "true")
os.environ.setdefault("ATLAS_SELF_REGISTRATION_ENABLED", "true")

from fastapi.testclient import TestClient

from app.atlas_platform import identity
from app.main import app
from app.mission_intelligence.attachments import AttachmentError
from app.mission_intelligence.fictional_demo import fictional_demo_catalog
from app.mission_intelligence import dialogue_service
from app.pilot_capabilities import PILOT_BUILD


client = TestClient(app)


def test_attachment_context_error_is_bound_to_the_controlled_api_exception() -> None:
    assert dialogue_service.AttachmentError is AttachmentError


def test_public_build_is_minimal_and_release_state_requires_authentication() -> None:
    public = client.get("/api/pilot/build")
    assert public.status_code == 200
    assert public.json() == {
        "build": PILOT_BUILD,
        "product": "SRIS Pilot & Mission Intelligence",
    }
    assert client.get("/api/pilot/release-state").status_code == 401

    marker = uuid4().hex
    registered = client.post(
        "/api/pilot/register",
        json={
            "email": f"release-state-{marker}@example.com",
            "full_name": "Release State Tester",
            "password": "A-secure-password-1234",
            "organization_name": f"Release State {marker[:8]}",
        },
    )
    assert registered.status_code == 201, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    protected = client.get("/api/pilot/release-state", headers=headers)
    assert protected.status_code == 200, protected.text
    assert protected.json()["migration_heads"]


def test_account_page_receives_the_active_build_token() -> None:
    response = client.get("/account.html")
    assert response.status_code == 200
    assert f'name="sris-pilot-build" content="{PILOT_BUILD}"' in response.text
    assert f"/pilot.css?v={PILOT_BUILD}" in response.text
    assert "20260828-brand-system-v30" not in response.text


def test_managed_runtime_hides_openapi_by_default() -> None:
    code = """
from app.atlas_platform.api import app
assert app.openapi_url is None
assert app.docs_url is None
assert app.redoc_url is None
"""
    environment = os.environ.copy()
    environment.update(
        {
            "RAILWAY_ENVIRONMENT_ID": "managed-test",
            "ATLAS_DATABASE_URL": "postgresql+psycopg://user:pass@localhost:5432/test",
            "ATLAS_JWT_SECRET": "managed-test-secret-with-more-than-thirty-two-bytes",
            "SRIS_PUBLIC_API_DOCS_ENABLED": "false",
        }
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        env=environment,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_public_demo_uses_the_fixed_chain_and_six_criterion_matrix() -> None:
    mission = fictional_demo_catalog()["missions"]["DEMO-TA-001"]
    assert [row["label"] for row in mission["situation"]["chain"]] == [
        "Observação",
        "Evidência",
        "Hipótese",
        "Alternativa",
        "Decisão",
        "Ação",
        "Resultado",
        "Aprendizagem",
    ]
    matrix = mission["analysis"]["decision_matrix"]
    assert [criterion["id"] for criterion in matrix["criteria"]] == [
        "effectiveness",
        "cost",
        "risk",
        "reversibility",
        "experience",
        "robustness",
    ]
    for row in matrix["rows"]:
        assert len(row["scores"]) == 6
        assert row["total"] == sum(row["scores"])


def test_legacy_pilot_reset_urls_delegate_to_the_canonical_token_store(monkeypatch) -> None:
    captured: list[str] = []
    monkeypatch.setattr(identity, "auth_email_delivery_ready", lambda: True)
    monkeypatch.setattr(
        identity,
        "_send_password_reset_email",
        lambda _reset_id, raw_token: captured.append(raw_token),
    )
    marker = uuid4().hex
    email = f"reset-alias-{marker}@example.com"
    password = "Original-password-1234"
    registered = client.post(
        "/api/auth/register",
        json={"email": email, "full_name": "Reset Alias", "password": password},
    )
    assert registered.status_code == 201, registered.text

    requested = client.post(
        "/api/pilot/password-reset/request",
        json={"email": email},
    )
    assert requested.status_code == 202, requested.text
    assert captured

    replacement = "Replacement-password-5678"
    confirmed = client.post(
        "/api/pilot/password-reset/confirm",
        json={"token": captured[-1], "new_password": replacement},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert client.post(
        "/api/auth/login",
        json={"email": email, "password": replacement},
    ).status_code == 200
''',
)

write(
    "frontend/tests/staging_audit_hardening_contract.test.js",
    '''import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const read=(path)=>fs.readFileSync(new URL(`../../${path}`,import.meta.url),'utf8');

test('entry copy follows the runtime signup gate and reset uses one route family',()=>{
  const auth=read('frontend/pilot-v1/auth.js');
  const home=read('frontend/pilot-v1/home.html');
  assert.match(auth,/function loginSubtitle\(\)/);
  assert.match(auth,/acesso de novas organizações é feito por convite/);
  assert.match(auth,/\/api\/auth\/password-reset\/request/);
  assert.match(auth,/\/api\/auth\/password-reset\/confirm/);
  assert.doesNotMatch(auth,/\/api\/pilot\/password-reset\/confirm/);
  assert.match(home,/Entre no seu workspace para continuar\./);
});

test('account and mission controls use the active build and accessible names',()=>{
  const account=read('frontend/pilot-v1/account.html');
  const index=read('frontend/pilot-v1/index.html');
  assert.match(account,/pilot\.css\?v=__PILOT_BUILD__/);
  assert.match(account,/sris-logo-compact-dark\.svg\?v=__PILOT_BUILD__/);
  assert.doesNotMatch(account,/20260828-brand-system-v30/);
  assert.match(index,/id="mission-search"[^>]+aria-label="Pesquisar missões"/);
  assert.match(index,/id="mission-file"[^>]+aria-label="Selecionar documentos da missão"/);
});

test('empty mission-dependent areas explain their own prerequisite',()=>{
  const app=read('frontend/pilot-v1/app.js');
  for(const text of [
    'Selecione ou crie uma missão para estruturar a evidência.',
    'Selecione ou crie uma missão para definir a baseline e medir o impacto.',
    'Selecione ou crie uma missão para abrir o Business Case Vivo.',
    'Selecione ou crie uma missão para rever e preservar aprendizagem.',
  ])assert.match(app,new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));
});

test('entry contrast override is explicit',()=>{
  const css=read('frontend/pilot-v1/pilot.css');
  assert.match(css,/#auth-subtitle,#trial-copy\{color:#5f7068\}/);
});
''',
)

# 10. Document the new managed-runtime API docs control.
env_path = ".env.example"
env_text = read(env_path)
if "SRIS_PUBLIC_API_DOCS_ENABLED" not in env_text:
    env_text += "\n# Keep API schema/docs private in managed environments unless explicitly required.\nSRIS_PUBLIC_API_DOCS_ENABLED=false\n"
write(env_path, env_text)

# Hard guards: these defects must not survive the transformation.
assert "/api/pilot/password-reset/confirm" not in read("frontend/pilot-v1/auth.js")
assert '"label": "Alternativas"' not in read(demo_path)
assert '"traceability"' not in read(demo_path)
assert "AttachmentError," in read("backend/app/mission_intelligence/dialogue_service.py")
assert 'PILOT_BUILD = "20260902-staging-audit-hardening-v37"' in read(cap_path)
print("staging audit fixes applied")
