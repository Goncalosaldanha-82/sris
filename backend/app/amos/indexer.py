from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from .models import MemoryEvent, MemoryEventType, MemoryObject, MemoryObjectType, MemoryState
from .store import SQLiteMemoryStore


FOLDER_TYPE_MAP = {
    "constitution": MemoryObjectType.DOCUMENT,
    "asm": MemoryObjectType.DOCUMENT,
    "missions": MemoryObjectType.MISSION,
    "research-notes": MemoryObjectType.KNOWLEDGE_ASSET,
    "theories": MemoryObjectType.THEORY,
    "ontology": MemoryObjectType.CONCEPT,
    "hypotheses": MemoryObjectType.HYPOTHESIS,
    "experiments": MemoryObjectType.EXPERIMENT,
    "validation": MemoryObjectType.VALIDATION,
    "chat-inbox": MemoryObjectType.CONVERSATION,
    "chat-receipts": MemoryObjectType.EVENT,
    "registry": MemoryObjectType.DOCUMENT,
    "knowledge-vault": MemoryObjectType.DOCUMENT,
}


class RepositoryMemoryIndexer:
    def __init__(self, repository_root: Path, store: SQLiteMemoryStore) -> None:
        self.repository_root = repository_root.resolve()
        self.store = store

    def index_all(self) -> int:
        atlas_root = self.repository_root / "docs/atlas"
        if not atlas_root.exists():
            return 0

        indexed = 0
        for path in atlas_root.rglob("*.md"):
            self.index_file(path)
            indexed += 1
        return indexed

    def index_file(self, path: Path) -> MemoryObject:
        relative = str(path.relative_to(self.repository_root)).replace("\\", "/")
        text = path.read_text(encoding="utf-8")
        title = self._title(text, path)
        summary = self._summary(text)
        type_ = self._infer_type(path, text)
        state = self._infer_state(text)
        tags = self._tags(path, text)

        existing = self.store.get_object_by_source(relative)
        now = datetime.now(timezone.utc)

        object_data = {
            "type": type_,
            "title": title,
            "state": state,
            "summary": summary,
            "source_path": relative,
            "source_id": self._source_id(path.name),
            "created_at": existing.created_at if existing else now,
            "updated_at": now,
            "tags": tags,
            "metadata": {"indexed_by": "AMOS RepositoryMemoryIndexer"},
        }
        if existing:
            object_data["object_id"] = existing.object_id

        obj = MemoryObject(**object_data)
        self.store.upsert_object(obj)
        self.store.add_event(
            MemoryEvent(
                event_type=MemoryEventType.UPDATED if existing else MemoryEventType.CREATED,
                object_id=obj.object_id,
                payload={"source_path": relative},
            )
        )
        return obj

    @staticmethod
    def _title(text: str, path: Path) -> str:
        match = re.search(r"(?m)^#\s+(.+?)\s*$", text)
        return match.group(1).strip() if match else path.stem

    @staticmethod
    def _summary(text: str) -> str:
        cleaned = re.sub(r"(?m)^#+\s+.*$", " ", text)
        cleaned = re.sub(r"`{1,3}.*?`{1,3}", " ", cleaned, flags=re.S)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned[:4000] or "No summary available."

    @staticmethod
    def _infer_type(path: Path, text: str) -> MemoryObjectType:
        for part in path.parts:
            if part in FOLDER_TYPE_MAP:
                return FOLDER_TYPE_MAP[part]
        low = text.lower()
        if "hypothesis" in low or "hipótese" in low:
            return MemoryObjectType.HYPOTHESIS
        if "decision" in low or "decisão" in low:
            return MemoryObjectType.DECISION
        return MemoryObjectType.DOCUMENT

    @staticmethod
    def _infer_state(text: str) -> MemoryState:
        low = text.lower()
        mappings = (
            ("adopted", MemoryState.ADOPTED),
            ("adotada", MemoryState.ADOPTED),
            ("contested", MemoryState.CONTESTED),
            ("refuted", MemoryState.REFUTED),
            ("deprecated", MemoryState.DEPRECATED),
            ("active", MemoryState.ACTIVE),
            ("ativa", MemoryState.ACTIVE),
            ("working", MemoryState.WORKING),
            ("provisória", MemoryState.WORKING),
        )
        for token, state in mappings:
            if token in low:
                return state
        return MemoryState.CANDIDATE

    @staticmethod
    def _tags(path: Path, text: str) -> list[str]:
        tags = {part for part in path.parts if part not in {"docs", "atlas"}}
        for token in ("ATLAS", "TICC", "SMK", "SRIS", "ASM", "CISM", "AMOS"):
            if token.lower() in text.lower():
                tags.add(token)
        return sorted(tags)

    @staticmethod
    def _source_id(filename: str) -> str | None:
        match = re.match(r"([A-Z]+-\d{3,})", filename)
        return match.group(1) if match else None
