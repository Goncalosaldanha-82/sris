from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.atlas_platform.api import platform_router
from app.atlas_platform.database import Base, engine
from app.decision_cycles import router as decision_cycles_router
from app.learning_inheritance.api import learning_router
from app.mission_intelligence.api import router as mission_intelligence_router
from app.organizational_learning.api import organizational_learning_router
from app.pilot_admin import router as pilot_admin_router
from app.pilot_bootstrap import router as pilot_bootstrap_router
from app.pilot_epistemic import router as evidence_graph_router
from app.pilot_intelligence import router as pilot_intelligence_router
from app.pilot_learning import router as pilot_learning_router
from app.pilot_product_secure import router as pilot_product_router
from app.repository_engine.api import repository_router

BASE_DIR = Path(__file__).resolve().parents[2]
PILOT_DIR = BASE_DIR / "frontend" / "pilot-v1"
ATLAS_OS_DIR = BASE_DIR / "frontend" / "atlas-os"
PILOT_ASSET_VERSION = "20260823-decision-first"

app = FastAPI(
    title="SRIS Mission Intelligence API",
    description="Mission-centred decision infrastructure for persistent evidence, action, outcomes and organizational learning.",
    version="1.7.3",
)

app.include_router(platform_router)
app.include_router(repository_router)
app.include_router(mission_intelligence_router)
app.include_router(learning_router)
app.include_router(organizational_learning_router)
app.include_router(pilot_product_router)
app.include_router(pilot_bootstrap_router)
app.include_router(pilot_intelligence_router)
app.include_router(pilot_admin_router)
app.include_router(decision_cycles_router)
app.include_router(evidence_graph_router)
app.include_router(pilot_learning_router)

if PILOT_DIR.exists():
    app.mount("/pilot-assets", StaticFiles(directory=str(PILOT_DIR)), name="pilot-assets")

if ATLAS_OS_DIR.exists():
    app.mount("/atlas-assets", StaticFiles(directory=str(ATLAS_OS_DIR)), name="atlas-assets")


@app.on_event("startup")
def ensure_schema() -> None:
    Base.metadata.create_all(bind=engine, checkfirst=True)


def _frontend_html(path: Path) -> HTMLResponse:
    html = path.read_text(encoding="utf-8")
    for marker in ("20260822-recovery1", "20260823-decision-first"):
        html = html.replace(marker, PILOT_ASSET_VERSION)
    return HTMLResponse(
        content=html,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/", response_class=HTMLResponse)
def root() -> HTMLResponse:
    return _frontend_html(PILOT_DIR / "home.html")


@app.get("/app", response_class=HTMLResponse)
def pilot_app() -> HTMLResponse:
    return _frontend_html(PILOT_DIR / "index.html")


@app.get("/internal/atlas-os", response_class=HTMLResponse, include_in_schema=False)
def internal_atlas_os() -> HTMLResponse:
    return FileResponse(ATLAS_OS_DIR / "index.html")


@app.get("/{asset_path:path}", include_in_schema=False)
def pilot_asset(asset_path: str) -> FileResponse:
    if not asset_path or asset_path.startswith(("api/", "docs", "openapi", "redoc", "internal/")):
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    candidate = (PILOT_DIR / asset_path).resolve()
    if PILOT_DIR.resolve() not in candidate.parents:
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    if not candidate.is_file():
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    media_type = None
    if candidate.suffix == ".css":
        media_type = "text/css"
    elif candidate.suffix == ".js":
        media_type = "application/javascript"
    elif candidate.suffix == ".svg":
        media_type = "image/svg+xml"
    elif candidate.suffix == ".webp":
        media_type = "image/webp"
    return FileResponse(candidate, media_type=media_type, headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.get("/health")
def health(request: Request, response: Response) -> dict[str, str]:
    payload: dict[str, str] = {"status": "ok"}
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        payload["database"] = "ok"
    except SQLAlchemyError:
        payload["status"] = "degraded"
        payload["database"] = "unavailable"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return payload
