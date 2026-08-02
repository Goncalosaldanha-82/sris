from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, Query

from .orchestrator import AtlasIntelligenceCore


def create_app(repository_root: Path | None = None) -> FastAPI:
    repo = repository_root or Path(os.getenv("ATLAS_REPOSITORY_ROOT", ".")).resolve()
    core = AtlasIntelligenceCore(repo)

    app = FastAPI(
        title="ATLAS Intelligence Core",
        version="0.1.0",
        description="Analytical intelligence over AMOS institutional memory.",
    )

    def authorize(value: str | None) -> None:
        expected = os.getenv("AIC_API_KEY")
        if expected and value != expected:
            raise HTTPException(status_code=401, detail="Invalid AIC API key")

    @app.get("/health")
    def health():
        return {"status": "ok", "repository_root": str(repo)}

    @app.post("/analyze")
    def analyze(
        refresh_memory: bool = True,
        x_aic_key: str | None = Header(default=None),
    ):
        authorize(x_aic_key)
        return core.analyze(refresh_memory=refresh_memory)

    @app.get("/impact/{object_id}")
    def impact(
        object_id: UUID,
        max_depth: int = Query(default=3, ge=1, le=10),
        x_aic_key: str | None = Header(default=None),
    ):
        authorize(x_aic_key)
        return core.impact(object_id, max_depth=max_depth)

    return app


app = create_app()
