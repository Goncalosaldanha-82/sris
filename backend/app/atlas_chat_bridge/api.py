from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, FastAPI, Header, HTTPException

from .bridge import AtlasChatBridge
from .models import BridgeReceipt, ChatConversation


def create_app(repository_root: Path | None = None) -> FastAPI:
    repo = repository_root or Path(os.getenv("ATLAS_REPOSITORY_ROOT", ".")).resolve()
    bridge = AtlasChatBridge()

    app = FastAPI(
        title="ATLAS Chat Bridge",
        version="0.1.0",
        description="Governed conversation intake for the ATLAS Knowledge Engine.",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "repository_root": str(repo)}

    @app.post("/ingest", response_model=BridgeReceipt)
    def ingest(
        conversation: ChatConversation,
        x_atlas_bridge_key: str | None = Header(default=None),
        apply: bool = False,
    ) -> BridgeReceipt:
        expected = os.getenv("ATLAS_CHAT_BRIDGE_KEY")
        if expected and x_atlas_bridge_key != expected:
            raise HTTPException(status_code=401, detail="Invalid bridge key")

        receipt, _ = bridge.ingest_conversation(
            conversation=conversation,
            repository_root=repo,
            apply=apply,
        )
        return receipt

    return app


app = create_app()
