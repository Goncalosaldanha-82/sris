from __future__ import annotations

import os
import re
import secrets
from datetime import date
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.atlas_platform.auth import current_user
from app.atlas_platform.database import get_db
from app.atlas_platform.models import Membership, Organization, Role, User
from app.atlas_platform.security import create_access_token, create_refresh_token, hash_password

router = APIRouter(prefix="/api/pilot", tags=["pilot-product"])

MICRO_EUR = 1_000_000
MICRO_USD = 1_000_000


class PilotRegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=12, max_length=200)
    organization_name: str | None = Field(default=None, min_length=2, max_length=200)


class PilotTopupRequest(BaseModel):
    amount_eur: Decimal = Field(gt=0, le=500)


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _pilot_runtime() -> bool:
    service = os.getenv("RAILWAY_SERVICE_NAME", "").strip().lower()
    return "pilot" in service or _flag("SRIS_PILOT_MODE", False)


def _public_signup_enabled() -> bool:
    return _flag("SRIS_PUBLIC_SIGNUP_ENABLED", _pilot_runtime())


def _slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return (value[:90] or "workspace") + "-" + secrets.token_hex(3)


def _trial_credit_eur() -> Decimal:
    try:
        value = Decimal(os.getenv("SRIS_TRIAL_CREDIT_EUR", "5.00"))
    except Exception:
        value = Decimal("5.00")
    return max(Decimal("0"), min(Decimal("100"), value))


def _eur_to_micro(value: Decimal) -> int:
    return int((value * MICRO_EUR).quantize(Decimal("1")))


def _micro_to_eur(value: int | None) -> float:
    return round((value or 0) / MICRO_EUR, 2)


def _month_start() -> date:
    today = date.today()
    return date(today.year, today.month, 1)


def _membership_for_user(db: Session, user_id: str) -> Membership | None:
    return (
        db.query(Membership)
        .filter(Membership.user_id == user_id)
        .order_by(Membership.created_at.asc())
        .first()
    )


def _ensure_ai_policy(db: Session, organization_id: str, user_id: str | None = None) -> None:
    existing = db.execute(
        text("SELECT id FROM mi_ai_organization_policies WHERE organization_id=:org LIMIT 1"),
        {"org": organization_id},
    ).first()
    if existing:
        return
    db.execute(
        text(
            """
            INSERT INTO mi_ai_organization_policies
            (id, organization_id, enabled, monthly_request_limit,
             monthly_input_token_limit, monthly_output_token_limit,
             monthly_budget_microusd, per_request_input_token_limit,
             per_request_output_token_limit, max_concurrent_requests,
             updated_by_user_id)
            VALUES (:id, :org, false, 40, 500000, 100000, 5000000, 60000, 4000, 1, :user_id)
            """
        ),
        {"id": str(uuid4()), "org": organization_id, "user_id": user_id},
    )


def _ensure_wallet(db: Session, organization_id: str) -> None:
    existing = db.execute(
        text("SELECT organization_id FROM pilot_ai_wallets WHERE organization_id=:org"),
        {"org": organization_id},
    ).first()
    if existing:
        return
    trial = _trial_credit_eur()
    amount = _eur_to_micro(trial)
    db.execute(
        text(
            """
            INSERT INTO pilot_ai_wallets
            (organization_id, plan_code, credit_microeur, trial_granted_at)
            VALUES (:org, 'pilot', :credit, now())
            """
        ),
        {"org": organization_id, "credit": amount},
    )
    if amount:
        db.execute(
            text(
                """
                INSERT INTO pilot_ai_wallet_ledger
                (id, organization_id, kind, amount_microeur, reference)
                VALUES (:id, :org, 'trial', :amount, 'pilot-signup')
                """
            ),
            {"id": str(uuid4()), "org": organization_id, "amount": amount},
        )


@router.get("/capabilities")
def pilot_capabilities() -> dict:
    return {
        "public_signup": _public_signup_enabled(),
        "password_reset": True,
        "ai_configured": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "ai_enabled": _flag("SRIS_AI_ENABLED", False),
        "trial_credit_eur": float(_trial_credit_eur()),
        "billing_mode": "pilot",
    }


@router.post("/register", status_code=status.HTTP_201_CREATED)
def pilot_register(payload: PilotRegisterRequest, db: Session = Depends(get_db)) -> dict:
    if not _public_signup_enabled():
        raise HTTPException(status_code=403, detail="A criação pública de conta está temporariamente fechada.")

    email = str(payload.email).strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="Já existe uma conta com este email.")

    org_name = (payload.organization_name or f"{payload.full_name.strip()} · Workspace").strip()
    user = User(
        email=email,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        is_active=True,
        auth_version=1,
    )
    organization = Organization(name=org_name, slug=_slugify(org_name))
    db.add_all([user, organization])
    db.flush()
    membership = Membership(
        user_id=user.id,
        organization_id=organization.id,
        role=Role.OWNER.value,
    )
    db.add(membership)
    _ensure_ai_policy(db, organization.id, user.id)
    _ensure_wallet(db, organization.id)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Não foi possível criar a conta.") from exc

    return {
        "status": "created",
        "access_token": create_access_token(user_id=user.id, auth_version=user.auth_version),
        "refresh_token": create_refresh_token(user_id=user.id, auth_version=user.auth_version),
        "organization_id": organization.id,
        "organization_name": organization.name,
        "trial_credit_eur": float(_trial_credit_eur()),
    }


@router.get("/profile")
def pilot_profile(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    membership = _membership_for_user(db, user.id)
    organization = db.get(Organization, membership.organization_id) if membership else None
    wallet = None
    policy = None
    usage = None
    if organization:
        _ensure_ai_policy(db, organization.id, user.id)
        _ensure_wallet(db, organization.id)
        db.commit()
        wallet = db.execute(
            text("SELECT plan_code, credit_microeur FROM pilot_ai_wallets WHERE organization_id=:org"),
            {"org": organization.id},
        ).mappings().first()
        policy = db.execute(
            text(
                """
                SELECT enabled, monthly_request_limit, monthly_budget_microusd
                FROM mi_ai_organization_policies WHERE organization_id=:org
                """
            ),
            {"org": organization.id},
        ).mappings().first()
        usage = db.execute(
            text(
                """
                SELECT request_count, estimated_cost_microusd
                FROM mi_ai_usage_periods
                WHERE organization_id=:org AND period_start=:period
                """
            ),
            {"org": organization.id, "period": _month_start()},
        ).mappings().first()

    return {
        "user": {"id": user.id, "email": user.email, "full_name": user.full_name},
        "organization": (
            {"id": organization.id, "name": organization.name, "slug": organization.slug, "role": membership.role}
            if organization and membership else None
        ),
        "ai": {
            "provider_configured": bool(os.getenv("OPENAI_API_KEY", "").strip()),
            "runtime_enabled": _flag("SRIS_AI_ENABLED", False),
            "organization_enabled": bool(policy and policy["enabled"]),
            "requests_used": int(usage["request_count"]) if usage else 0,
            "request_limit": int(policy["monthly_request_limit"]) if policy else 0,
            "provider_cost_usd": round((usage["estimated_cost_microusd"] if usage else 0) / MICRO_USD, 4),
            "credit_eur": _micro_to_eur(wallet["credit_microeur"] if wallet else 0),
            "plan": wallet["plan_code"] if wallet else "pilot",
        },
    }


@router.get("/plans")
def pilot_plans() -> dict:
    def env_money(name: str, default: str) -> float:
        try:
            return float(Decimal(os.getenv(name, default)))
        except Exception:
            return float(Decimal(default))

    return {
        "currency": "EUR",
        "plans": [
            {"code": "pilot", "name": "Pilot", "monthly_eur": 0.0, "label": "Validação inicial", "status": "active"},
            {"code": "professional", "name": "Professional", "monthly_eur": env_money("SRIS_PLAN_PROFESSIONAL_EUR", "49"), "label": "Equipas e missões recorrentes", "status": "proposal"},
            {"code": "organization", "name": "Organization", "monthly_eur": env_money("SRIS_PLAN_ORGANIZATION_EUR", "149"), "label": "Memória organizacional e governação", "status": "proposal"},
        ],
        "topups": [
            {"code": "credit-10", "credit_eur": 10.0},
            {"code": "credit-25", "credit_eur": 25.0},
            {"code": "credit-50", "credit_eur": 50.0},
        ],
        "payments_live": False,
        "note": "Os preços são configuráveis. A compra online permanece desligada até ser integrado um prestador de pagamentos.",
    }


@router.post("/credits/test-topup")
def pilot_test_topup(
    payload: PilotTopupRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not _flag("SRIS_BILLING_TEST_MODE", _pilot_runtime()):
        raise HTTPException(status_code=403, detail="Carregamentos de teste estão desativados.")
    membership = _membership_for_user(db, user.id)
    if membership is None or membership.role not in {Role.OWNER.value, Role.ADMIN.value}:
        raise HTTPException(status_code=403, detail="Sem permissão para carregar créditos.")
    _ensure_wallet(db, membership.organization_id)
    amount = _eur_to_micro(payload.amount_eur)
    db.execute(
        text("UPDATE pilot_ai_wallets SET credit_microeur=credit_microeur+:amount, updated_at=now() WHERE organization_id=:org"),
        {"amount": amount, "org": membership.organization_id},
    )
    db.execute(
        text(
            """
            INSERT INTO pilot_ai_wallet_ledger
            (id, organization_id, kind, amount_microeur, reference)
            VALUES (:id, :org, 'test_topup', :amount, 'pilot-ui')
            """
        ),
        {"id": str(uuid4()), "org": membership.organization_id, "amount": amount},
    )
    db.commit()
    balance = db.execute(
        text("SELECT credit_microeur FROM pilot_ai_wallets WHERE organization_id=:org"),
        {"org": membership.organization_id},
    ).scalar_one()
    return {"status": "credited", "credit_eur": _micro_to_eur(balance)}
