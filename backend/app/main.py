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


PROJECT_ROOT = Path(__file__).resolve().parents[2]

ASSETS_DIR = PROJECT_ROOT / "frontend" / "assets"
FRONTEND_DIR = PROJECT_ROOT / "frontend" / "pilot-v1"

app.include_router(learning_inheritance_router)
app.include_router(organizational_learning_router)
app.include_router(organizational_memory_router)
app.include_router(pilot_product_router)
app.include_router(pilot_intelligence_router)
app.include_router(evidence_graph_router)
app.include_router(learning_lineage_router)


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
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


if ASSETS_DIR.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=str(ASSETS_DIR)),
        name="assets",
    )


@app.get("/", include_in_schema=False)
def pilot_home() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "home.html")


@app.get("/app", include_in_schema=False)
def pilot_app() -> HTMLResponse:
    html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    marker = '<script src="/app.js" defer></script>'
    if marker in html:
        html = html.replace(
            marker,
            '<script src="/learning-lineage.js"></script>'
            '<script src="/intelligence-v2.js"></script>'
            '<script src="/evidence-graph.js"></script>'
            + marker,
        )
    return HTMLResponse(html)


if FRONTEND_DIR.exists():
    app.mount(
        "/",
        StaticFiles(directory=str(FRONTEND_DIR), html=True),
        name="frontend",
    )
