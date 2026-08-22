from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.atlas_platform.auth import current_user
from app.atlas_platform.database import get_db
from app.atlas_platform.models import Membership, User
from app.mission_intelligence.governance import (
    AIGovernanceBlocked,
    reserve_ai_usage,
    settle_ai_usage,
)
from app.mission_intelligence.models import CanonicalMission, MissionAttachment

router = APIRouter(prefix="/api/pilot/intelligence", tags=["pilot-intelligence"])
MICRO_EUR = 1_000_000
MICRO_USD = 1_000_000


class PilotIntelligenceRequest(BaseModel):
    message: str = Field(min_length=2, max_length=20000)
    context: str | None = Field(default=None, max_length=40000)
    mission_id: str | None = Field(default=None, max_length=64)
    mission_code: str | None = Field(default=None, max_length=80)


def _membership(db: Session, user_id: str) -> Membership | None:
    return (
        db.query(Membership)
        .filter(Membership.user_id == user_id)
        .order_by(Membership.created_at.asc())
        .first()
    )


def _model() -> str:
    return os.getenv("SRIS_OPENAI_MODEL", "gpt-5.6-terra").strip() or "gpt-5.6-terra"


def _estimate_tokens(value: str) -> int:
    # Deliberately conservative approximation used only for the governance reservation.
    return max(1, (len(value) + 2) // 3)


def _terms(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-ZÀ-ÿ0-9_-]{4,}", value.lower())
        if token not in {"para", "como", "mais", "esta", "este", "isso", "sobre", "entre", "pela", "pelo"}
    }


def _mission_context(
    db: Session,
    *,
    organization_id: str,
    payload: PilotIntelligenceRequest,
) -> tuple[str, dict]:
    if not payload.mission_id and not payload.mission_code:
        return payload.context or "", {"mission": None, "sources": []}

    query = db.query(CanonicalMission).filter(CanonicalMission.organization_id == organization_id)
    if payload.mission_id:
        query = query.filter(CanonicalMission.id == payload.mission_id)
    else:
        query = query.filter(CanonicalMission.code == payload.mission_code)
    mission = query.one_or_none()
    if mission is None:
        raise HTTPException(status_code=404, detail="A missão indicada não existe neste workspace.")

    try:
        document = json.loads(mission.document_json or "{}")
    except Exception:
        document = {}
    mission_text = json.dumps(document, ensure_ascii=False, indent=2)
    query_terms = _terms(payload.message + "\n" + (payload.context or "") + "\n" + mission.title)

    attachments = (
        db.query(MissionAttachment)
        .filter(
            MissionAttachment.organization_id == organization_id,
            MissionAttachment.mission_id == mission.id,
            MissionAttachment.extraction_status == "ready",
        )
        .order_by(MissionAttachment.created_at.desc())
        .all()
    )
    ranked: list[tuple[int, MissionAttachment]] = []
    for item in attachments:
        text_value = item.extracted_text or ""
        score = len(query_terms.intersection(_terms(text_value[:40000])))
        ranked.append((score, item))
    ranked.sort(key=lambda pair: (pair[0], pair[1].created_at), reverse=True)

    budget = int(os.getenv("SRIS_PILOT_CONTEXT_CHAR_BUDGET", "24000"))
    parts = [f"MISSÃO {mission.code} — {mission.title}\n{mission_text[:9000]}"]
    used = len(parts[0])
    sources: list[dict] = []
    for score, item in ranked:
        if used >= budget:
            break
        available = max(0, budget - used)
        excerpt = (item.extracted_text or "")[: min(available, 7000)]
        if not excerpt:
            continue
        parts.append(f"FONTE: {item.original_filename}\n{excerpt}")
        used += len(parts[-1])
        sources.append(
            {
                "attachment_id": item.id,
                "filename": item.original_filename,
                "relevance_score": score,
                "characters_used": len(excerpt),
            }
        )
    if payload.context:
        parts.append("CONTEXTO ADICIONAL DO UTILIZADOR:\n" + payload.context[:6000])
    return "\n\n---\n\n".join(parts), {
        "mission": {"id": mission.id, "code": mission.code, "title": mission.title, "revision": mission.revision},
        "sources": sources,
        "context_characters": min(sum(len(x) for x in parts), budget + 6000),
        "retrieval_mode": "mission_scoped_selective",
    }


def _extract_output(payload: dict) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    chunks: list[str] = []
    for item in payload.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) or []:
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                value = content["text"].strip()
                if value:
                    chunks.append(value)
    return "\n\n".join(chunks)


def _call_openai(*, message: str, context: str, model: str) -> tuple[str, dict, str | None]:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise HTTPException(status_code=503, detail="A chave OpenAI ainda não está configurada no Pilot V1.")
    instructions = (
        "És o motor de Mission Intelligence do SRIS. Responde em português europeu. "
        "Distingue factos confirmados, declarações, inferências, hipóteses, lacunas de evidência, riscos e decisões. "
        "Não inventes factos, fontes ou certezas. Quando usares contexto documental, identifica a fonte pelo nome. "
        "Termina com próximos passos ordenados por valor decisório."
    )
    if context:
        instructions += "\n\nCONTEXTO RECUPERADO PELO SRIS:\n" + context
    body = json.dumps(
        {"model": model, "instructions": instructions, "input": message, "max_output_tokens": 2200}
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")[:500]
        raise HTTPException(status_code=502, detail=f"O fornecedor de IA recusou o pedido ({exc.code}). {raw}") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Não foi possível contactar o fornecedor de IA.") from exc
    output = _extract_output(data)
    if not output:
        raise HTTPException(status_code=502, detail="A IA respondeu sem conteúdo utilizável.")
    return output, data.get("usage") or {}, data.get("id")


def _ensure_interaction_schema(db: Session) -> None:
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS pilot_ai_interactions (
            id VARCHAR(64) PRIMARY KEY,
            organization_id VARCHAR(64) NOT NULL,
            user_id VARCHAR(64) NULL,
            mission_id VARCHAR(64) NULL,
            mission_code VARCHAR(80) NULL,
            usage_event_id VARCHAR(64) NULL,
            model VARCHAR(160) NOT NULL,
            user_message TEXT NOT NULL,
            answer TEXT NOT NULL,
            context_manifest_json TEXT NOT NULL,
            charged_microeur BIGINT NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_pilot_ai_interactions_org_created
        ON pilot_ai_interactions (organization_id, created_at DESC)
    """))


def _retail_charge_microeur(provider_cost_microusd: int) -> int:
    eur_per_usd = Decimal(os.getenv("SRIS_BILLING_EUR_PER_USD", "0.92"))
    multiplier = Decimal(os.getenv("SRIS_AI_RETAIL_MULTIPLIER", "1.50"))
    eur = (Decimal(provider_cost_microusd) / MICRO_USD) * eur_per_usd * multiplier
    return max(1, int((eur * MICRO_EUR).quantize(Decimal("1"), rounding=ROUND_HALF_UP)))


@router.post("/ask")
def governed_pilot_intelligence(
    payload: PilotIntelligenceRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _membership(db, user.id)
    if membership is None:
        raise HTTPException(status_code=403, detail="A conta não tem um workspace associado.")
    organization_id = membership.organization_id
    _ensure_interaction_schema(db)

    context, manifest = _mission_context(db, organization_id=organization_id, payload=payload)
    model = _model()
    reserved_input = _estimate_tokens(payload.message + "\n" + context)
    reserved_output = 2200

    try:
        reservation = reserve_ai_usage(
            db,
            organization_id=organization_id,
            user_id=user.id,
            model=model,
            input_tokens=reserved_input,
            output_tokens=reserved_output,
        )
    except AIGovernanceBlocked as exc:
        db.rollback()
        raise HTTPException(status_code=429, detail={"code": exc.code, "message": exc.message}) from exc

    wallet = db.execute(
        text("SELECT credit_microeur FROM pilot_ai_wallets WHERE organization_id=:org FOR UPDATE"),
        {"org": organization_id},
    ).mappings().first()
    if not wallet or int(wallet["credit_microeur"]) <= 0:
        try:
            settle_ai_usage(
                db,
                reservation=reservation,
                provider_response_id=None,
                input_tokens=0,
                cached_input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                failure_code="wallet_empty",
            )
        finally:
            db.rollback()
        raise HTTPException(status_code=402, detail="O saldo de IA terminou. Faça um carregamento para continuar.")

    try:
        answer, usage, response_id = _call_openai(message=payload.message, context=context, model=model)
    except HTTPException:
        settle_ai_usage(
            db,
            reservation=reservation,
            provider_response_id=None,
            input_tokens=None,
            cached_input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            failure_code="provider_request_failed",
        )
        raise

    event = settle_ai_usage(
        db,
        reservation=reservation,
        provider_response_id=response_id,
        input_tokens=int(usage.get("input_tokens") or 0),
        cached_input_tokens=int((usage.get("input_tokens_details") or {}).get("cached_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        total_tokens=int(usage.get("total_tokens") or 0),
    )
    charge = _retail_charge_microeur(int(event.estimated_cost_microusd or 0))
    current_balance = int(wallet["credit_microeur"])
    if charge > current_balance:
        raise HTTPException(status_code=402, detail="O saldo é insuficiente para concluir este pedido.")

    db.execute(text("""
        UPDATE pilot_ai_wallets
        SET credit_microeur=credit_microeur-:charge, updated_at=CURRENT_TIMESTAMP
        WHERE organization_id=:org
    """), {"charge": charge, "org": organization_id})
    db.execute(text("""
        INSERT INTO pilot_ai_wallet_ledger
        (id, organization_id, kind, amount_microeur, reference, provider_cost_microusd)
        VALUES (:id, :org, 'ai_usage', :amount, :reference, :provider_cost)
    """), {
        "id": str(uuid4()), "org": organization_id, "amount": -charge,
        "reference": f"governed:{event.id}", "provider_cost": int(event.estimated_cost_microusd or 0),
    })
    db.execute(text("""
        INSERT INTO pilot_ai_interactions
        (id, organization_id, user_id, mission_id, mission_code, usage_event_id, model,
         user_message, answer, context_manifest_json, charged_microeur)
        VALUES (:id, :org, :user_id, :mission_id, :mission_code, :usage_event_id, :model,
                :message, :answer, :manifest, :charge)
    """), {
        "id": str(uuid4()), "org": organization_id, "user_id": user.id,
        "mission_id": (manifest.get("mission") or {}).get("id"),
        "mission_code": (manifest.get("mission") or {}).get("code"),
        "usage_event_id": event.id, "model": model, "message": payload.message,
        "answer": answer, "manifest": json.dumps(manifest, ensure_ascii=False), "charge": charge,
    })
    db.commit()
    return {
        "answer": answer,
        "model": model,
        "usage_event_id": event.id,
        "usage": {
            "input_tokens": int(event.input_tokens or 0),
            "output_tokens": int(event.output_tokens or 0),
            "total_tokens": int(event.total_tokens or 0),
        },
        "provider_cost_usd": round(int(event.estimated_cost_microusd or 0) / MICRO_USD, 6),
        "charged_eur": round(charge / MICRO_EUR, 4),
        "balance_eur": round((current_balance - charge) / MICRO_EUR, 4),
        "context": manifest,
        "governance": {"status": event.status, "cost_basis": event.cost_basis},
    }


@router.get("/history")
def pilot_intelligence_history(
    mission_code: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    membership = _membership(db, user.id)
    if membership is None:
        raise HTTPException(status_code=403, detail="A conta não tem um workspace associado.")
    _ensure_interaction_schema(db)
    sql = """
        SELECT id, mission_id, mission_code, usage_event_id, model, user_message, answer,
               context_manifest_json, charged_microeur, created_at
        FROM pilot_ai_interactions WHERE organization_id=:org
    """
    params = {"org": membership.organization_id}
    if mission_code:
        sql += " AND mission_code=:mission_code"
        params["mission_code"] = mission_code
    sql += " ORDER BY created_at DESC LIMIT 50"
    rows = db.execute(text(sql), params).mappings().all()
    return [
        {
            "id": row["id"], "mission_id": row["mission_id"], "mission_code": row["mission_code"],
            "usage_event_id": row["usage_event_id"], "model": row["model"],
            "message": row["user_message"], "answer": row["answer"],
            "context": json.loads(row["context_manifest_json"] or "{}"),
            "charged_eur": round(int(row["charged_microeur"] or 0) / MICRO_EUR, 4),
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }
        for row in rows
    ]
