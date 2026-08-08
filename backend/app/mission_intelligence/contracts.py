from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ConfidenceLevel(StrEnum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    NOT_EVALUABLE = "not_evaluable"


class MissionStatus(StrEnum):
    ON_TRACK = "on_track"
    REQUIRES_ATTENTION = "requires_attention"
    CRITICAL = "critical"
    COMPLETED = "completed"


class MissionTrend(StrEnum):
    IMPROVING = "improving"
    STABLE = "stable"
    DETERIORATING = "deteriorating"
    NOT_EVALUABLE = "not_evaluable"


class RecordKind(StrEnum):
    OBSERVATION = "observation"
    REPRESENTATION = "representation"
    INFORMATION = "information"
    EVIDENCE = "evidence"
    KNOWLEDGE = "knowledge"
    HYPOTHESIS = "hypothesis"
    ASSUMPTION = "assumption"
    CONSTRAINT = "constraint"
    ALTERNATIVE = "alternative"
    DECISION = "decision"
    ACTION = "action"
    OUTCOME = "outcome"
    LEARNING = "learning"


class Provenance(StrictModel):
    origin_type: Literal["human", "system", "ai_model", "unspecified"] = "unspecified"
    source: str = Field(default="", max_length=1000)
    method: str = Field(default="", max_length=10000)
    limitations: str = Field(default="", max_length=10000)
    model_or_system: str | None = Field(default=None, max_length=240)
    version: str | None = Field(default=None, max_length=120)
    verification_status: Literal[
        "declared", "in_review", "confirmed", "invalidated"
    ] = "declared"

    @model_validator(mode="after")
    def require_machine_identity(self) -> "Provenance":
        if self.origin_type in {"system", "ai_model"} and (
            not self.model_or_system or not self.version
        ):
            raise ValueError("Machine provenance requires model_or_system and version")
        return self


class MissionRecord(StrictModel):
    canonical_id: str = Field(min_length=1, max_length=100)
    kind: RecordKind
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=30000)
    state: str = Field(default="declared", max_length=80)
    confidence: ConfidenceLevel = ConfidenceLevel.NOT_EVALUABLE
    provenance: Provenance
    observed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MissionRelation(StrictModel):
    relation_id: str = Field(min_length=1, max_length=120)
    source_id: str = Field(min_length=1, max_length=100)
    target_id: str = Field(min_length=1, max_length=100)
    relation_type: str = Field(min_length=1, max_length=100)
    explanation: str = Field(default="", max_length=10000)
    confidence: ConfidenceLevel = ConfidenceLevel.NOT_EVALUABLE


class MissionDocumentV13(StrictModel):
    schema_name: Literal["sris.mission"] = "sris.mission"
    schema_version: Literal["1.3"] = "1.3"
    mission_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=500)
    context: str = Field(default="", max_length=30000)
    central_question: str = Field(default="", max_length=10000)
    records: list[MissionRecord] = Field(default_factory=list, max_length=1000)
    relations: list[MissionRelation] = Field(default_factory=list, max_length=3000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_identity_graph(self) -> "MissionDocumentV13":
        ids = [record.canonical_id for record in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("Mission record canonical IDs must be unique")
        known = set(ids)
        for relation in self.relations:
            if relation.source_id not in known or relation.target_id not in known:
                raise ValueError("Mission relations must reference existing records")
        return self


class AnalysisInput(StrictModel):
    title: str = Field(default="", max_length=500)
    context: str = Field(default="", max_length=30000)
    central_question: str = Field(default="", max_length=10000)
    available_evidence: str = Field(default="", max_length=30000)
    unknowns: str = Field(default="", max_length=30000)
    use_ai: bool = False


class Gap(StrictModel):
    code: str
    severity: Literal["high", "medium", "low"]
    title: str
    explanation: str
    affected_ids: list[str] = Field(default_factory=list)
    evidence_needed: str = ""


class ConfidenceFactor(StrictModel):
    factor: str
    assessment: Literal["strong", "partial", "weak", "not_applicable"]
    explanation: str


class AlternativeView(StrictModel):
    canonical_id: str
    title: str
    state: str
    description: str = ""


class DeterministicReport(StrictModel):
    methodology_version: str
    mission_status: MissionStatus
    mission_trend: MissionTrend
    decision_confidence: ConfidenceLevel
    confidence_factors: list[ConfidenceFactor]
    headline: str
    summary: str
    principal_risk: str
    next_decision: str
    gaps: list[Gap]
    assumptions_to_test: list[str]
    alternatives: list[AlternativeView]
    non_inferences: list[str]
    counts: dict[str, int]
    review_required: bool = True


class AIInference(StrictModel):
    statement: str
    based_on_ids: list[str]
    uncertainty: str
    confidence: ConfidenceLevel

    @field_validator("based_on_ids")
    @classmethod
    def require_basis(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("Every AI inference must cite at least one canonical ID")
        return value


class AIOption(StrictModel):
    title: str
    rationale: str
    risks: list[str]
    prerequisites: list[str]
    based_on_ids: list[str]

    @field_validator("based_on_ids")
    @classmethod
    def require_basis(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("Every AI option must cite at least one canonical ID")
        return value


class AIAdvisory(StrictModel):
    executive_summary: str
    inferences: list[AIInference]
    critical_gaps: list[str]
    decision_options: list[AIOption]
    recommended_next_step: str
    cautions: list[str]


class ReviewRequest(StrictModel):
    decision: Literal["approved", "rejected"]
    comment: str = Field(min_length=3, max_length=10000)


class AIGovernancePolicyUpdate(StrictModel):
    enabled: bool = False
    monthly_request_limit: int = Field(default=20, ge=1, le=100_000)
    monthly_input_token_limit: int = Field(default=250_000, ge=1_000, le=1_000_000_000)
    monthly_output_token_limit: int = Field(default=50_000, ge=500, le=1_000_000_000)
    monthly_budget_usd: Decimal = Field(
        default=Decimal("5.00"),
        gt=Decimal("0"),
        le=Decimal("1000000"),
        decimal_places=6,
    )
    per_request_input_token_limit: int = Field(default=60_000, ge=1_000, le=1_000_000)
    per_request_output_token_limit: int = Field(default=3_000, ge=500, le=128_000)
    max_concurrent_requests: int = Field(default=1, ge=1, le=100)

    @model_validator(mode="after")
    def validate_limits(self) -> "AIGovernancePolicyUpdate":
        if self.per_request_input_token_limit > self.monthly_input_token_limit:
            raise ValueError(
                "per_request_input_token_limit cannot exceed the monthly input limit"
            )
        if self.per_request_output_token_limit > self.monthly_output_token_limit:
            raise ValueError(
                "per_request_output_token_limit cannot exceed the monthly output limit"
            )
        return self
