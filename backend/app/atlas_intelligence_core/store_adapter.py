from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import UUID

from app.amos.models import (
    MemoryObject,
    MemoryObjectType,
    MemoryRelationType,
    MemoryState,
)


class AMOSReadAdapter:
    """Read-only analytical access to the AMOS memory database."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path.resolve()

    def _connect(self) -> sqlite3.Connection:
        if not self.database_path.exists():
            raise FileNotFoundError(
                f"AMOS database not found: {self.database_path}. Run AMOS bootstrap first."
            )
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def objects(self) -> list[MemoryObject]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM memory_objects ORDER BY created_at"
            ).fetchall()

        import json
        return [
            MemoryObject(
                object_id=UUID(row["object_id"]),
                type=MemoryObjectType(row["type"]),
                title=row["title"],
                state=MemoryState(row["state"]),
                summary=row["summary"],
                source_path=row["source_path"],
                source_id=row["source_id"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                tags=json.loads(row["tags_json"]),
                metadata=json.loads(row["metadata_json"]),
            )
            for row in rows
        ]

    def relations(self) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM memory_relations ORDER BY created_at"
            ).fetchall()
        return [dict(row) for row in rows]

    def event_count(self) -> int:
        with self._connect() as connection:
            return int(
                connection.execute("SELECT COUNT(*) FROM memory_events").fetchone()[0]
            )

    def relation_graph(self) -> dict[UUID, list[tuple[UUID, str]]]:
        graph: dict[UUID, list[tuple[UUID, str]]] = {}
        for row in self.relations():
            source = UUID(row["source_object_id"])
            target = UUID(row["target_object_id"])
            relation = row["type"]
            graph.setdefault(source, []).append((target, relation))
            graph.setdefault(target, []).append((source, f"inverse:{relation}"))
        return graph
