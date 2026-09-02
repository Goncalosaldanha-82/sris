from __future__ import annotations

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.evidence_graph import _ensure_schema as _ensure_graph_schema
from app.learning_lineage import _ensure_schema as _ensure_learning_schema
from app.mission_intelligence.models import MissionAttachment
from app.pilot_alternative_matrix import matrix_readiness
from app.pilot_business_case import business_case_readiness
from app.pilot_decision_cycle import _ensure_schema as _ensure_decision_schema
from app.pilot_mission_state import build_mission_state, mission_axis_policy
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
                FROM pilot_evidence_graph_nodes hypothesis
                WHERE hypothesis.organization_id=:org
                  AND hypothesis.mission_id=:mission
                  AND hypothesis.node_type='hypothesis'
                  AND hypothesis.status NOT IN ('rejected', 'superseded')
                  AND TRIM(COALESCE(hypothesis.body, '')) <> ''
                  AND (
                    EXISTS (
                      SELECT 1
                      FROM pilot_evidence_graph_edges direct_edge
                      JOIN pilot_evidence_graph_nodes evidence
                        ON evidence.id=direct_edge.from_node_id
                      WHERE direct_edge.organization_id=:org
                        AND direct_edge.mission_id=:mission
                        AND direct_edge.to_node_id=hypothesis.id
                        AND direct_edge.edge_type IN ('supports', 'contradicts', 'informs', 'tests')
                        AND evidence.node_type='evidence'
                        AND evidence.status NOT IN ('rejected', 'superseded')
                    )
                    OR EXISTS (
                      SELECT 1
                      FROM pilot_evidence_graph_edges source_edge
                      JOIN pilot_evidence_graph_nodes evidence
                        ON evidence.id=source_edge.from_node_id
                      JOIN pilot_evidence_graph_nodes bridge
                        ON bridge.id=source_edge.to_node_id
                      JOIN pilot_evidence_graph_edges hypothesis_edge
                        ON hypothesis_edge.from_node_id=bridge.id
                       AND hypothesis_edge.to_node_id=hypothesis.id
                      WHERE source_edge.organization_id=:org
                        AND source_edge.mission_id=:mission
                        AND hypothesis_edge.organization_id=:org
                        AND hypothesis_edge.mission_id=:mission
                        AND source_edge.edge_type IN ('supports', 'informs', 'derived_from')
                        AND hypothesis_edge.edge_type IN ('supports', 'contradicts', 'informs', 'tests')
                        AND evidence.node_type='evidence'
                        AND bridge.node_type IN ('observation', 'claim')
                        AND evidence.status NOT IN ('rejected', 'superseded')
                        AND bridge.status NOT IN ('rejected', 'superseded')
                    )
                  )
                """
            ),
            {"org": organization_id, "mission": mission_id},
        ).scalar()
        or 0
    )

    alternative_matrix = matrix_readiness(
        db,
        organization_id=organization_id,
        mission_id=mission_id,
    )

    cycles = db.execute(
        text(
            """
            SELECT cycle.id, cycle.status, cycle.action, cycle.owner,
                   cycle.due_date, cycle.expected_outcome,
                   cycle.evidence_node_id, foundation.status AS evidence_status,
                   cycle.action_started_at, cycle.actual_outcome_at,
                   cycle.outcome_evidence_node_id,
                   outcome_foundation.status AS outcome_evidence_status,
                   cycle.actual_outcome, cycle.learning
            FROM pilot_decision_cycles cycle
            LEFT JOIN pilot_evidence_graph_nodes foundation
              ON foundation.id=cycle.evidence_node_id
             AND foundation.organization_id=cycle.organization_id
             AND foundation.mission_code=cycle.mission_code
            LEFT JOIN pilot_evidence_graph_nodes outcome_foundation
              ON outcome_foundation.id=cycle.outcome_evidence_node_id
             AND outcome_foundation.organization_id=cycle.organization_id
             AND outcome_foundation.mission_code=cycle.mission_code
            WHERE cycle.organization_id=:org AND cycle.mission_code=:mission
            """
        ),
        {"org": organization_id, "mission": mission_code},
    ).mappings().all()
    completed_cycles = [
        row
        for row in cycles
        if row["status"] == "completed"
        and str(row["evidence_node_id"] or "").strip()
        and row["evidence_status"] in {"accepted", "verified"}
        and str(row["action"] or "").strip()
        and str(row["owner"] or "").strip()
        and row["due_date"] is not None
        and str(row["expected_outcome"] or "").strip()
        and row["action_started_at"] is not None
        and row["actual_outcome_at"] is not None
        and str(row["outcome_evidence_node_id"] or "").strip()
        and row["outcome_evidence_status"] in {"accepted", "verified"}
        and str(row["actual_outcome"] or "").strip()
        and str(row["learning"] or "").strip()
    ]
    open_cycles = [
        row for row in cycles if row["status"] not in {"completed", "abandoned"}
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

    policy = mission_axis_policy(
        db,
        organization_id=organization_id,
        mission_id=mission_id,
        mission_code=mission_code,
    )
    checks = [
        {
            "key": "governance_policy_current",
            "label": "Aplicabilidade alinhada com a revisão atual da missão",
            "passed": bool(policy.get("current", True)),
            "count": 1 if policy.get("current", True) else 0,
        },
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
            "label": "Hipótese com linhagem explícita até à evidência",
            "passed": linked_hypotheses > 0,
            "count": linked_hypotheses,
        },
        {
            "key": "decision_observed",
            "label": "Decisão, ação, resultado e aprendizagem completos",
            "passed": len(completed_cycles) > 0,
            "count": len(completed_cycles),
        },
        {
            "key": "decision_cycles_resolved",
            "label": "Sem ciclos de decisão ainda abertos",
            "passed": not open_cycles,
            "count": len(cycles) - len(open_cycles),
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
    alternatives_applicability = policy.get("alternatives_applicability", "required")
    if alternatives_applicability == "required" or (
        alternatives_applicability == "optional" and alternative_matrix.get("matrix_id")
    ):
        checks.insert(
            4,
            {
                "key": "alternatives_compared",
                "label": "Pelo menos duas alternativas comparadas por critérios",
                "passed": alternative_matrix["passed"],
                "count": alternative_matrix["count"],
            },
        )
    validation = validation_readiness(
        db,
        organization_id=organization_id,
        mission_id=mission_id,
    )
    measurement_applicability = policy.get("measurement_applicability", "optional")
    if measurement_applicability == "required" and not validation["required"]:
        checks.append(
            {
                "key": "validation_required_by_mission",
                "label": "Protocolo mensurável exigido pela aplicabilidade da missão",
                "passed": False,
                "count": 0,
            }
        )
    elif measurement_applicability == "required" or (
        measurement_applicability == "optional" and validation["required"]
    ):
        checks.extend(validation["checks"])
    business_case = business_case_readiness(
        db,
        organization_id=organization_id,
        mission_id=mission_id,
        mission_code=mission_code,
    )
    economics_applicability = policy.get("economics_applicability", "required")
    if economics_applicability == "required" and not business_case["required"]:
        checks.append(
            {
                "key": "business_case_required",
                "label": "Economia e recursos estruturados para a missão",
                "passed": False,
                "count": 0,
            }
        )
    elif economics_applicability == "required" or (
        economics_applicability == "optional" and business_case["required"]
    ):
        checks.extend(business_case["checks"])
    governed_state = build_mission_state(
        db,
        organization_id=organization_id,
        mission_id=mission_id,
        mission_code=mission_code,
    )
    critical_conflicts = [
        item for item in governed_state["conflicts"] if item["severity"] == "critical"
    ]
    checks.append(
        {
            "key": "cross_module_consistency",
            "label": "Sem contradições críticas entre os módulos da missão",
            "passed": not critical_conflicts,
            "count": len(critical_conflicts),
        }
    )
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
        "business_case": business_case,
        "governed_state": {
            "state_hash": governed_state["state_hash"],
            "health": governed_state["health"],
            "policy": governed_state["policy"],
            "critical_conflicts": critical_conflicts,
        },
    }
