"""
Foundational contracts for the SRIS Epistemic Engine (SEE).

These contracts define the minimum invariants required for objects
that participate in institutional reasoning.

They are deliberately independent from database models, API schemas
and user-interface concerns.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> datetime:
"""Return a timezone-aware UTC timestamp."""
return datetime.now(timezone.utc)


class InstitutionalObjectFamily(StrEnum):
"""Top-level families of objects governed by the SRIS."""

SOURCE = "source"
EPISTEMIC = "epistemic"
DECISION = "decision"
GOVERNANCE = "governance"
TECHNICAL_INTEGRITY = "technical_integrity"


class EpistemicAssetType(StrEnum):
"""Recognised types of Meaning Asset."""

SOURCE_CLAIM = "source_claim"
OBSERVATION = "observation"
EVIDENCE_CANDIDATE = "evidence_candidate"
EVIDENCE = "evidence"
HYPOTHESIS = "hypothesis"
INVESTIGATION = "investigation"
ASSUMPTION = "assumption"
ALTERNATIVE = "alternative"
DECISION = "decision"
IMPLEMENTATION = "implementation"
OUTCOME = "outcome"
LEARNING = "learning"
KNOWLEDGE = "knowledge"
DOCTRINE_PROPOSAL = "doctrine_proposal"
DOCTRINE = "doctrine"


class EpistemicStatus(StrEnum):
"""
Current epistemic status of an asset.

Status does not represent absolute truth. It records the position
attributed to the asset in a defined context and at a defined time.
"""

RAW = "raw"
CAPTURED = "captured"
ASSERTED = "asserted"
OBSERVED = "observed"
CANDIDATE = "candidate"
UNDER_REVIEW = "under_review"
ACCEPTED = "accepted"
CONTESTED = "contested"
LIMITED = "limited"
SUPERSEDED = "superseded"
REVOKED = "revoked"
ARCHIVED = "archived"


class RelationType(StrEnum):
"""Canonical relation types used by the epistemic graph."""

SUPPORTS = "supports"
CONTRADICTS = "contradicts"
QUALIFIES = "qualifies"
DERIVES_FROM = "derives_from"
DEPENDS_ON = "depends_on"
TRIGGERS = "triggers"
IMPLEMENTED_BY = "implemented_by"
PRODUCES = "produces"
SUPERSEDES = "supersedes"
LIMITS = "limits"
INVALIDATES = "invalidates"
REQUIRES_REVIEW = "requires_review"


class InstitutionalObjectContract(BaseModel):
"""
Minimum contract for every persistent institutional object.

This is broader than MeaningAsset. Not every object in the SRIS
carries epistemic meaning; identities, delegations and audit records
are examples of institutional objects that may not be Meaning Assets.
"""

model_config = ConfigDict(
extra="forbid",
frozen=True,
str_strip_whitespace=True,
)

id: UUID = Field(default_factory=uuid4)
organization_id: UUID
family: InstitutionalObjectFamily
created_at: datetime = Field(default_factory=utc_now)
created_by: UUID | None = None
version: int = Field(default=1, ge=1)

@model_validator(mode="after")
def validate_created_at(self) -> "InstitutionalObjectContract":
if self.created_at.tzinfo is None:
raise ValueError("created_at must be timezone-aware")
return self


class MeaningAssetContract(InstitutionalObjectContract):
"""
Foundational contract for an asset that participates in institutional
reasoning.

A Meaning Asset does not represent absolute truth. It represents an
institutionally recorded meaning with provenance, context, status,
scope and limitations.
"""

family: InstitutionalObjectFamily = InstitutionalObjectFamily.EPISTEMIC

asset_type: EpistemicAssetType
mission_id: UUID

title: str = Field(min_length=1, max_length=240)
statement: str = Field(min_length=1)

epistemic_status: EpistemicStatus = EpistemicStatus.CAPTURED

context: dict[str, Any] = Field(default_factory=dict)
provenance: dict[str, Any] = Field(default_factory=dict)
limitations: list[str] = Field(default_factory=list)
usage_scope: list[str] = Field(default_factory=list)

valid_from: datetime | None = None
valid_until: datetime | None = None

authority_id: UUID | None = None
review_required: bool = True

@model_validator(mode="after")
def validate_temporal_validity(self) -> "MeaningAssetContract":
if self.valid_from and self.valid_from.tzinfo is None:
raise ValueError("valid_from must be timezone-aware")

if self.valid_until and self.valid_until.tzinfo is None:
raise ValueError("valid_until must be timezone-aware")

if (
self.valid_from is not None
and self.valid_until is not None
and self.valid_until <= self.valid_from
):
raise ValueError("valid_until must be later than valid_from")

return self


class EpistemicRelationContract(InstitutionalObjectContract):
"""
Directed, typed and contextual relation between two institutional
objects.

Relations are first-class records. They carry their own provenance,
temporal validity and limitations instead of being hidden database
links.
"""

family: InstitutionalObjectFamily = InstitutionalObjectFamily.EPISTEMIC

source_id: UUID
target_id: UUID
relation_type: RelationType

explanation: str = Field(min_length=1)
context: dict[str, Any] = Field(default_factory=dict)
provenance: dict[str, Any] = Field(default_factory=dict)
limitations: list[str] = Field(default_factory=list)

valid_from: datetime = Field(default_factory=utc_now)
valid_until: datetime | None = None

asserted_by: UUID | None = None
review_required: bool = True

@model_validator(mode="after")
def validate_relation(self) -> "EpistemicRelationContract":
if self.source_id == self.target_id:
raise ValueError(
"source_id and target_id must be different"
)

if self.valid_from.tzinfo is None:
raise ValueError("valid_from must be timezone-aware")

if self.valid_until is not None:
if self.valid_until.tzinfo is None:
raise ValueError("valid_until must be timezone-aware")

if self.valid_until <= self.valid_from:
raise ValueError(
"valid_until must be later than valid_from"
)

return self
