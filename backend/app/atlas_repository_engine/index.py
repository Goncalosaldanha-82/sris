from __future__ import annotations

import json
from pathlib import Path

from .models import RepositoryAsset


class RepositoryIndex:
    def __init__(self, repository_root: Path) -> None:
        self.repository_root = repository_root.resolve()
        self.index_path = self.repository_root / ".atlas/repository/index.json"

    def save(self, assets: list[RepositoryAsset]) -> Path:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": "0.1",
            "asset_count": len(assets),
            "assets": [asset.model_dump(mode="json") for asset in assets],
        }
        self.index_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return self.index_path

    def load(self) -> list[RepositoryAsset]:
        if not self.index_path.exists():
            return []
        payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        return [RepositoryAsset.model_validate(item) for item in payload["assets"]]
