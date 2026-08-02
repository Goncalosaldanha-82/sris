from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class WorkflowCreate(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    source_name: str = Field(default="manual-intake", max_length=500)
    source_type: str = Field(default="note", max_length=60)
    content: str = Field(min_length=1, max_length=200000)


class CandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    candidate_type: str
    title: str
    summary: str
    confidence: str
    source_excerpt: str | None
    approved: str | None
    reviewer_comment: str | None


class WorkflowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    created_by_user_id: str
    title: str
    source_name: str
    source_type: str
    state: str
    error: str | None
    candidates: list[CandidateRead] = []


class ReviewPayload(BaseModel):
    approvals: dict[str, bool]
    comment: str | None = None


class RepositoryProposalRead(BaseModel):
    branch_name: str
    commit_message: str
    changed_paths: list[str]
    diff_text: str
    status: str
