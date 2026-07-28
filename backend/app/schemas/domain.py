from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class StrictBase(BaseModel):
    model_config = {"extra": "forbid", "str_strip_whitespace": True}


class EpistemicBase(StrictBase):
    limitations: str

    @field_validator("limitations")
    @classmethod
    def limitations_must_be_explicit(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError(
                "A limitação declarada é obrigatória. Indique o que este registo não permite concluir."
            )
        return value.strip()


class MissionCreate(StrictBase):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=240)
    description: str = ""
    objective: str = ""
    owner_user_id: str | None = None


class EntityCreate(StrictBase):
    kind: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=240)
    external_ref: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    sensitive_payload: str | None = None


class EventCreate(EpistemicBase):
    mission_id: str | None = None
    event_type: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=240)
    source: str = "manual"
    occurred_at: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    quality: float | None = Field(default=None, ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)


class ObservationCreate(EpistemicBase):
    mission_id: str | None = None
    investigation_id: str | None = None
    code: str = ""
    title: str = Field(min_length=1, max_length=240)
    observed_at: datetime | None = None
    source: str = "manual"
    method: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    quality: float | None = Field(default=None, ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)


class InvestigationCreate(EpistemicBase):
    mission_id: str | None = None
    title: str = Field(min_length=1, max_length=240)
    question: str = Field(min_length=1)
    impact_domain: str = "operational"
    impact_estimate: float | None = None
    owner_user_id: str | None = None


class HypothesisCreate(EpistemicBase):
    investigation_id: str
    statement: str = Field(min_length=1)
    prior: float = Field(0.5, ge=0, le=1)
    missing_data: list[str] = Field(default_factory=list)



class ProvenanceCreate(EpistemicBase):
    origin_type: Literal["human", "ai_model", "ai_agent", "system", "organization", "unknown"]
    origin_actor: str | None = Field(default=None, max_length=240)
    acquisition_type: Literal["direct_observation", "interview", "document", "sensor", "drone", "satellite", "api", "import", "generated", "other"] = "other"
    source_reference: str | None = None
    method_or_modality: str = Field(min_length=1)
    model_or_system: str | None = Field(default=None, max_length=240)
    version: str | None = Field(default=None, max_length=120)
    occurred_at: datetime | None = None
    input_context_reference: str | None = None
    policy_context: dict[str, Any] = Field(default_factory=dict)
    confidence_claim: float | None = Field(default=None, ge=0, le=1)
    uncertainty_notes: str = ""
    verification_status: Literal["declared", "in_review", "confirmed", "contested", "invalidated", "unavailable"] = "declared"
    verification_record: dict[str, Any] = Field(default_factory=dict)
    integrity_reference: str | None = Field(default=None, max_length=240)
    metadata_payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_machine_provenance(self):
        if self.origin_type != "human":
            missing = []
            if not self.model_or_system:
                missing.append("model_or_system")
            if not self.version:
                missing.append("version")
            if missing:
                raise ValueError(
                    "Contributos de origem não humana exigem model_or_system e version para serem auditáveis."
                )
        return self

class EvidenceCreate(EpistemicBase):
    investigation_id: str
    provenance_id: str | None = None
    provenance: ProvenanceCreate | None = None
    hypothesis_id: str | None = None
    observation_id: str | None = None
    direction: Literal["supports", "contradicts", "refutes", "neutral"] = "supports"
    title: str = Field(min_length=1, max_length=240)
    source: str = Field(min_length=1)
    method: str = Field(min_length=1)
    weight: float = Field(0.5, ge=0, le=1)
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def provenance_is_required(self):
        if bool(self.provenance_id) == bool(self.provenance):
            raise ValueError("Indique exatamente um de provenance_id ou provenance.")
        return self


class EvidenceProposalCreate(EpistemicBase):
    investigation_id: str
    title: str = Field(min_length=1, max_length=240)
    description: str = ""
    expected_effects: dict[str, float] = Field(default_factory=dict)
    weight: float = Field(0.5, ge=0, le=1)
    estimated_cost: float | None = Field(default=None, ge=0)
    estimated_days: float | None = Field(default=None, ge=0)
    risk_level: Literal["low", "medium", "high"] = "low"
    feasibility: Literal["unknown", "low", "medium", "high"] = "unknown"

    @field_validator("expected_effects")
    @classmethod
    def validate_effects(cls, value: dict[str, float]) -> dict[str, float]:
        for hypothesis_id, effect in value.items():
            if not -1 <= float(effect) <= 1:
                raise ValueError(
                    f"O efeito esperado para {hypothesis_id} deve estar entre -1 e 1."
                )
        return {str(k): float(v) for k, v in value.items()}


class AssumptionCreate(EpistemicBase):
    mission_id: str | None = None
    investigation_id: str | None = None
    decision_id: str | None = None
    code: str = ""
    statement: str = Field(min_length=1)
    status: Literal["active", "refuted", "expired", "superseded"] = "active"
    method: str = Field(min_length=1)
    valid_from: datetime | None = None
    valid_to: datetime | None = None


class ConstraintCreate(EpistemicBase):
    mission_id: str | None = None
    investigation_id: str | None = None
    decision_id: str | None = None
    code: str = ""
    statement: str = Field(min_length=1)
    status: Literal["active", "violated", "expired", "superseded"] = "active"
    source: str = Field(min_length=1)
    valid_from: datetime | None = None
    valid_to: datetime | None = None


class AlternativeCreate(EpistemicBase):
    mission_id: str | None = None
    investigation_id: str | None = None
    decision_id: str | None = None
    code: str = ""
    title: str = Field(min_length=1, max_length=240)
    description: str = ""
    status: Literal["considered", "selected", "rejected", "deferred"] = "considered"
    rejection_reason: str = ""
    criteria: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def rejected_requires_reason(self):
        if self.status == "rejected" and not self.rejection_reason.strip():
            raise ValueError("Uma alternativa rejeitada exige motivo de rejeição.")
        return self


class DecisionCreate(StrictBase):
    mission_id: str | None = None
    investigation_id: str | None = None
    title: str = Field(min_length=1, max_length=240)
    rationale: str = Field(min_length=1)
    risks: list[Any] = Field(default_factory=list)
    expected_outcome: str = ""


class ActionCreate(StrictBase):
    decision_id: str
    title: str = Field(min_length=1, max_length=240)
    owner_user_id: str | None = None
    cost: float | None = Field(default=None, ge=0)
    due_at: datetime | None = None


class ImplementationCreate(StrictBase):
    decision_id: str
    code: str = ""
    title: str = Field(min_length=1, max_length=240)
    status: Literal["planned", "in_progress", "completed", "cancelled"] = "planned"
    plan: dict[str, Any] = Field(default_factory=dict)
    deviations: list[Any] = Field(default_factory=list)
    evidence_of_execution: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None


class OutcomeCreate(EpistemicBase):
    action_id: str
    observed: str = Field(
        min_length=1,
        description="Descrição do resultado efetivamente observado, distinta do resultado esperado.",
    )
    expected: str = ""
    baseline: dict[str, Any] = Field(default_factory=dict)
    measured: dict[str, Any] = Field(default_factory=dict)
    attribution_confidence: float | None = Field(default=None, ge=0, le=1)


class LearningCreate(EpistemicBase):
    outcome_id: str | None = None
    statement: str = Field(min_length=1)
    status: Literal["emerging", "confirmed", "revised", "obsolete"] = "emerging"
    confidence: float = Field(0, ge=0, le=1)


class LearningReuseCreate(StrictBase):
    mission_id: str | None = None
    decision_id: str | None = None
    explanation: str = Field(min_length=1)


# Kept only for migration compatibility. Opportunity is not exposed in the public pilot API.
class OpportunityCreate(StrictBase):
    mission_id: str | None = None
    investigation_id: str | None = None
    title: str
    domain: str = "cost"
    estimated_value: float | None = None
    currency: str = "EUR"
    mechanism: str = ""
    baseline: dict[str, Any] = Field(default_factory=dict)
    validation_plan: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0, le=1)


class OpportunityUpdate(StrictBase):
    value_status: str | None = None
    realized_value: float | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class RelationCreate(StrictBase):
    source_type: str = Field(min_length=1)
    source_id: str
    target_type: str = Field(min_length=1)
    target_id: str
    relation_type: str = Field(min_length=1)
    strength: float | None = Field(default=None, ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    explanation: str = ""

    @model_validator(mode="after")
    def no_self_relation(self):
        if self.source_id == self.target_id and self.source_type == self.target_type:
            raise ValueError("Um objeto não pode ser relacionado consigo próprio.")
        return self


class StateChange(StrictBase):
    status: Literal["active", "violated", "expired", "superseded"]
    reason: str = Field(min_length=1)


class AttributionRequest(StrictBase):
    force_recalculate: bool = False


class APIKeyCreate(StrictBase):
    name: str
    scopes: list[str] = Field(default_factory=list)


class IntegrationCreate(StrictBase):
    kind: str
    name: str
    config: dict[str, Any]


class WebhookCreate(StrictBase):
    url: str
    events: list[str] = Field(default_factory=list)
