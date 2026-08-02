"""
Lifecycle governance for the SRIS Epistemic Engine (SEE).

This module governs changes in epistemic status.

It does not convert one asset type into another. An Observation does not
become Evidence, and Evidence does not become a Hypothesis. Distinct
assets are connected through explicit, auditable relations and decisions.

A lifecycle transition changes only the status of the same persistent
asset while preserving its identity and history.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Final
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.ske.contracts import EpistemicStatus


def utc_now() -> datetime:
"""Return a timezone-aware UTC timestamp."""
return datetime.now(timezone.utc)


class TransitionDecision(StrEnum):
"""Result of evaluating a requested lifecycle transition."""

ALLOWED = "allowed"
DENIED = "denied"
REQUIRES_REVIEW = "requires_review"


class TransitionReason(StrEnum):
"""Canonical reasons for a lifecycle transition."""

INITIAL_CAPTURE = "initial_capture"
FORMAL_ASSERTION = "formal_assertion"
OBSERVATION_RECORDED = "observation_recorded"
SUBMITTED_FOR_REVIEW = "submitted_for_review"
HUMAN_ACCEPTANCE = "human_acceptance"
MATERIAL_CONTRADICTION = "material_contradiction"
SCOPE_RESTRICTION = "scope_restriction"
SUPERSEDED_BY_NEWER_ASSET = "superseded_by_newer_asset"
FORMAL_REVOCATION = "formal_revocation"
RETENTION_ARCHIVE = "retention_archive"
REVIEW_REOPENED = "review_reopened"


@dataclass(frozen=True, slots=True)
class TransitionRule:
"""
Declarative lifecycle rule.

``requires_authority`` means that an identified institutional actor
must approve the transition.

``requires_explanation`` means that a non-empty justification must be
recorded in the transition event.
"""

source: EpistemicStatus
target: EpistemicStatus
requires_authority: bool = True
requires_explanation: bool = True


TRANSITION_RULES: Final[tuple[TransitionRule, ...]] = (
TransitionRule(
EpistemicStatus.RAW,
EpistemicStatus.CAPTURED,
requires_authority=False,
),
TransitionRule(
EpistemicStatus.CAPTURED,
EpistemicStatus.ASSERTED,
),
TransitionRule(
EpistemicStatus.CAPTURED,
EpistemicStatus.OBSERVED,
),
TransitionRule(
EpistemicStatus.ASSERTED,
EpistemicStatus.CANDIDATE,
),
TransitionRule(
EpistemicStatus.OBSERVED,
EpistemicStatus.CANDIDATE,
),
TransitionRule(
EpistemicStatus.CANDIDATE,
EpistemicStatus.UNDER_REVIEW,
),
TransitionRule(
EpistemicStatus.UNDER_REVIEW,
EpistemicStatus.ACCEPTED,
),
TransitionRule(
EpistemicStatus.UNDER_REVIEW,
EpistemicStatus.CONTESTED,
),
TransitionRule(
EpistemicStatus.ACCEPTED,
EpistemicStatus.CONTESTED,
),
TransitionRule(
EpistemicStatus.ACCEPTED,
EpistemicStatus.LIMITED,
),
TransitionRule(
EpistemicStatus.CONTESTED,
EpistemicStatus.UNDER_REVIEW,
),
TransitionRule(
EpistemicStatus.LIMITED,
EpistemicStatus.UNDER_REVIEW,
),
TransitionRule(
EpistemicStatus.ACCEPTED,
EpistemicStatus.SUPERSEDED,
),
TransitionRule(
EpistemicStatus.CONTESTED,
EpistemicStatus.REVOKED,
),
TransitionRule(
EpistemicStatus.LIMITED,
EpistemicStatus.REVOKED,
),
TransitionRule(
EpistemicStatus.ACCEPTED,
EpistemicStatus.REVOKED,
),
TransitionRule(
EpistemicStatus.SUPERSEDED,
EpistemicStatus.ARCHIVED,
),
TransitionRule(
EpistemicStatus.REVOKED,
EpistemicStatus.ARCHIVED,
),
)

_RULE_INDEX: Final[
dict[tuple[EpistemicStatus, EpistemicStatus], TransitionRule]
] = {
(rule.source, rule.target): rule
for rule in TRANSITION_RULES
}


class LifecycleTransitionRequest(BaseModel):
"""Requested change to the status of one persistent epistemic asset."""

model_config = ConfigDict(
extra="forbid",
frozen=True,
str_strip_whitespace=True,
)

asset_id: UUID
organization_id: UUID

current_status: EpistemicStatus
requested_status: EpistemicStatus

requested_by: UUID | None = None
authority_id: UUID | None = None

reason: TransitionReason
explanation: str = Field(min_length=1)
requested_at: datetime = Field(default_factory=utc_now)

@model_validator(mode="after")
def validate_request(self) -> "LifecycleTransitionRequest":
if self.current_status == self.requested_status:
raise ValueError(
"requested_status must differ from current_status"
)

if self.requested_at.tzinfo is None:
raise ValueError(
"requested_at must be timezone-aware"
)

return self


class LifecycleTransitionResult(BaseModel):
"""Outcome of evaluating a lifecycle transition request."""

model_config = ConfigDict(
extra="forbid",
frozen=True,
str_strip_whitespace=True,
)

decision: TransitionDecision
allowed: bool
rule_found: bool
requires_authority: bool

current_status: EpistemicStatus
requested_status: EpistemicStatus

explanation: str


class LifecycleTransitionEvent(BaseModel):
"""
Immutable audit record for an approved lifecycle transition.

Persistence and append-only enforcement belong to the audit layer.
"""

model_config = ConfigDict(
extra="forbid",
frozen=True,
str_strip_whitespace=True,
)

id: UUID = Field(default_factory=uuid4)
asset_id: UUID
organization_id: UUID

previous_status: EpistemicStatus
new_status: EpistemicStatus

reason: TransitionReason
explanation: str = Field(min_length=1)

requested_by: UUID | None = None
approved_by: UUID | None = None

occurred_at: datetime = Field(default_factory=utc_now)

@model_validator(mode="after")
def validate_event(self) -> "LifecycleTransitionEvent":
if self.previous_status == self.new_status:
raise ValueError(
"previous_status and new_status must differ"
)

if self.occurred_at.tzinfo is None:
raise ValueError(
"occurred_at must be timezone-aware"
)

return self


def get_transition_rule(
source: EpistemicStatus,
target: EpistemicStatus,
) -> TransitionRule | None:
"""Return the declarative rule for a transition, if one exists."""
return _RULE_INDEX.get((source, target))


def evaluate_transition(
request: LifecycleTransitionRequest,
) -> LifecycleTransitionResult:
"""
Evaluate whether a requested status transition is permitted.

This function does not mutate assets or persist audit records.
"""

rule = get_transition_rule(
request.current_status,
request.requested_status,
)

if rule is None:
return LifecycleTransitionResult(
decision=TransitionDecision.DENIED,
allowed=False,
rule_found=False,
requires_authority=False,
current_status=request.current_status,
requested_status=request.requested_status,
explanation=(
"No lifecycle rule permits the requested transition."
),
)

if rule.requires_authority and request.authority_id is None:
return LifecycleTransitionResult(
decision=TransitionDecision.REQUIRES_REVIEW,
allowed=False,
rule_found=True,
requires_authority=True,
current_status=request.current_status,
requested_status=request.requested_status,
explanation=(
"The transition is recognised but requires an "
"identified institutional authority."
),
)

return LifecycleTransitionResult(
decision=TransitionDecision.ALLOWED,
allowed=True,
rule_found=True,
requires_authority=rule.requires_authority,
current_status=request.current_status,
requested_status=request.requested_status,
explanation=(
"The transition is permitted by the SEE lifecycle rules."
),
)


def create_transition_event(
request: LifecycleTransitionRequest,
result: LifecycleTransitionResult,
) -> LifecycleTransitionEvent:
"""
Create an immutable transition event after successful evaluation.

Raises:
ValueError: If the transition was not allowed.
"""

if not result.allowed:
raise ValueError(
"Cannot create a transition event for a denied "
"or pending transition"
)

return LifecycleTransitionEvent(
asset_id=request.asset_id,
organization_id=request.organization_id,
previous_status=request.current_status,
new_status=request.requested_status,
reason=request.reason,
explanation=request.explanation,
requested_by=request.requested_by,
approved_by=request.authority_id,
)
