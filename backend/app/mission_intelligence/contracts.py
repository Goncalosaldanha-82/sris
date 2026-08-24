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
    # Mission scale is a storage/retrieval concern, not a provider-context
    # limit. A mission may therefore grow beyond one model call's window.
    records: list[MissionRecord] = Field(default_factory=list)
    relations: list[MissionRelation] = Field(default_factory=list)
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


class MissionCreateRequest(StrictModel):
    """Create an institutional mission without converting narrative into evidence."""

    code: str | None = Field(default=None, min_length=2, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    title: str = Field(min_length=3, max_length=300)
    objective: str = Field(min_length=10, max_length=10000)
    context: str = Field(min_length=10, max_length=30000)
    central_question: str = Field(min_length=10, max_length=10000)
    parent_mission_id: str | None = Field(default=None, max_length=36)
    mission_kind: Literal["program", "mission"] = "mission"
    domain: str = Field(default="cross_domain", min_length=2, max_length=80)
    priority: Literal["critical", "strategic", "standard", "exploratory"] = "strategic"
    horizon: str = Field(default="", max_length=120)
    stakeholders: list[str] = Field(default_factory=list, max_length=50)
    validation_profile: Literal[
        "none",
        "measurable_decision",
        "tourism_advance_resource_efficiency",
    ] = "none"


class MissionUpdateRequest(StrictModel):
    """Revise mission identity or hierarchy with optimistic concurrency."""

    expected_revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=3, max_length=300)
    objective: str | None = Field(default=None, min_length=10, max_length=10000)
    context: str | None = Field(default=None, min_length=10, max_length=30000)
    central_question: str | None = Field(default=None, min_length=10, max_length=10000)
    parent_mission_id: str | None = Field(default=None, max_length=36)
    clear_parent: bool = False
    mission_kind: Literal["program", "mission"] | None = None
    domain: str | None = Field(default=None, min_length=2, max_length=80)
    priority: Literal["critical", "strategic", "standard", "exploratory"] | None = None
    horizon: str | None = Field(default=None, max_length=120)
    stakeholders: list[str] | None = Field(default=None, max_length=50)
    validation_profile: Literal[
        "none",
        "measurable_decision",
        "tourism_advance_resource_efficiency",
    ] | None = None
    lifecycle_state: Literal["active", "paused", "completed", "archived"] | None = None
    change_note: str = Field(min_length=3, max_length=1000)

    @model_validator(mode="after")
    def parent_instruction_is_unambiguous(self) -> "MissionUpdateRequest":
        if self.clear_parent and self.parent_mission_id is not None:
            raise ValueError("Use clear_parent or parent_mission_id, not both")
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


class MIInteractionIntent(StrEnum):
    """The cognitive job requested from the interactive intelligence layer."""

    DIAGNOSE = "diagnose"
    ANSWER = "answer"
    CHALLENGE = "challenge"
    EXPLORE_ALTERNATIVES = "explore_alternatives"
    DESIGN_EXPERIMENT = "design_experiment"
    COMPARE_OPTIONS = "compare_options"
    SYNTHESIZE = "synthesize"


class MIQuestionAnswer(StrictModel):
    question_id: str = Field(min_length=1, max_length=120)
    answer: str = Field(min_length=1, max_length=12000)


class MIInteractionInput(StrictModel):
    """One governed turn in a mission-scoped intelligence dialogue."""

    session_id: str | None = Field(default=None, max_length=36)
    intent: MIInteractionIntent = MIInteractionIntent.DIAGNOSE
    message: str = Field(min_length=1, max_length=12000)
    answers: list[MIQuestionAnswer] = Field(default_factory=list, max_length=30)
    # All referenced sources remain attached to the governed turn. The
    # provider receives only a retrieved working set, so this list must not be
    # confused with a per-call context limit.
    attachment_ids: list[str] = Field(default_factory=list)
    mission_input: AnalysisInput = Field(default_factory=AnalysisInput)
    research_context: bool = False

    @field_validator("attachment_ids")
    @classmethod
    def require_unique_attachment_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Attachment IDs must be unique within a turn")
        return value


class MIDirectAnswer(StrictModel):
    answer: str = Field(min_length=1, max_length=12000)
    status: Literal[
        "provisional",
        "conditional",
        "blocked_by_missing_information",
    ]
    what_changed: str = Field(
        min_length=1,
        max_length=5000,
        description=(
            "What this turn adds or changes relative to the canonical mission and prior turns."
        ),
    )


class MIMissionReading(StrictModel):
    decision_problem: str = Field(min_length=1, max_length=5000)
    current_blocker: str = Field(min_length=1, max_length=5000)
    key_tension: str = Field(min_length=1, max_length=5000)
    blind_spot: str = Field(min_length=1, max_length=5000)
    based_on_ids: list[str] = Field(min_length=1, max_length=50)


class MIDecisionUpdate(StrictModel):
    decision_before: str = Field(min_length=1, max_length=3000)
    decision_now: str = Field(min_length=1, max_length=3000)
    what_changed: str = Field(min_length=1, max_length=3000)
    confidence_before: ConfidenceLevel
    confidence_now: ConfidenceLevel
    confidence_direction: Literal["increased", "decreased", "unchanged", "not_evaluable"]
    reason: str = Field(min_length=1, max_length=3000)
    remaining_uncertainty: str = Field(min_length=1, max_length=3000)
    based_on_ids: list[str] = Field(min_length=1, max_length=50)


class MIConfidenceChange(StrictModel):
    subject_id: str = Field(min_length=1, max_length=120)
    subject: str = Field(min_length=1, max_length=1000)
    confidence_before: ConfidenceLevel
    confidence_now: ConfidenceLevel
    direction: Literal["increased", "decreased", "unchanged", "not_evaluable"]
    reason: str = Field(min_length=1, max_length=3000)
    based_on_ids: list[str] = Field(min_length=1, max_length=50)


class MIClarifyingQuestion(StrictModel):
    question_id: str = Field(pattern=r"^Q-[A-Z0-9][A-Z0-9_-]{1,117}$")
    question: str = Field(min_length=1, max_length=5000)
    why_it_matters: str = Field(min_length=1, max_length=5000)
    priority: Literal["critical", "high", "medium", "low"]
    answer_type: Literal[
        "free_text",
        "yes_no",
        "single_choice",
        "multi_choice",
        "number",
        "date",
    ]
    options: list[str] = Field(default_factory=list, max_length=12)
    decision_unlocked: str = Field(min_length=1, max_length=3000)
    based_on_ids: list[str] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def choices_require_options(self) -> "MIClarifyingQuestion":
        if self.answer_type in {"single_choice", "multi_choice"} and len(self.options) < 2:
            raise ValueError("Choice questions require at least two options")
        if self.answer_type not in {"single_choice", "multi_choice"} and self.options:
            raise ValueError("Only choice questions may define options")
        return self


class MIHypothesisProposal(StrictModel):
    proposal_id: str = Field(pattern=r"^HYP-AI-[A-Z0-9][A-Z0-9_-]{1,111}$")
    statement: str = Field(min_length=1, max_length=5000)
    rationale: str = Field(min_length=1, max_length=5000)
    what_is_new: str = Field(min_length=1, max_length=3000)
    based_on_ids: list[str] = Field(min_length=1, max_length=50)
    evidence_needed: list[str] = Field(min_length=1, max_length=30)
    disconfirming_evidence: list[str] = Field(min_length=1, max_length=30)
    confidence: ConfidenceLevel
    impact_if_true: str = Field(min_length=1, max_length=3000)
    epistemic_status: Literal["hypothesis_for_testing"] = "hypothesis_for_testing"


class MIAlternativeProposal(StrictModel):
    proposal_id: str = Field(pattern=r"^ALT-AI-[A-Z0-9][A-Z0-9_-]{1,111}$")
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=7000)
    difference_from_existing: str = Field(min_length=1, max_length=5000)
    potential_value: list[str] = Field(min_length=1, max_length=30)
    risks: list[str] = Field(min_length=1, max_length=30)
    prerequisites: list[str] = Field(min_length=1, max_length=30)
    reversibility: Literal["high", "moderate", "low", "unknown"]
    based_on_ids: list[str] = Field(min_length=1, max_length=50)
    epistemic_status: Literal["alternative_proposal"] = "alternative_proposal"


class MIDecisionCriterionProposal(StrictModel):
    proposal_id: str = Field(pattern=r"^CRT-AI-[A-Z0-9][A-Z0-9_-]{1,111}$")
    name: str = Field(min_length=1, max_length=500)
    definition: str = Field(min_length=1, max_length=4000)
    measurement: str = Field(min_length=1, max_length=4000)
    threshold_or_rule: str = Field(min_length=1, max_length=4000)
    trade_off: str = Field(min_length=1, max_length=4000)
    based_on_ids: list[str] = Field(min_length=1, max_length=50)
    epistemic_status: Literal["criterion_proposal"] = "criterion_proposal"


class MIExperimentProposal(StrictModel):
    proposal_id: str = Field(pattern=r"^EXP-AI-[A-Z0-9][A-Z0-9_-]{1,111}$")
    title: str = Field(min_length=1, max_length=500)
    question: str = Field(min_length=1, max_length=5000)
    target_hypothesis_ids: list[str] = Field(min_length=1, max_length=30)
    design: str = Field(min_length=1, max_length=7000)
    baseline: str = Field(min_length=1, max_length=4000)
    comparator: str = Field(min_length=1, max_length=4000)
    measures: list[str] = Field(min_length=1, max_length=30)
    success_or_decision_rules: list[str] = Field(min_length=1, max_length=30)
    stop_conditions: list[str] = Field(min_length=1, max_length=30)
    timeframe: str = Field(min_length=1, max_length=1000)
    limitations: list[str] = Field(min_length=1, max_length=30)
    based_on_ids: list[str] = Field(min_length=1, max_length=50)
    epistemic_status: Literal["experiment_proposal"] = "experiment_proposal"


class MICriticalChallenge(StrictModel):
    challenge_id: str = Field(pattern=r"^CHL-AI-[A-Z0-9][A-Z0-9_-]{1,111}$")
    target: str = Field(min_length=1, max_length=3000)
    objection: str = Field(min_length=1, max_length=5000)
    why_it_matters: str = Field(min_length=1, max_length=5000)
    response_needed: str = Field(min_length=1, max_length=5000)
    based_on_ids: list[str] = Field(min_length=1, max_length=50)


class MIRecommendedAction(StrictModel):
    action_id: str = Field(pattern=r"^ACT-AI-[A-Z0-9][A-Z0-9_-]{1,111}$")
    action: str = Field(min_length=1, max_length=5000)
    purpose: str = Field(min_length=1, max_length=4000)
    owner_role: str = Field(min_length=1, max_length=500)
    dependencies: list[str] = Field(default_factory=list, max_length=30)
    urgency: Literal["now", "next", "later"]
    action_class: Literal[
        "documentary_no_touch",
        "access_non_intrusive",
        "intrusive",
    ]
    authorization_note: str = Field(min_length=1, max_length=2000)
    decision_effect: str = Field(min_length=1, max_length=4000)
    based_on_ids: list[str] = Field(min_length=1, max_length=50)


class MIInteractionBoundary(StrictModel):
    human_review_required: Literal[True] = True
    canonical_mutation: Literal["prohibited_without_explicit_human_promotion"] = (
        "prohibited_without_explicit_human_promotion"
    )
    facts_added: Literal[False] = False
    statement: str = Field(min_length=1, max_length=3000)


class MIInteractiveOutput(StrictModel):
    """Structured output for an active, mission-scoped reasoning turn."""

    response_version: Literal["2.3"] = "2.3"
    intent: MIInteractionIntent
    direct_answer: MIDirectAnswer
    mission_reading: MIMissionReading
    decision_update: MIDecisionUpdate
    confidence_changes: list[MIConfidenceChange] = Field(min_length=1, max_length=8)
    questions: list[MIClarifyingQuestion] = Field(default_factory=list, max_length=8)
    hypotheses: list[MIHypothesisProposal] = Field(default_factory=list, max_length=8)
    alternative_proposals: list[MIAlternativeProposal] = Field(
        default_factory=list,
        max_length=8,
    )
    decision_criteria: list[MIDecisionCriterionProposal] = Field(
        default_factory=list,
        max_length=12,
    )
    experiment_proposals: list[MIExperimentProposal] = Field(
        default_factory=list,
        max_length=6,
    )
    challenges: list[MICriticalChallenge] = Field(default_factory=list, max_length=8)
    recommended_actions: list[MIRecommendedAction] = Field(
        default_factory=list,
        max_length=10,
    )
    recommended_next_move: str = Field(min_length=1, max_length=5000)
    boundary: MIInteractionBoundary

    @model_validator(mode="after")
    def require_unique_generated_ids(self) -> "MIInteractiveOutput":
        generated = [
            *(item.question_id for item in self.questions),
            *(item.proposal_id for item in self.hypotheses),
            *(item.proposal_id for item in self.alternative_proposals),
            *(item.proposal_id for item in self.decision_criteria),
            *(item.proposal_id for item in self.experiment_proposals),
            *(item.challenge_id for item in self.challenges),
            *(item.action_id for item in self.recommended_actions),
        ]
        if len(generated) != len(set(generated)):
            raise ValueError("Interactive output IDs must be unique within a turn")
        return self


class MIInteractiveResearchBundle(StrictModel):
    context_dossier: ContextDossier
    intelligence: MIInteractiveOutput


class MIProposalReviewRequest(StrictModel):
    decision: Literal["accepted_as_draft", "rejected", "deferred"]
    comment: str = Field(min_length=3, max_length=10000)


class ReviewRequest(StrictModel):
    decision: Literal["approved", "rejected"]
    comment: str = Field(min_length=3, max_length=10000)


class AIGovernancePolicyUpdate(StrictModel):
    enabled: bool = False
    enforce_monthly_limits: bool = False
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
        if (
            self.enforce_monthly_limits
            and self.per_request_input_token_limit > self.monthly_input_token_limit
        ):
            raise ValueError(
                "per_request_input_token_limit cannot exceed the monthly input limit"
            )
        if (
            self.enforce_monthly_limits
            and self.per_request_output_token_limit > self.monthly_output_token_limit
        ):
            raise ValueError(
                "per_request_output_token_limit cannot exceed the monthly output limit"
            )
        return self
