from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4
from pydantic import BaseModel, Field

class WorkflowState(StrEnum):
    RECEIVED="received"; REVIEW_REQUIRED="review_required"; APPROVED="approved"
    REJECTED="rejected"; COMMIT_PROPOSED="commit_proposed"; FAILED="failed"

class CandidateType(StrEnum):
    DECISION="decision"; HYPOTHESIS="hypothesis"; CONCEPT="concept"
    MISSION="mission"; THEORY="theory"; RISK="risk"; ACTION="action"
    OBSERVATION="observation"; ARCHITECTURE="architecture"

class Candidate(BaseModel):
    candidate_id: UUID = Field(default_factory=uuid4)
    type: CandidateType
    title: str
    summary: str
    confidence: float = 0.5
    approved: bool | None = None

class IntakeRequest(BaseModel):
    title: str
    content: str
    source_name: str = "manual-intake"

class WorkflowRecord(BaseModel):
    workflow_id: UUID = Field(default_factory=uuid4)
    title: str
    source_name: str
    original_content: str
    state: WorkflowState = WorkflowState.RECEIVED
    candidates: list[Candidate] = Field(default_factory=list)
    output_paths: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ReviewDecision(BaseModel):
    approvals: dict[UUID, bool]
    comment: str | None = None
