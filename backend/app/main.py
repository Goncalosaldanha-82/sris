from pathlib import Path
from uuid import uuid4

from fastapi import Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.atlas_platform.api import app
from app.evidence_graph import router as evidence_graph_router
from app.learning_lineage import router as learning_lineage_router
from app.mission_intelligence.evolution_api import router as organizational_learning_router
from app.mission_intelligence.learning_api import router as learning_inheritance_router
from app.mission_intelligence.memory_api import router as organizational_memory_router
from app.mission_intelligence import memory_models  # noqa: F401
from app.pilot_product import router as pilot_product_router
from app.pilot_intelligence import router as pilot_intelligence_router
from app.pilot_operations import PilotRateLimitMiddleware, router as pilot_operations_router


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = PROJECT_ROOT / "frontend" / "assets"
FRONTEND_DIR = PROJECT_ROOT / "frontend" / "pilot-v1"
PILOT_ASSET_VERSION = "20260822-integrated-v3"

app.include_router(learning_inheritance_router)
app.include_router(organizational_learning_router)
app.include_router(organizational_memory_router)
app.include_router(pilot_product_router)
app.include_router(pilot_intelligence_router)
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
    if request.url.path.startswith("/api/") or request.url.path in {"/", "/app"}:
        response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


if ASSETS_DIR.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=str(ASSETS_DIR)),
        name="assets",
    )


@app.get("/", include_in_schema=False)
def pilot_home() -> FileResponse:
    return FileResponse(
        FRONTEND_DIR / "home.html",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/app", include_in_schema=False)
def pilot_app() -> HTMLResponse:
    """Serve the Pilot V1 shell with every built capability wired explicitly.

    The previous implementation loaded enhancement scripts before the deferred
    legacy app shell and depended on runtime injection order.  That made a
    successful Railway deploy capable of looking exactly like the old Pilot.
    The contract below is deterministic: base app first, then the Mission
    Workspace, Evidence Graph, learning/memory, intelligence and account
    administration layers.  A version query prevents stale browser/CDN assets.
    """
    html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    marker = '<script src="/app.js" defer></script>'
    scripts = (
        f'<script src="/app.js?v={PILOT_ASSET_VERSION}" defer></script>'
        f'<script src="/mission-workspace-v2.js?v={PILOT_ASSET_VERSION}" defer></script>'
        f'<script src="/evidence-graph.js?v={PILOT_ASSET_VERSION}" defer></script>'
        f'<script src="/learning-lineage.js?v={PILOT_ASSET_VERSION}" defer></script>'
        f'<script src="/intelligence-v2.js?v={PILOT_ASSET_VERSION}" defer></script>'
        f'<script src="/admin-accounts.js?v={PILOT_ASSET_VERSION}" defer></script>'
        f'<script src="/pilot-integration-v3.js?v={PILOT_ASSET_VERSION}" defer></script>'
    )
    if marker in html:
        html = html.replace(marker, scripts)
    return HTMLResponse(
        html,
        headers={
            "Cache-Control": "no-store, max-age=0",
            "X-SRIS-Pilot-Build": PILOT_ASSET_VERSION,
        },
    )


if FRONTEND_DIR.exists():
    app.mount(
        "/",
        StaticFiles(directory=str(FRONTEND_DIR), html=True),
        name="frontend",
    )
