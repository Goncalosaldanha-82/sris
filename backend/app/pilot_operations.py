from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from app.atlas_platform.auth import current_user
from app.atlas_platform.database import get_db
from app.atlas_platform.models import AuditEvent, Membership, Organization, Role, User
from app.evidence_graph import _ensure_schema as _ensure_graph_schema
from app.learning_lineage import _ensure_schema as _ensure_learning_schema
from app.mission_intelligence.models import CanonicalMission, MissionAttachment
from app.pilot_decision_cycle import _ensure_schema as _ensure_decision_schema
from app.pilot_readiness import mission_completion_readiness
from app.pilot_serialization import as_iso

router = APIRouter(prefix="/api/pilot", tags=["pilot-operations"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _env_int(name: str, default: int, minimum: int = 1, maximum: int = 100000) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def _membership(db: Session, user_id: str) -> Membership:
    membership = (
        db.query(Membership)
        .filter(Membership.user_id == user_id)
        .order_by(Membership.created_at.asc())
        .first()
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="O utilizador não pertence a um workspace.")
    return membership


def _require_admin(db: Session, user: User) -> Membership:
    membership = _membership(db, user.id)
    if membership.role not in {Role.OWNER.value, Role.ADMIN.value}:
        raise HTTPException(status_code=403, detail="Apenas proprietários ou administradores podem gerir contas.")
    return membership


def _audit(
    db: Session,
    *,
    organization_id: str | None,
    user_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    payload: dict,
) -> None:
    db.add(
        AuditEvent(
            id=str(uuid4()),
            organization_id=organization_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            payload_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
        )
    )


class AccountStateRequest(BaseModel):
    is_active: bool


class AccountRoleRequest(BaseModel):
    role: str


@router.get("/ops/status")
def ops_status(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _membership(db, user.id)
    org_id = membership.organization_id
    return {
        "status": "ok",
        "timestamp": _utcnow().isoformat(),
        "service": os.getenv("RAILWAY_SERVICE_NAME", "local"),
        "environment": os.getenv("RAILWAY_ENVIRONMENT_NAME", os.getenv("ATLAS_ENV", "unknown")),
        "organization_id": org_id,
        "members": db.query(Membership).filter(Membership.organization_id == org_id).count(),
        "active_members": (
            db.query(User)
            .join(Membership, Membership.user_id == User.id)
            .filter(Membership.organization_id == org_id, User.is_active.is_(True))
            .count()
        ),
        "audit_events": db.query(AuditEvent).filter(AuditEvent.organization_id == org_id).count(),
        "ai_configured": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "ai_enabled": os.getenv("SRIS_AI_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"},
        "rate_limit_scope": "process-local-pilot",
    }


@router.get("/workspace-summary")
def workspace_summary(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Operational command view for the authenticated workspace.

    This endpoint is deliberately deterministic.  It reports what is present
    in the mission, evidence, decision and learning stores without asking an
    assistant to infer progress.
    """

    membership = _membership(db, user.id)
    org_id = membership.organization_id
    _ensure_graph_schema(db)
    _ensure_decision_schema(db)
    _ensure_learning_schema(db)

    mission_rows = (
        db.query(CanonicalMission)
        .filter(CanonicalMission.organization_id == org_id)
        .order_by(CanonicalMission.updated_at.desc(), CanonicalMission.created_at.desc())
        .all()
    )

    attachment_rows = db.execute(
        text(
            """
            SELECT mission_id, extraction_status, COUNT(*) AS total
            FROM mi_mission_attachments
            WHERE organization_id=:org
            GROUP BY mission_id, extraction_status
            """
        ),
        {"org": org_id},
    ).mappings().all()
    attachment_counts: dict[str, dict[str, int]] = defaultdict(dict)
    for row in attachment_rows:
        attachment_counts[str(row["mission_id"])][str(row["extraction_status"])] = int(row["total"] or 0)

    graph_rows = db.execute(
        text(
            """
            SELECT mission_id, node_type, status, source_kind, COUNT(*) AS total
            FROM pilot_evidence_graph_nodes
            WHERE organization_id=:org
              AND status NOT IN ('rejected', 'superseded')
            GROUP BY mission_id, node_type, status, source_kind
            """
        ),
        {"org": org_id},
    ).mappings().all()
    graph_counts: dict[str, dict[str, int]] = defaultdict(dict)
    reviewed_learning: dict[str, int] = defaultdict(int)
    for row in graph_rows:
        mission_id = str(row["mission_id"])
        node_type = str(row["node_type"])
        graph_counts[mission_id][node_type] = graph_counts[mission_id].get(node_type, 0) + int(row["total"] or 0)
        if node_type == "learning" and row["status"] in {"accepted", "verified"}:
            reviewed_learning[mission_id] += int(row["total"] or 0)

    cycle_rows = db.execute(
        text(
            """
            SELECT mission_code, status, action, owner, due_date, evidence_node_id,
                   expected_outcome, actual_outcome, learning
            FROM pilot_decision_cycles
            WHERE organization_id=:org
            """
        ),
        {"org": org_id},
    ).mappings().all()
    cycles_by_mission: dict[str, list] = defaultdict(list)
    for row in cycle_rows:
        cycles_by_mission[str(row["mission_code"])].append(row)

    packet_rows = db.execute(
        text(
            """
            SELECT source_mission_id, COUNT(*) AS total
            FROM pilot_learning_packets
            WHERE organization_id=:org
            GROUP BY source_mission_id
            """
        ),
        {"org": org_id},
    ).mappings().all()
    packet_counts = {str(row["source_mission_id"]): int(row["total"] or 0) for row in packet_rows}

    now = _utcnow().date()
    mission_cards: list[dict] = []
    total_gaps = 0
    pending_results = 0
    for mission in mission_rows:
        attachments = attachment_counts.get(mission.id, {})
        source_ready = sum(attachments.get(status, 0) for status in ("ready", "visual_ready", "provider_ready"))
        graph = graph_counts.get(mission.id, {})
        cycles = cycles_by_mission.get(mission.code, [])
        total_gaps += graph.get("gap", 0)

        attention = 0
        for cycle in cycles:
            incomplete_execution = cycle["status"] in {"committed", "in_progress"} and (
                not str(cycle["action"] or "").strip()
                or not str(cycle["owner"] or "").strip()
                or not str(cycle["expected_outcome"] or "").strip()
            )
            incomplete_result = cycle["status"] == "completed" and (
                not str(cycle["actual_outcome"] or "").strip()
                or not str(cycle["learning"] or "").strip()
            )
            overdue = (
                cycle["due_date"] is not None
                and str(cycle["due_date"]) < now.isoformat()
                and cycle["status"] not in {"completed", "abandoned"}
            )
            if incomplete_execution or incomplete_result or overdue:
                attention += 1
            if cycle["status"] in {"committed", "in_progress"} or incomplete_result:
                pending_results += 1

        readiness = mission_completion_readiness(
            db,
            organization_id=org_id,
            mission_id=mission.id,
            mission_code=mission.code,
        )
        next_action = next(
            (check["label"] for check in readiness["checks"] if not check["passed"]),
            "Missão pronta para conclusão",
        )
        if mission.lifecycle_state == "paused":
            next_action = "Reativar a missão ou arquivá-la com justificação"
        elif mission.lifecycle_state == "completed":
            next_action = "Aprendizagem preservada; reutilizar quando for relevante"
        elif mission.lifecycle_state == "archived":
            next_action = "Missão arquivada"

        mission_cards.append(
            {
                "id": mission.id,
                "code": mission.code,
                "title": mission.title,
                "priority": mission.priority,
                "lifecycle_state": mission.lifecycle_state,
                "revision": mission.revision,
                "content_hash": mission.content_hash,
                "updated_at": as_iso(mission.updated_at),
                "documents": sum(attachments.values()),
                "documents_ready": source_ready,
                "document_errors": attachments.get("error", 0),
                "evidence": graph.get("evidence", 0),
                "hypotheses": graph.get("hypothesis", 0),
                "alternatives": graph.get("alternative", 0),
                "gaps": graph.get("gap", 0),
                "decisions": len(cycles),
                "attention": attention,
                "reviewed_learning": reviewed_learning.get(mission.id, 0),
                "published_learning": packet_counts.get(mission.id, 0),
                "progress_percent": readiness["progress_percent"],
                "next_action": next_action,
            }
        )

    active_states = {"active", "paused"}
    attention_missions = sum(
        1
        for mission in mission_cards
        if mission["lifecycle_state"] in active_states
        and (mission["attention"] > 0 or mission["progress_percent"] < 100)
    )
    db.commit()
    return {
        "generated_at": _utcnow().isoformat(),
        "organization_id": org_id,
        "role": membership.role,
        "metrics": {
            "missions_total": len(mission_cards),
            "missions_active": sum(1 for row in mission_cards if row["lifecycle_state"] == "active"),
            "missions_attention": attention_missions,
            "evidence_gaps": total_gaps,
            "pending_results": pending_results,
            "published_learning": sum(packet_counts.values()),
        },
        "missions": mission_cards,
    }


@router.get("/missions/{mission_code}/completion-readiness")
def completion_readiness(
    mission_code: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _membership(db, user.id)
    mission = (
        db.query(CanonicalMission)
        .filter(
            CanonicalMission.organization_id == membership.organization_id,
            CanonicalMission.code == mission_code,
        )
        .one_or_none()
    )
    if mission is None:
        raise HTTPException(status_code=404, detail="A missão indicada não existe neste workspace.")
    result = mission_completion_readiness(
        db,
        organization_id=membership.organization_id,
        mission_id=mission.id,
        mission_code=mission.code,
    )
    db.commit()
    return result


@router.get("/admin/audit")
def list_audit_events(
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _require_admin(db, user)
    rows = (
        db.query(AuditEvent)
        .filter(AuditEvent.organization_id == membership.organization_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    events = []
    for row in rows:
        try:
            payload = json.loads(row.payload_json or "{}")
        except (TypeError, ValueError):
            payload = {}
        events.append(
            {
                "id": row.id,
                "action": row.action,
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
                "user_id": row.user_id,
                "payload": payload,
                "created_at": as_iso(row.created_at),
            }
        )
    return {"events": events, "count": len(events)}


@router.get("/admin/accounts")
def list_accounts(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    admin_membership = _require_admin(db, user)
    rows = (
        db.query(User, Membership)
        .join(Membership, Membership.user_id == User.id)
        .filter(Membership.organization_id == admin_membership.organization_id)
        .order_by(User.created_at.asc())
        .all()
    )
    return {
        "organization_id": admin_membership.organization_id,
        "accounts": [
            {
                "id": account.id,
                "email": account.email,
                "full_name": account.full_name,
                "is_active": account.is_active,
                "role": membership.role,
                "last_login_at": account.last_login_at.isoformat() if account.last_login_at else None,
                "created_at": account.created_at.isoformat() if account.created_at else None,
            }
            for account, membership in rows
        ],
    }


@router.patch("/admin/accounts/{account_id}/state")
def set_account_state(
    account_id: str,
    payload: AccountStateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    admin_membership = _require_admin(db, user)
    target_membership = (
        db.query(Membership)
        .filter(
            Membership.user_id == account_id,
            Membership.organization_id == admin_membership.organization_id,
        )
        .one_or_none()
    )
    target = db.get(User, account_id)
    if target is None or target_membership is None:
        raise HTTPException(status_code=404, detail="Conta não encontrada neste workspace.")
    if target.id == user.id and not payload.is_active:
        raise HTTPException(status_code=409, detail="Não pode desativar a sua própria conta durante a sessão ativa.")

    before = target.is_active
    target.is_active = payload.is_active
    if before != payload.is_active:
        target.auth_version = int(target.auth_version or 1) + 1
    _audit(
        db,
        organization_id=admin_membership.organization_id,
        user_id=user.id,
        action="pilot.account.state_changed",
        resource_type="user",
        resource_id=target.id,
        payload={"before": before, "after": payload.is_active},
    )
    db.commit()
    return {"status": "updated", "account_id": target.id, "is_active": target.is_active}


@router.patch("/admin/accounts/{account_id}/role")
def set_account_role(
    account_id: str,
    payload: AccountRoleRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    admin_membership = _require_admin(db, user)
    allowed = {Role.ADMIN.value, Role.REVIEWER.value, Role.CONTRIBUTOR.value, Role.OBSERVER.value}
    if payload.role not in allowed:
        raise HTTPException(status_code=422, detail="Função inválida para administração do piloto.")

    target_membership = (
        db.query(Membership)
        .filter(
            Membership.user_id == account_id,
            Membership.organization_id == admin_membership.organization_id,
        )
        .one_or_none()
    )
    target = db.get(User, account_id)
    if target is None or target_membership is None:
        raise HTTPException(status_code=404, detail="Conta não encontrada neste workspace.")
    if target_membership.role == Role.OWNER.value:
        raise HTTPException(status_code=409, detail="A função de proprietário não pode ser alterada por este endpoint.")

    before = target_membership.role
    target_membership.role = payload.role
    _audit(
        db,
        organization_id=admin_membership.organization_id,
        user_id=user.id,
        action="pilot.account.role_changed",
        resource_type="membership",
        resource_id=target_membership.id,
        payload={"account_id": target.id, "before": before, "after": payload.role},
    )
    db.commit()
    return {"status": "updated", "account_id": target.id, "role": target_membership.role}


class PilotRateLimitMiddleware(BaseHTTPMiddleware):
    """Pilot-grade abuse control for sensitive public and AI endpoints.

    This limiter is intentionally process-local: it protects the current one-replica
    Pilot deployment without adding an external dependency. Before horizontal scale,
    replace the storage with a shared Redis-compatible backend.
    """

    _lock = threading.Lock()
    _buckets: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        rule = self._rule(request)
        if rule is None:
            return await call_next(request)

        limit, window_seconds, namespace = rule
        forwarded = request.headers.get("x-forwarded-for", "")
        client_ip = forwarded.split(",", 1)[0].strip() or (request.client.host if request.client else "unknown")
        key = f"{namespace}:{client_ip}"
        now = time.monotonic()

        with self._lock:
            bucket = self._buckets[key]
            cutoff = now - window_seconds
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, int(window_seconds - (now - bucket[0])))
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Demasiados pedidos. Tente novamente dentro de momentos."},
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": "0",
                    },
                )
            bucket.append(now)
            remaining = max(0, limit - len(bucket))

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response

    @staticmethod
    def _rule(request: Request) -> tuple[int, int, str] | None:
        if request.method not in {"POST", "PUT", "PATCH"}:
            return None
        path = request.url.path
        if path == "/api/pilot/register":
            return (_env_int("SRIS_RATE_LIMIT_SIGNUP_PER_15M", 8), 900, "signup")
        if path == "/api/pilot/password-reset/request":
            return (_env_int("SRIS_RATE_LIMIT_PASSWORD_RESET_PER_15M", 6), 900, "password-reset")
        if path.startswith("/api/pilot/ai") or path.startswith("/api/pilot/intelligence"):
            return (_env_int("SRIS_RATE_LIMIT_AI_PER_MINUTE", 20), 60, "ai")
        return None
