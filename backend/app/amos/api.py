from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query

from .orchestrator import AMOSOrchestrator


def create_app(repository_root: Path | None = None) -> FastAPI:
    repo = repository_root or Path(os.getenv("ATLAS_REPOSITORY_ROOT", ".")).resolve()
    amos = AMOSOrchestrator(repo)

    app = FastAPI(
        title="ATLAS Memory Operating System",
        version="0.1.0",
        description="Institutional memory orchestration for Project ATLAS.",
    )

    def authorize(key: str | None) -> None:
        expected = os.getenv("AMOS_API_KEY")
        if expected and key != expected:
            raise HTTPException(status_code=401, detail="Invalid AMOS API key")

    @app.get("/health")
    def health():
        return amos.status()

    @app.post("/bootstrap")
    def bootstrap(x_amos_key: str | None = Header(default=None)):
        authorize(x_amos_key)
        return amos.bootstrap()

    @app.post("/refresh")
    def refresh(x_amos_key: str | None = Header(default=None)):
        authorize(x_amos_key)
        return amos.refresh()

    @app.get("/search")
    def search(
        q: str = Query(min_length=1),
        limit: int = Query(default=20, ge=1, le=100),
        x_amos_key: str | None = Header(default=None),
    ):
        authorize(x_amos_key)
        return amos.search(q, limit=limit)

    @app.post("/snapshot")
    def snapshot(x_amos_key: str | None = Header(default=None)):
        authorize(x_amos_key)
        path = amos.snapshot()
        return {"snapshot": str(path.relative_to(repo))}

    return app


app = create_app()
