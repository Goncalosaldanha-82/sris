from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal
from urllib.parse import urlsplit

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
    research_context: bool = False

    @model_validator(mode="after")
    def research_requires_governed_ai(self) -> "AnalysisInput":
        if self.research_context and not self.use_ai:
            raise ValueError("Context research requires governed AI execution")
        return self


class ContextSource(StrictModel):
    source_id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=1000)
    url: str = Field(pattern=r"^https?://", max_length=3000)
    publisher: str = Field(default="", max_length=500)
    source_type: Literal[
        "academic",
        "official",
        "legal",
        "cartographic",
        "technical",
        "local_history",
        "news",
        "other",
    ] = "other"
    authority: Literal["primary", "secondary", "unknown"] = "unknown"
    publication_date: str | None = Field(default=None, max_length=40)
    limitations: str = Field(default="", max_length=5000)

    @field_validator("url")
    @classmethod
    def require_absolute_http_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("Context source URL must be an absolute HTTP(S) URL")
        return value


class ContextClaim(StrictModel):
    claim_id: str = Field(min_length=1, max_length=120)
    statement: str = Field(min_length=1, max_length=5000)
    domain: str = Field(min_length=1, max_length=160)
    epistemic_status: Literal[
        "supported",
        "partially_supported",
        "hypothesis",
        "contested",
        "unverified",
    ]
    source_ids: list[str] = Field(default_factory=list, max_length=50)
    relevance: str = Field(default="", max_length=5000)
    limitations: str = Field(default="", max_length=5000)

    @model_validator(mode="after")
    def supported_claims_require_sources(self) -> "ContextClaim":
        if self.epistemic_status in {
            "supported",
            "partially_supported",
            "contested",
        } and not self.source_ids:
            raise ValueError("Supported or contested context claims require sources")
        return self


class ContextGap(StrictModel):
    gap_id: str = Field(min_length=1, max_length=120)
    question: str = Field(min_length=1, max_length=5000)
    domain: str = Field(min_length=1, max_length=160)
    why_it_matters: str = Field(default="", max_length=5000)
    evidence_needed: str = Field(default="", max_length=5000)
    priority: Literal["critical", "high", "medium", "low"] = "medium"


class ContextDossier(StrictModel):
    dossier_version: Literal["1.0"] = "1.0"
    mission_id: str = Field(min_length=1, max_length=100)
    scope: str = Field(min_length=1, max_length=5000)
    synthesis: str = Field(default="", max_length=15000)
    domains: list[str] = Field(default_factory=list, max_length=50)
    sources: list[ContextSource] = Field(default_factory=list, max_length=200)
    claims: list[ContextClaim] = Field(default_factory=list, max_length=500)
    gaps: list[ContextGap] = Field(default_factory=list, max_length=300)
    limits: list[str] = Field(default_factory=list, max_length=100)
    research_status: Literal[
        "not_started",
        "preliminary",
        "in_review",
        "reviewed",
    ] = "in_review"
    review_required: bool = True

    @model_validator(mode="after")
    def validate_context_graph(self) -> "ContextDossier":
        source_ids = [source.source_id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Context source IDs must be unique")
        source_urls = [source.url.rstrip("/").casefold() for source in self.sources]
        if len(source_urls) != len(set(source_urls)):
            raise ValueError("Context source URLs must be unique")
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("Context claim IDs must be unique")
        known_sources = set(source_ids)
        for claim in self.claims:
            unknown = set(claim.source_ids) - known_sources
            if unknown:
                raise ValueError(
                    "Context claims reference unknown sources: "
                    + ", ".join(sorted(unknown))
                )
        return self


class ContextAssessment(StrictModel):
    status: Literal[
        "not_required",
        "not_started",
        "preliminary",
        "in_review",
        "reviewed",
    ]
    domains: list[str] = Field(default_factory=list)
    source_count: int = Field(default=0, ge=0)
    supported_claim_count: int = Field(default=0, ge=0)
    hypothesis_count: int = Field(default=0, ge=0)
    unverified_claim_count: int = Field(default=0, ge=0)
    critical_gap_count: int = Field(default=0, ge=0)
    synthesis: str = ""
    boundary: str = ""


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
    context_assessment: ContextAssessment
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


class AIResearchBundle(StrictModel):
    context_dossier: ContextDossier
    advisory: AIAdvisory


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
    per_request_output_token_limit: int = Field(default=6_000, ge=500, le=128_000)
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
