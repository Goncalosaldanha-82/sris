from __future__ import annotations

import re
from pathlib import Path

from .models import MemoryEvent, MemoryEventType, MemoryRelation, MemoryRelationType
from .store import SQLiteMemoryStore


class RelationBuilder:
    def __init__(self, repository_root: Path, store: SQLiteMemoryStore) -> None:
        self.repository_root = repository_root.resolve()
        self.store = store

    def rebuild(self) -> int:
        objects = self.store.all_objects()
        by_source_id = {obj.source_id: obj for obj in objects if obj.source_id}
        created = 0

        for obj in objects:
            if not obj.source_path:
                continue
            path = self.repository_root / obj.source_path
            if not path.exists() or path.suffix.lower() != ".md":
                continue

            text = path.read_text(encoding="utf-8")
            references = set(re.findall(r"\b[A-Z]{2,}-\d{3,}\b", text))
            for reference in references:
                target = by_source_id.get(reference)
                if target is None or target.object_id == obj.object_id:
                    continue
                relation = MemoryRelation(
                    source_object_id=obj.object_id,
                    target_object_id=target.object_id,
                    type=MemoryRelationType.RELATED_TO,
                    rationale=f"Explicit reference to {reference} in {obj.source_path}",
                )
                self.store.add_relation(relation)
                self.store.add_event(
                    MemoryEvent(
                        event_type=MemoryEventType.RELATED,
                        object_id=obj.object_id,
                        payload={"target": str(target.object_id), "reference": reference},
                    )
                )
                created += 1
        return created
