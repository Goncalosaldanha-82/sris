from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .models import MemoryEvent, MemoryEventType
from .store import SQLiteMemoryStore


class SnapshotManager:
    def __init__(self, repository_root: Path, store: SQLiteMemoryStore) -> None:
        self.repository_root = repository_root.resolve()
        self.store = store

    def create_snapshot(self) -> Path:
        now = datetime.now(timezone.utc)
        snapshot_dir = self.repository_root / "docs/atlas/knowledge-vault/snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        objects = [obj.model_dump(mode="json") for obj in self.store.all_objects()]
        relations = [dict(row) for row in self.store.all_relations()]
        payload = {
            "snapshot_version": "0.1",
            "created_at": now.isoformat(),
            "objects": objects,
            "relations": relations,
        }

        path = snapshot_dir / f"AMOS-SNAPSHOT-{now.strftime('%Y%m%d-%H%M%S')}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.store.add_event(
            MemoryEvent(
                event_type=MemoryEventType.SNAPSHOT,
                payload={"snapshot_path": str(path.relative_to(self.repository_root))},
            )
        )
        return path

    def latest_snapshot(self) -> Path | None:
        folder = self.repository_root / "docs/atlas/knowledge-vault/snapshots"
        if not folder.exists():
            return None
        snapshots = sorted(folder.glob("AMOS-SNAPSHOT-*.json"))
        return snapshots[-1] if snapshots else None
