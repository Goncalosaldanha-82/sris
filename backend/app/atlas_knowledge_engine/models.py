from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class KnowledgeType(StrEnum):
    DECISION = "decision"
    HYPOTHESIS = "hypothesis"
    CONCEPT = "concept"
    MISSION = "mission"
    RESEARCH_NOTE = "research_note"
    THEORY = "theory"
    ONTOLOGY = "ontology"
    EXPERIMENT = "experiment"
    VALIDATION = "validation"
    RISK = "risk"
    ACTION = "action"
    OBSERVATION = "observation"
    CORRECTION = "correction"
    ARCHITECTURE = "architecture"


class KnowledgeState(StrEnum):
    CANDIDATE = "candidate"
    WORKING = "working"
    PROPOSED = "proposed"
    ACTIVE = "active"
    CONTESTED = "contested"
    REFUTED = "refuted"
    ADOPTED = "adopted"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class ConfidenceLevel(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class KnowledgeItem(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    type: KnowledgeType
    title: Annotated[str, Field(min_length=3, max_length=180)]
    summary: Annotated[str, Field(min_length=3, max_length=5000)]
    state: KnowledgeState = KnowledgeState.CANDIDATE
    confidence: ConfidenceLevel = ConfidenceLevel.MODERATE
    source_excerpt: str | None = None
    basis: str | None = None
    limitations: list[str] = Field(default_factory=list)
    affected_assets: list[str] = Field(default_factory=list)
    related_concepts: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    requires_human_approval: bool = True

    @field_validator("affected_assets", "related_concepts", "tags")
    @classmethod
    def sanitize_lists(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for raw in values:
            value = raw.strip()
            if not value:
                continue
            if ".." in value or value.startswith("/") or value.startswith("\\"):
                raise ValueError("Logical identifiers only; paths are not allowed")
            cleaned.append(value)
        return sorted(set(cleaned))


class KnowledgePacket(BaseModel):
    packet_id: UUID = Field(default_factory=uuid4)
    title: Annotated[str, Field(min_length=3, max_length=180)]
    source_name: Annotated[str, Field(min_length=1, max_length=255)]
    source_type: str = "markdown"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    author: str = "Human-supervised ATLAS workflow"
    overall_summary: Annotated[str, Field(min_length=3, max_length=5000)]
    items: list[KnowledgeItem] = Field(min_length=1)
    requires_human_approval: bool = True

    @field_validator("created_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        return value


class PlannedMutation(BaseModel):
    path: str
    content: str
    reason: str

    @field_validator("path")
    @classmethod
    def safe_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Unsafe repository path")
        return str(path)


class ConflictFinding(BaseModel):
    severity: str
    code: str
    message: str
    related_paths: list[str] = Field(default_factory=list)


class KnowledgePlan(BaseModel):
    packet: KnowledgePacket
    mutations: list[PlannedMutation]
    conflicts: list[ConflictFinding]
    branch_name: str
    commit_message: str
    pull_request_title: str
    pull_request_body: str
