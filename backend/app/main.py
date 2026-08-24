from pathlib import Path
import re
from uuid import uuid4

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.atlas_platform.api import app
from app.pilot_epistemic import router as evidence_graph_router
from app.learning_lineage import router as learning_lineage_router
from app.mission_intelligence.evolution_api import router as organizational_learning_router
from app.mission_intelligence.learning_api import router as learning_inheritance_router
from app.mission_intelligence.memory_api import router as organizational_memory_router
from app.mission_intelligence import memory_models  # noqa: F401
from app.pilot_bootstrap import router as pilot_bootstrap_router
from app.pilot_capabilities import router as pilot_capabilities_router
from app.pilot_product_secure import router as pilot_product_router
from app.pilot_intelligence import router as pilot_intelligence_router
from app.pilot_decision_cycle import router as pilot_decision_cycle_router
from app.pilot_operations import PilotRateLimitMiddleware, router as pilot_operations_router

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = PROJECT_ROOT / "frontend" / "assets"
FRONTEND_DIR = PROJECT_ROOT / "frontend" / "pilot-v1"
PILOT_ASSET_VERSION = "20260824-staging-stable-v1"

# These two presentation layers both attach broad MutationObservers to the
# authenticated page and repeatedly rewrite overlapping navigation and mission
# nodes. They remain in the repository for forensic comparison, but are not
# executed in the staging browser shell.
DISABLED_RUNTIME_ASSETS = (
    "pilot-integration-v3.js",
    "mission-experience-v1.js",
)

app.include_router(learning_inheritance_router)
app.include_router(organizational_learning_router)
app.include_router(organizational_memory_router)
app.include_router(pilot_bootstrap_router)
app.include_router(pilot_capabilities_router)
app.include_router(pilot_product_router)
app.include_router(pilot_intelligence_router)
app.include_router(pilot_decision_cycle_router)
app.include_router(evidence_graph_router)
app.include_router(learning_lineage_router)
app.include_router(pilot_operations_router)
app.add_middleware(PilotRateLimitMiddleware)


@app.middleware("http")
async def security_and_trace_headers(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; connect-src 'self'; "
        "img-src 'self' data:; object-src 'none'; base-uri 'self'; "
        "frame-ancestors 'none'; form-action 'self'"
    )
    if request.headers.get("x-forwarded-proto", "").lower() == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    path = request.url.path
    is_frontend_asset = path.endswith((".js", ".css", ".svg", ".webp", ".png", ".jpg", ".jpeg"))
    if path.startswith("/api/") or path in {"/", "/app"} or is_frontend_asset:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


def _remove_disabled_runtime_assets(html: str) -> str:
    for filename in DISABLED_RUNTIME_ASSETS:
        html = re.sub(
            rf"\s*<script\b[^>]*\bsrc=[\"']/[^\"']*{re.escape(filename)}[^\"']*[\"'][^>]*>\s*</script>",
            "",
            html,
            flags=re.IGNORECASE,
        )
    return html


def _inject_stable_runtime(html: str, filename: str) -> str:
    release_css = (
        f'  <link rel="stylesheet" href="/release-hardening-v2.css?v={PILOT_ASSET_VERSION}" '
        'data-sris-release-hardening="true">\n'
    )
    emergency_css = (
        f'  <link rel="stylesheet" href="/emergency-stability-v1.css?v={PILOT_ASSET_VERSION}">\n'
    )

    if filename == "index.html":
        # Preserve uploads, report exports, governed AI readiness and the
        # navigation fix, but load them directly rather than through the
        # disabled observer-based integration layer.
        html = html.replace("</head>", release_css + emergency_css + "</head>", 1)
        release_js = (
            f'<script src="/release-hardening-v2.js?v={PILOT_ASSET_VERSION}" '
            'data-sris-release-hardening="true" defer></script>\n'
        )
        html = html.replace("</body>", release_js + "</body>", 1)
    else:
        html = html.replace("</head>", emergency_css + "</head>", 1)
    return html


def _frontend_html(filename: str) -> str:
    html = (FRONTEND_DIR / filename).read_text(encoding="utf-8")
    # Every deployment receives a unique asset URL. This prevents an older
    # Pilot shell from surviving in a browser while the backend has moved on.
    for marker in (
        "20260822-recovery1",
        "20260822-decision-loop-v2",
        "20260823-decision-first",
        "20260823-release-hardening-v2",
        "20260824-emergency-stability-v1",
    ):
        html = html.replace(marker, PILOT_ASSET_VERSION)

    html = _remove_disabled_runtime_assets(html)
    html = _inject_stable_runtime(html, filename)
    html = html.replace(
        "<head>",
        f'<head>\n  <meta name="sris-pilot-build" content="{PILOT_ASSET_VERSION}">',
        1,
    )
    return html


@app.get("/", include_in_schema=False)
def pilot_home() -> HTMLResponse:
    return HTMLResponse(
        _frontend_html("home.html"),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "X-SRIS-Pilot-Build": PILOT_ASSET_VERSION,
        },
    )


@app.get("/app", include_in_schema=False)
def pilot_app() -> HTMLResponse:
    return HTMLResponse(
        _frontend_html("index.html"),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "X-SRIS-Pilot-Build": PILOT_ASSET_VERSION,
        },
    )


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
