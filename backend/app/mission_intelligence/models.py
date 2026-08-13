from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.atlas_platform.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CanonicalMission(Base):
    """Current, authoritative MDL document for one organizational mission."""

    __tablename__ = "mi_missions"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_mi_mission_org_code"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    parent_mission_id: Mapped[str | None] = mapped_column(
        ForeignKey("mi_missions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    code: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(300))
    mission_kind: Mapped[str] = mapped_column(String(30), default="mission", index=True)
    domain: Mapped[str] = mapped_column(String(80), default="cross_domain", index=True)
    priority: Mapped[str] = mapped_column(String(20), default="strategic", index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    schema_version: Mapped[str] = mapped_column(String(20), default="1.3")
    document_json: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    lifecycle_state: Mapped[str] = mapped_column(String(40), default="active")
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    revisions: Mapped[list["MissionRevision"]] = relationship(
        back_populates="mission", cascade="all, delete-orphan"
    )
    parent: Mapped["CanonicalMission | None"] = relationship(
        remote_side="CanonicalMission.id",
        back_populates="children",
        foreign_keys=[parent_mission_id],
    )
    children: Mapped[list["CanonicalMission"]] = relationship(
        back_populates="parent",
        foreign_keys=[parent_mission_id],
    )
    intelligence_runs: Mapped[list["IntelligenceRun"]] = relationship(
        back_populates="mission", cascade="all, delete-orphan"
    )
    dialogue_sessions: Mapped[list["MissionDialogueSession"]] = relationship(
        back_populates="mission", cascade="all, delete-orphan"
    )


class MissionRevision(Base):
    """Append-only copy of every accepted canonical mission revision."""

    __tablename__ = "mi_mission_revisions"
    __table_args__ = (
        UniqueConstraint("mission_id", "revision", name="uq_mi_revision_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    mission_id: Mapped[str] = mapped_column(
        ForeignKey("mi_missions.id", ondelete="CASCADE"), index=True
    )
    revision: Mapped[int] = mapped_column(Integer)
    document_json: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    change_note: Mapped[str] = mapped_column(Text, default="")
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    mission: Mapped[CanonicalMission] = relationship(back_populates="revisions")


class IntelligenceRun(Base):
    """Auditable execution record; model output is never accepted implicitly."""

    __tablename__ = "mi_intelligence_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    mission_id: Mapped[str] = mapped_column(
        ForeignKey("mi_missions.id", ondelete="CASCADE"), index=True
    )
    mission_code: Mapped[str] = mapped_column(String(80), index=True)
    execution_mode: Mapped[str] = mapped_column(String(30), default="deterministic")
    status: Mapped[str] = mapped_column(String(30), default="completed")
    engine_version: Mapped[str] = mapped_column(String(80))
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    provider_response_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    snapshot_hash: Mapped[str] = mapped_column(String(64), index=True)
    input_json: Mapped[str] = mapped_column(Text)
    deterministic_json: Mapped[str] = mapped_column(Text)
    ai_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[str] = mapped_column(String(30), default="required", index=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    review_comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    mission: Mapped[CanonicalMission] = relationship(back_populates="intelligence_runs")
    ai_usage_event: Mapped["AIUsageEvent | None"] = relationship(
        back_populates="intelligence_run",
        uselist=False,
    )
    dialogue_turn: Mapped["MissionDialogueTurn | None"] = relationship(
        back_populates="intelligence_run",
        uselist=False,
    )


class MissionDialogueSession(Base):
    """Long-running, locally persisted intelligence dialogue for one snapshot."""

    __tablename__ = "mi_dialogue_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    mission_id: Mapped[str] = mapped_column(
        ForeignKey("mi_missions.id", ondelete="CASCADE"), index=True
    )
    mission_code: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(300))
    objective: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    snapshot_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    mission: Mapped[CanonicalMission] = relationship(back_populates="dialogue_sessions")
    turns: Mapped[list["MissionDialogueTurn"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="MissionDialogueTurn.sequence",
    )


class MissionDialogueTurn(Base):
    """One governed user/model exchange, linked to the existing run ledger."""

    __tablename__ = "mi_dialogue_turns"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "sequence",
            name="uq_mi_dialogue_turn_sequence",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(
        ForeignKey("mi_dialogue_sessions.id", ondelete="CASCADE"), index=True
    )
    intelligence_run_id: Mapped[str] = mapped_column(
        ForeignKey("mi_intelligence_runs.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer)
    intent: Mapped[str] = mapped_column(String(40))
    user_message: Mapped[str] = mapped_column(Text)
    answers_json: Mapped[str] = mapped_column(Text, default="[]")
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[MissionDialogueSession] = relationship(back_populates="turns")
    intelligence_run: Mapped[IntelligenceRun] = relationship(
        back_populates="dialogue_turn"
    )
    proposal_reviews: Mapped[list["MissionProposalReview"]] = relationship(
        back_populates="turn",
        cascade="all, delete-orphan",
    )


class MissionProposalReview(Base):
    """Granular human disposition of an AI proposal; never canonical by itself."""

    __tablename__ = "mi_proposal_reviews"
    __table_args__ = (
        UniqueConstraint(
            "turn_id",
            "proposal_id",
            name="uq_mi_proposal_review_turn_proposal",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[str] = mapped_column(
        ForeignKey("mi_dialogue_sessions.id", ondelete="CASCADE"), index=True
    )
    turn_id: Mapped[str] = mapped_column(
        ForeignKey("mi_dialogue_turns.id", ondelete="CASCADE"), index=True
    )
    proposal_id: Mapped[str] = mapped_column(String(120), index=True)
    proposal_type: Mapped[str] = mapped_column(String(40))
    decision: Mapped[str] = mapped_column(String(40), index=True)
    comment: Mapped[str] = mapped_column(Text)
    reviewed_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    turn: Mapped[MissionDialogueTurn] = relationship(back_populates="proposal_reviews")


class AIOrganizationPolicy(Base):
    """Explicit, fail-closed AI spending policy for one organization."""

    __tablename__ = "mi_ai_organization_policies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    monthly_request_limit: Mapped[int] = mapped_column(Integer, default=20)
    monthly_input_token_limit: Mapped[int] = mapped_column(BigInteger, default=250_000)
    monthly_output_token_limit: Mapped[int] = mapped_column(BigInteger, default=50_000)
    monthly_budget_microusd: Mapped[int] = mapped_column(BigInteger, default=5_000_000)
    per_request_input_token_limit: Mapped[int] = mapped_column(Integer, default=60_000)
    per_request_output_token_limit: Mapped[int] = mapped_column(Integer, default=6_000)
    max_concurrent_requests: Mapped[int] = mapped_column(Integer, default=1)
    updated_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AIUsagePeriod(Base):
    """Monthly UTC counters, including active reservations for concurrent safety."""

    __tablename__ = "mi_ai_usage_periods"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "period_start",
            name="uq_mi_ai_usage_period_org_month",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    period_start: Mapped[date] = mapped_column(Date, index=True)
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    cached_input_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    output_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    web_search_calls: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_microusd: Mapped[int] = mapped_column(BigInteger, default=0)
    active_reservations: Mapped[int] = mapped_column(Integer, default=0)
    reserved_input_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    reserved_output_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    reserved_web_search_calls: Mapped[int] = mapped_column(Integer, default=0)
    reserved_cost_microusd: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AIUsageEvent(Base):
    """Append-oriented provider usage ledger with an immutable pricing snapshot."""

    __tablename__ = "mi_ai_usage_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    intelligence_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("mi_intelligence_runs.id", ondelete="SET NULL"),
        unique=True,
        nullable=True,
        index=True,
    )
    requested_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    period_start: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(40), default="reserved", index=True)
    provider: Mapped[str] = mapped_column(String(80), default="openai")
    model: Mapped[str] = mapped_column(String(160))
    provider_response_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    input_count_method: Mapped[str] = mapped_column(String(40), default="conservative")
    reserved_input_tokens: Mapped[int] = mapped_column(BigInteger)
    reserved_output_tokens: Mapped[int] = mapped_column(BigInteger)
    reserved_web_search_calls: Mapped[int] = mapped_column(Integer, default=0)
    reserved_cost_microusd: Mapped[int] = mapped_column(BigInteger)
    input_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    cached_input_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    output_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    web_search_calls: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    estimated_cost_microusd: Mapped[int] = mapped_column(BigInteger, default=0)
    web_search_cost_microusd: Mapped[int] = mapped_column(BigInteger, default=0)
    web_search_rate_microusd_per_call: Mapped[int] = mapped_column(
        BigInteger, default=10_000
    )
    cost_basis: Mapped[str] = mapped_column(String(50), default="pending")
    input_rate_microusd_per_million: Mapped[int] = mapped_column(BigInteger)
    cached_input_rate_microusd_per_million: Mapped[int] = mapped_column(BigInteger)
    output_rate_microusd_per_million: Mapped[int] = mapped_column(BigInteger)
    price_multiplier_bps: Mapped[int] = mapped_column(Integer, default=10_000)
    pricing_source: Mapped[str] = mapped_column(String(1000))
    pricing_effective_date: Mapped[str] = mapped_column(String(20))
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finalized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    intelligence_run: Mapped[IntelligenceRun | None] = relationship(
        back_populates="ai_usage_event"
    )
