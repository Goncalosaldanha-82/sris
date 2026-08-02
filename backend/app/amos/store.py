from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import UUID

from .models import (
    MemoryEvent,
    MemoryObject,
    MemoryObjectType,
    MemoryRelation,
    MemoryState,
    SearchResult,
)


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS memory_objects (
    object_id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    state TEXT NOT NULL,
    summary TEXT NOT NULL,
    source_path TEXT,
    source_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    tags_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_relations (
    relation_id TEXT PRIMARY KEY,
    source_object_id TEXT NOT NULL,
    target_object_id TEXT NOT NULL,
    type TEXT NOT NULL,
    rationale TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(source_object_id) REFERENCES memory_objects(object_id),
    FOREIGN KEY(target_object_id) REFERENCES memory_objects(object_id)
);

CREATE TABLE IF NOT EXISTS memory_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    object_id TEXT,
    actor TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    object_id UNINDEXED,
    title,
    summary,
    tags
);
"""


class SQLiteMemoryStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    def upsert_object(self, obj: MemoryObject) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO memory_objects (
                    object_id, type, title, state, summary, source_path, source_id,
                    created_at, updated_at, tags_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(object_id) DO UPDATE SET
                    type=excluded.type,
                    title=excluded.title,
                    state=excluded.state,
                    summary=excluded.summary,
                    source_path=excluded.source_path,
                    source_id=excluded.source_id,
                    updated_at=excluded.updated_at,
                    tags_json=excluded.tags_json,
                    metadata_json=excluded.metadata_json
                """,
                (
                    str(obj.object_id),
                    obj.type.value,
                    obj.title,
                    obj.state.value,
                    obj.summary,
                    obj.source_path,
                    obj.source_id,
                    obj.created_at.isoformat(),
                    obj.updated_at.isoformat(),
                    json.dumps(obj.tags, ensure_ascii=False),
                    json.dumps(obj.metadata, ensure_ascii=False),
                ),
            )
            connection.execute("DELETE FROM memory_fts WHERE object_id = ?", (str(obj.object_id),))
            connection.execute(
                "INSERT INTO memory_fts (object_id, title, summary, tags) VALUES (?, ?, ?, ?)",
                (
                    str(obj.object_id),
                    obj.title,
                    obj.summary,
                    " ".join(obj.tags),
                ),
            )

    def add_relation(self, relation: MemoryRelation) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO memory_relations (
                    relation_id, source_object_id, target_object_id, type, rationale, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(relation.relation_id),
                    str(relation.source_object_id),
                    str(relation.target_object_id),
                    relation.type.value,
                    relation.rationale,
                    relation.created_at.isoformat(),
                ),
            )

    def add_event(self, event: MemoryEvent) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO memory_events (
                    event_id, event_type, object_id, actor, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(event.event_id),
                    event.event_type.value,
                    str(event.object_id) if event.object_id else None,
                    event.actor,
                    json.dumps(event.payload, ensure_ascii=False),
                    event.created_at.isoformat(),
                ),
            )

    def search(self, query: str, limit: int = 20) -> list[SearchResult]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT o.*, bm25(memory_fts) AS rank
                FROM memory_fts
                JOIN memory_objects o ON o.object_id = memory_fts.object_id
                WHERE memory_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()

        return [
            SearchResult(
                object_id=UUID(row["object_id"]),
                title=row["title"],
                type=MemoryObjectType(row["type"]),
                state=MemoryState(row["state"]),
                summary=row["summary"],
                source_path=row["source_path"],
                score=float(-row["rank"]),
            )
            for row in rows
        ]

    def counts(self) -> tuple[int, int, int]:
        with self._connect() as connection:
            objects = connection.execute("SELECT COUNT(*) FROM memory_objects").fetchone()[0]
            relations = connection.execute("SELECT COUNT(*) FROM memory_relations").fetchone()[0]
            events = connection.execute("SELECT COUNT(*) FROM memory_events").fetchone()[0]
        return int(objects), int(relations), int(events)

    def get_object_by_source(self, source_path: str) -> MemoryObject | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM memory_objects WHERE source_path = ? LIMIT 1",
                (source_path,),
            ).fetchone()
        if row is None:
            return None
        return MemoryObject(
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

    def all_objects(self) -> list[MemoryObject]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM memory_objects ORDER BY created_at"
            ).fetchall()
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

    def all_relations(self) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM memory_relations ORDER BY created_at"
            ).fetchall()
