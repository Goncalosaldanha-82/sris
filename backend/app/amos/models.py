from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class MemoryObjectType(StrEnum):
    CONVERSATION = "conversation"
    KNOWLEDGE_ASSET = "knowledge_asset"
    DECISION = "decision"
    HYPOTHESIS = "hypothesis"
    CONCEPT = "concept"
    MISSION = "mission"
    THEORY = "theory"
    EXPERIMENT = "experiment"
    VALIDATION = "validation"
    DOCUMENT = "document"
    CODE = "code"
    EVENT = "event"


class MemoryState(StrEnum):
    CANDIDATE = "candidate"
    WORKING = "working"
    ACTIVE = "active"
    ADOPTED = "adopted"
    CONTESTED = "contested"
    REFUTED = "refuted"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class MemoryObject(BaseModel):
    object_id: UUID = Field(default_factory=uuid4)
    type: MemoryObjectType
    title: Annotated[str, Field(min_length=1, max_length=255)]
    state: MemoryState = MemoryState.CANDIDATE
    summary: Annotated[str, Field(min_length=1, max_length=10000)]
    source_path: str | None = None
    source_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("created_at", "updated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("datetime must be timezone-aware")
        return value


class MemoryRelationType(StrEnum):
    DERIVED_FROM = "derived_from"
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    REVISES = "revises"
    IMPLEMENTS = "implements"
    VALIDATES = "validates"
    AFFECTS = "affects"
    RELATED_TO = "related_to"
    SUPERSEDES = "supersedes"
    PRODUCED_BY = "produced_by"


class MemoryRelation(BaseModel):
    relation_id: UUID = Field(default_factory=uuid4)
    source_object_id: UUID
    target_object_id: UUID
    type: MemoryRelationType
    rationale: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MemoryEventType(StrEnum):
    INGESTED = "ingested"
    CLASSIFIED = "classified"
    CREATED = "created"
    UPDATED = "updated"
    RELATED = "related"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    REJECTED = "rejected"
    SNAPSHOT = "snapshot"
    ERROR = "error"


class MemoryEvent(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    event_type: MemoryEventType
    object_id: UUID | None = None
    actor: str = "AMOS"
    payload: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SearchResult(BaseModel):
    object_id: UUID
    title: str
    type: MemoryObjectType
    state: MemoryState
    summary: str
    source_path: str | None = None
    score: float = 0.0


class AMOSStatus(BaseModel):
    status: str
    repository_root: str
    database_path: str
    object_count: int
    relation_count: int
    event_count: int
    last_snapshot: str | None = None
