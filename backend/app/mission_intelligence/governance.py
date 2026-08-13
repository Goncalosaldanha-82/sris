from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_CEILING, Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.atlas_platform.audit import record_audit

from .contracts import AIGovernancePolicyUpdate
from .models import AIOrganizationPolicy, AIUsageEvent, AIUsagePeriod

PRICING_SOURCE = "https://developers.openai.com/api/docs/pricing"
PRICING_EFFECTIVE_DATE = "2026-08-10"
DEFAULT_WEB_SEARCH_RATE_MICROUSD_PER_CALL = 10_000
DEFAULT_RESERVATION_TTL_MINUTES = 10
MICROUSD_PER_USD = 1_000_000
TOKENS_PER_MILLION = 1_000_000
BASIS_POINTS = 10_000


class AIGovernanceBlocked(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ModelPricing:
    model: str
    input_rate_microusd_per_million: int
    cached_input_rate_microusd_per_million: int
    output_rate_microusd_per_million: int
    multiplier_bps: int
    source: str
    effective_date: str


@dataclass(frozen=True)
class AIUsageReservation:
    event_id: str
    organization_id: str
    model: str
    input_tokens: int
    output_tokens: int
    web_search_calls: int
    estimated_cost_microusd: int


_STANDARD_MODEL_PRICES_USD_PER_MTOK: dict[str, tuple[str, str, str]] = {
    "gpt-5.6": ("5.00", "0.50", "30.00"),
    "gpt-5.6-sol": ("5.00", "0.50", "30.00"),
    "gpt-5.6-terra": ("2.00", "0.20", "12.00"),
    "gpt-5.6-luna": ("0.20", "0.02", "1.20"),
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def current_period_start(now: datetime | None = None) -> date:
    value = now or utcnow()
    return date(value.year, value.month, 1)


def next_period_start(period_start: date) -> date:
    if period_start.month == 12:
        return date(period_start.year + 1, 1, 1)
    return date(period_start.year, period_start.month + 1, 1)


def _positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise AIGovernanceBlocked("pricing_unavailable", f"Invalid {name}") from exc
    if value <= 0:
        raise AIGovernanceBlocked("pricing_unavailable", f"Invalid {name}")
    return value


def _usd_rate_to_microusd(value: str, variable_name: str) -> int:
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise AIGovernanceBlocked(
            "pricing_unavailable", f"Invalid {variable_name}"
        ) from exc
    if amount < 0:
        raise AIGovernanceBlocked("pricing_unavailable", f"Invalid {variable_name}")
    return int((amount * MICROUSD_PER_USD).to_integral_value(rounding=ROUND_CEILING))


def pricing_for_model(model: str) -> ModelPricing:
    override_names = (
        "SRIS_AI_INPUT_USD_PER_MTOK",
        "SRIS_AI_CACHED_INPUT_USD_PER_MTOK",
        "SRIS_AI_OUTPUT_USD_PER_MTOK",
    )
    overrides = tuple(os.getenv(name, "").strip() for name in override_names)
    if any(overrides) and not all(overrides):
        raise AIGovernanceBlocked(
            "pricing_unavailable",
            "All three SRIS AI pricing overrides must be configured together",
        )

    if all(overrides):
        raw_rates = overrides
        source = os.getenv("SRIS_AI_PRICING_SOURCE", "operator_configured").strip()
        effective_date = os.getenv(
            "SRIS_AI_PRICING_EFFECTIVE_DATE", utcnow().date().isoformat()
        ).strip()
    else:
        raw_rates = _STANDARD_MODEL_PRICES_USD_PER_MTOK.get(model)
        if raw_rates is None:
            raise AIGovernanceBlocked(
                "pricing_unavailable",
                f"No governed pricing snapshot exists for model {model}",
            )
        source = PRICING_SOURCE
        effective_date = PRICING_EFFECTIVE_DATE

    multiplier = _positive_int_env("SRIS_AI_PRICE_MULTIPLIER_BPS", BASIS_POINTS)
    return ModelPricing(
        model=model,
        input_rate_microusd_per_million=_usd_rate_to_microusd(
            raw_rates[0], override_names[0]
        ),
        cached_input_rate_microusd_per_million=_usd_rate_to_microusd(
            raw_rates[1], override_names[1]
        ),
        output_rate_microusd_per_million=_usd_rate_to_microusd(
            raw_rates[2], override_names[2]
        ),
        multiplier_bps=multiplier,
        source=source,
        effective_date=effective_date,
    )


def estimate_cost_microusd(
    *,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    pricing: ModelPricing,
    web_search_calls: int = 0,
    web_search_rate_microusd_per_call: int = 0,
) -> int:
    input_tokens = max(0, input_tokens)
    cached_input_tokens = min(max(0, cached_input_tokens), input_tokens)
    output_tokens = max(0, output_tokens)
    uncached_input_tokens = input_tokens - cached_input_tokens
    numerator = (
        uncached_input_tokens * pricing.input_rate_microusd_per_million
        + cached_input_tokens * pricing.cached_input_rate_microusd_per_million
        + output_tokens * pricing.output_rate_microusd_per_million
    )
    base_cost = (numerator + TOKENS_PER_MILLION - 1) // TOKENS_PER_MILLION
    token_cost = (base_cost * pricing.multiplier_bps + BASIS_POINTS - 1) // BASIS_POINTS
    tool_cost = max(0, web_search_calls) * max(
        0, web_search_rate_microusd_per_call
    )
    return token_cost + tool_cost


def web_search_rate_microusd_per_call() -> int:
    return _positive_int_env(
        "SRIS_WEB_SEARCH_RATE_MICROUSD_PER_CALL",
        DEFAULT_WEB_SEARCH_RATE_MICROUSD_PER_CALL,
    )


def usd_to_microusd(value: Decimal) -> int:
    return int((value * MICROUSD_PER_USD).to_integral_value(rounding=ROUND_CEILING))


def microusd_to_usd(value: int) -> str:
    return f"{Decimal(value) / Decimal(MICROUSD_PER_USD):.6f}"


def _locked_policy(db: Session, organization_id: str) -> AIOrganizationPolicy | None:
    return (
        db.query(AIOrganizationPolicy)
        .filter(AIOrganizationPolicy.organization_id == organization_id)
        .with_for_update()
        .one_or_none()
    )


def _locked_period(
    db: Session,
    *,
    organization_id: str,
    period_start: date,
) -> AIUsagePeriod:
    period = (
        db.query(AIUsagePeriod)
        .filter(
            AIUsagePeriod.organization_id == organization_id,
            AIUsagePeriod.period_start == period_start,
        )
        .with_for_update()
        .one_or_none()
    )
    if period is None:
        # Reservation paths lock the unique organization policy first. That lock
        # serializes creation of the organization's monthly row in PostgreSQL.
        period = AIUsagePeriod(
            organization_id=organization_id,
            period_start=period_start,
        )
        db.add(period)
        db.flush()
    return period


def _expire_stale_reservations(
    db: Session,
    *,
    organization_id: str,
    period: AIUsagePeriod,
    now: datetime,
) -> None:
    ttl_minutes = _positive_int_env(
        "SRIS_AI_RESERVATION_TTL_MINUTES", DEFAULT_RESERVATION_TTL_MINUTES
    )
    cutoff = now - timedelta(minutes=ttl_minutes)
    stale = (
        db.query(AIUsageEvent)
        .filter(
            AIUsageEvent.organization_id == organization_id,
            AIUsageEvent.period_start == period.period_start,
            AIUsageEvent.status == "reserved",
            AIUsageEvent.created_at < cutoff,
        )
        .with_for_update()
        .all()
    )
    for event in stale:
        period.active_reservations = max(0, period.active_reservations - 1)
        period.reserved_input_tokens = max(
            0, period.reserved_input_tokens - event.reserved_input_tokens
        )
        period.reserved_output_tokens = max(
            0, period.reserved_output_tokens - event.reserved_output_tokens
        )
        period.reserved_web_search_calls = max(
            0,
            period.reserved_web_search_calls - event.reserved_web_search_calls,
        )
        period.reserved_cost_microusd = max(
            0, period.reserved_cost_microusd - event.reserved_cost_microusd
        )
        event.status = "expired"
        event.cost_basis = "reservation_released"
        event.failure_code = "reservation_timeout"
        event.finalized_at = now


def _quota_check(
    *,
    policy: AIOrganizationPolicy,
    period: AIUsagePeriod,
    input_tokens: int,
    output_tokens: int,
    estimated_cost_microusd: int,
) -> None:
    if input_tokens > policy.per_request_input_token_limit:
        raise AIGovernanceBlocked(
            "per_request_input_limit",
            "The governed input-token limit for one request would be exceeded",
        )
    if output_tokens > policy.per_request_output_token_limit:
        raise AIGovernanceBlocked(
            "per_request_output_limit",
            "The governed output-token limit for one request would be exceeded",
        )
    if period.request_count + 1 > policy.monthly_request_limit:
        raise AIGovernanceBlocked(
            "monthly_request_limit", "The organization's monthly AI request limit is exhausted"
        )
    if period.active_reservations >= policy.max_concurrent_requests:
        raise AIGovernanceBlocked(
            "concurrency_limit", "The organization's concurrent AI request limit is active"
        )
    if (
        period.input_tokens + period.reserved_input_tokens + input_tokens
        > policy.monthly_input_token_limit
    ):
        raise AIGovernanceBlocked(
            "monthly_input_limit", "The organization's monthly input-token limit would be exceeded"
        )
    if (
        period.output_tokens + period.reserved_output_tokens + output_tokens
        > policy.monthly_output_token_limit
    ):
        raise AIGovernanceBlocked(
            "monthly_output_limit", "The organization's monthly output-token limit would be exceeded"
        )
    if (
        period.estimated_cost_microusd
        + period.reserved_cost_microusd
        + estimated_cost_microusd
        > policy.monthly_budget_microusd
    ):
        raise AIGovernanceBlocked(
            "monthly_budget", "The organization's monthly AI cost ceiling would be exceeded"
        )


def reserve_ai_usage(
    db: Session,
    *,
    organization_id: str,
    user_id: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    web_search_calls: int = 0,
) -> AIUsageReservation:
    now = utcnow()
    policy = _locked_policy(db, organization_id)
    if policy is None:
        raise AIGovernanceBlocked(
            "policy_required", "An explicit organizational AI policy is required"
        )
    if not policy.enabled:
        raise AIGovernanceBlocked(
            "organization_disabled", "AI is disabled by the organization's policy"
        )

    pricing = pricing_for_model(model)
    period = _locked_period(
        db,
        organization_id=organization_id,
        period_start=current_period_start(now),
    )
    _expire_stale_reservations(
        db,
        organization_id=organization_id,
        period=period,
        now=now,
    )
    estimated_cost = estimate_cost_microusd(
        input_tokens=input_tokens,
        cached_input_tokens=0,
        output_tokens=output_tokens,
        pricing=pricing,
        web_search_calls=web_search_calls,
        web_search_rate_microusd_per_call=web_search_rate_microusd_per_call(),
    )
    _quota_check(
        policy=policy,
        period=period,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_microusd=estimated_cost,
    )

    event = AIUsageEvent(
        organization_id=organization_id,
        requested_by_user_id=user_id,
        period_start=period.period_start,
        status="reserved",
        provider="openai",
        model=model,
        reserved_input_tokens=input_tokens,
        reserved_output_tokens=output_tokens,
        reserved_web_search_calls=web_search_calls,
        reserved_cost_microusd=estimated_cost,
        input_rate_microusd_per_million=pricing.input_rate_microusd_per_million,
        cached_input_rate_microusd_per_million=(
            pricing.cached_input_rate_microusd_per_million
        ),
        output_rate_microusd_per_million=pricing.output_rate_microusd_per_million,
        price_multiplier_bps=pricing.multiplier_bps,
        pricing_source=pricing.source,
        pricing_effective_date=pricing.effective_date,
        web_search_rate_microusd_per_call=web_search_rate_microusd_per_call(),
    )
    db.add(event)
    period.request_count += 1
    period.active_reservations += 1
    period.reserved_input_tokens += input_tokens
    period.reserved_output_tokens += output_tokens
    period.reserved_web_search_calls += web_search_calls
    period.reserved_cost_microusd += estimated_cost
    db.flush()
    record_audit(
        db,
        action="mission_intelligence.ai_usage_reserved",
        resource_type="ai_usage_event",
        resource_id=event.id,
        organization_id=organization_id,
        user_id=user_id,
        payload={
            "model": model,
            "reserved_input_tokens": input_tokens,
            "reserved_output_tokens": output_tokens,
            "reserved_web_search_calls": web_search_calls,
            "reserved_cost_usd": microusd_to_usd(estimated_cost),
        },
    )
    db.commit()
    return AIUsageReservation(
        event_id=event.id,
        organization_id=organization_id,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        web_search_calls=web_search_calls,
        estimated_cost_microusd=estimated_cost,
    )


def apply_exact_input_count(
    db: Session,
    *,
    reservation: AIUsageReservation,
    exact_input_tokens: int,
) -> AIUsageReservation:
    if exact_input_tokens <= 0 or exact_input_tokens >= reservation.input_tokens:
        return reservation

    policy = _locked_policy(db, reservation.organization_id)
    if policy is None:
        return reservation
    event = (
        db.query(AIUsageEvent)
        .filter(AIUsageEvent.id == reservation.event_id)
        .with_for_update()
        .one()
    )
    if event.status != "reserved":
        return reservation
    period = _locked_period(
        db,
        organization_id=reservation.organization_id,
        period_start=event.period_start,
    )
    pricing = ModelPricing(
        model=event.model,
        input_rate_microusd_per_million=event.input_rate_microusd_per_million,
        cached_input_rate_microusd_per_million=(
            event.cached_input_rate_microusd_per_million
        ),
        output_rate_microusd_per_million=event.output_rate_microusd_per_million,
        multiplier_bps=event.price_multiplier_bps,
        source=event.pricing_source,
        effective_date=event.pricing_effective_date,
    )
    exact_cost = estimate_cost_microusd(
        input_tokens=exact_input_tokens,
        cached_input_tokens=0,
        output_tokens=event.reserved_output_tokens,
        pricing=pricing,
        web_search_calls=event.reserved_web_search_calls,
        web_search_rate_microusd_per_call=(
            event.web_search_rate_microusd_per_call
        ),
    )
    period.reserved_input_tokens -= event.reserved_input_tokens - exact_input_tokens
    period.reserved_cost_microusd -= event.reserved_cost_microusd - exact_cost
    event.reserved_input_tokens = exact_input_tokens
    event.reserved_cost_microusd = exact_cost
    event.input_count_method = "provider_exact"
    db.commit()
    return AIUsageReservation(
        event_id=event.id,
        organization_id=event.organization_id,
        model=event.model,
        input_tokens=exact_input_tokens,
        output_tokens=event.reserved_output_tokens,
        web_search_calls=event.reserved_web_search_calls,
        estimated_cost_microusd=exact_cost,
    )


def settle_ai_usage(
    db: Session,
    *,
    reservation: AIUsageReservation,
    provider_response_id: str | None,
    input_tokens: int | None,
    cached_input_tokens: int | None,
    output_tokens: int | None,
    total_tokens: int | None,
    web_search_calls: int | None = 0,
    failure_code: str | None = None,
) -> AIUsageEvent:
    policy = _locked_policy(db, reservation.organization_id)
    if policy is None:
        raise RuntimeError("AI policy disappeared while usage was reserved")
    event = (
        db.query(AIUsageEvent)
        .filter(AIUsageEvent.id == reservation.event_id)
        .with_for_update()
        .one()
    )
    if event.status != "reserved":
        raise RuntimeError("AI usage reservation is no longer active")
    period = _locked_period(
        db,
        organization_id=reservation.organization_id,
        period_start=event.period_start,
    )

    usage_known = input_tokens is not None and output_tokens is not None
    if usage_known:
        charged_input = max(0, int(input_tokens))
        charged_cached = min(max(0, int(cached_input_tokens or 0)), charged_input)
        charged_output = max(0, int(output_tokens))
        charged_total = max(
            charged_input + charged_output,
            int(total_tokens or 0),
        )
        charged_web_search_calls = max(0, int(web_search_calls or 0))
        status = "provider_output_rejected" if failure_code else "completed"
        cost_basis = "provider_reported_usage"
    else:
        # A timeout or missing usage object can occur after the provider has
        # processed a request. Charge the full reservation until reconciled so
        # a provider failure can never bypass the organizational ceiling.
        charged_input = event.reserved_input_tokens
        charged_cached = 0
        charged_output = event.reserved_output_tokens
        charged_total = charged_input + charged_output
        charged_web_search_calls = event.reserved_web_search_calls
        status = "provider_error" if failure_code else "usage_unavailable"
        cost_basis = (
            "conservative_failure_reservation"
            if failure_code
            else "conservative_missing_usage_reservation"
        )

    pricing = ModelPricing(
        model=event.model,
        input_rate_microusd_per_million=event.input_rate_microusd_per_million,
        cached_input_rate_microusd_per_million=(
            event.cached_input_rate_microusd_per_million
        ),
        output_rate_microusd_per_million=event.output_rate_microusd_per_million,
        multiplier_bps=event.price_multiplier_bps,
        source=event.pricing_source,
        effective_date=event.pricing_effective_date,
    )
    charged_cost = estimate_cost_microusd(
        input_tokens=charged_input,
        cached_input_tokens=charged_cached,
        output_tokens=charged_output,
        pricing=pricing,
        web_search_calls=charged_web_search_calls,
        web_search_rate_microusd_per_call=(
            event.web_search_rate_microusd_per_call
        ),
    )
    if (
        charged_input > event.reserved_input_tokens
        or charged_output > event.reserved_output_tokens
        or charged_cost > event.reserved_cost_microusd
        or charged_web_search_calls > event.reserved_web_search_calls
    ):
        status = "completed_with_overage" if usage_known else status
        failure_code = failure_code or "provider_usage_exceeded_reservation"

    period.active_reservations = max(0, period.active_reservations - 1)
    period.reserved_input_tokens = max(
        0, period.reserved_input_tokens - event.reserved_input_tokens
    )
    period.reserved_output_tokens = max(
        0, period.reserved_output_tokens - event.reserved_output_tokens
    )
    period.reserved_web_search_calls = max(
        0,
        period.reserved_web_search_calls - event.reserved_web_search_calls,
    )
    period.reserved_cost_microusd = max(
        0, period.reserved_cost_microusd - event.reserved_cost_microusd
    )
    period.input_tokens += charged_input
    period.cached_input_tokens += charged_cached
    period.output_tokens += charged_output
    period.web_search_calls += charged_web_search_calls
    period.estimated_cost_microusd += charged_cost

    event.status = status
    event.provider_response_id = provider_response_id
    event.input_tokens = charged_input
    event.cached_input_tokens = charged_cached
    event.output_tokens = charged_output
    event.web_search_calls = charged_web_search_calls
    event.total_tokens = charged_total
    event.estimated_cost_microusd = charged_cost
    event.web_search_cost_microusd = (
        charged_web_search_calls * event.web_search_rate_microusd_per_call
    )
    event.cost_basis = cost_basis
    event.failure_code = failure_code
    event.finalized_at = utcnow()
    record_audit(
        db,
        action=f"mission_intelligence.ai_usage_{status}",
        resource_type="ai_usage_event",
        resource_id=event.id,
        organization_id=event.organization_id,
        user_id=event.requested_by_user_id,
        payload={
            "model": event.model,
            "input_tokens": charged_input,
            "cached_input_tokens": charged_cached,
            "output_tokens": charged_output,
            "web_search_calls": charged_web_search_calls,
            "estimated_cost_usd": microusd_to_usd(charged_cost),
            "cost_basis": cost_basis,
            "failure_code": failure_code,
        },
    )
    db.commit()
    db.refresh(event)
    return event


def update_policy(
    db: Session,
    *,
    organization_id: str,
    user_id: str,
    payload: AIGovernancePolicyUpdate,
) -> AIOrganizationPolicy:
    policy = _locked_policy(db, organization_id)
    if policy is None:
        policy = AIOrganizationPolicy(organization_id=organization_id)
        db.add(policy)
    policy.enabled = payload.enabled
    policy.monthly_request_limit = payload.monthly_request_limit
    policy.monthly_input_token_limit = payload.monthly_input_token_limit
    policy.monthly_output_token_limit = payload.monthly_output_token_limit
    policy.monthly_budget_microusd = usd_to_microusd(payload.monthly_budget_usd)
    policy.per_request_input_token_limit = payload.per_request_input_token_limit
    policy.per_request_output_token_limit = payload.per_request_output_token_limit
    policy.max_concurrent_requests = payload.max_concurrent_requests
    policy.updated_by_user_id = user_id
    db.flush()
    record_audit(
        db,
        action="mission_intelligence.ai_policy_updated",
        resource_type="ai_organization_policy",
        resource_id=policy.id,
        organization_id=organization_id,
        user_id=user_id,
        payload={
            "enabled": policy.enabled,
            "monthly_request_limit": policy.monthly_request_limit,
            "monthly_input_token_limit": policy.monthly_input_token_limit,
            "monthly_output_token_limit": policy.monthly_output_token_limit,
            "monthly_budget_usd": microusd_to_usd(policy.monthly_budget_microusd),
            "per_request_input_token_limit": policy.per_request_input_token_limit,
            "per_request_output_token_limit": policy.per_request_output_token_limit,
            "max_concurrent_requests": policy.max_concurrent_requests,
        },
    )
    db.commit()
    db.refresh(policy)
    return policy


def policy_view(policy: AIOrganizationPolicy | None) -> dict:
    if policy is None:
        return {"configured": False, "enabled": False}
    return {
        "configured": True,
        "enabled": policy.enabled,
        "monthly_request_limit": policy.monthly_request_limit,
        "monthly_input_token_limit": policy.monthly_input_token_limit,
        "monthly_output_token_limit": policy.monthly_output_token_limit,
        "monthly_budget_usd": microusd_to_usd(policy.monthly_budget_microusd),
        "per_request_input_token_limit": policy.per_request_input_token_limit,
        "per_request_output_token_limit": policy.per_request_output_token_limit,
        "max_concurrent_requests": policy.max_concurrent_requests,
        "updated_at": policy.updated_at,
    }


def usage_event_view(event: AIUsageEvent) -> dict:
    return {
        "id": event.id,
        "intelligence_run_id": event.intelligence_run_id,
        "period_start": event.period_start,
        "status": event.status,
        "provider": event.provider,
        "model": event.model,
        "provider_response_id": event.provider_response_id,
        "input_count_method": event.input_count_method,
        "reserved_input_tokens": event.reserved_input_tokens,
        "reserved_output_tokens": event.reserved_output_tokens,
        "reserved_web_search_calls": event.reserved_web_search_calls,
        "reserved_cost_usd": microusd_to_usd(event.reserved_cost_microusd),
        "input_tokens": event.input_tokens,
        "cached_input_tokens": event.cached_input_tokens,
        "output_tokens": event.output_tokens,
        "web_search_calls": event.web_search_calls,
        "total_tokens": event.total_tokens,
        "estimated_cost_usd": microusd_to_usd(event.estimated_cost_microusd),
        "web_search_cost_usd": microusd_to_usd(
            event.web_search_cost_microusd
        ),
        "cost_basis": event.cost_basis,
        "pricing": {
            "input_usd_per_million_tokens": microusd_to_usd(
                event.input_rate_microusd_per_million
            ),
            "cached_input_usd_per_million_tokens": microusd_to_usd(
                event.cached_input_rate_microusd_per_million
            ),
            "output_usd_per_million_tokens": microusd_to_usd(
                event.output_rate_microusd_per_million
            ),
            "multiplier_bps": event.price_multiplier_bps,
            "source": event.pricing_source,
            "effective_date": event.pricing_effective_date,
            "web_search_usd_per_call": microusd_to_usd(
                event.web_search_rate_microusd_per_call
            ),
        },
        "failure_code": event.failure_code,
        "created_at": event.created_at,
        "finalized_at": event.finalized_at,
    }


def governance_view(
    db: Session,
    *,
    organization_id: str,
    ai_globally_configured: bool,
    ai_organization_authorized: bool,
) -> dict:
    policy = (
        db.query(AIOrganizationPolicy)
        .filter(AIOrganizationPolicy.organization_id == organization_id)
        .one_or_none()
    )
    start = current_period_start()
    period = (
        db.query(AIUsagePeriod)
        .filter(
            AIUsagePeriod.organization_id == organization_id,
            AIUsagePeriod.period_start == start,
        )
        .one_or_none()
    )
    current = {
        "period_start": start,
        "period_end_exclusive": next_period_start(start),
        "request_count": period.request_count if period else 0,
        "input_tokens": period.input_tokens if period else 0,
        "cached_input_tokens": period.cached_input_tokens if period else 0,
        "output_tokens": period.output_tokens if period else 0,
        "web_search_calls": period.web_search_calls if period else 0,
        "estimated_cost_usd": microusd_to_usd(
            period.estimated_cost_microusd if period else 0
        ),
        "active_reservations": period.active_reservations if period else 0,
        "reserved_input_tokens": period.reserved_input_tokens if period else 0,
        "reserved_output_tokens": period.reserved_output_tokens if period else 0,
        "reserved_web_search_calls": (
            period.reserved_web_search_calls if period else 0
        ),
        "reserved_cost_usd": microusd_to_usd(
            period.reserved_cost_microusd if period else 0
        ),
    }
    if policy:
        current["remaining"] = {
            "requests": max(0, policy.monthly_request_limit - current["request_count"]),
            "input_tokens": max(
                0,
                policy.monthly_input_token_limit
                - current["input_tokens"]
                - current["reserved_input_tokens"],
            ),
            "output_tokens": max(
                0,
                policy.monthly_output_token_limit
                - current["output_tokens"]
                - current["reserved_output_tokens"],
            ),
            "budget_usd": microusd_to_usd(
                max(
                    0,
                    policy.monthly_budget_microusd
                    - (period.estimated_cost_microusd if period else 0)
                    - (period.reserved_cost_microusd if period else 0),
                )
            ),
        }
    quota_reason: str | None = None
    if policy:
        used_input = current["input_tokens"] + current["reserved_input_tokens"]
        used_output = current["output_tokens"] + current["reserved_output_tokens"]
        used_cost = (period.estimated_cost_microusd if period else 0) + (
            period.reserved_cost_microusd if period else 0
        )
        if current["request_count"] >= policy.monthly_request_limit:
            quota_reason = "monthly_request_limit"
        elif current["active_reservations"] >= policy.max_concurrent_requests:
            quota_reason = "concurrency_limit"
        elif used_input >= policy.monthly_input_token_limit:
            quota_reason = "monthly_input_limit"
        elif used_output >= policy.monthly_output_token_limit:
            quota_reason = "monthly_output_limit"
        elif used_cost >= policy.monthly_budget_microusd:
            quota_reason = "monthly_budget"

    ready = bool(
        policy
        and policy.enabled
        and ai_globally_configured
        and ai_organization_authorized
        and quota_reason is None
    )
    if policy is None:
        reason = "policy_required"
    elif not policy.enabled:
        reason = "organization_disabled"
    elif not ai_globally_configured:
        reason = "provider_not_configured"
    elif not ai_organization_authorized:
        reason = "organization_not_authorized"
    elif quota_reason:
        reason = quota_reason
    else:
        reason = "ready"
    return {
        "schema": "sris_ai_governance",
        "schema_version": "1.0",
        "organization_id": organization_id,
        "ready": ready,
        "readiness_reason": reason,
        "global_provider_configured": ai_globally_configured,
        "organization_authorized": ai_organization_authorized,
        "policy": policy_view(policy),
        "current_period": current,
        "currency": "USD",
        "cost_notice": (
            "Costs are governed estimates derived from provider-reported token usage "
            "and the stored pricing snapshot; the provider invoice remains authoritative."
        ),
    }
