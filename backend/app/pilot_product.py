from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.atlas_platform.auth import current_user
from app.atlas_platform.database import get_db
from app.atlas_platform.models import Membership, Organization, Role, User
from app.atlas_platform.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
)

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


class PilotPasswordResetRequest(BaseModel):
    email: EmailStr


class PilotPasswordResetConfirm(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    new_password: str = Field(min_length=12, max_length=200)


class PilotAIRequest(BaseModel):
    message: str = Field(min_length=2, max_length=12000)
    context: str | None = Field(default=None, max_length=16000)


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


def _money_env(name: str, default: str) -> Decimal:
    try:
        return Decimal(os.getenv(name, default))
    except Exception:
        return Decimal(default)


def _eur_to_micro(value: Decimal) -> int:
    return int((value * MICRO_EUR).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _micro_to_eur(value: int | None) -> float:
    return round((value or 0) / MICRO_EUR, 4)


def _month_start() -> date:
    today = date.today()
    return date(today.year, today.month, 1)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _iso_datetime(value: object | None) -> str | None:
    return _coerce_datetime(value).isoformat() if value is not None else None


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _membership_for_user(db: Session, user_id: str) -> Membership | None:
    return (
        db.query(Membership)
        .filter(Membership.user_id == user_id)
        .order_by(Membership.created_at.asc())
        .first()
    )


def _ensure_pilot_schema(db: Session) -> None:
    """Verify the migrated Pilot schema without mutating it at request time."""

    required = {
        "pilot_ai_wallets",
        "pilot_ai_wallet_ledger",
        "pilot_password_reset_tokens",
    }
    available = set(inspect(db.get_bind()).get_table_names())
    missing = sorted(required - available)
    if missing:
        raise RuntimeError(
            "Pilot database schema is incomplete; run `alembic upgrade head` "
            f"before serving requests (missing: {', '.join(missing)})"
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
            (id, organization_id, enabled, enforce_monthly_limits,
             monthly_request_limit,
             monthly_input_token_limit, monthly_output_token_limit,
             monthly_budget_microusd, per_request_input_token_limit,
             per_request_output_token_limit, max_concurrent_requests,
             updated_by_user_id, created_at, updated_at)
            VALUES (:id, :org, :enabled, false, 200, 3000000, 800000,
                    25000000, 120000, 12000, 2, :user_id, :now, :now)
            """
        ),
        {
            "id": str(uuid4()),
            "org": organization_id,
            "enabled": _flag("SRIS_AI_ENABLED", False),
            "user_id": user_id,
            "now": _utcnow(),
        },
    )


def _ensure_wallet(db: Session, organization_id: str) -> None:
    _ensure_pilot_schema(db)
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
            VALUES (:org, 'pilot', :credit, :now)
            """
        ),
        {"org": organization_id, "credit": amount, "now": _utcnow()},
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


def _ai_model() -> str:
    return os.getenv("SRIS_OPENAI_MODEL", "gpt-5.6-terra").strip() or "gpt-5.6-terra"


def _extract_output_text(payload: dict) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    chunks: list[str] = []
    for item in payload.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) or []:
            if isinstance(content, dict):
                text_value = content.get("text")
                if isinstance(text_value, str) and text_value.strip():
                    chunks.append(text_value.strip())
    return "\n\n".join(chunks).strip()


def _provider_cost_microusd(model: str, input_tokens: int, output_tokens: int) -> int:
    # Default rates reflect the cost-balanced GPT-5.6 Terra standard tier.
    # They remain environment-configurable so pricing can be updated without a deploy.
    if "luna" in model:
        in_rate = _money_env("SRIS_OPENAI_INPUT_USD_PER_M", "0.50")
        out_rate = _money_env("SRIS_OPENAI_OUTPUT_USD_PER_M", "3.00")
    elif "sol" in model:
        in_rate = _money_env("SRIS_OPENAI_INPUT_USD_PER_M", "2.50")
        out_rate = _money_env("SRIS_OPENAI_OUTPUT_USD_PER_M", "15.00")
    else:
        in_rate = _money_env("SRIS_OPENAI_INPUT_USD_PER_M", "1.25")
        out_rate = _money_env("SRIS_OPENAI_OUTPUT_USD_PER_M", "7.50")
    usd = (Decimal(input_tokens) * in_rate + Decimal(output_tokens) * out_rate) / Decimal(1_000_000)
    return int((usd * MICRO_USD).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _customer_charge_microeur(provider_cost_microusd: int) -> int:
    usd = Decimal(provider_cost_microusd) / MICRO_USD
    eur_per_usd = _money_env("SRIS_BILLING_EUR_PER_USD", "0.92")
    multiplier = _money_env("SRIS_AI_PRICE_MULTIPLIER", "1.50")
    eur = usd * eur_per_usd * multiplier
    return max(1, _eur_to_micro(eur))


def _openai_response(message: str, context: str | None) -> tuple[str, int, int, str]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="A integração de IA ainda não tem uma chave configurada.")
    if not _flag("SRIS_AI_ENABLED", False):
        raise HTTPException(status_code=503, detail="A IA está instalada mas temporariamente desativada neste ambiente.")

    model = _ai_model()
    system = (
        "És o copiloto de decisão do SRIS. Responde em português europeu, com clareza executiva, "
        "distinguindo factos, inferências, incertezas e próximos passos. Não inventes fontes nem dados. "
        "Quando a informação for insuficiente, identifica exatamente o que falta."
    )
    if context:
        system += "\n\nContexto de trabalho fornecido pelo utilizador:\n" + context
    body = json.dumps(
        {
            "model": model,
            "instructions": system,
            "input": message,
            "max_output_tokens": 1800,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")[:1000]
        raise HTTPException(status_code=502, detail=f"O fornecedor de IA recusou o pedido ({exc.code}). {raw}") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Não foi possível contactar o fornecedor de IA.") from exc

    output = _extract_output_text(payload)
    if not output:
        raise HTTPException(status_code=502, detail="A IA respondeu sem conteúdo utilizável.")
    usage = payload.get("usage") or {}
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    return output, input_tokens, output_tokens, model


@router.get("/capabilities")
def pilot_capabilities(db: Session = Depends(get_db)) -> dict:
    _ensure_pilot_schema(db)
    db.commit()
    return {
        "public_signup": _public_signup_enabled(),
        "password_reset": True,
        "password_reset_delivery": "pilot-link" if _pilot_runtime() else "external-email-required",
        "ai_configured": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "ai_enabled": _flag("SRIS_AI_ENABLED", False),
        "ai_model": _ai_model(),
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


@router.post("/password-reset/request")
def pilot_password_reset_request(payload: PilotPasswordResetRequest, db: Session = Depends(get_db)) -> dict:
    _ensure_pilot_schema(db)
    email = str(payload.email).strip().lower()
    user = db.query(User).filter(User.email == email, User.is_active.is_(True)).one_or_none()
    # Always return a neutral response to avoid account enumeration.
    response: dict = {"status": "accepted", "message": "Se a conta existir, foi criado um pedido de recuperação."}
    if user is None:
        db.commit()
        return response

    db.execute(
        text("UPDATE pilot_password_reset_tokens SET used_at=:now WHERE user_id=:uid AND used_at IS NULL"),
        {"uid": user.id, "now": _utcnow()},
    )
    raw_token = secrets.token_urlsafe(48)
    db.execute(
        text(
            """
            INSERT INTO pilot_password_reset_tokens (id, user_id, token_hash, expires_at)
            VALUES (:id, :uid, :token_hash, :expires_at)
            """
        ),
        {
            "id": str(uuid4()),
            "uid": user.id,
            "token_hash": _hash_token(raw_token),
            "expires_at": _utcnow() + timedelta(minutes=30),
        },
    )
    db.commit()

    # For an isolated Pilot service we expose the one-time link in the response
    # so recovery can be tested end-to-end before an email provider is selected.
    # This is never exposed outside explicit pilot mode.
    if _pilot_runtime() and _flag("SRIS_PILOT_SHOW_RESET_LINK", True):
        response["reset_token"] = raw_token
        response["expires_minutes"] = 30
    return response


@router.post("/password-reset/confirm")
def pilot_password_reset_confirm(payload: PilotPasswordResetConfirm, db: Session = Depends(get_db)) -> dict:
    _ensure_pilot_schema(db)
    token_hash = _hash_token(payload.token)
    row = db.execute(
        text(
            """
            SELECT id, user_id, expires_at, used_at
            FROM pilot_password_reset_tokens
            WHERE token_hash=:token_hash
            LIMIT 1
            """
        ),
        {"token_hash": token_hash},
    ).mappings().first()
    if not row or row["used_at"] is not None or _coerce_datetime(row["expires_at"]) <= _utcnow():
        raise HTTPException(status_code=400, detail="O link de recuperação é inválido ou expirou.")

    user = db.get(User, row["user_id"])
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail="O link de recuperação é inválido ou expirou.")
    user.password_hash = hash_password(payload.new_password)
    user.auth_version = int(user.auth_version or 0) + 1
    db.execute(
        text("UPDATE pilot_password_reset_tokens SET used_at=:now WHERE id=:id"),
        {"id": row["id"], "now": _utcnow()},
    )
    db.commit()
    return {"status": "password_updated"}


@router.get("/profile")
def pilot_profile(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    membership = _membership_for_user(db, user.id)
    organization = db.get(Organization, membership.organization_id) if membership else None
    wallet = None
    policy = None
    usage = None
    recent_ledger: list[dict] = []
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
        rows = db.execute(
            text(
                """
                SELECT kind, amount_microeur, reference, provider_cost_microusd, created_at
                FROM pilot_ai_wallet_ledger
                WHERE organization_id=:org
                ORDER BY created_at DESC
                LIMIT 8
                """
            ),
            {"org": organization.id},
        ).mappings().all()
        recent_ledger = [
            {
                "kind": row["kind"],
                "amount_eur": _micro_to_eur(row["amount_microeur"]),
                "reference": row["reference"],
                "provider_cost_usd": round((row["provider_cost_microusd"] or 0) / MICRO_USD, 6),
                "created_at": _iso_datetime(row["created_at"]),
            }
            for row in rows
        ]

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
            "model": _ai_model(),
            "requests_used": int(usage["request_count"]) if usage else 0,
            "request_limit": int(policy["monthly_request_limit"]) if policy else 0,
            "provider_cost_usd": round((usage["estimated_cost_microusd"] if usage else 0) / MICRO_USD, 4),
            "credit_eur": _micro_to_eur(wallet["credit_microeur"] if wallet else 0),
            "plan": wallet["plan_code"] if wallet else "pilot",
            "ledger": recent_ledger,
        },
    }


@router.get("/plans")
def pilot_plans() -> dict:
    return {
        "currency": "EUR",
        "plans": [
            {"code": "pilot", "name": "Pilot", "monthly_eur": 0.0, "label": "Validação inicial", "status": "active"},
            {"code": "professional", "name": "Professional", "monthly_eur": float(_money_env("SRIS_PLAN_PROFESSIONAL_EUR", "49")), "label": "Equipas e missões recorrentes", "status": "proposal"},
            {"code": "organization", "name": "Organization", "monthly_eur": float(_money_env("SRIS_PLAN_ORGANIZATION_EUR", "149")), "label": "Memória organizacional e governação", "status": "proposal"},
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
        text("UPDATE pilot_ai_wallets SET credit_microeur=credit_microeur+:amount, updated_at=:now WHERE organization_id=:org"),
        {"amount": amount, "org": membership.organization_id, "now": _utcnow()},
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


@router.post("/ai/ask")
def pilot_ai_ask(
    payload: PilotAIRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _membership_for_user(db, user.id)
    if membership is None:
        raise HTTPException(status_code=403, detail="A conta não tem um workspace associado.")
    _ensure_wallet(db, membership.organization_id)
    wallet = db.execute(
        text("SELECT credit_microeur FROM pilot_ai_wallets WHERE organization_id=:org FOR UPDATE"),
        {"org": membership.organization_id},
    ).mappings().first()
    if not wallet or int(wallet["credit_microeur"]) <= 0:
        db.rollback()
        raise HTTPException(status_code=402, detail="O saldo de IA terminou. Faça um carregamento para continuar.")

    output, input_tokens, output_tokens, model = _openai_response(payload.message, payload.context)
    provider_cost = _provider_cost_microusd(model, input_tokens, output_tokens)
    charge = _customer_charge_microeur(provider_cost)
    current_balance = int(wallet["credit_microeur"])
    if charge > current_balance:
        db.rollback()
        raise HTTPException(status_code=402, detail="O saldo é insuficiente para concluir este pedido.")

    db.execute(
        text(
            """
            UPDATE pilot_ai_wallets
            SET credit_microeur=credit_microeur-:charge, updated_at=:now
            WHERE organization_id=:org
            """
        ),
        {"charge": charge, "org": membership.organization_id, "now": _utcnow()},
    )
    db.execute(
        text(
            """
            INSERT INTO pilot_ai_wallet_ledger
            (id, organization_id, kind, amount_microeur, reference, provider_cost_microusd)
            VALUES (:id, :org, 'ai_usage', :amount, :reference, :provider_cost)
            """
        ),
        {
            "id": str(uuid4()),
            "org": membership.organization_id,
            "amount": -charge,
            "reference": model,
            "provider_cost": provider_cost,
        },
    )
    db.commit()
    return {
        "answer": output,
        "model": model,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        "provider_cost_usd": round(provider_cost / MICRO_USD, 6),
        "charged_eur": _micro_to_eur(charge),
        "balance_eur": _micro_to_eur(current_balance - charge),
    }
