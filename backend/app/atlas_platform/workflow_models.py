from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WorkflowState(StrEnum):
    RECEIVED = "received"
    NORMALIZED = "normalized"
    CLASSIFIED = "classified"
    REVIEW_REQUIRED = "review_required"
    APPROVED = "approved"
    REJECTED = "rejected"
    MATERIALIZED = "materialized"
    INDEXED = "indexed"
    ANALYZED = "analyzed"
    COMMIT_PROPOSED = "commit_proposed"
    COMMITTED = "committed"
    PUBLISHED = "published"
    FAILED = "failed"


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(240))
    source_name: Mapped[str] = mapped_column(String(500))
    source_type: Mapped[str] = mapped_column(String(60), default="note")
    original_content: Mapped[str] = mapped_column(Text)
    normalized_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(String(40), default=WorkflowState.RECEIVED.value, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )

    candidates: Mapped[list["WorkflowCandidate"]] = relationship(
        back_populates="workflow",
        cascade="all, delete-orphan",
    )
    history: Mapped[list["WorkflowHistory"]] = relationship(
        back_populates="workflow",
        cascade="all, delete-orphan",
    )
    repository_changes: Mapped[list["RepositoryChange"]] = relationship(
        back_populates="workflow",
        cascade="all, delete-orphan",
    )


class WorkflowCandidate(Base):
    __tablename__ = "workflow_candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"))
    candidate_type: Mapped[str] = mapped_column(String(60), index=True)
    title: Mapped[str] = mapped_column(String(240))
    summary: Mapped[str] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(20), default="0.50")
    source_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved: Mapped[str | None] = mapped_column(String(10), nullable=True)
    reviewer_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    workflow: Mapped[Workflow] = relationship(back_populates="candidates")


class WorkflowHistory(Base):
    __tablename__ = "workflow_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"))
    from_state: Mapped[str] = mapped_column(String(40))
    to_state: Mapped[str] = mapped_column(String(40))
    note: Mapped[str] = mapped_column(Text)
    actor_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    workflow: Mapped[Workflow] = relationship(back_populates="history")


class RepositoryChange(Base):
    __tablename__ = "repository_changes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"))
    branch_name: Mapped[str] = mapped_column(String(255))
    commit_message: Mapped[str] = mapped_column(String(500))
    changed_paths_json: Mapped[str] = mapped_column(Text, default="[]")
    diff_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="pending")
    pull_request_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    workflow: Mapped[Workflow] = relationship(back_populates="repository_changes")
