from pathlib import Path
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
from app.pilot_capabilities import PILOT_BUILD, router as pilot_capabilities_router
from app.pilot_product_secure import router as pilot_product_router
from app.pilot_intelligence import router as pilot_intelligence_router
from app.pilot_alternative_matrix import router as pilot_alternative_matrix_router
from app.pilot_business_case import router as pilot_business_case_router
from app.pilot_decision_cycle import router as pilot_decision_cycle_router
from app.pilot_mission_state import router as pilot_mission_state_router
from app.pilot_operations import PilotRateLimitMiddleware, router as pilot_operations_router
from app.pilot_validation import router as pilot_validation_router

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = PROJECT_ROOT / "frontend" / "assets"
FRONTEND_DIR = PROJECT_ROOT / "frontend" / "pilot-v1"

app.include_router(learning_inheritance_router)
app.include_router(organizational_learning_router)
app.include_router(organizational_memory_router)
app.include_router(pilot_capabilities_router)
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
    is_frontend_asset = path.endswith((".js", ".css", ".svg", ".webp", ".png", ".jpg", ".jpeg"))
    if path.startswith("/api/") or path in {"/", "/app", "/account.html"}:
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
    # HTML uses one explicit build placeholder. There is no server-side script
    # injection and therefore no second, hidden runtime composition layer.
    html = html.replace("__PILOT_BUILD__", PILOT_BUILD)
    html = html.replace(
        "<head>",
        f'<head>\n  <meta name="sris-pilot-build" content="{PILOT_BUILD}">',
        1,
    )
    return html


@app.get("/", include_in_schema=False)
def pilot_home() -> HTMLResponse:
    return HTMLResponse(
        _frontend_html("home.html"),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "X-SRIS-Pilot-Build": PILOT_BUILD,
        },
    )


@app.get("/app", include_in_schema=False)
def pilot_app() -> HTMLResponse:
    return HTMLResponse(
        _frontend_html("index.html"),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "X-SRIS-Pilot-Build": PILOT_BUILD,
        },
    )


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
