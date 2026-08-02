from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class ChangeKind(StrEnum):
    DECISION = "decision"
    HYPOTHESIS = "hypothesis"
    CONCEPT = "concept"
    RISK = "risk"
    ACTION = "action"
    OBSERVATION = "observation"
    ARCHITECTURE = "architecture"
    CORRECTION = "correction"


class EpistemicState(StrEnum):
    CANDIDATE = "candidate"
    WORKING = "working"
    PROPOSED = "proposed"
    ACTIVE = "active"
    CONTESTED = "contested"
    REFUTED = "refuted"
    ADOPTED = "adopted"
    DEPRECATED = "deprecated"


class AtlasChangeItem(BaseModel):
    kind: ChangeKind
    title: Annotated[str, Field(min_length=3, max_length=180)]
    summary: Annotated[str, Field(min_length=3, max_length=4000)]
    state: EpistemicState = EpistemicState.CANDIDATE
    affected_assets: list[str] = Field(default_factory=list)
    evidence_or_basis: str | None = None
    limitations: list[str] = Field(default_factory=list)
    source_excerpt: str | None = None

    @field_validator("affected_assets")
    @classmethod
    def validate_assets(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            item = item.strip()
            if not item:
                continue
            # Logical asset identifiers only; never accept filesystem traversal.
            if ".." in item or item.startswith(("/", "\\")):
                raise ValueError("affected_assets must contain logical identifiers, not paths")
            cleaned.append(item)
        return cleaned


class AtlasChangeSet(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    title: Annotated[str, Field(min_length=3, max_length=180)]
    source_name: Annotated[str, Field(min_length=1, max_length=255)]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    author: str = "Human-supervised ATLAS workflow"
    items: list[AtlasChangeItem] = Field(min_length=1)
    overall_summary: Annotated[str, Field(min_length=3, max_length=5000)]
    requires_human_approval: bool = True

    @field_validator("created_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        return value


class FileMutation(BaseModel):
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


class AgentPlan(BaseModel):
    changeset: AtlasChangeSet
    mutations: list[FileMutation]
    branch_name: str
    commit_message: str
    pull_request_title: str
    pull_request_body: str
