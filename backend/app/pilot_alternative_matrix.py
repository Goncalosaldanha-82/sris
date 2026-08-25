from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StrictInt, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.atlas_platform.auth import current_user
from app.atlas_platform.audit import record_audit
from app.atlas_platform.database import get_db
from app.atlas_platform.models import Membership, Role, User
from app.evidence_graph import (
    _ensure_schema as _ensure_graph_schema,
    _membership,
    _mission,
    _upsert_node,
)
from app.pilot_serialization import as_iso


router = APIRouter(
    prefix="/api/pilot/alternative-matrices",
    tags=["pilot-alternative-matrix"],
)

WRITER_ROLES = {
    Role.OWNER.value,
    Role.ADMIN.value,
    Role.REVIEWER.value,
    Role.CONTRIBUTOR.value,
}
REVIEWER_ROLES = {
    Role.OWNER.value,
    Role.ADMIN.value,
    Role.REVIEWER.value,
}

CriterionKey = Literal[
    "efficacy",
    "cost",
    "risk",
    "reversibility",
    "guest_experience",
    "evidence_robustness",
]

CRITERIA: list[dict] = [
    {
        "key": "efficacy",
        "label": "Eficácia",
        "description": "Capacidade esperada para produzir o resultado definido.",
        "scale_hint": "1 = eficácia muito baixa · 5 = eficácia muito alta",
    },
    {
        "key": "cost",
        "label": "Custo",
        "description": "Custo total de adoção, operação e manutenção.",
        "scale_hint": "1 = custo muito elevado · 5 = custo muito favorável",
    },
    {
        "key": "risk",
        "label": "Risco",
        "description": "Exposição operacional, financeira, legal e reputacional.",
        "scale_hint": "1 = risco muito elevado · 5 = risco muito controlado",
    },
    {
        "key": "reversibility",
        "label": "Reversibilidade",
        "description": "Facilidade de interromper, corrigir ou reverter a alternativa.",
        "scale_hint": "1 = dificilmente reversível · 5 = facilmente reversível",
    },
    {
        "key": "guest_experience",
        "label": "Experiência do hóspede",
        "description": "Efeito previsível no conforto, confiança e qualidade percebida.",
        "scale_hint": "1 = impacto muito negativo · 5 = impacto muito positivo",
    },
    {
        "key": "evidence_robustness",
        "label": "Robustez da evidência",
        "description": "Qualidade, proveniência e suficiência da evidência disponível.",
        "scale_hint": "1 = evidência muito frágil · 5 = evidência muito robusta",
    },
]
CRITERION_KEYS = tuple(item["key"] for item in CRITERIA)
DEFAULT_WEIGHTS = {
    "efficacy": 25,
    "cost": 15,
    "risk": 15,
    "reversibility": 10,
    "guest_experience": 20,
    "evidence_robustness": 15,
}


class CriterionAssessment(BaseModel):
    criterion: CriterionKey
    score: StrictInt = Field(ge=1, le=5)
    rationale: str = Field(min_length=2, max_length=3000)
    evidence_node_id: str | None = Field(default=None, min_length=8, max_length=64)


class AlternativeAssessment(BaseModel):
    alternative_node_id: str = Field(min_length=8, max_length=64)
    scores: list[CriterionAssessment] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def validate_criteria(self):
        keys = [score.criterion for score in self.scores]
        if len(set(keys)) != len(keys) or set(keys) != set(CRITERION_KEYS):
            raise ValueError("Cada alternativa deve avaliar uma vez os seis critérios canónicos.")
        return self


class MatrixSave(BaseModel):
    weights: dict[str, StrictInt]
    evaluations: list[AlternativeAssessment] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_matrix(self):
        if set(self.weights) != set(CRITERION_KEYS):
            raise ValueError("Os pesos devem abranger exatamente os seis critérios canónicos.")
        if any(not isinstance(value, int) or value < 0 or value > 100 for value in self.weights.values()):
            raise ValueError("Cada peso deve ser um número inteiro entre 0 e 100.")
        if sum(self.weights.values()) != 100:
            raise ValueError("A soma dos pesos deve ser exatamente 100%.")
        alternative_ids = [item.alternative_node_id for item in self.evaluations]
        if len(set(alternative_ids)) != len(alternative_ids):
            raise ValueError("Cada alternativa só pode aparecer uma vez na matriz.")
        return self


class AlternativeCreate(BaseModel):
    title: str = Field(min_length=3, max_length=500)
    body: str = Field(min_length=5, max_length=6000)

    @model_validator(mode="after")
    def normalize_text(self):
        self.title = " ".join(self.title.split())
        self.body = " ".join(self.body.split())
        if len(self.title) < 3 or len(self.body) < 5:
            raise ValueError("Indique um título e uma descrição material para a alternativa.")
        return self


def _require_membership(db: Session, user_id: str) -> Membership:
    membership = _membership(db, user_id)
    if membership is None:
        raise HTTPException(status_code=403, detail="A conta não tem um workspace associado.")
    return membership


def _require_writer(membership: Membership) -> None:
    if membership.role not in WRITER_ROLES:
        raise HTTPException(status_code=403, detail="A sua função permite consultar, mas não alterar a matriz.")


def _require_reviewer(membership: Membership) -> None:
    if membership.role not in REVIEWER_ROLES:
        raise HTTPException(status_code=403, detail="A revisão da matriz exige a função de revisor ou administrador.")


def _ensure_schema(db: Session) -> None:
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS pilot_alternative_matrices (
            id VARCHAR(64) PRIMARY KEY,
            organization_id VARCHAR(64) NOT NULL,
            mission_id VARCHAR(64) NOT NULL,
            mission_code VARCHAR(80) NOT NULL,
            revision INTEGER NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'draft',
            weights_json TEXT NOT NULL,
            snapshot_json TEXT NOT NULL,
            content_hash VARCHAR(64) NOT NULL,
            created_by_user_id VARCHAR(64) NULL,
            reviewed_by_user_id VARCHAR(64) NULL,
            reviewed_at TIMESTAMP NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (organization_id, mission_id, revision)
        )
    """))
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_pilot_alt_matrix_org_mission
        ON pilot_alternative_matrices (organization_id, mission_id, revision)
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS pilot_alternative_matrix_scores (
            id VARCHAR(64) PRIMARY KEY,
            matrix_id VARCHAR(64) NOT NULL,
            organization_id VARCHAR(64) NOT NULL,
            mission_id VARCHAR(64) NOT NULL,
            alternative_node_id VARCHAR(64) NOT NULL,
            criterion VARCHAR(50) NOT NULL,
            score INTEGER NOT NULL CHECK (score >= 1 AND score <= 5),
            rationale TEXT NOT NULL,
            evidence_node_id VARCHAR(64) NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (matrix_id, alternative_node_id, criterion)
        )
    """))
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_pilot_alt_matrix_scores_matrix
        ON pilot_alternative_matrix_scores (matrix_id, alternative_node_id, criterion)
    """))


def _json_loads(raw: str | None, fallback: dict | list) -> dict | list:
    try:
        value = json.loads(raw or "")
    except (TypeError, ValueError):
        return fallback
    return value if isinstance(value, type(fallback)) else fallback


def _stored_weights(raw: str | None) -> dict[str, int]:
    """Read persisted weights without allowing a damaged revision to raise 500."""

    parsed = _json_loads(raw, {})
    if (
        not isinstance(parsed, dict)
        or set(parsed) != set(CRITERION_KEYS)
        or any(not isinstance(value, int) or isinstance(value, bool) for value in parsed.values())
    ):
        return {key: 0 for key in CRITERION_KEYS}
    return {key: parsed[key] for key in CRITERION_KEYS}


def _weights_valid(weights: dict[str, int]) -> bool:
    """Keep corrupted or manually altered revisions out of readiness/ranking."""

    return bool(
        set(weights) == set(CRITERION_KEYS)
        and all(
            isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100
            for value in weights.values()
        )
        and sum(weights.values()) == 100
    )


def _active_nodes(db: Session, *, organization_id: str, mission_id: str, node_type: str) -> list[dict]:
    rows = db.execute(
        text("""
            SELECT node.id, node.label, node.body, node.status, node.source_kind,
                   node.source_id, node.source_sha256, node.created_at,
                   (SELECT COUNT(*) FROM pilot_evidence_graph_edges edge
                    WHERE edge.organization_id=node.organization_id
                      AND edge.mission_id=node.mission_id
                      AND (edge.from_node_id=node.id OR edge.to_node_id=node.id))
                   +
                   (SELECT COUNT(*) FROM pilot_alternative_matrix_scores score
                    WHERE score.organization_id=node.organization_id
                      AND score.mission_id=node.mission_id
                      AND score.alternative_node_id=node.id) AS reference_count
            FROM pilot_evidence_graph_nodes node
            WHERE node.organization_id=:org AND node.mission_id=:mission
              AND node.node_type=:node_type
              AND node.status NOT IN ('rejected', 'superseded')
            ORDER BY node.created_at ASC, node.label ASC, node.id ASC
        """),
        {"org": organization_id, "mission": mission_id, "node_type": node_type},
    ).mappings().all()
    return [dict(row) for row in rows]


def _alternative_identity(label: str | None, body: str | None) -> tuple[str, str]:
    return (
        " ".join(str(label or "").split()).casefold(),
        " ".join(str(body or "").split()).casefold(),
    )


def _mark_duplicates(alternatives: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = {}
    for alternative in alternatives:
        groups.setdefault(
            _alternative_identity(alternative.get("label"), alternative.get("body")),
            [],
        ).append(alternative)
    retained_by_identity = {
        identity: sorted(
            items,
            key=lambda item: (
                -int(item.get("reference_count") or 0),
                str(item.get("created_at") or ""),
                str(item["id"]),
            ),
        )[0]["id"]
        for identity, items in groups.items()
    }
    marked: list[dict] = []
    for alternative in alternatives:
        item = dict(alternative)
        identity = _alternative_identity(item.get("label"), item.get("body"))
        retained_id = str(retained_by_identity[identity])
        item["duplicate_of_id"] = retained_id if str(item["id"]) != retained_id else None
        marked.append(item)
    return marked


def _latest_matrix_row(db: Session, *, organization_id: str, mission_id: str):
    return db.execute(
        text("""
            SELECT * FROM pilot_alternative_matrices
            WHERE organization_id=:org AND mission_id=:mission
            ORDER BY revision DESC LIMIT 1
        """),
        {"org": organization_id, "mission": mission_id},
    ).mappings().first()


def _score_rows(db: Session, matrix_id: str) -> list[dict]:
    rows = db.execute(
        text("""
            SELECT score.*, alternative.label AS alternative_label,
                   alternative.body AS alternative_body,
                   evidence.label AS evidence_label
            FROM pilot_alternative_matrix_scores score
            LEFT JOIN pilot_evidence_graph_nodes alternative
              ON alternative.id=score.alternative_node_id
             AND alternative.organization_id=score.organization_id
             AND alternative.mission_id=score.mission_id
            LEFT JOIN pilot_evidence_graph_nodes evidence
              ON evidence.id=score.evidence_node_id
             AND evidence.organization_id=score.organization_id
             AND evidence.mission_id=score.mission_id
            WHERE score.matrix_id=:matrix
            ORDER BY alternative.label ASC, score.criterion ASC
        """),
        {"matrix": matrix_id},
    ).mappings().all()
    return [dict(row) for row in rows]


def _weighted_score(scores: dict[str, int], weights: dict[str, int]) -> float:
    return round(sum(scores[key] * weights[key] for key in CRITERION_KEYS) / 5, 1)


def _canonical_snapshot_scores(snapshot: dict) -> list[dict] | None:
    try:
        evaluations = snapshot["evaluations"]
        if not isinstance(evaluations, list):
            return None
        canonical = [
            {
                "alternative_node_id": str(evaluation["alternative_node_id"]),
                "criterion": str(score["criterion"]),
                "score": int(score["score"]),
                "rationale": str(score["rationale"]).strip(),
                "evidence_node_id": (
                    str(score["evidence_node_id"])
                    if score.get("evidence_node_id")
                    else None
                ),
            }
            for evaluation in evaluations
            if isinstance(evaluation, dict)
            for score in evaluation["scores"]
            if isinstance(score, dict)
        ]
    except (KeyError, TypeError, ValueError):
        return None
    return sorted(
        canonical,
        key=lambda item: (item["alternative_node_id"], item["criterion"]),
    )


def _canonical_stored_scores(scores: list[dict]) -> list[dict] | None:
    try:
        canonical = [
            {
                "alternative_node_id": str(score["alternative_node_id"]),
                "criterion": str(score["criterion"]),
                "score": int(score["score"]),
                "rationale": str(score["rationale"]).strip(),
                "evidence_node_id": (
                    str(score["evidence_node_id"])
                    if score.get("evidence_node_id")
                    else None
                ),
            }
            for score in scores
        ]
    except (KeyError, TypeError, ValueError):
        return None
    return sorted(
        canonical,
        key=lambda item: (item["alternative_node_id"], item["criterion"]),
    )


def _matrix_integrity(row, snapshot: dict, weights: dict[str, int], scores: list[dict]) -> bool:
    snapshot_hash_valid = hashlib.sha256(
        str(row["snapshot_json"]).encode("utf-8")
    ).hexdigest() == row["content_hash"]
    if not snapshot_hash_valid:
        return False
    try:
        if set(snapshot["weights"]) != set(CRITERION_KEYS):
            return False
        snapshot_weights = {
            key: int(snapshot["weights"][key])
            for key in CRITERION_KEYS
        }
        snapshot_identity_valid = (
            str(snapshot["mission_id"]) == str(row["mission_id"])
            and str(snapshot["mission_code"]) == str(row["mission_code"])
            and int(snapshot["revision"]) == int(row["revision"])
        )
    except (KeyError, TypeError, ValueError):
        return False
    return bool(
        snapshot_identity_valid
        and _weights_valid(weights)
        and snapshot_weights == weights
        and _canonical_snapshot_scores(snapshot) == _canonical_stored_scores(scores)
    )


def _matrix_view(db: Session, row) -> dict | None:
    if row is None:
        return None
    weights = _stored_weights(row["weights_json"])
    snapshot = _json_loads(row["snapshot_json"], {})
    snapshot_evaluations = {
        str(item.get("alternative_node_id")): item
        for item in snapshot.get("evaluations", [])
        if isinstance(item, dict) and item.get("alternative_node_id")
    }
    score_rows = _score_rows(db, str(row["id"]))
    grouped: dict[str, dict] = {}
    for score in score_rows:
        alternative_id = str(score["alternative_node_id"])
        snapshot_evaluation = snapshot_evaluations.get(alternative_id, {})
        snapshot_scores = {
            str(item.get("criterion")): item
            for item in snapshot_evaluation.get("scores", [])
            if isinstance(item, dict) and item.get("criterion")
        }
        snapshot_score = snapshot_scores.get(str(score["criterion"]), {})
        item = grouped.setdefault(
            alternative_id,
            {
                "alternative_node_id": alternative_id,
                "alternative_label": snapshot_evaluation.get("alternative_label")
                or score.get("alternative_label")
                or f"Alternativa {alternative_id[:8]}",
                "alternative_body": snapshot_evaluation.get("alternative_body")
                or score.get("alternative_body")
                or "",
                "scores": [],
            },
        )
        item["scores"].append(
            {
                "criterion": score["criterion"],
                "score": int(score["score"]),
                "rationale": score["rationale"],
                "evidence_node_id": score["evidence_node_id"],
                "evidence_label": snapshot_score.get("evidence_label") or score.get("evidence_label"),
            }
        )
    evaluations = list(grouped.values())
    for evaluation in evaluations:
        score_map = {item["criterion"]: int(item["score"]) for item in evaluation["scores"]}
        evaluation["weighted_score"] = (
            _weighted_score(score_map, weights)
            if set(score_map) == set(CRITERION_KEYS)
            else None
        )
    evaluations.sort(
        key=lambda item: (
            -(item["weighted_score"] if item["weighted_score"] is not None else -1),
            item["alternative_label"].casefold(),
            item["alternative_node_id"],
        )
    )
    return {
        "id": row["id"],
        "mission_code": row["mission_code"],
        "revision": int(row["revision"]),
        "status": row["status"],
        "weights": weights,
        "content_hash": row["content_hash"],
        "snapshot_version": int(snapshot.get("snapshot_version") or 1),
        "integrity_verified": _matrix_integrity(row, snapshot, weights, score_rows),
        "created_by_user_id": row["created_by_user_id"],
        "reviewed_by_user_id": row["reviewed_by_user_id"],
        "reviewed_at": as_iso(row["reviewed_at"]),
        "created_at": as_iso(row["created_at"]),
        "evaluations": evaluations,
    }


def _ranking(matrix: dict | None) -> list[dict]:
    if matrix is None or not matrix["integrity_verified"] or not _weights_valid(matrix["weights"]):
        return []
    ranked: list[dict] = []
    for evaluation in matrix["evaluations"]:
        score_map = {item["criterion"]: item["score"] for item in evaluation["scores"]}
        if set(score_map) != set(CRITERION_KEYS):
            continue
        ranked.append(
            {
                "alternative_node_id": evaluation["alternative_node_id"],
                "alternative_label": evaluation["alternative_label"],
                "weighted_score": evaluation["weighted_score"],
                "scores": score_map,
            }
        )
    ranked.sort(
        key=lambda item: (
            -item["weighted_score"],
            -item["scores"]["evidence_robustness"],
            -item["scores"]["efficacy"],
            item["alternative_label"].casefold(),
            item["alternative_node_id"],
        )
    )
    for position, item in enumerate(ranked, start=1):
        item["position"] = position
    return ranked


def matrix_readiness(
    db: Session,
    *,
    organization_id: str,
    mission_id: str,
) -> dict:
    """Read readiness from the latest immutable comparison revision."""

    _ensure_schema(db)
    row = _latest_matrix_row(db, organization_id=organization_id, mission_id=mission_id)
    if row is None:
        return {
            "passed": False,
            "count": 0,
            "matrix_id": None,
            "revision": None,
            "status": None,
            "integrity_verified": False,
        }
    matrix = _matrix_view(db, row)
    assert matrix is not None
    weights_valid = _weights_valid(matrix["weights"])
    complete = 0
    active_alternatives = {
        item["id"]
        for item in _active_nodes(
            db,
            organization_id=organization_id,
            mission_id=mission_id,
            node_type="alternative",
        )
    }
    for evaluation in matrix["evaluations"]:
        score_keys = {item["criterion"] for item in evaluation["scores"] if str(item["rationale"] or "").strip()}
        if evaluation["alternative_node_id"] in active_alternatives and score_keys == set(CRITERION_KEYS):
            complete += 1
    return {
        "passed": matrix["integrity_verified"] and weights_valid and complete >= 2,
        "count": complete,
        "matrix_id": matrix["id"],
        "revision": matrix["revision"],
        "status": matrix["status"],
        "integrity_verified": matrix["integrity_verified"],
    }


def _history(db: Session, *, organization_id: str, mission_id: str) -> list[dict]:
    rows = db.execute(
        text("""
            SELECT matrix.*, COUNT(DISTINCT score.alternative_node_id) AS alternative_count
            FROM pilot_alternative_matrices matrix
            LEFT JOIN pilot_alternative_matrix_scores score ON score.matrix_id=matrix.id
            WHERE matrix.organization_id=:org AND matrix.mission_id=:mission
            GROUP BY matrix.id, matrix.organization_id, matrix.mission_id, matrix.mission_code,
                     matrix.revision, matrix.status, matrix.weights_json, matrix.snapshot_json,
                     matrix.content_hash,
                     matrix.created_by_user_id, matrix.reviewed_by_user_id, matrix.reviewed_at,
                     matrix.created_at
            ORDER BY matrix.revision DESC
        """),
        {"org": organization_id, "mission": mission_id},
    ).mappings().all()
    history: list[dict] = []
    for row in rows:
        matrix = _matrix_view(db, row)
        history.append(
            {
                "id": row["id"],
                "revision": int(row["revision"]),
                "status": row["status"],
                "content_hash": row["content_hash"],
                "integrity_verified": bool(matrix and matrix["integrity_verified"]),
                "alternative_count": int(row["alternative_count"] or 0),
                "created_by_user_id": row["created_by_user_id"],
                "reviewed_by_user_id": row["reviewed_by_user_id"],
                "reviewed_at": as_iso(row["reviewed_at"]),
                "created_at": as_iso(row["created_at"]),
            }
        )
    return history


def _response(db: Session, *, organization_id: str, mission) -> dict:
    latest = _latest_matrix_row(db, organization_id=organization_id, mission_id=mission.id)
    matrix = _matrix_view(db, latest)
    alternatives = _mark_duplicates(
        _active_nodes(
            db,
            organization_id=organization_id,
            mission_id=mission.id,
            node_type="alternative",
        )
    )
    evidence = _active_nodes(
        db,
        organization_id=organization_id,
        mission_id=mission.id,
        node_type="evidence",
    )
    return {
        "mission_id": mission.id,
        "mission_code": mission.code,
        "criteria": CRITERIA,
        "default_weights": DEFAULT_WEIGHTS,
        "alternatives": alternatives,
        "evidence": evidence,
        "matrix": matrix,
        "ranking": _ranking(matrix),
        "readiness": matrix_readiness(
            db,
            organization_id=organization_id,
            mission_id=mission.id,
        ),
        "history": _history(db, organization_id=organization_id, mission_id=mission.id),
        "calculation": {
            "formula": "sum(score × weight) / 5",
            "score_range": [1, 5],
            "result_range": [20, 100],
            "tie_break": ["robustez da evidência", "eficácia", "título da alternativa"],
            "decision_policy": "A ordenação informa a revisão humana e nunca seleciona automaticamente uma decisão.",
        },
    }


@router.post("/missions/{mission_code}/alternatives")
def add_alternative(
    mission_code: str,
    payload: AlternativeCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _require_membership(db, user.id)
    _require_writer(membership)
    _ensure_graph_schema(db)
    _ensure_schema(db)
    mission = _mission(db, membership.organization_id, mission_code)
    active = _active_nodes(
        db,
        organization_id=membership.organization_id,
        mission_id=mission.id,
        node_type="alternative",
    )
    identity = _alternative_identity(payload.title, payload.body)
    existing = next(
        (
            item
            for item in active
            if _alternative_identity(item.get("label"), item.get("body")) == identity
        ),
        None,
    )
    if existing is not None:
        response = _response(db, organization_id=membership.organization_id, mission=mission)
        response["alternative_change"] = {
            "created": False,
            "alternative_id": existing["id"],
            "reason": "exact_duplicate",
        }
        db.commit()
        return response

    node_id = _upsert_node(
        db,
        organization_id=membership.organization_id,
        mission=mission,
        node_type="alternative",
        label=payload.title,
        body=payload.body,
        status="proposed",
        confidence=None,
        source_kind="human_entry",
        source_id=f"matrix-human:{uuid4()}",
        attachment_id=None,
        char_start=None,
        char_end=None,
        source_sha256=None,
        provenance={"human_authored": True, "entry_point": "alternative_matrix"},
        user_id=user.id,
    )
    record_audit(
        db,
        action="pilot.alternative.created",
        resource_type="evidence_graph_node",
        resource_id=node_id,
        organization_id=membership.organization_id,
        user_id=user.id,
        payload={"mission_code": mission.code, "entry_point": "alternative_matrix"},
    )
    db.commit()
    response = _response(db, organization_id=membership.organization_id, mission=mission)
    response["alternative_change"] = {
        "created": True,
        "alternative_id": node_id,
        "reason": None,
    }
    return response


@router.delete("/missions/{mission_code}/alternatives/{alternative_node_id}/duplicate")
def retire_duplicate_alternative(
    mission_code: str,
    alternative_node_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _require_membership(db, user.id)
    _require_writer(membership)
    _ensure_graph_schema(db)
    _ensure_schema(db)
    mission = _mission(db, membership.organization_id, mission_code)
    alternatives = _active_nodes(
        db,
        organization_id=membership.organization_id,
        mission_id=mission.id,
        node_type="alternative",
    )
    target = next((item for item in alternatives if item["id"] == alternative_node_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="A alternativa indicada não está ativa nesta missão.")
    identity = _alternative_identity(target.get("label"), target.get("body"))
    identical = [
        item
        for item in alternatives
        if _alternative_identity(item.get("label"), item.get("body")) == identity
    ]
    if len(identical) < 2:
        raise HTTPException(
            status_code=409,
            detail="Esta alternativa é única e não pode ser retirada como duplicado.",
        )
    retained = sorted(
        identical,
        key=lambda item: (
            -int(item.get("reference_count") or 0),
            str(item.get("created_at") or ""),
            str(item["id"]),
        ),
    )[0]
    if retained["id"] == alternative_node_id:
        raise HTTPException(
            status_code=409,
            detail="Retire a cópia mais recente para preservar a alternativa original.",
        )
    db.execute(
        text("""
            UPDATE pilot_evidence_graph_nodes
            SET status='superseded', updated_at=CURRENT_TIMESTAMP
            WHERE id=:id AND organization_id=:org AND mission_id=:mission
        """),
        {
            "id": alternative_node_id,
            "org": membership.organization_id,
            "mission": mission.id,
        },
    )
    record_audit(
        db,
        action="pilot.alternative.duplicate_retired",
        resource_type="evidence_graph_node",
        resource_id=alternative_node_id,
        organization_id=membership.organization_id,
        user_id=user.id,
        payload={
            "mission_code": mission.code,
            "retained_alternative_id": retained["id"],
            "label": target["label"],
            "retirement_status": "superseded",
        },
    )
    db.commit()
    response = _response(db, organization_id=membership.organization_id, mission=mission)
    response["alternative_change"] = {
        "retired": True,
        "alternative_id": alternative_node_id,
        "retained_alternative_id": retained["id"],
    }
    return response


@router.get("/missions/{mission_code}")
def get_matrix(
    mission_code: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _require_membership(db, user.id)
    _ensure_graph_schema(db)
    _ensure_schema(db)
    mission = _mission(db, membership.organization_id, mission_code)
    response = _response(db, organization_id=membership.organization_id, mission=mission)
    db.commit()
    return response


@router.put("/missions/{mission_code}")
def save_matrix(
    mission_code: str,
    payload: MatrixSave,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _require_membership(db, user.id)
    _require_writer(membership)
    _ensure_graph_schema(db)
    _ensure_schema(db)
    mission = _mission(db, membership.organization_id, mission_code)

    active_alternatives = {
        item["id"]: item
        for item in _active_nodes(
            db,
            organization_id=membership.organization_id,
            mission_id=mission.id,
            node_type="alternative",
        )
    }
    unknown_alternatives = [
        item.alternative_node_id
        for item in payload.evaluations
        if item.alternative_node_id not in active_alternatives
    ]
    if unknown_alternatives:
        raise HTTPException(status_code=422, detail="A matriz contém alternativas que já não estão ativas nesta missão.")

    active_evidence = {
        item["id"]: item
        for item in _active_nodes(
            db,
            organization_id=membership.organization_id,
            mission_id=mission.id,
            node_type="evidence",
        )
    }
    for evaluation in payload.evaluations:
        for score in evaluation.scores:
            if score.evidence_node_id and score.evidence_node_id not in active_evidence:
                raise HTTPException(status_code=422, detail="Uma avaliação refere evidência indisponível nesta missão.")

    revision = int(
        db.execute(
            text("""
                SELECT COALESCE(MAX(revision), 0) + 1
                FROM pilot_alternative_matrices
                WHERE organization_id=:org AND mission_id=:mission
            """),
            {"org": membership.organization_id, "mission": mission.id},
        ).scalar()
        or 1
    )
    snapshot = {
        "snapshot_version": 1,
        "mission_id": mission.id,
        "mission_code": mission.code,
        "revision": revision,
        "weights": {key: payload.weights[key] for key in CRITERION_KEYS},
        "evaluations": [
            {
                "alternative_node_id": evaluation.alternative_node_id,
                "alternative_label": active_alternatives[evaluation.alternative_node_id]["label"],
                "alternative_body": active_alternatives[evaluation.alternative_node_id]["body"],
                "scores": [
                    {
                        "criterion": score.criterion,
                        "score": score.score,
                        "rationale": score.rationale.strip(),
                        "evidence_node_id": score.evidence_node_id,
                        "evidence_label": (
                            active_evidence[score.evidence_node_id]["label"]
                            if score.evidence_node_id
                            else None
                        ),
                    }
                    for score in sorted(evaluation.scores, key=lambda item: item.criterion)
                ],
            }
            for evaluation in sorted(payload.evaluations, key=lambda item: item.alternative_node_id)
        ],
    }
    snapshot_json = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    content_hash = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
    matrix_id = str(uuid4())
    db.execute(
        text("""
            INSERT INTO pilot_alternative_matrices
            (id, organization_id, mission_id, mission_code, revision, status,
             weights_json, snapshot_json, content_hash, created_by_user_id)
            VALUES (:id, :org, :mission, :code, :revision, 'draft',
                    :weights, :snapshot, :content_hash, :user)
        """),
        {
            "id": matrix_id,
            "org": membership.organization_id,
            "mission": mission.id,
            "code": mission.code,
            "revision": revision,
            "weights": json.dumps(payload.weights, ensure_ascii=False, sort_keys=True),
            "snapshot": snapshot_json,
            "content_hash": content_hash,
            "user": user.id,
        },
    )
    for evaluation in payload.evaluations:
        for score in evaluation.scores:
            db.execute(
                text("""
                    INSERT INTO pilot_alternative_matrix_scores
                    (id, matrix_id, organization_id, mission_id, alternative_node_id,
                     criterion, score, rationale, evidence_node_id)
                    VALUES (:id, :matrix, :org, :mission, :alternative,
                            :criterion, :score, :rationale, :evidence)
                """),
                {
                    "id": str(uuid4()),
                    "matrix": matrix_id,
                    "org": membership.organization_id,
                    "mission": mission.id,
                    "alternative": evaluation.alternative_node_id,
                    "criterion": score.criterion,
                    "score": score.score,
                    "rationale": score.rationale.strip(),
                    "evidence": score.evidence_node_id,
                },
            )
    record_audit(
        db,
        action="pilot.alternative_matrix.revision_created",
        resource_type="alternative_matrix",
        resource_id=matrix_id,
        organization_id=membership.organization_id,
        user_id=user.id,
        payload={
            "mission_code": mission.code,
            "revision": revision,
            "content_hash": content_hash,
            "alternative_count": len(payload.evaluations),
        },
    )
    db.commit()
    return _response(db, organization_id=membership.organization_id, mission=mission)


@router.post("/missions/{mission_code}/review")
def review_matrix(
    mission_code: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    membership = _require_membership(db, user.id)
    _require_reviewer(membership)
    _ensure_graph_schema(db)
    _ensure_schema(db)
    mission = _mission(db, membership.organization_id, mission_code)
    latest = _latest_matrix_row(db, organization_id=membership.organization_id, mission_id=mission.id)
    if latest is None:
        raise HTTPException(status_code=409, detail="Guarde primeiro uma revisão completa da matriz.")
    if latest["status"] == "reviewed":
        raise HTTPException(status_code=409, detail="A revisão mais recente já foi validada por uma pessoa.")
    readiness = matrix_readiness(
        db,
        organization_id=membership.organization_id,
        mission_id=mission.id,
    )
    if not readiness["passed"]:
        raise HTTPException(status_code=409, detail="A revisão exige pelo menos duas alternativas avaliadas nos seis critérios.")
    now = datetime.now(timezone.utc)
    db.execute(
        text("""
            UPDATE pilot_alternative_matrices
            SET status='reviewed', reviewed_by_user_id=:user, reviewed_at=:reviewed_at
            WHERE id=:id AND organization_id=:org AND mission_id=:mission
        """),
        {
            "id": latest["id"],
            "org": membership.organization_id,
            "mission": mission.id,
            "user": user.id,
            "reviewed_at": now,
        },
    )
    record_audit(
        db,
        action="pilot.alternative_matrix.reviewed",
        resource_type="alternative_matrix",
        resource_id=latest["id"],
        organization_id=membership.organization_id,
        user_id=user.id,
        payload={
            "mission_code": mission.code,
            "revision": int(latest["revision"]),
            "content_hash": latest["content_hash"],
        },
    )
    db.commit()
    return _response(db, organization_id=membership.organization_id, mission=mission)
