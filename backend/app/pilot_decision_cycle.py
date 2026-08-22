from __future__ import annotations

from datetime import date
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.atlas_platform.auth import current_user
from app.atlas_platform.database import get_db
from app.atlas_platform.models import Membership, User

router = APIRouter(prefix="/api/pilot/decision-cycles", tags=["pilot-decision-cycle"])


class DecisionCycleCreate(BaseModel):
    mission_code: str = Field(min_length=1, max_length=80)
    decision: str = Field(min_length=2, max_length=5000)
    action: str | None = Field(default=None, max_length=5000)
    owner: str | None = Field(default=None, max_length=200)
    due_date: date | None = None
    expected_outcome: str | None = Field(default=None, max_length=5000)
    evidence_node_id: str | None = Field(default=None, max_length=64)


class DecisionCycleUpdate(BaseModel):
    action: str | None = Field(default=None, max_length=5000)
    owner: str | None = Field(default=None, max_length=200)
    due_date: date | None = None
    status: str | None = Field(default=None, pattern="^(proposed|committed|in_progress|completed|abandoned)$")
    expected_outcome: str | None = Field(default=None, max_length=5000)
    actual_outcome: str | None = Field(default=None, max_length=8000)
    learning: str | None = Field(default=None, max_length=8000)


def _membership(db: Session, user_id: str) -> Membership:
    membership = (
        db.query(Membership)
        .filter(Membership.user_id == user_id)
        .order_by(Membership.created_at.asc())
        .first()
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="A conta não tem um workspace associado.")
    return membership


def _ensure_schema(db: Session) -> None:
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS pilot_decision_cycles (
            id VARCHAR(64) PRIMARY KEY,
            organization_id VARCHAR(64) NOT NULL,
            mission_code VARCHAR(80) NOT NULL,
            decision TEXT NOT NULL,
            action TEXT NULL,
            owner VARCHAR(200) NULL,
            due_date DATE NULL,
            status VARCHAR(40) NOT NULL DEFAULT 'proposed',
            expected_outcome TEXT NULL,
            actual_outcome TEXT NULL,
            learning TEXT NULL,
            evidence_node_id VARCHAR(64) NULL,
            created_by_user_id VARCHAR(64) NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_pilot_decision_cycles_org_mission
        ON pilot_decision_cycles (organization_id, mission_code, created_at)
    """))


def _row(row) -> dict:
    return {
        "id": row["id"],
        "mission_code": row["mission_code"],
        "decision": row["decision"],
        "action": row["action"],
        "owner": row["owner"],
        "due_date": row["due_date"].isoformat() if row["due_date"] else None,
        "status": row["status"],
        "expected_outcome": row["expected_outcome"],
        "actual_outcome": row["actual_outcome"],
        "learning": row["learning"],
        "evidence_node_id": row["evidence_node_id"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


@router.get("/missions/{mission_code}")
def list_cycles(mission_code: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    membership = _membership(db, user.id)
    _ensure_schema(db)
    rows = db.execute(text("""
        SELECT * FROM pilot_decision_cycles
        WHERE organization_id=:org AND mission_code=:mission
        ORDER BY created_at DESC
    """), {"org": membership.organization_id, "mission": mission_code}).mappings().all()
    db.commit()
    return [_row(r) for r in rows]


@router.post("", status_code=201)
def create_cycle(payload: DecisionCycleCreate, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    membership = _membership(db, user.id)
    _ensure_schema(db)
    cycle_id = str(uuid4())
    db.execute(text("""
        INSERT INTO pilot_decision_cycles
        (id, organization_id, mission_code, decision, action, owner, due_date, status,
         expected_outcome, evidence_node_id, created_by_user_id)
        VALUES (:id,:org,:mission,:decision,:action,:owner,:due,'proposed',:expected,:node,:user)
    """), {
        "id": cycle_id, "org": membership.organization_id, "mission": payload.mission_code,
        "decision": payload.decision, "action": payload.action, "owner": payload.owner,
        "due": payload.due_date, "expected": payload.expected_outcome,
        "node": payload.evidence_node_id, "user": user.id,
    })
    db.commit()
    row = db.execute(text("SELECT * FROM pilot_decision_cycles WHERE id=:id"), {"id": cycle_id}).mappings().one()
    return _row(row)


@router.patch("/{cycle_id}")
def update_cycle(cycle_id: str, payload: DecisionCycleUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    membership = _membership(db, user.id)
    _ensure_schema(db)
    current = db.execute(text("""
        SELECT * FROM pilot_decision_cycles WHERE id=:id AND organization_id=:org
    """), {"id": cycle_id, "org": membership.organization_id}).mappings().first()
    if current is None:
        raise HTTPException(status_code=404, detail="Ciclo de decisão não encontrado.")
    values = payload.model_dump(exclude_unset=True)
    if not values:
        return _row(current)
    allowed = {"action", "owner", "due_date", "status", "expected_outcome", "actual_outcome", "learning"}
    parts=[];params={"id": cycle_id, "org": membership.organization_id}
    for key,value in values.items():
        if key not in allowed:
            continue
        parts.append(f"{key}=:{key}")
        params[key]=value
    parts.append("updated_at=CURRENT_TIMESTAMP")
    db.execute(text(f"UPDATE pilot_decision_cycles SET {', '.join(parts)} WHERE id=:id AND organization_id=:org"), params)
    db.commit()
    row = db.execute(text("SELECT * FROM pilot_decision_cycles WHERE id=:id"), {"id": cycle_id}).mappings().one()
    return _row(row)
