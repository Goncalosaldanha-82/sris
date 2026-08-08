"""Tests for explicit, authority-governed epistemic lifecycle changes."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.ske.contracts import EpistemicStatus
from app.ske.lifecycle import (
    LifecycleTransitionRequest,
    TransitionDecision,
    TransitionReason,
    create_transition_event,
    evaluate_transition,
)


def make_request(
    current_status: EpistemicStatus,
    requested_status: EpistemicStatus,
    *,
    with_authority: bool = True,
) -> LifecycleTransitionRequest:
    return LifecycleTransitionRequest(
        asset_id=uuid4(),
        organization_id=uuid4(),
        current_status=current_status,
        requested_status=requested_status,
        requested_by=uuid4(),
        authority_id=uuid4() if with_authority else None,
        reason=TransitionReason.SUBMITTED_FOR_REVIEW,
        explanation="Lifecycle transition requested during SEE testing.",
    )


def test_known_transition_with_authority_is_allowed() -> None:
    request = make_request(EpistemicStatus.CANDIDATE, EpistemicStatus.UNDER_REVIEW)
    result = evaluate_transition(request)
    assert result.allowed is True
    assert result.rule_found is True
    assert result.decision == TransitionDecision.ALLOWED
    assert result.requires_authority is True


def test_known_transition_without_authority_requires_review() -> None:
    request = make_request(
        EpistemicStatus.CANDIDATE,
        EpistemicStatus.UNDER_REVIEW,
        with_authority=False,
    )
    result = evaluate_transition(request)
    assert result.allowed is False
    assert result.rule_found is True
    assert result.decision == TransitionDecision.REQUIRES_REVIEW
    assert result.requires_authority is True


def test_unknown_transition_is_denied() -> None:
    request = make_request(EpistemicStatus.RAW, EpistemicStatus.ACCEPTED)
    result = evaluate_transition(request)
    assert result.allowed is False
    assert result.rule_found is False
    assert result.decision == TransitionDecision.DENIED


def test_raw_to_captured_does_not_require_authority() -> None:
    request = make_request(
        EpistemicStatus.RAW,
        EpistemicStatus.CAPTURED,
        with_authority=False,
    )
    result = evaluate_transition(request)
    assert result.allowed is True
    assert result.decision == TransitionDecision.ALLOWED
    assert result.requires_authority is False


def test_allowed_transition_creates_audit_event() -> None:
    request = make_request(EpistemicStatus.UNDER_REVIEW, EpistemicStatus.ACCEPTED)
    result = evaluate_transition(request)
    event = create_transition_event(request, result)
    assert event.asset_id == request.asset_id
    assert event.organization_id == request.organization_id
    assert event.previous_status == EpistemicStatus.UNDER_REVIEW
    assert event.new_status == EpistemicStatus.ACCEPTED
    assert event.approved_by == request.authority_id
    assert event.occurred_at.tzinfo is not None


def test_denied_transition_cannot_create_audit_event() -> None:
    request = make_request(EpistemicStatus.RAW, EpistemicStatus.ACCEPTED)
    result = evaluate_transition(request)
    with pytest.raises(ValueError, match="Cannot create a transition event"):
        create_transition_event(request, result)


def test_request_rejects_identical_statuses() -> None:
    with pytest.raises(
        ValidationError,
        match="requested_status must differ from current_status",
    ):
        make_request(EpistemicStatus.CAPTURED, EpistemicStatus.CAPTURED)
