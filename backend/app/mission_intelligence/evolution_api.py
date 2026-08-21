from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.atlas_platform.auth import require_org_role
from app.atlas_platform.database import get_db
from app.atlas_platform.models import Membership, Role

from .contracts import MissionDocumentV13, RecordKind
from .learning_api import _candidate_rows, _document, _mission_or_404, _tokens
from .models import CanonicalMission


router = APIRouter(
    prefix="/api/organizations/{organization_id}/mission-intelligence",
    tags=["Organizational Learning"],
)

READ_ROLES = (
    Role.OWNER.value,
    Role.ADMIN.value,
    Role.REVIEWER.value,
    Role.CONTRIBUTOR.value,
    Role.OBSERVER.value,
)

CONTRADICTION_RELATIONS = {
    "contradicts",
    "contradicted_by",
    "invalidates",
    "invalidated_by",
    "supersedes",
    "superseded_by",
}
OUTCOME_RELATIONS = {
    "produced",
    "produced_outcome",
    "resulted_in",
    "result_of",
    "outcome_of",
    "measured_by",
}
DECISION_DEPENDENCY_RELATIONS = {
    "depends_on",
    "based_on",
    "constrained_by",
    "assumes",
    "supported_by",
}
OPEN_STATES = {
    "declared",
    "open",
    "unverified",
    "requires_revalidation",
    "assumed",
    "pending",
    "in_review",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _fingerprint_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _metadata_list(document: MissionDocumentV13, key: str) -> list[str]:
    value = document.metadata.get(key) or []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _record_counts(document: MissionDocumentV13) -> dict[str, int]:
    return dict(Counter(record.kind.value for record in document.records))


def _context_fingerprint(row: CanonicalMission, document: MissionDocumentV13) -> dict[str, Any]:
    keywords = sorted(
        _tokens(
            row.title,
            document.context,
            document.central_question,
            str(document.metadata.get("objective") or ""),
        )
    )[:80]
    constraints = sorted(
        record.canonical_id
        for record in document.records
        if record.kind == RecordKind.CONSTRAINT
    )
    assumptions = sorted(
        record.canonical_id
        for record in document.records
        if record.kind == RecordKind.ASSUMPTION
    )
    evidence = sorted(
        record.canonical_id
        for record in document.records
        if record.kind == RecordKind.EVIDENCE
    )
    payload = {
        "mission_code": row.code,
        "domain": row.domain,
        "mission_kind": row.mission_kind,
        "parent_mission_id": row.parent_mission_id,
        "priority": row.priority,
        "horizon": str(document.metadata.get("horizon") or ""),
        "stakeholders": sorted(_metadata_list(document, "stakeholders")),
        "keywords": keywords,
        "record_counts": _record_counts(document),
        "constraint_ids": constraints,
        "assumption_ids": assumptions,
        "evidence_ids": evidence,
    }
    return {
        "schema": "sris.context_fingerprint",
        "schema_version": "0.1",
        "fingerprint_hash": _fingerprint_hash(payload),
        **payload,
        "interpretation_boundary": (
            "A impressão contextual descreve estrutura e semelhança; não prova causalidade "
            "nem torna duas missões equivalentes."
        ),
    }


def _fingerprint_similarity(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    score = 0
    reasons: list[str] = []
    differences: list[str] = []
    if left["domain"] == right["domain"]:
        score += 35
        reasons.append("mesmo domínio")
    else:
        differences.append(f"domínio: {left['domain']} ≠ {right['domain']}")
    if left["mission_kind"] == right["mission_kind"]:
        score += 5
    if left.get("parent_mission_id") and left.get("parent_mission_id") == right.get("parent_mission_id"):
        score += 15
        reasons.append("mesma missão-mãe")
    left_words = set(left.get("keywords") or [])
    right_words = set(right.get("keywords") or [])
    if left_words and right_words:
        overlap = len(left_words & right_words) / max(1, len(left_words | right_words))
        points = min(35, round(overlap * 100))
        score += points
        if points:
            reasons.append(f"sobreposição contextual {round(overlap * 100)}%")
    left_stakeholders = set(left.get("stakeholders") or [])
    right_stakeholders = set(right.get("stakeholders") or [])
    if left_stakeholders and right_stakeholders:
        overlap = len(left_stakeholders & right_stakeholders) / max(1, len(left_stakeholders | right_stakeholders))
        points = min(10, round(overlap * 10))
        score += points
        if points:
            reasons.append("atores parcialmente coincidentes")
    return {
        "score": min(100, score),
        "reasons": reasons,
        "material_differences": differences,
    }


def _age_days(value: datetime | None) -> int | None:
    if value is None:
        return None
    current = value
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return max(0, (_utcnow() - current).days)


def _knowledge_decay(document: MissionDocumentV13) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in document.records:
        if record.kind not in {RecordKind.EVIDENCE, RecordKind.LEARNING, RecordKind.KNOWLEDGE}:
            continue
        age = _age_days(record.observed_at)
        if age is None:
            pressure = "unknown_age"
        elif age >= 730:
            pressure = "critical_review"
        elif age >= 365:
            pressure = "review_due"
        elif age >= 180:
            pressure = "watch"
        else:
            pressure = "fresh"
        if pressure == "fresh":
            continue
        rows.append(
            {
                "record_id": record.canonical_id,
                "kind": record.kind.value,
                "title": record.title,
                "age_days": age,
                "review_pressure": pressure,
                "confidence": record.confidence.value,
                "note": (
                    "A idade cria pressão de revisão; não reduz automaticamente a verdade "
                    "ou a confiança do registo."
                ),
            }
        )
    return rows


def _explicit_contradictions(document: MissionDocumentV13) -> list[dict[str, Any]]:
    by_id = {record.canonical_id: record for record in document.records}
    output: list[dict[str, Any]] = []
    for relation in document.relations:
        relation_type = relation.relation_type.strip().casefold()
        if relation_type not in CONTRADICTION_RELATIONS:
            continue
        source = by_id.get(relation.source_id)
        target = by_id.get(relation.target_id)
        output.append(
            {
                "relation_id": relation.relation_id,
                "relation_type": relation.relation_type,
                "source_id": relation.source_id,
                "source_title": source.title if source else relation.source_id,
                "target_id": relation.target_id,
                "target_title": target.title if target else relation.target_id,
                "explanation": relation.explanation,
                "confidence": relation.confidence.value,
                "status": "declared_conflict",
            }
        )
    return output


def _inheritance_invalidations(document: MissionDocumentV13) -> list[dict[str, Any]]:
    container = document.metadata.get("learning_inheritance") or {}
    decisions = container.get("decisions") or {}
    if not isinstance(decisions, dict):
        return []
    output = []
    for decision in decisions.values():
        if not isinstance(decision, dict) or decision.get("disposition") != "invalidated":
            continue
        output.append(
            {
                "relation_id": decision.get("inheritance_key"),
                "relation_type": "context_invalidated_learning",
                "source_id": decision.get("source_learning_id"),
                "source_title": decision.get("source_learning_title"),
                "target_id": document.mission_id,
                "target_title": document.title,
                "explanation": decision.get("context_change") or decision.get("rationale"),
                "confidence": "human_reviewed",
                "status": "resolved_by_invalidation",
            }
        )
    return output


def _decision_debt_for_document(row: CanonicalMission, document: MissionDocumentV13) -> dict[str, Any]:
    by_id = {record.canonical_id: record for record in document.records}
    decisions = [record for record in document.records if record.kind == RecordKind.DECISION]
    assumptions = [record for record in document.records if record.kind == RecordKind.ASSUMPTION]
    constraints = [record for record in document.records if record.kind == RecordKind.CONSTRAINT]
    evidence = [record for record in document.records if record.kind == RecordKind.EVIDENCE]
    outcomes = {record.canonical_id for record in document.records if record.kind == RecordKind.OUTCOME}

    connected_to_outcome: set[str] = set()
    decision_dependencies: dict[str, set[str]] = {record.canonical_id: set() for record in decisions}
    for relation in document.relations:
        rel = relation.relation_type.strip().casefold()
        if rel in OUTCOME_RELATIONS:
            if relation.source_id in decision_dependencies and relation.target_id in outcomes:
                connected_to_outcome.add(relation.source_id)
            if relation.target_id in decision_dependencies and relation.source_id in outcomes:
                connected_to_outcome.add(relation.target_id)
        if rel in DECISION_DEPENDENCY_RELATIONS:
            if relation.source_id in decision_dependencies:
                decision_dependencies[relation.source_id].add(relation.target_id)
            if relation.target_id in decision_dependencies:
                decision_dependencies[relation.target_id].add(relation.source_id)

    decisions_without_outcome = [d.canonical_id for d in decisions if d.canonical_id not in connected_to_outcome]
    unresolved_assumptions = [
        r.canonical_id for r in assumptions if r.state.strip().casefold() in OPEN_STATES
    ]
    unresolved_constraints = [
        r.canonical_id for r in constraints if r.state.strip().casefold() in OPEN_STATES
    ]
    stale_evidence = [
        r.canonical_id
        for r in evidence
        if (_age_days(r.observed_at) is None or (_age_days(r.observed_at) or 0) >= 365)
    ]
    revalidation = [
        r.canonical_id
        for r in document.records
        if r.kind == RecordKind.HYPOTHESIS and r.metadata.get("revalidation_required")
    ]
    learnings_without_scope = [
        r.canonical_id
        for r in document.records
        if r.kind == RecordKind.LEARNING
        and not r.metadata.get("inherited_learning")
        and not (r.metadata.get("validity_conditions") or [])
    ]

    score = min(
        100,
        len(decisions_without_outcome) * 18
        + len(unresolved_assumptions) * 10
        + len(unresolved_constraints) * 8
        + len(stale_evidence) * 7
        + len(revalidation) * 15
        + len(learnings_without_scope) * 8,
    )
    severity = "low" if score < 20 else "moderate" if score < 45 else "high" if score < 70 else "critical"
    return {
        "mission_id": row.id,
        "mission_code": row.code,
        "title": row.title,
        "score": score,
        "severity": severity,
        "components": {
            "decisions_without_outcome": decisions_without_outcome,
            "unresolved_assumptions": unresolved_assumptions,
            "unresolved_constraints": unresolved_constraints,
            "stale_or_undated_evidence": stale_evidence,
            "learning_revalidation_open": revalidation,
            "learnings_without_validity_scope": learnings_without_scope,
        },
        "boundary": (
            "Decision Debt é um indicador operacional determinístico de pendências documentais; "
            "não é uma medida validada de risco, qualidade da gestão ou desempenho."
        ),
    }


def _related_missions(
    db: Session,
    *,
    organization_id: str,
    target: CanonicalMission,
    limit: int = 8,
) -> list[dict[str, Any]]:
    target_document = _document(target)
    left = _context_fingerprint(target, target_document)
    output: list[dict[str, Any]] = []
    rows = (
        db.query(CanonicalMission)
        .filter(
            CanonicalMission.organization_id == organization_id,
            CanonicalMission.id != target.id,
            CanonicalMission.lifecycle_state != "archived",
        )
        .all()
    )
    for row in rows:
        document = _document(row)
        right = _context_fingerprint(row, document)
        similarity = _fingerprint_similarity(left, right)
        if similarity["score"] <= 0:
            continue
        output.append(
            {
                "mission_id": row.id,
                "mission_code": row.code,
                "title": row.title,
                "domain": row.domain,
                "revision": row.revision,
                "fingerprint_hash": right["fingerprint_hash"],
                **similarity,
            }
        )
    output.sort(key=lambda item: (-item["score"], item["mission_code"]))
    return output[:limit]


def _pattern_clusters(rows: list[tuple[CanonicalMission, MissionDocumentV13]]) -> list[dict[str, Any]]:
    learnings: list[dict[str, Any]] = []
    for row, document in rows:
        for record in document.records:
            if record.kind != RecordKind.LEARNING or record.metadata.get("inherited_learning"):
                continue
            words = _tokens(record.title, record.description)
            if not words:
                continue
            learnings.append(
                {
                    "mission_id": row.id,
                    "mission_code": row.code,
                    "learning_id": record.canonical_id,
                    "title": record.title,
                    "description": record.description,
                    "tokens": words,
                }
            )

    parent = list(range(len(learnings)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        root_left = find(left)
        root_right = find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    for left in range(len(learnings)):
        for right in range(left + 1, len(learnings)):
            if learnings[left]["mission_id"] == learnings[right]["mission_id"]:
                continue
            a = learnings[left]["tokens"]
            b = learnings[right]["tokens"]
            similarity = len(a & b) / max(1, len(a | b))
            if similarity >= 0.42:
                union(left, right)

    groups: dict[int, list[dict[str, Any]]] = {}
    for index, item in enumerate(learnings):
        groups.setdefault(find(index), []).append(item)

    patterns: list[dict[str, Any]] = []
    for items in groups.values():
        missions = sorted({item["mission_code"] for item in items})
        if len(missions) < 2:
            continue
        shared = set.intersection(*(set(item["tokens"]) for item in items)) if items else set()
        pattern_id = "PAT-" + hashlib.sha256(
            "|".join(sorted(f"{item['mission_code']}:{item['learning_id']}" for item in items)).encode("utf-8")
        ).hexdigest()[:12].upper()
        patterns.append(
            {
                "pattern_id": pattern_id,
                "status": "emergent_hypothesis",
                "mission_count": len(missions),
                "missions": missions,
                "shared_terms": sorted(shared)[:20],
                "basis": [
                    {
                        "mission_code": item["mission_code"],
                        "learning_id": item["learning_id"],
                        "title": item["title"],
                    }
                    for item in items
                ],
                "hypothesis": (
                    "Aprendizagens semanticamente próximas reaparecem em múltiplas missões. "
                    "O padrão deve ser testado antes de ser promovido a conhecimento transversal."
                ),
                "boundary": "Sem inferência causal ou transferência automática entre domínios.",
            }
        )
    patterns.sort(key=lambda item: (-item["mission_count"], item["pattern_id"]))
    return patterns


def _learning_graph(rows: list[tuple[CanonicalMission, MissionDocumentV13]]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for row, document in rows:
        mission_node = f"mission:{row.id}"
        nodes.append(
            {
                "id": mission_node,
                "node_type": "mission",
                "label": f"{row.code} · {row.title}",
                "domain": row.domain,
            }
        )
        for record in document.records:
            if record.kind not in {
                RecordKind.EVIDENCE,
                RecordKind.HYPOTHESIS,
                RecordKind.ASSUMPTION,
                RecordKind.DECISION,
                RecordKind.OUTCOME,
                RecordKind.LEARNING,
            }:
                continue
            record_node = f"record:{row.id}:{record.canonical_id}"
            nodes.append(
                {
                    "id": record_node,
                    "node_type": record.kind.value,
                    "label": record.title,
                    "mission_code": row.code,
                    "record_id": record.canonical_id,
                    "state": record.state,
                    "confidence": record.confidence.value,
                }
            )
            edges.append(
                {
                    "source": mission_node,
                    "target": record_node,
                    "edge_type": "contains",
                }
            )
        local_ids = {record.canonical_id for record in document.records}
        for relation in document.relations:
            if relation.source_id not in local_ids or relation.target_id not in local_ids:
                continue
            edges.append(
                {
                    "source": f"record:{row.id}:{relation.source_id}",
                    "target": f"record:{row.id}:{relation.target_id}",
                    "edge_type": relation.relation_type,
                    "confidence": relation.confidence.value,
                }
            )
        inheritance = document.metadata.get("learning_inheritance") or {}
        decisions = inheritance.get("decisions") or {}
        if isinstance(decisions, dict):
            for decision in decisions.values():
                if not isinstance(decision, dict):
                    continue
                source_mission_id = decision.get("source_mission_id")
                source_learning_id = decision.get("source_learning_id")
                if not source_mission_id or not source_learning_id:
                    continue
                edges.append(
                    {
                        "source": f"record:{source_mission_id}:{source_learning_id}",
                        "target": mission_node,
                        "edge_type": f"inheritance:{decision.get('disposition', 'reviewed')}",
                        "reviewed_at": decision.get("reviewed_at"),
                    }
                )
    return {
        "schema": "sris.organizational_learning_graph",
        "schema_version": "0.1",
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "mission_nodes": sum(1 for item in nodes if item["node_type"] == "mission"),
            "knowledge_nodes": sum(1 for item in nodes if item["node_type"] != "mission"),
            "edges": len(edges),
        },
    }


def _organization_rows(db: Session, organization_id: str) -> list[tuple[CanonicalMission, MissionDocumentV13]]:
    rows = (
        db.query(CanonicalMission)
        .filter(
            CanonicalMission.organization_id == organization_id,
            CanonicalMission.lifecycle_state != "archived",
        )
        .order_by(CanonicalMission.created_at.asc())
        .all()
    )
    return [(row, _document(row)) for row in rows]


@router.get("/missions/{mission_id}/context-fingerprint")
def context_fingerprint(
    organization_id: str,
    mission_id: str,
    _: Membership = Depends(require_org_role(*READ_ROLES)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row = _mission_or_404(db, organization_id=organization_id, mission_id=mission_id)
    document = _document(row)
    return _context_fingerprint(row, document)


@router.get("/missions/{mission_id}/preflight")
def mission_preflight(
    organization_id: str,
    mission_id: str,
    _: Membership = Depends(require_org_role(*READ_ROLES)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row = _mission_or_404(db, organization_id=organization_id, mission_id=mission_id)
    document = _document(row)
    candidates = _candidate_rows(db, organization_id=organization_id, target=row)
    top_candidates = [item for item in candidates if item.get("relevance_score", 0) >= 20][:12]
    decay = _knowledge_decay(document)
    contradictions = [*_explicit_contradictions(document), *_inheritance_invalidations(document)]
    debt = _decision_debt_for_document(row, document)
    related = _related_missions(db, organization_id=organization_id, target=row)

    actions: list[dict[str, str]] = []
    unreviewed = [item for item in top_candidates if not item.get("decision")]
    revalidate = [
        item for item in top_candidates
        if (item.get("decision") or {}).get("disposition") == "requires_revalidation"
    ]
    if unreviewed:
        actions.append({"priority": "high", "action": f"Rever {len(unreviewed)} aprendizagem(ns) potencialmente reutilizável(eis)."})
    if revalidate:
        actions.append({"priority": "high", "action": f"Revalidar {len(revalidate)} aprendizagem(ns) antes de as usar como conhecimento."})
    if contradictions:
        actions.append({"priority": "high", "action": f"Resolver ou enquadrar {len(contradictions)} conflito(s) de conhecimento registado(s)."})
    if debt["score"] >= 20:
        actions.append({"priority": "medium", "action": f"Reduzir Decision Debt ({debt['score']}/100) antes de aumentar o compromisso da missão."})
    if decay:
        actions.append({"priority": "medium", "action": f"Rever {len(decay)} registo(s) com pressão temporal de atualização."})
    if not actions:
        actions.append({"priority": "normal", "action": "Não foram detetadas pendências estruturais prioritárias no preflight determinístico."})

    return {
        "schema": "sris.mission_preflight",
        "schema_version": "0.1",
        "mission": {
            "id": row.id,
            "code": row.code,
            "title": row.title,
            "revision": row.revision,
            "domain": row.domain,
        },
        "context_fingerprint": _context_fingerprint(row, document),
        "related_missions": related,
        "learning_candidates": top_candidates,
        "knowledge_decay": decay,
        "contradictions": contradictions,
        "decision_debt": debt,
        "recommended_preflight_actions": actions,
        "principle": (
            "A missão deve começar com o conhecimento anterior relevante, mas cada herança "
            "mantém contexto, proveniência e necessidade de revalidação."
        ),
    }


@router.get("/decision-debt")
def organization_decision_debt(
    organization_id: str,
    _: Membership = Depends(require_org_role(*READ_ROLES)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rows = _organization_rows(db, organization_id)
    missions = [_decision_debt_for_document(row, document) for row, document in rows]
    total = round(sum(item["score"] for item in missions) / max(1, len(missions)))
    return {
        "schema": "sris.decision_debt",
        "schema_version": "0.1",
        "organization_id": organization_id,
        "portfolio_score": total,
        "portfolio_severity": "low" if total < 20 else "moderate" if total < 45 else "high" if total < 70 else "critical",
        "missions": sorted(missions, key=lambda item: (-item["score"], item["mission_code"])),
        "boundary": "Indicador interno de pendências estruturais; não é benchmark externo nem score científico.",
    }


@router.get("/learning-graph")
def organization_learning_graph(
    organization_id: str,
    _: Membership = Depends(require_org_role(*READ_ROLES)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return _learning_graph(_organization_rows(db, organization_id))


@router.get("/emergent-patterns")
def organization_emergent_patterns(
    organization_id: str,
    _: Membership = Depends(require_org_role(*READ_ROLES)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    patterns = _pattern_clusters(_organization_rows(db, organization_id))
    return {
        "schema": "sris.emergent_patterns",
        "schema_version": "0.1",
        "organization_id": organization_id,
        "patterns": patterns,
        "count": len(patterns),
        "boundary": (
            "Padrões emergentes são hipóteses geradas por recorrência semântica entre aprendizagens; "
            "não são conhecimento transversal até revisão e teste explícitos."
        ),
    }


@router.get("/evolution-dashboard")
def organization_evolution_dashboard(
    organization_id: str,
    _: Membership = Depends(require_org_role(*READ_ROLES)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rows = _organization_rows(db, organization_id)
    graph = _learning_graph(rows)
    patterns = _pattern_clusters(rows)
    debts = [_decision_debt_for_document(row, document) for row, document in rows]
    total_learnings = sum(
        1
        for _, document in rows
        for record in document.records
        if record.kind == RecordKind.LEARNING
    )
    inherited_valid = sum(
        1
        for _, document in rows
        for record in document.records
        if record.kind == RecordKind.LEARNING and record.metadata.get("inherited_learning")
    )
    revalidation_open = sum(
        1
        for _, document in rows
        for record in document.records
        if record.kind == RecordKind.HYPOTHESIS and record.metadata.get("revalidation_required")
    )
    contradictions = sum(
        len(_explicit_contradictions(document)) + len(_inheritance_invalidations(document))
        for _, document in rows
    )
    stale = sum(len(_knowledge_decay(document)) for _, document in rows)
    avg_debt = round(sum(item["score"] for item in debts) / max(1, len(debts)))
    reuse_rate = round((inherited_valid / max(1, total_learnings)) * 100)
    return {
        "schema": "sris.organizational_learning_evolution",
        "schema_version": "0.1",
        "organization_id": organization_id,
        "metrics": {
            "active_missions": len(rows),
            "canonical_learnings": total_learnings,
            "inherited_valid_learnings": inherited_valid,
            "open_revalidations": revalidation_open,
            "declared_or_resolved_knowledge_conflicts": contradictions,
            "records_with_review_pressure": stale,
            "emergent_pattern_hypotheses": len(patterns),
            "average_decision_debt": avg_debt,
            "learning_reuse_rate_percent": reuse_rate,
            "learning_graph_nodes": graph["summary"]["knowledge_nodes"],
            "learning_graph_edges": graph["summary"]["edges"],
        },
        "principle": (
            "O sistema não mede inteligência organizacional. Mede sinais operacionais de continuidade, "
            "reutilização, revalidação e pendências do conhecimento preservado."
        ),
    }
