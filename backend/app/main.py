from pathlib import Path
from uuid import uuid4

from fastapi import Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from app.atlas_platform.api import app
from app.atlas_platform.workspace_scope import (
    reset_active_organization_id,
    set_active_organization_id,
)
from app.internal_analytics import (
    dashboard_router as internal_analytics_dashboard_router,
    router as internal_analytics_router,
    safe_track_request,
)
from app.pilot_epistemic import router as evidence_graph_router
from app.learning_lineage import router as learning_lineage_router
from app.mission_intelligence.evolution_api import router as organizational_learning_router
from app.mission_intelligence.learning_api import router as learning_inheritance_router
from app.mission_intelligence.memory_api import router as organizational_memory_router
from app.mission_intelligence import memory_models  # noqa: F401
from app.pilot_capabilities import PILOT_BUILD, router as pilot_capabilities_router
from app.pilot_platform import router as pilot_platform_router
from app.pilot_value import router as pilot_value_router
from app.pilot_product_secure import router as pilot_product_router
from app.pilot_intelligence import router as pilot_intelligence_router
from app.pilot_alternative_matrix import router as pilot_alternative_matrix_router
from app.pilot_business_case import router as pilot_business_case_router
from app.pilot_decision_cycle import router as pilot_decision_cycle_router
from app.pilot_mission_state import router as pilot_mission_state_router
from app.pilot_operations import PilotRateLimitMiddleware, router as pilot_operations_router
from app.pilot_validation import router as pilot_validation_router
from app.pilot_release_readiness import router as pilot_release_readiness_router

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = PROJECT_ROOT / "frontend" / "assets"
FRONTEND_DIR = PROJECT_ROOT / "frontend" / "pilot-v1"

app.include_router(learning_inheritance_router)
app.include_router(organizational_learning_router)
app.include_router(organizational_memory_router)
app.include_router(pilot_capabilities_router)
app.include_router(pilot_platform_router)
app.include_router(pilot_value_router)
app.include_router(pilot_product_router)
app.include_router(pilot_intelligence_router)
app.include_router(pilot_alternative_matrix_router)
app.include_router(pilot_business_case_router)
app.include_router(pilot_decision_cycle_router)
app.include_router(pilot_mission_state_router)
app.include_router(evidence_graph_router)
app.include_router(learning_lineage_router)
app.include_router(pilot_operations_router)
app.include_router(pilot_validation_router)
app.include_router(pilot_release_readiness_router)
app.include_router(internal_analytics_router)
app.include_router(internal_analytics_dashboard_router)
app.add_middleware(PilotRateLimitMiddleware)


@app.middleware("http")
async def security_and_trace_headers(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid4())
    workspace_token = set_active_organization_id(
        request.headers.get("x-sris-organization")
    )
    try:
        response = await call_next(request)
    finally:
        reset_active_organization_id(workspace_token)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["X-SRIS-Pilot-Build"] = PILOT_BUILD
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; connect-src 'self'; "
        "img-src 'self' data:; object-src 'none'; base-uri 'self'; "
        "frame-ancestors 'none'; form-action 'self'"
    )
    if request.headers.get("x-forwarded-proto", "").lower() == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    path = request.url.path
    if 200 <= response.status_code < 300 and request.method == "POST":
        if path == "/api/auth/login":
            safe_track_request(request, event_name="login_success", surface="app")
        elif path.startswith("/api/organizations/") and path.endswith("/pilots"):
            safe_track_request(request, event_name="pilot_created", surface="app")

    is_frontend_asset = path.endswith((".js", ".css", ".svg", ".webp", ".png", ".jpg", ".jpeg"))
    if path.startswith("/api/") or path in {"/", "/app", "/account.html", "/demonstracao", "/pilot-platform-v1.js", "/admin/analytics"}:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    elif is_frontend_asset:
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


def _frontend_html(filename: str) -> str:
    html = (FRONTEND_DIR / filename).read_text(encoding="utf-8")
    html = html.replace("__PILOT_BUILD__", PILOT_BUILD)
    html = html.replace(
        "<head>",
        f'<head>\n  <meta name="sris-pilot-build" content="{PILOT_BUILD}">',
        1,
    )
    if filename == "index.html":
        runtime_scripts = "\n".join(
            (
                f'<script src="/pilot-platform-v1.js?v={PILOT_BUILD}" defer></script>',
                f'<script src="/pilot-value-v1.js?v={PILOT_BUILD}" defer></script>',
                f'<script src="/pilot-mission-bridge-v1.js?v={PILOT_BUILD}" defer></script>',
            )
        )
        html = html.replace("</body>", f"{runtime_scripts}\n</body>", 1)
    return html


def _pilot_platform_javascript() -> str:
    """Serve the pilot UI with a surgical fix for the create-editor reload race."""
    script = (FRONTEND_DIR / "pilot-platform-v1.js").read_text(encoding="utf-8")

    open_section_old = """  function openPilotSection(){
    $$('.section').forEach(section=>section.classList.toggle('active',section.id==='pilots'));$$('.nav button').forEach(button=>button.classList.toggle('active',button.classList.contains('pp-nav-button')));$('#page-title')&&($('#page-title').textContent='Pilotos');$('#sidebar')?.classList.remove('open');$('#menu-btn')?.setAttribute('aria-expanded','false');document.body.classList.remove('menu-open');window.scrollTo({top:0,behavior:'smooth'});loadAll();
  }"""
    open_section_new = """  function openPilotSection(reload=true){
    $$('.section').forEach(section=>section.classList.toggle('active',section.id==='pilots'));$$('.nav button').forEach(button=>button.classList.toggle('active',button.classList.contains('pp-nav-button')));$('#page-title')&&($('#page-title').textContent='Pilotos');$('#sidebar')?.classList.remove('open');$('#menu-btn')?.setAttribute('aria-expanded','false');document.body.classList.remove('menu-open');window.scrollTo({top:0,behavior:'smooth'});if(reload)loadAll();
  }"""
    show_create_old = """  function showCreate(templateKey=''){
    openPilotSection();state.selected=null;"""
    show_create_new = """  function showCreate(templateKey=''){
    openPilotSection(false);state.selected=null;"""
    primary_cta_old = "button.addEventListener('click',()=>{openPilotSection();showCreate()})"
    primary_cta_new = "button.addEventListener('click',()=>showCreate())"

    replacements = (
        (open_section_old, open_section_new, "openPilotSection"),
        (show_create_old, show_create_new, "showCreate"),
        (primary_cta_old, primary_cta_new, "primary pilot CTA"),
    )
    for old, new, label in replacements:
        if old not in script:
            raise RuntimeError(f"Pilot platform patch target not found: {label}")
        script = script.replace(old, new, 1)
    return script


@app.get("/pilot-platform-v1.js", include_in_schema=False)
def pilot_platform_javascript() -> Response:
    return Response(
        _pilot_platform_javascript(),
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "X-SRIS-Pilot-Build": PILOT_BUILD,
        },
    )


@app.get("/", include_in_schema=False)
def pilot_home(request: Request) -> HTMLResponse:
    safe_track_request(request, event_name="app_entry_view", surface="app")
    return HTMLResponse(
        _frontend_html("home.html"),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "X-SRIS-Pilot-Build": PILOT_BUILD,
        },
    )


@app.get("/app", include_in_schema=False)
def pilot_app(request: Request) -> HTMLResponse:
    safe_track_request(request, event_name="app_view", surface="app")
    if (request.query_params.get("src") or "").lower() == "demo":
        safe_track_request(request, event_name="demo_to_app", surface="app")
    return HTMLResponse(
        _frontend_html("index.html"),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "X-SRIS-Pilot-Build": PILOT_BUILD,
        },
    )


@app.get("/account.html", include_in_schema=False)
def pilot_account() -> HTMLResponse:
    return HTMLResponse(
        _frontend_html("account.html"),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "X-SRIS-Pilot-Build": PILOT_BUILD,
        },
    )


@app.get("/demonstracao", include_in_schema=False)
def public_demo(request: Request) -> HTMLResponse:
    safe_track_request(request, event_name="demo_view", surface="demo")
    return HTMLResponse(
        _frontend_html("demonstracao.html"),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "X-SRIS-Pilot-Build": PILOT_BUILD,
        },
    )


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
