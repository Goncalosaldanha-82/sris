from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class FindingType(StrEnum):
    CONTRADICTION = "contradiction"
    DUPLICATION = "duplication"
    ORPHAN = "orphan"
    STALENESS = "staleness"
    MISSING_VALIDATION = "missing_validation"
    MISSING_PROVENANCE = "missing_provenance"
    IMPACT = "impact"
    PRIORITY = "priority"
    GOVERNANCE = "governance"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FindingStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class IntelligenceFinding(BaseModel):
    finding_id: UUID = Field(default_factory=uuid4)
    type: FindingType
    severity: Severity
    title: Annotated[str, Field(min_length=3, max_length=240)]
    summary: Annotated[str, Field(min_length=3, max_length=10000)]
    object_ids: list[UUID] = Field(default_factory=list)
    source_paths: list[str] = Field(default_factory=list)
    rationale: str
    recommended_action: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    status: FindingStatus = FindingStatus.OPEN
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("created_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        return value


class ImpactNode(BaseModel):
    object_id: UUID
    title: str
    relation: str
    depth: int = Field(ge=0)
    source_path: str | None = None


class ImpactReport(BaseModel):
    root_object_id: UUID
    root_title: str
    affected: list[ImpactNode]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PriorityItem(BaseModel):
    finding_id: UUID
    title: str
    severity: Severity
    score: float
    reason: str
    recommended_action: str


class IntelligenceReport(BaseModel):
    report_id: UUID = Field(default_factory=uuid4)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    object_count: int
    relation_count: int
    finding_count: int
    findings: list[IntelligenceFinding]
    priorities: list[PriorityItem]
    summary: str
