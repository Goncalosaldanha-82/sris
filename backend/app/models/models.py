import enum, uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, JSON, Float, Integer, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db import Base

def uid(): return str(uuid.uuid4())
def now(): return datetime.now(timezone.utc)

class Role(str, enum.Enum):
    owner="owner"; admin="admin"; manager="manager"; analyst="analyst"; contributor="contributor"; viewer="viewer"; auditor="auditor"
class Status(str, enum.Enum):
    draft="draft"; active="active"; paused="paused"; closed="closed"; archived="archived"
class ValueStatus(str, enum.Enum):
    identified="identified"; validating="validating"; realized="realized"; rejected="rejected"

class Organization(Base):
    __tablename__="organizations"
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str]=mapped_column(String(200), nullable=False)
    slug: Mapped[str]=mapped_column(String(120), unique=True, index=True)
    active: Mapped[bool]=mapped_column(Boolean, default=True)
    settings: Mapped[dict]=mapped_column(JSON, default=dict)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)

class User(Base):
    __tablename__="users"
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str]=mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str]=mapped_column(String(200), default="")
    password_hash: Mapped[str]=mapped_column(String(200))
    active: Mapped[bool]=mapped_column(Boolean, default=True)
    is_platform_admin: Mapped[bool]=mapped_column(Boolean, default=False)
    mfa_enabled: Mapped[bool]=mapped_column(Boolean, default=False)
    token_version: Mapped[int]=mapped_column(Integer, default=1)
    last_login_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)

class Membership(Base):
    __tablename__="memberships"
    __table_args__=(UniqueConstraint("organization_id","user_id",name="uq_membership"),)
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str]=mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str]=mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str]=mapped_column(String(30), default=Role.viewer.value)
    active: Mapped[bool]=mapped_column(Boolean, default=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)

class TenantMixin:
    organization_id: Mapped[str]=mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)

class Mission(Base, TenantMixin):
    __tablename__="missions"
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid)
    code: Mapped[str]=mapped_column(String(40), index=True)
    name: Mapped[str]=mapped_column(String(240))
    description: Mapped[str]=mapped_column(Text, default="")
    objective: Mapped[str]=mapped_column(Text, default="")
    status: Mapped[str]=mapped_column(String(30), default=Status.active.value)
    owner_user_id: Mapped[str|None]=mapped_column(ForeignKey("users.id"), nullable=True)
    starts_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)

class OrgEntity(Base, TenantMixin):
    __tablename__="org_entities"
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid)
    kind: Mapped[str]=mapped_column(String(60), index=True)
    name: Mapped[str]=mapped_column(String(240))
    external_ref: Mapped[str|None]=mapped_column(String(200), nullable=True, index=True)
    status: Mapped[str]=mapped_column(String(30), default="active")
    attributes: Mapped[dict]=mapped_column(JSON, default=dict)
    sensitive_payload: Mapped[str|None]=mapped_column(Text, nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)

class Relation(Base, TenantMixin):
    __tablename__="relations"
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid)
    source_type: Mapped[str]=mapped_column(String(50)); source_id: Mapped[str]=mapped_column(String(36), index=True)
    target_type: Mapped[str]=mapped_column(String(50)); target_id: Mapped[str]=mapped_column(String(36), index=True)
    relation_type: Mapped[str]=mapped_column(String(60), index=True)
    strength: Mapped[float|None]=mapped_column(Float, nullable=True)
    confidence: Mapped[float|None]=mapped_column(Float, nullable=True)
    valid_from: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    explanation: Mapped[str]=mapped_column(Text, default="")
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)

class Event(Base, TenantMixin):
    __tablename__="events"
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid)
    mission_id: Mapped[str|None]=mapped_column(ForeignKey("missions.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type: Mapped[str]=mapped_column(String(80), index=True)
    occurred_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now, index=True)
    source: Mapped[str]=mapped_column(String(120), default="manual")
    title: Mapped[str]=mapped_column(String(240))
    payload: Mapped[dict]=mapped_column(JSON, default=dict)
    quality: Mapped[float|None]=mapped_column(Float, nullable=True)
    confidence: Mapped[float|None]=mapped_column(Float, nullable=True)
    limitations: Mapped[str]=mapped_column(Text, default="")
    created_by: Mapped[str|None]=mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)

class Investigation(Base, TenantMixin):
    __tablename__="investigations"
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid)
    mission_id: Mapped[str|None]=mapped_column(ForeignKey("missions.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str]=mapped_column(String(240)); question: Mapped[str]=mapped_column(Text)
    status: Mapped[str]=mapped_column(String(30), default="open")
    impact_domain: Mapped[str]=mapped_column(String(60), default="operational")
    impact_estimate: Mapped[float|None]=mapped_column(Float, nullable=True)
    owner_user_id: Mapped[str|None]=mapped_column(ForeignKey("users.id"), nullable=True)
    limitations: Mapped[str]=mapped_column(Text, default="")
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)

class Hypothesis(Base, TenantMixin):
    __tablename__="hypotheses"
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid)
    investigation_id: Mapped[str]=mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    statement: Mapped[str]=mapped_column(Text)
    status: Mapped[str]=mapped_column(String(30), default="active")
    prior: Mapped[float]=mapped_column(Float, default=0.5)
    confidence: Mapped[float]=mapped_column(Float, default=0.0)
    missing_data: Mapped[list]=mapped_column(JSON, default=list)
    limitations: Mapped[str]=mapped_column(Text, default="")
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)


class Provenance(Base, TenantMixin):
    __tablename__="provenance_records"
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid)
    origin_type: Mapped[str]=mapped_column(String(30), index=True)
    origin_actor: Mapped[str|None]=mapped_column(String(240), nullable=True)
    acquisition_type: Mapped[str]=mapped_column(String(40), default="other", index=True)
    source_reference: Mapped[str|None]=mapped_column(Text, nullable=True)
    method_or_modality: Mapped[str]=mapped_column(Text)
    model_or_system: Mapped[str|None]=mapped_column(String(240), nullable=True)
    version: Mapped[str|None]=mapped_column(String(120), nullable=True)
    occurred_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now, index=True)
    input_context_reference: Mapped[str|None]=mapped_column(Text, nullable=True)
    policy_context: Mapped[dict]=mapped_column(JSON, default=dict)
    confidence_claim: Mapped[float|None]=mapped_column(Float, nullable=True)
    uncertainty_notes: Mapped[str]=mapped_column(Text, default="")
    limitations: Mapped[str]=mapped_column(Text)
    verification_status: Mapped[str]=mapped_column(String(30), default="declared", index=True)
    verification_record: Mapped[dict]=mapped_column(JSON, default=dict)
    integrity_reference: Mapped[str|None]=mapped_column(String(240), nullable=True)
    metadata_payload: Mapped[dict]=mapped_column(JSON, default=dict)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)

class Evidence(Base, TenantMixin):
    __tablename__="evidence"
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid)
    investigation_id: Mapped[str]=mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    observation_id: Mapped[str|None]=mapped_column(ForeignKey("observations.id", ondelete="SET NULL"), nullable=True, index=True)
    hypothesis_id: Mapped[str|None]=mapped_column(ForeignKey("hypotheses.id", ondelete="SET NULL"), nullable=True, index=True)
    provenance_id: Mapped[str|None]=mapped_column(ForeignKey("provenance_records.id", ondelete="SET NULL"), nullable=True, index=True)
    direction: Mapped[str]=mapped_column(String(20), default="supports")
    title: Mapped[str]=mapped_column(String(240)); source: Mapped[str]=mapped_column(String(200), default="")
    method: Mapped[str]=mapped_column(Text, default=""); limitations: Mapped[str]=mapped_column(Text, default="")
    weight: Mapped[float]=mapped_column(Float, default=0.5); payload: Mapped[dict]=mapped_column(JSON, default=dict)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)

class EvidenceProposal(Base, TenantMixin):
    __tablename__="evidence_proposals"
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid)
    investigation_id: Mapped[str]=mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    title: Mapped[str]=mapped_column(String(240))
    description: Mapped[str]=mapped_column(Text, default="")
    expected_effects: Mapped[dict]=mapped_column(JSON, default=dict)
    weight: Mapped[float]=mapped_column(Float, default=0.5)
    estimated_cost: Mapped[float|None]=mapped_column(Float, nullable=True)
    estimated_days: Mapped[float|None]=mapped_column(Float, nullable=True)
    risk_level: Mapped[str]=mapped_column(String(20), default="low")
    feasibility: Mapped[str]=mapped_column(String(30), default="unknown")
    status: Mapped[str]=mapped_column(String(30), default="proposed", index=True)
    limitations: Mapped[str]=mapped_column(Text, default="")
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)

class Decision(Base, TenantMixin):
    __tablename__="decisions"
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid)
    mission_id: Mapped[str|None]=mapped_column(ForeignKey("missions.id"), nullable=True, index=True)
    investigation_id: Mapped[str|None]=mapped_column(ForeignKey("investigations.id"), nullable=True, index=True)
    title: Mapped[str]=mapped_column(String(240)); rationale: Mapped[str]=mapped_column(Text)
    # Legacy JSON fields retained only for backwards-compatible import. New records use
    # Alternative, Assumption and Constraint as first-class versionable entities.
    alternatives: Mapped[list]=mapped_column(JSON, default=list)
    assumptions: Mapped[list]=mapped_column(JSON, default=list)
    risks: Mapped[list]=mapped_column(JSON, default=list)
    expected_outcome: Mapped[str]=mapped_column(Text, default="")
    decided_by: Mapped[str|None]=mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)

class Action(Base, TenantMixin):
    __tablename__="actions"
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid)
    decision_id: Mapped[str]=mapped_column(ForeignKey("decisions.id", ondelete="CASCADE"), index=True)
    title: Mapped[str]=mapped_column(String(240)); status: Mapped[str]=mapped_column(String(30), default="planned")
    owner_user_id: Mapped[str|None]=mapped_column(ForeignKey("users.id"), nullable=True)
    cost: Mapped[float|None]=mapped_column(Float, nullable=True); starts_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    due_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True); completed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    evidence_of_execution: Mapped[dict]=mapped_column(JSON, default=dict)

class Outcome(Base, TenantMixin):
    __tablename__="outcomes"
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid)
    action_id: Mapped[str]=mapped_column(ForeignKey("actions.id", ondelete="CASCADE"), index=True)
    observed: Mapped[str]=mapped_column(Text); expected: Mapped[str]=mapped_column(Text, default="")
    baseline: Mapped[dict]=mapped_column(JSON, default=dict); measured: Mapped[dict]=mapped_column(JSON, default=dict)
    attribution_confidence: Mapped[float|None]=mapped_column(Float, nullable=True)
    limitations: Mapped[str]=mapped_column(Text, default=""); observed_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)

class Learning(Base, TenantMixin):
    __tablename__="learnings"
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid)
    outcome_id: Mapped[str|None]=mapped_column(ForeignKey("outcomes.id"), nullable=True, index=True)
    statement: Mapped[str]=mapped_column(Text); status: Mapped[str]=mapped_column(String(30), default="emerging")
    confidence: Mapped[float]=mapped_column(Float, default=0.0); valid_until: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    reuse_count: Mapped[int]=mapped_column(Integer, default=0); last_reused_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    limitations: Mapped[str]=mapped_column(Text, default="")
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)

class Opportunity(Base, TenantMixin):
    __tablename__="opportunities"
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid)
    mission_id: Mapped[str|None]=mapped_column(ForeignKey("missions.id"), nullable=True, index=True)
    investigation_id: Mapped[str|None]=mapped_column(ForeignKey("investigations.id"), nullable=True, index=True)
    title: Mapped[str]=mapped_column(String(240)); domain: Mapped[str]=mapped_column(String(60), default="cost")
    value_status: Mapped[str]=mapped_column(String(30), default=ValueStatus.identified.value)
    estimated_value: Mapped[float|None]=mapped_column(Float, nullable=True); realized_value: Mapped[float|None]=mapped_column(Float, nullable=True)
    currency: Mapped[str]=mapped_column(String(3), default="EUR"); mechanism: Mapped[str]=mapped_column(Text, default="")
    baseline: Mapped[dict]=mapped_column(JSON, default=dict); validation_plan: Mapped[dict]=mapped_column(JSON, default=dict)
    confidence: Mapped[float|None]=mapped_column(Float, nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)


class Observation(Base, TenantMixin):
    __tablename__="observations"
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid)
    mission_id: Mapped[str|None]=mapped_column(ForeignKey("missions.id", ondelete="SET NULL"), nullable=True, index=True)
    investigation_id: Mapped[str|None]=mapped_column(ForeignKey("investigations.id", ondelete="SET NULL"), nullable=True, index=True)
    code: Mapped[str]=mapped_column(String(40), default="", index=True)
    title: Mapped[str]=mapped_column(String(240))
    observed_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now, index=True)
    source: Mapped[str]=mapped_column(String(200), default="manual")
    method: Mapped[str]=mapped_column(Text, default="")
    limitations: Mapped[str]=mapped_column(Text, default="")
    payload: Mapped[dict]=mapped_column(JSON, default=dict)
    quality: Mapped[float|None]=mapped_column(Float, nullable=True)
    confidence: Mapped[float|None]=mapped_column(Float, nullable=True)
    created_by: Mapped[str|None]=mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)

class Assumption(Base, TenantMixin):
    __tablename__="assumptions"
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid)
    mission_id: Mapped[str|None]=mapped_column(ForeignKey("missions.id", ondelete="SET NULL"), nullable=True, index=True)
    investigation_id: Mapped[str|None]=mapped_column(ForeignKey("investigations.id", ondelete="SET NULL"), nullable=True, index=True)
    decision_id: Mapped[str|None]=mapped_column(ForeignKey("decisions.id", ondelete="SET NULL"), nullable=True, index=True)
    code: Mapped[str]=mapped_column(String(40), default="", index=True)
    statement: Mapped[str]=mapped_column(Text)
    status: Mapped[str]=mapped_column(String(30), default="active", index=True)
    method: Mapped[str]=mapped_column(Text, default="")
    limitations: Mapped[str]=mapped_column(Text, default="")
    valid_from: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int]=mapped_column(Integer, default=1)
    supersedes_id: Mapped[str|None]=mapped_column(ForeignKey("assumptions.id"), nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)

class Constraint(Base, TenantMixin):
    __tablename__="constraints"
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid)
    mission_id: Mapped[str|None]=mapped_column(ForeignKey("missions.id", ondelete="SET NULL"), nullable=True, index=True)
    investigation_id: Mapped[str|None]=mapped_column(ForeignKey("investigations.id", ondelete="SET NULL"), nullable=True, index=True)
    decision_id: Mapped[str|None]=mapped_column(ForeignKey("decisions.id", ondelete="SET NULL"), nullable=True, index=True)
    code: Mapped[str]=mapped_column(String(40), default="", index=True)
    statement: Mapped[str]=mapped_column(Text)
    status: Mapped[str]=mapped_column(String(30), default="active", index=True)
    source: Mapped[str]=mapped_column(String(200), default="")
    limitations: Mapped[str]=mapped_column(Text, default="")
    valid_from: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int]=mapped_column(Integer, default=1)
    supersedes_id: Mapped[str|None]=mapped_column(ForeignKey("constraints.id"), nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)

class Alternative(Base, TenantMixin):
    __tablename__="alternatives"
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid)
    mission_id: Mapped[str|None]=mapped_column(ForeignKey("missions.id", ondelete="SET NULL"), nullable=True, index=True)
    investigation_id: Mapped[str|None]=mapped_column(ForeignKey("investigations.id", ondelete="SET NULL"), nullable=True, index=True)
    decision_id: Mapped[str|None]=mapped_column(ForeignKey("decisions.id", ondelete="SET NULL"), nullable=True, index=True)
    code: Mapped[str]=mapped_column(String(40), default="", index=True)
    title: Mapped[str]=mapped_column(String(240))
    description: Mapped[str]=mapped_column(Text, default="")
    status: Mapped[str]=mapped_column(String(30), default="considered", index=True)
    rejection_reason: Mapped[str]=mapped_column(Text, default="")
    criteria: Mapped[dict]=mapped_column(JSON, default=dict)
    limitations: Mapped[str]=mapped_column(Text, default="")
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)

class Implementation(Base, TenantMixin):
    __tablename__="implementations"
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid)
    decision_id: Mapped[str]=mapped_column(ForeignKey("decisions.id", ondelete="CASCADE"), index=True)
    code: Mapped[str]=mapped_column(String(40), default="", index=True)
    title: Mapped[str]=mapped_column(String(240))
    status: Mapped[str]=mapped_column(String(30), default="planned", index=True)
    plan: Mapped[dict]=mapped_column(JSON, default=dict)
    deviations: Mapped[list]=mapped_column(JSON, default=list)
    evidence_of_execution: Mapped[dict]=mapped_column(JSON, default=dict)
    started_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)

class AttributionAssessment(Base, TenantMixin):
    __tablename__="attribution_assessments"
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid)
    outcome_id: Mapped[str]=mapped_column(ForeignKey("outcomes.id", ondelete="CASCADE"), index=True)
    status: Mapped[str]=mapped_column(String(40), default="not_assessed", index=True)
    penalty: Mapped[float]=mapped_column(Float, default=0.0)
    baseline_status: Mapped[str]=mapped_column(String(40), default="unknown")
    implementation_deviation: Mapped[bool]=mapped_column(Boolean, default=False)
    external_variables: Mapped[list]=mapped_column(JSON, default=list)
    refuted_assumptions: Mapped[list]=mapped_column(JSON, default=list)
    violated_constraints: Mapped[list]=mapped_column(JSON, default=list)
    reasons: Mapped[list]=mapped_column(JSON, default=list)
    rationale: Mapped[str]=mapped_column(Text, default="")
    algorithm_version: Mapped[str]=mapped_column(String(40), default="attribution-1")
    evaluated_by: Mapped[str|None]=mapped_column(ForeignKey("users.id"), nullable=True)
    evaluated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)

class LearningReuse(Base, TenantMixin):
    __tablename__="learning_reuses"
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid)
    learning_id: Mapped[str]=mapped_column(ForeignKey("learnings.id", ondelete="CASCADE"), index=True)
    mission_id: Mapped[str|None]=mapped_column(ForeignKey("missions.id", ondelete="SET NULL"), nullable=True, index=True)
    decision_id: Mapped[str|None]=mapped_column(ForeignKey("decisions.id", ondelete="SET NULL"), nullable=True, index=True)
    explanation: Mapped[str]=mapped_column(Text, default="")
    reused_by: Mapped[str|None]=mapped_column(ForeignKey("users.id"), nullable=True)
    reused_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)


class GuidedReasoningSession(Base, TenantMixin):
    __tablename__="guided_reasoning_sessions"
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid)
    mission_id: Mapped[str]=mapped_column(ForeignKey("missions.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str|None]=mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    intention: Mapped[str]=mapped_column(String(30), index=True)
    guidance_version: Mapped[str]=mapped_column(String(50), default="sees-guidance-0.7")
    status: Mapped[str]=mapped_column(String(20), default="active", index=True)
    current_index: Mapped[int]=mapped_column(Integer, default=0)
    answers: Mapped[list]=mapped_column(JSON, default=list)
    started_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    completed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)

class APIKey(Base, TenantMixin):
    __tablename__="api_keys"
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str]=mapped_column(String(120)); prefix: Mapped[str]=mapped_column(String(20), index=True); key_hash: Mapped[str]=mapped_column(String(64), unique=True)
    scopes: Mapped[list]=mapped_column(JSON, default=list); active: Mapped[bool]=mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True); last_used_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str|None]=mapped_column(ForeignKey("users.id"), nullable=True); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)

class Integration(Base, TenantMixin):
    __tablename__="integrations"
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid)
    kind: Mapped[str]=mapped_column(String(60)); name: Mapped[str]=mapped_column(String(120)); status: Mapped[str]=mapped_column(String(30), default="active")
    config_encrypted: Mapped[str|None]=mapped_column(Text, nullable=True); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)

class WebhookEndpoint(Base, TenantMixin):
    __tablename__="webhook_endpoints"
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid)
    url: Mapped[str]=mapped_column(String(500)); secret_encrypted: Mapped[str]=mapped_column(Text); events: Mapped[list]=mapped_column(JSON, default=list)
    active: Mapped[bool]=mapped_column(Boolean, default=True); failures: Mapped[int]=mapped_column(Integer, default=0)

class AuditLog(Base, TenantMixin):
    __tablename__="audit_logs"
    id: Mapped[str]=mapped_column(String(36), primary_key=True, default=uid)
    actor_user_id: Mapped[str|None]=mapped_column(String(36), nullable=True, index=True)
    action: Mapped[str]=mapped_column(String(100), index=True); resource_type: Mapped[str]=mapped_column(String(80)); resource_id: Mapped[str|None]=mapped_column(String(36), nullable=True)
    request_id: Mapped[str|None]=mapped_column(String(80), nullable=True); ip_address: Mapped[str|None]=mapped_column(String(80), nullable=True)
    before: Mapped[dict|None]=mapped_column(JSON, nullable=True); after: Mapped[dict|None]=mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now, index=True)

Index("ix_events_org_time", Event.organization_id, Event.occurred_at)
Index("ix_audit_org_time", AuditLog.organization_id, AuditLog.created_at)
