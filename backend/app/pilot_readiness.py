from __future__ import annotations

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.evidence_graph import _ensure_schema as _ensure_graph_schema
from app.learning_lineage import _ensure_schema as _ensure_learning_schema
from app.mission_intelligence.models import MissionAttachment
from app.pilot_decision_cycle import _ensure_schema as _ensure_decision_schema
from app.pilot_validation import validation_readiness


def mission_completion_readiness(
    db: Session,
    *,
    organization_id: str,
    mission_id: str,
    mission_code: str,
) -> dict:
    """Return the governed pre-flight required to conclude a mission.

    A mission is only complete after its source material, reasoning, decision,
    observed result and reviewed learning are all durable and linked.  The
    checks deliberately use the persistent stores rather than UI state.
    """

    _ensure_graph_schema(db)
    _ensure_decision_schema(db)
    _ensure_learning_schema(db)

    ready_documents = (
        db.query(MissionAttachment)
        .filter(
            MissionAttachment.organization_id == organization_id,
            MissionAttachment.mission_id == mission_id,
            MissionAttachment.extraction_status.in_(("ready", "visual_ready", "provider_ready")),
        )
        .count()
    )

    node_rows = db.execute(
        text(
            """
            SELECT node_type, status, COUNT(*) AS total
            FROM pilot_evidence_graph_nodes
            WHERE organization_id=:org AND mission_id=:mission
              AND status NOT IN ('rejected', 'superseded')
            GROUP BY node_type, status
            """
        ),
        {"org": organization_id, "mission": mission_id},
    ).mappings().all()
    node_counts: dict[str, int] = {}
    reviewed_learning_ids: list[str] = []
    for row in node_rows:
        node_type = str(row["node_type"])
        node_counts[node_type] = node_counts.get(node_type, 0) + int(row["total"] or 0)

    reviewed_learning_rows = db.execute(
        text(
            """
            SELECT id FROM pilot_evidence_graph_nodes
            WHERE organization_id=:org AND mission_id=:mission
              AND node_type='learning' AND status IN ('accepted', 'verified')
            """
        ),
        {"org": organization_id, "mission": mission_id},
    ).scalars().all()
    reviewed_learning_ids = [str(value) for value in reviewed_learning_rows]

    documentary_evidence = int(
        db.execute(
            text(
                """
                SELECT COUNT(*) FROM pilot_evidence_graph_nodes
                WHERE organization_id=:org AND mission_id=:mission
                  AND node_type='evidence'
                  AND status NOT IN ('rejected', 'superseded')
                  AND source_kind IN ('document_chunk', 'visual_document')
                  AND attachment_id IS NOT NULL AND source_sha256 IS NOT NULL
                """
            ),
            {"org": organization_id, "mission": mission_id},
        ).scalar()
        or 0
    )
    linked_hypotheses = int(
        db.execute(
            text(
                """
                SELECT COUNT(DISTINCT hypothesis.id)
                FROM pilot_evidence_graph_edges edge
                JOIN pilot_evidence_graph_nodes evidence
                  ON evidence.id=edge.from_node_id
                JOIN pilot_evidence_graph_nodes hypothesis
                  ON hypothesis.id=edge.to_node_id
                WHERE edge.organization_id=:org AND edge.mission_id=:mission
                  AND evidence.node_type='evidence'
                  AND hypothesis.node_type='hypothesis'
                  AND evidence.status NOT IN ('rejected', 'superseded')
                  AND hypothesis.status NOT IN ('rejected', 'superseded')
                  AND TRIM(COALESCE(hypothesis.body, '')) <> ''
                  AND edge.edge_type IN ('supports', 'contradicts', 'informs', 'tests')
                """
            ),
            {"org": organization_id, "mission": mission_id},
        ).scalar()
        or 0
    )

    comparable_alternatives = int(
        db.execute(
            text(
                """
                SELECT COUNT(*) FROM pilot_evidence_graph_nodes
                WHERE organization_id=:org AND mission_id=:mission
                  AND node_type='alternative'
                  AND status NOT IN ('rejected', 'superseded')
                  AND TRIM(COALESCE(body, '')) <> ''
                """
            ),
            {"org": organization_id, "mission": mission_id},
        ).scalar()
        or 0
    )

    cycles = db.execute(
        text(
            """
            SELECT id, status, action, owner, due_date, expected_outcome,
                   evidence_node_id,
                   actual_outcome, learning
            FROM pilot_decision_cycles
            WHERE organization_id=:org AND mission_code=:mission
            """
        ),
        {"org": organization_id, "mission": mission_code},
    ).mappings().all()
    completed_cycles = [
        row
        for row in cycles
        if row["status"] == "completed"
        and str(row["evidence_node_id"] or "").strip()
        and str(row["action"] or "").strip()
        and str(row["owner"] or "").strip()
        and row["due_date"] is not None
        and str(row["expected_outcome"] or "").strip()
        and str(row["actual_outcome"] or "").strip()
        and str(row["learning"] or "").strip()
    ]

    published_learning = 0
    if reviewed_learning_ids:
        published_learning = int(
            db.execute(
                text(
                    """
                    SELECT COUNT(*) FROM pilot_learning_packets
                    WHERE organization_id=:org AND source_mission_id=:mission
                      AND source_learning_node_id IN :node_ids
                    """
                ).bindparams(bindparam("node_ids", expanding=True)),
                {
                    "org": organization_id,
                    "mission": mission_id,
                    "node_ids": reviewed_learning_ids,
                },
            ).scalar()
            or 0
        )

    checks = [
        {
            "key": "document_ready",
            "label": "Fonte recebida e preparada para revisão",
            "passed": ready_documents > 0,
            "count": ready_documents,
        },
        {
            "key": "evidence_structured",
            "label": "Evidência documental com fonte, posição e hash",
            "passed": documentary_evidence > 0,
            "count": documentary_evidence,
        },
        {
            "key": "hypothesis_explicit",
            "label": "Hipótese explicitamente ligada à evidência",
            "passed": linked_hypotheses > 0,
            "count": linked_hypotheses,
        },
        {
            "key": "alternatives_compared",
            "label": "Pelo menos duas alternativas comparáveis",
            "passed": comparable_alternatives >= 2,
            "count": comparable_alternatives,
        },
        {
            "key": "decision_observed",
            "label": "Decisão, ação, resultado e aprendizagem completos",
            "passed": len(completed_cycles) > 0,
            "count": len(completed_cycles),
        },
        {
            "key": "learning_reviewed",
            "label": "Aprendizagem revista por uma pessoa",
            "passed": len(reviewed_learning_ids) > 0,
            "count": len(reviewed_learning_ids),
        },
        {
            "key": "learning_published",
            "label": "Aprendizagem publicada com linhagem",
            "passed": published_learning > 0,
            "count": published_learning,
        },
    ]
    validation = validation_readiness(
        db,
        organization_id=organization_id,
        mission_id=mission_id,
    )
    checks.extend(validation["checks"])
    completed = sum(1 for check in checks if check["passed"])
    return {
        "mission_id": mission_id,
        "mission_code": mission_code,
        "ready": completed == len(checks),
        "completed_checks": completed,
        "total_checks": len(checks),
        "progress_percent": round(completed / len(checks) * 100),
        "checks": checks,
        "blocking_keys": [check["key"] for check in checks if not check["passed"]],
        "validation": validation,
    }
