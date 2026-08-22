from __future__ import annotations

import os
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.atlas_platform.auth import current_user
from app.atlas_platform.database import Base, get_db
from app.atlas_platform.models import Membership, Organization, User
from app.mission_intelligence import models as mission_models  # noqa: F401

router = APIRouter(prefix="/api/pilot", tags=["pilot-bootstrap"])
MICRO_EUR = 1_000_000
MICRO_USD = 1_000_000


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _month_start() -> date:
    today = date.today()
    return date(today.year, today.month, 1)


def _model() -> str:
    return os.getenv("SRIS_OPENAI_MODEL", "gpt-5.6-terra").strip() or "gpt-5.6-terra"


def _micro_to_eur(value: int | None) -> float:
    return round((value or 0) / MICRO_EUR, 4)


def _pilot_tables(db: Session) -> None:
    """Make the isolated Pilot self-healing for tables already declared by SRIS.

    Production still uses migrations. The September Pilot is intentionally able to
    create missing declared tables on first authenticated access so a Railway
    redeploy cannot leave UI code ahead of its backing schema.
    """
    Base.metadata.create_all(bind=db.get_bind(), checkfirst=True)
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS pilot_ai_wallets (
            organization_id VARCHAR(64) PRIMARY KEY,
            plan_code VARCHAR(40) NOT NULL DEFAULT 'pilot',
            credit_microeur BIGINT NOT NULL DEFAULT 0,
            trial_granted_at TIMESTAMPTZ NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS pilot_ai_wallet_ledger (
            id VARCHAR(64) PRIMARY KEY,
            organization_id VARCHAR(64) NOT NULL,
            kind VARCHAR(40) NOT NULL,
            amount_microeur BIGINT NOT NULL,
            reference VARCHAR(200) NULL,
            provider_cost_microusd BIGINT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))


def _membership(db: Session, user_id: str) -> Membership | None:
    return (
        db.query(Membership)
        .filter(Membership.user_id == user_id)
        .order_by(Membership.created_at.asc())
        .first()
    )


def _ensure_workspace_state(db: Session, membership: Membership, user_id: str) -> None:
    org_id = membership.organization_id
    policy = db.execute(
        text("SELECT id FROM mi_ai_organization_policies WHERE organization_id=:org LIMIT 1"),
        {"org": org_id},
    ).first()
    if not policy:
        db.execute(text("""
            INSERT INTO mi_ai_organization_policies
            (id, organization_id, enabled, enforce_monthly_limits,
             monthly_request_limit, monthly_input_token_limit,
             monthly_output_token_limit, monthly_budget_microusd,
             per_request_input_token_limit, per_request_output_token_limit,
             max_concurrent_requests, updated_by_user_id, created_at, updated_at)
            VALUES
            (gen_random_uuid()::text, :org, :enabled, false,
             200, 3000000, 800000, 25000000,
             120000, 12000, 2, :uid, now(), now())
        """), {"org": org_id, "enabled": _flag("SRIS_AI_ENABLED", False), "uid": user_id})

    wallet = db.execute(
        text("SELECT organization_id FROM pilot_ai_wallets WHERE organization_id=:org"),
        {"org": org_id},
    ).first()
    if not wallet:
        trial_eur = float(os.getenv("SRIS_TRIAL_CREDIT_EUR", "5.00") or 5.0)
        credit = max(0, int(trial_eur * MICRO_EUR))
        db.execute(text("""
            INSERT INTO pilot_ai_wallets
            (organization_id, plan_code, credit_microeur, trial_granted_at)
            VALUES (:org, 'pilot', :credit, now())
        """), {"org": org_id, "credit": credit})
        if credit:
            db.execute(text("""
                INSERT INTO pilot_ai_wallet_ledger
                (id, organization_id, kind, amount_microeur, reference)
                VALUES (gen_random_uuid()::text, :org, 'trial', :credit, 'pilot-bootstrap')
            """), {"org": org_id, "credit": credit})


@router.get("/profile")
def pilot_profile_bootstrap(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    _pilot_tables(db)
    membership = _membership(db, user.id)
    organization = db.get(Organization, membership.organization_id) if membership else None

    policy = None
    usage = None
    wallet = None
    ledger: list[dict] = []
    if membership and organization:
        _ensure_workspace_state(db, membership, user.id)
        db.commit()
        policy = db.execute(text("""
            SELECT enabled, monthly_request_limit, monthly_budget_microusd
            FROM mi_ai_organization_policies
            WHERE organization_id=:org
        """), {"org": organization.id}).mappings().first()
        usage = db.execute(text("""
            SELECT request_count, estimated_cost_microusd
            FROM mi_ai_usage_periods
            WHERE organization_id=:org AND period_start=:period
        """), {"org": organization.id, "period": _month_start()}).mappings().first()
        wallet = db.execute(text("""
            SELECT plan_code, credit_microeur
            FROM pilot_ai_wallets WHERE organization_id=:org
        """), {"org": organization.id}).mappings().first()
        rows = db.execute(text("""
            SELECT kind, amount_microeur, reference, provider_cost_microusd, created_at
            FROM pilot_ai_wallet_ledger
            WHERE organization_id=:org
            ORDER BY created_at DESC
            LIMIT 8
        """), {"org": organization.id}).mappings().all()
        ledger = [{
            "kind": row["kind"],
            "amount_eur": _micro_to_eur(row["amount_microeur"]),
            "reference": row["reference"],
            "provider_cost_usd": round((row["provider_cost_microusd"] or 0) / MICRO_USD, 6),
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        } for row in rows]

    return {
        "user": {"id": user.id, "email": user.email, "full_name": user.full_name},
        "organization": ({
            "id": organization.id,
            "name": organization.name,
            "slug": organization.slug,
            "role": membership.role,
        } if organization and membership else None),
        "ai": {
            "provider_configured": bool(os.getenv("OPENAI_API_KEY", "").strip()),
            "runtime_enabled": _flag("SRIS_AI_ENABLED", False),
            "organization_enabled": bool(policy and policy["enabled"]),
            "model": _model(),
            "requests_used": int(usage["request_count"]) if usage else 0,
            "request_limit": int(policy["monthly_request_limit"]) if policy else 0,
            "provider_cost_usd": round((usage["estimated_cost_microusd"] if usage else 0) / MICRO_USD, 4),
            "credit_eur": _micro_to_eur(wallet["credit_microeur"] if wallet else 0),
            "plan": wallet["plan_code"] if wallet else "pilot",
            "ledger": ledger,
        },
        "integration": {
            "schema_ready": True,
            "workspace_ready": bool(organization and membership),
            "mission_intelligence": True,
            "document_intelligence": True,
            "evidence_graph": True,
            "organizational_memory": True,
        },
    }
