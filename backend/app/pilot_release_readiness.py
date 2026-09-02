from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.atlas_platform.audit import record_audit
from app.atlas_platform.auth import current_user, require_org_role
from app.atlas_platform.auth_delivery import auth_email_delivery_ready
from app.atlas_platform.database import get_db
from app.atlas_platform.models import (
    AuditEvent,
    Membership,
    PilotReleaseAcceptance,
    Role,
    User,
)
from app.mission_intelligence.models import (
    AIOrganizationPolicy,
    AIUsageEvent,
    CanonicalMission,
)
from app.pilot_capabilities import PILOT_BUILD
from app.pilot_readiness import mission_completion_readiness


router = APIRouter(prefix="/api/pilot/release-readiness", tags=["pilot-release-readiness"])

MANUAL_CHECKS = {
    "identity_flow_accepted": (
        "Identidade multiutilizador testada",
        "Convite, ativação, recuperação e revogação confirmados com contas de teste.",
    ),
    "exports_accepted": (
        "Exportações verificadas",
        "Download, nome e conteúdo confirmados em dois browsers.",
    ),
    "mobile_ios_accepted": (
        "iPhone físico aceite",
        "Menus, formulários, uploads, tabelas, modais e downloads verificados num iPhone.",
    ),
    "mobile_android_accepted": (
        "Android físico aceite",
        "Menus, formulários, uploads, tabelas, modais e downloads verificados num Android.",
    ),
    "demo_data_reconciled": (
        "Dados demonstrativos reconciliados",
        "MIS-002 e contadores do portefólio não apresentam estados suspensos como válidos.",
    ),
    "regression_accepted": (
        "Regressão final e build congelado",
        "Bateria integral concluída depois de todos os restantes gates ficarem verdes.",
    ),
}

AUTOMATIC_LABELS = {
    "email_configured": (
        "Email transacional configurado",
        "Existe um único transporte seguro para convites e recuperação.",
    ),
    "ai_operational": (
        "IA operacional comprovada",
        "Runtime, política da organização e pelo menos uma resposta real do fornecedor estão confirmados.",
    ),
    "owner_password_rotated": (
        "Palavra-passe do proprietário rodada",
        "Existe um evento auditável de rotação da credencial proprietária.",
    ),
    "real_mission_completed": (
        "Missão real concluída",
        "Uma missão percorreu a cadeia governada até à aprendizagem publicada.",
    ),
}

CHECK_ORDER = [
    "email_configured",
    "identity_flow_accepted",
    "ai_operational",
    "exports_accepted",
    "mobile_ios_accepted",
    "mobile_android_accepted",
    "demo_data_reconciled",
    "owner_password_rotated",
    "real_mission_completed",
    "regression_accepted",
]


class AcceptanceUpdate(BaseModel):
    accepted: bool
    evidence: str = Field(min_length=10, max_length=4000)


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _ai_operational(db: Session, organization_id: str) -> bool:
    policy = (
        db.query(AIOrganizationPolicy)
        .filter(AIOrganizationPolicy.organization_id == organization_id)
        .one_or_none()
    )
    successful_event = (
        db.query(AIUsageEvent.id)
        .filter(
            AIUsageEvent.organization_id == organization_id,
            AIUsageEvent.status.in_(("completed", "completed_with_overage")),
            AIUsageEvent.provider_response_id.is_not(None),
            AIUsageEvent.provider_response_id != "",
        )
        .first()
    )
    return bool(
        os.getenv("OPENAI_API_KEY", "").strip()
        and _flag("SRIS_AI_ENABLED")
        and policy
        and policy.enabled
        and successful_event
    )


def _owner_password_rotated(db: Session, organization_id: str) -> bool:
    owner_ids = {
        row[0]
        for row in db.query(Membership.user_id)
        .filter(
            Membership.organization_id == organization_id,
            Membership.role == Role.OWNER.value,
        )
        .all()
    }
    if not owner_ids:
        return False
    return (
        db.query(AuditEvent.id)
        .filter(
            AuditEvent.organization_id == organization_id,
            AuditEvent.user_id.in_(owner_ids),
            AuditEvent.action == "user.password_reset_completed",
        )
        .first()
        is not None
    )


def _real_mission_completed(db: Session, organization_id: str) -> tuple[bool, str]:
    missions = (
        db.query(CanonicalMission)
        .filter(
            CanonicalMission.organization_id == organization_id,
            CanonicalMission.lifecycle_state.in_(("completed", "archived")),
        )
        .order_by(CanonicalMission.updated_at.desc())
        .all()
    )
    for mission in missions:
        readiness = mission_completion_readiness(
            db,
            organization_id=organization_id,
            mission_id=mission.id,
            mission_code=mission.code,
        )
        if readiness.get("ready"):
            return True, f"{mission.code} — {mission.title}"
    return False, ""


def _automatic_checks(db: Session, organization_id: str) -> dict[str, tuple[bool, str]]:
    mission_ready, mission_evidence = _real_mission_completed(db, organization_id)
    return {
        "email_configured": (auth_email_delivery_ready(), "Configuração do servidor validada."),
        "ai_operational": (_ai_operational(db, organization_id), "Existe uma resposta real registada no ledger de utilização."),
        "owner_password_rotated": (_owner_password_rotated(db, organization_id), "Evento de rotação encontrado na auditoria."),
        "real_mission_completed": (mission_ready, mission_evidence),
    }


def build_readiness_payload(
    db: Session,
    *,
    organization_id: str,
    role: str,
) -> dict:
    automatic = _automatic_checks(db, organization_id)
    manual_rows = {
        row.check_key: row
        for row in db.query(PilotReleaseAcceptance)
        .filter(
            PilotReleaseAcceptance.organization_id == organization_id,
            PilotReleaseAcceptance.build == PILOT_BUILD,
        )
        .all()
    }
    checks = []
    for key in CHECK_ORDER:
        if key in automatic:
            passed, evidence = automatic[key]
            label, description = AUTOMATIC_LABELS[key]
            checks.append({
                "key": key,
                "label": label,
                "description": description,
                "passed": bool(passed),
                "source": "automatic",
                "evidence": evidence if passed else "",
                "tested_at": None,
                "tested_by": None,
            })
            continue
        row = manual_rows.get(key)
        label, description = MANUAL_CHECKS[key]
        checks.append({
            "key": key,
            "label": label,
            "description": description,
            "passed": bool(row and row.accepted),
            "source": "human_acceptance",
            "evidence": row.evidence if row else "",
            "tested_at": row.tested_at if row else None,
            "tested_by": row.tested_by_user_id if row else None,
        })
    passed_count = sum(1 for check in checks if check["passed"])
    return {
        "build": PILOT_BUILD,
        "ready_for_external_test": passed_count == len(checks),
        "passed_count": passed_count,
        "total_count": len(checks),
        "can_manage": role in {Role.OWNER.value, Role.ADMIN.value},
        "checks": checks,
    }


@router.get("")
def release_readiness(
    organization_id: str,
    membership: Membership = Depends(
        require_org_role(
            Role.OWNER.value,
            Role.ADMIN.value,
            Role.REVIEWER.value,
            Role.CONTRIBUTOR.value,
            Role.OBSERVER.value,
        )
    ),
    db: Session = Depends(get_db),
) -> dict:
    return build_readiness_payload(db, organization_id=organization_id, role=membership.role)


@router.put("/checks/{check_key}")
def update_release_acceptance(
    check_key: str,
    payload: AcceptanceUpdate,
    organization_id: str,
    membership: Membership = Depends(require_org_role(Role.OWNER.value, Role.ADMIN.value)),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    if check_key not in MANUAL_CHECKS:
        raise HTTPException(status_code=404, detail="Gate de aceitação desconhecido")
    current = build_readiness_payload(db, organization_id=organization_id, role=membership.role)
    if check_key == "regression_accepted" and payload.accepted:
        pending = [
            check["label"]
            for check in current["checks"]
            if check["key"] != check_key and not check["passed"]
        ]
        if pending:
            raise HTTPException(
                status_code=409,
                detail="A regressão final só pode ser aceite depois dos restantes gates.",
            )
    row = (
        db.query(PilotReleaseAcceptance)
        .filter(
            PilotReleaseAcceptance.organization_id == organization_id,
            PilotReleaseAcceptance.build == PILOT_BUILD,
            PilotReleaseAcceptance.check_key == check_key,
        )
        .one_or_none()
    )
    if row is None:
        row = PilotReleaseAcceptance(
            organization_id=organization_id,
            build=PILOT_BUILD,
            check_key=check_key,
        )
        db.add(row)
    row.accepted = payload.accepted
    row.evidence = payload.evidence.strip()
    row.tested_by_user_id = user.id
    row.tested_at = datetime.now(timezone.utc)
    record_audit(
        db,
        action="pilot.release_acceptance_recorded",
        resource_type="pilot_release_gate",
        resource_id=check_key,
        organization_id=organization_id,
        user_id=user.id,
        payload={"build": PILOT_BUILD, "accepted": payload.accepted, "evidence": row.evidence},
    )
    db.commit()
    return build_readiness_payload(db, organization_id=organization_id, role=membership.role)
