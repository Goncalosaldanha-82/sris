from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class RepositoryAssetType(StrEnum):
    DOCUMENT = "document"
    CODE = "code"
    TEST = "test"
    CONFIGURATION = "configuration"
    WORKFLOW = "workflow"
    MIGRATION = "migration"
    OTHER = "other"


class ChangeType(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class RepositoryAsset(BaseModel):
    path: str
    asset_type: RepositoryAssetType
    title: str
    checksum: str
    size_bytes: int
    references: list[str] = Field(default_factory=list)
    referenced_by: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


class PlannedFileChange(BaseModel):
    change_id: UUID = Field(default_factory=uuid4)
    change_type: ChangeType
    path: str
    content: str | None = None
    reason: str
    source_workflow_id: str | None = None
    source_knowledge_object_id: str | None = None
    risk_level: str = "low"

    @field_validator("path")
    @classmethod
    def safe_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Unsafe repository path")
        return str(path)


class DependencyImpact(BaseModel):
    path: str
    direct_dependants: list[str] = Field(default_factory=list)
    referenced_assets: list[str] = Field(default_factory=list)
    broken_references: list[str] = Field(default_factory=list)
    risk_level: str = "low"


class RepositoryChangePlan(BaseModel):
    plan_id: UUID = Field(default_factory=uuid4)
    title: Annotated[str, Field(min_length=3, max_length=240)]
    summary: str
    branch_name: str
    commit_message: str
    pull_request_title: str
    pull_request_body: str
    changes: list[PlannedFileChange]
    impacts: list[DependencyImpact] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    requires_human_approval: bool = True


class ApplyResult(BaseModel):
    plan_id: UUID
    changed_paths: list[str]
    branch_name: str
    commit_hash: str | None = None
    committed: bool = False
    pushed: bool = False
    pull_request_url: str | None = None
