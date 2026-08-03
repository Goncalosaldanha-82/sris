from pathlib import Path

from fastapi.staticfiles import StaticFiles

from app.atlas_platform.api import app


FRONTEND_DIR = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "atlas-os"
)

if FRONTEND_DIR.exists():
    app.mount(
        "/",
        StaticFiles(directory=str(FRONTEND_DIR), html=True),
        name="frontend",
    )
