from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.api.dependencies import Principal, principal
from app.core.db import get_db
from app.models.models import (
    Alternative, Assumption, AttributionAssessment, AuditLog, Constraint,
    Decision, Evidence, EvidenceProposal, Hypothesis, Implementation, Provenance,
    Investigation, Learning, LearningReuse, Mission, Observation, Outcome,
    Relation, GuidedReasoningSession,
)
from app.services.confidence import recalculate_investigation_posteriors
from app.services.audit import record_audit

router = APIRouter(prefix="/v1/experience", tags=["SRIS Experience"])

MODEL_MAP = {
    "mission": Mission,
    "investigation": Investigation,
    "observation": Observation,
    "evidence": Evidence,
    "provenance": Provenance,
    "hypothesis": Hypothesis,
    "assumption": Assumption,
    "constraint": Constraint,
    "alternative": Alternative,
    "decision": Decision,
    "implementation": Implementation,
    "outcome": Outcome,
    "learning": Learning,
}
LABEL_FIELD = {
    "mission": "name",
    "investigation": "title",
    "observation": "title",
    "evidence": "title",
    "provenance": "origin_actor",
    "hypothesis": "statement",
    "assumption": "statement",
    "constraint": "statement",
    "alternative": "title",
    "decision": "title",
    "implementation": "title",
    "outcome": "observed",
    "learning": "statement",
}


def tenant_get(db: Session, p: Principal, model, object_id: str):
    obj = db.query(model).filter_by(id=object_id, organization_id=p.organization.id).first()
    if not obj:
        raise HTTPException(404, "Objeto não encontrado nesta organização.")
    return obj


def belongs_to_mission(obj: Any, mission_id: str, db: Session, p: Principal) -> bool:
    direct = getattr(obj, "mission_id", None)
    if direct is not None:
        return direct == mission_id
    if isinstance(obj, Hypothesis):
        inv = db.query(Investigation).filter_by(id=obj.investigation_id, organization_id=p.organization.id).first()
        return bool(inv and inv.mission_id == mission_id)
    if isinstance(obj, Evidence):
        inv = db.query(Investigation).filter_by(id=obj.investigation_id, organization_id=p.organization.id).first()
        return bool(inv and inv.mission_id == mission_id)
    if isinstance(obj, Provenance):
        evidence = db.query(Evidence).filter_by(provenance_id=obj.id, organization_id=p.organization.id).first()
        if not evidence:
            return False
        inv = db.query(Investigation).filter_by(id=evidence.investigation_id, organization_id=p.organization.id).first()
        return bool(inv and inv.mission_id == mission_id)
    if isinstance(obj, Implementation):
        dec = db.query(Decision).filter_by(id=obj.decision_id, organization_id=p.organization.id).first()
        return bool(dec and dec.mission_id == mission_id)
    if isinstance(obj, AttributionAssessment):
        out = db.query(Outcome).filter_by(id=obj.outcome_id, organization_id=p.organization.id).first()
        if not out:
            return False
        # Outcome -> Action -> Decision is handled indirectly in existing core; not needed for map projection.
    return True


def object_view(kind: str, obj: Any) -> dict[str, Any]:
    label = str(getattr(obj, LABEL_FIELD[kind], "") or getattr(obj, "model_or_system", "") or "Origem não identificada")[:240]
    return {
        "id": obj.id,
        "type": kind,
        "label": label,
        "status": getattr(obj, "status", None),
        "created_at": getattr(obj, "created_at", None),
        "mission_id": getattr(obj, "mission_id", None),
    }


def mission_nodes(db: Session, p: Principal, mission_id: str) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for kind, model in MODEL_MAP.items():
        if model is Mission:
            rows = [tenant_get(db, p, Mission, mission_id)]
        elif hasattr(model, "mission_id"):
            rows = db.query(model).filter_by(organization_id=p.organization.id, mission_id=mission_id).all()
        elif model in (Hypothesis, Evidence):
            inv_ids = [x.id for x in db.query(Investigation).filter_by(organization_id=p.organization.id, mission_id=mission_id).all()]
            rows = db.query(model).filter(model.organization_id == p.organization.id, model.investigation_id.in_(inv_ids or ["-"])).all()
        elif model is Provenance:
            inv_ids = [x.id for x in db.query(Investigation).filter_by(organization_id=p.organization.id, mission_id=mission_id).all()]
            provenance_ids = [x.provenance_id for x in db.query(Evidence).filter(Evidence.organization_id == p.organization.id, Evidence.investigation_id.in_(inv_ids or ["-"])).all() if x.provenance_id]
            rows = db.query(Provenance).filter(Provenance.organization_id == p.organization.id, Provenance.id.in_(provenance_ids or ["-"])).all()
        elif model is Implementation:
            dec_ids = [x.id for x in db.query(Decision).filter_by(organization_id=p.organization.id, mission_id=mission_id).all()]
            rows = db.query(model).filter(model.organization_id == p.organization.id, model.decision_id.in_(dec_ids or ["-"])).all()
        else:
            rows = []
        nodes.extend(object_view(kind, row) for row in rows)
    return nodes


def audit_gaps(db: Session, p: Principal, mission_id: str) -> list[dict[str, Any]]:
    invs = db.query(Investigation).filter_by(organization_id=p.organization.id, mission_id=mission_id).all()
    inv_ids = [x.id for x in invs]
    hyps = db.query(Hypothesis).filter(Hypothesis.organization_id == p.organization.id, Hypothesis.investigation_id.in_(inv_ids or ["-"])).all()
    evid = db.query(Evidence).filter(Evidence.organization_id == p.organization.id, Evidence.investigation_id.in_(inv_ids or ["-"])).all()
    decisions = db.query(Decision).filter_by(organization_id=p.organization.id, mission_id=mission_id).all()
    alternatives = db.query(Alternative).filter_by(organization_id=p.organization.id, mission_id=mission_id).all()
    assumptions = db.query(Assumption).filter_by(organization_id=p.organization.id, mission_id=mission_id).all()
    constraints = db.query(Constraint).filter_by(organization_id=p.organization.id, mission_id=mission_id).all()
    outcomes = db.query(Outcome).filter(Outcome.organization_id == p.organization.id).all()
    learnings = db.query(Learning).filter(Learning.organization_id == p.organization.id).all()
    gaps: list[dict[str, Any]] = []
    provenance_ids = {row.id for row in db.query(Provenance).filter(Provenance.organization_id == p.organization.id).all()}
    for e in evid:
        if not e.provenance_id or e.provenance_id not in provenance_ids:
            gaps.append({"severity": "high", "ref": e.id, "rule": "EVD_NO_PROVENANCE", "message": "Evidência sem registo de proveniência não é auditável."})
    for h in hyps:
        linked = [e for e in evid if e.hypothesis_id == h.id]
        if not linked:
            gaps.append({"severity": "high", "ref": h.id, "rule": "HYP_NO_EVIDENCE", "message": "Hipótese sem evidência associada."})
        elif not any(e.direction in ("contradicts", "refutes") for e in linked):
            gaps.append({"severity": "medium", "ref": h.id, "rule": "HYP_NO_COUNTER", "message": "Hipótese sem evidência contrária registada."})
    for d in decisions:
        if not any(x.decision_id == d.id for x in alternatives):
            gaps.append({"severity": "high", "ref": d.id, "rule": "DEC_NO_ALT", "message": "Decisão sem alternativas de primeira classe."})
        if not any(x.decision_id == d.id for x in assumptions) and not any(x.decision_id == d.id for x in constraints):
            gaps.append({"severity": "medium", "ref": d.id, "rule": "DEC_NO_CONTEXT", "message": "Decisão sem pressupostos nem restrições declarados."})
    for o in outcomes:
        if not o.baseline:
            gaps.append({"severity": "high", "ref": o.id, "rule": "OUT_NO_BASELINE", "message": "Resultado sem baseline comparável."})
    for l in learnings:
        if getattr(l, "reuse_count", 0) == 0:
            gaps.append({"severity": "low", "ref": l.id, "rule": "LRN_NOT_REUSED", "message": "Aprendizagem ainda não reutilizada."})
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(gaps, key=lambda x: order[x["severity"]])


@router.get("/missions/{mission_id}/entry")
def mission_entry(mission_id: str, p: Principal = Depends(principal), db: Session = Depends(get_db)):
    mission = tenant_get(db, p, Mission, mission_id)
    nodes = mission_nodes(db, p, mission_id)
    gaps = audit_gaps(db, p, mission_id)
    refuted = [n for n in nodes if n["type"] == "assumption" and n.get("status") == "refuted"]
    invs = db.query(Investigation).filter_by(organization_id=p.organization.id, mission_id=mission_id).all()
    proposals = []
    for inv in invs:
        for proposal in db.query(EvidenceProposal).filter_by(organization_id=p.organization.id, investigation_id=inv.id).all():
            proposals.append({
                "id": proposal.id,
                "title": proposal.title,
                "description": proposal.description,
                "limitations": proposal.limitations,
                "estimated_cost": proposal.estimated_cost,
                "estimated_days": proposal.estimated_days,
            })
    main_change = (
        {"type": "assumption_refuted", "object_id": refuted[0]["id"], "summary": "Um pressuposto utilizado na missão foi refutado."}
        if refuted else
        {"type": "mission_state", "object_id": mission.id, "summary": "A missão permanece no estado atual sem nova refutação material registada."}
    )
    return {
        "mission": {"id": mission.id, "code": mission.code, "name": mission.name, "status": mission.status, "objective": mission.objective},
        "main_change": main_change,
        "attention": gaps[:3],
        "knowledge_gaps": proposals[:3],
        "counts": {
            "investigations": sum(1 for n in nodes if n["type"] == "investigation"),
            "decisions": sum(1 for n in nodes if n["type"] == "decision"),
            "assumptions_refuted": len(refuted),
            "learnings": sum(1 for n in nodes if n["type"] == "learning"),
        },
        "available_intentions": ["understand", "investigate", "decide", "review", "learn"],
    }


@router.get("/missions/{mission_id}/map")
def mission_map(mission_id: str, p: Principal = Depends(principal), db: Session = Depends(get_db)):
    tenant_get(db, p, Mission, mission_id)
    nodes = mission_nodes(db, p, mission_id)
    ids = {n["id"] for n in nodes}
    relations = db.query(Relation).filter_by(organization_id=p.organization.id).all()
    edges = [
        {"id": r.id, "source": r.source_id, "target": r.target_id, "type": r.relation_type, "confidence": r.confidence, "explanation": r.explanation}
        for r in relations if r.source_id in ids and r.target_id in ids
    ]
    return {"nodes": nodes, "edges": edges}


@router.get("/missions/{mission_id}/impact/{object_id}")
def impact_chain(
    mission_id: str,
    object_id: str,
    depth: int = Query(default=4, ge=1, le=8),
    p: Principal = Depends(principal),
    db: Session = Depends(get_db),
):
    tenant_get(db, p, Mission, mission_id)
    graph = mission_map(mission_id, p, db)
    node_by_id = {n["id"]: n for n in graph["nodes"]}
    if object_id not in node_by_id:
        raise HTTPException(404, "O objeto não pertence a esta missão.")
    adjacency: dict[str, list[dict[str, Any]]] = {}
    for edge in graph["edges"]:
        adjacency.setdefault(edge["source"], []).append(edge)
    queue = deque([(object_id, 0)])
    visited = {object_id}
    chain_nodes = [node_by_id[object_id]]
    chain_edges = []
    while queue:
        current, level = queue.popleft()
        if level >= depth:
            continue
        for edge in adjacency.get(current, []):
            target = edge["target"]
            chain_edges.append({**edge, "distance": level + 1})
            if target not in visited and target in node_by_id:
                visited.add(target)
                chain_nodes.append(node_by_id[target])
                queue.append((target, level + 1))
    return {"root": node_by_id[object_id], "nodes": chain_nodes, "edges": chain_edges, "max_depth": depth}




def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _decision_confidence(db: Session, p: Principal, decision: Decision, assumptions, constraints, alternatives) -> dict[str, Any]:
    """Explainable decision-support score. It is not a probability of correctness."""
    hypotheses = []
    evidence = []
    if decision.investigation_id:
        hypotheses = db.query(Hypothesis).filter_by(organization_id=p.organization.id, investigation_id=decision.investigation_id).all()
        evidence = db.query(Evidence).filter_by(organization_id=p.organization.id, investigation_id=decision.investigation_id).all()
    source_keys = {((e.source or '').strip().lower() or f'evidence:{e.id}') for e in evidence}
    refuted = [a for a in assumptions if a.status == 'refuted']
    violated = [c for c in constraints if c.status == 'violated']
    has_counter = any(e.direction in ('contradicts','refutes') for e in evidence)
    evidence_coverage = _clamp01(len(evidence) / 4)
    source_diversity = _clamp01(len(source_keys) / 3)
    alternatives_coverage = _clamp01(len(alternatives) / 2)
    contextual_integrity = _clamp01(1 - 0.35 * len(refuted) - 0.25 * len(violated))
    critical_review = 1.0 if has_counter or len(evidence) == 0 else 0.65
    score = round(100 * (
        0.30 * evidence_coverage +
        0.20 * source_diversity +
        0.20 * alternatives_coverage +
        0.20 * contextual_integrity +
        0.10 * critical_review
    ))
    label = 'high' if score >= 75 else ('moderate' if score >= 50 else 'low')
    return {
        'score': score,
        'label': label,
        'meaning': 'Grau de sustentação documentada da decisão; não representa probabilidade de estar correta.',
        'algorithm_version': 'decision-support-0.8',
        'factors': [
            {'code':'evidence_coverage','label':'Cobertura de evidência','value':round(evidence_coverage,3),'detail':f'{len(evidence)} evidência(s) ligadas à investigação.'},
            {'code':'source_diversity','label':'Diversidade de fontes','value':round(source_diversity,3),'detail':f'{len(source_keys)} origem(ns) distinguíveis.'},
            {'code':'alternatives','label':'Alternativas consideradas','value':round(alternatives_coverage,3),'detail':f'{len(alternatives)} alternativa(s) de primeira classe.'},
            {'code':'context_integrity','label':'Integridade dos pressupostos e restrições','value':round(contextual_integrity,3),'detail':f'{len(refuted)} pressuposto(s) refutado(s); {len(violated)} restrição(ões) violada(s).'},
            {'code':'critical_review','label':'Contradição procurada','value':round(critical_review,3),'detail':'Existe evidência contrária registada.' if has_counter else 'Não existe evidência contrária registada.'},
        ],
        'limitations': [
            'O cálculo avalia a estrutura documentada, não a qualidade substantiva da decisão.',
            'Fontes com nomes distintos podem ainda depender da mesma origem primária.',
        ],
    }


@router.get('/missions/{mission_id}/decisions/{decision_id}/workspace')
def decision_workspace(mission_id: str, decision_id: str, p: Principal = Depends(principal), db: Session = Depends(get_db)):
    tenant_get(db, p, Mission, mission_id)
    decision = tenant_get(db, p, Decision, decision_id)
    if decision.mission_id != mission_id:
        raise HTTPException(404, 'A decisão não pertence a esta missão.')
    alternatives = db.query(Alternative).filter_by(organization_id=p.organization.id, decision_id=decision.id).order_by(Alternative.created_at.asc()).all()
    assumptions = db.query(Assumption).filter_by(organization_id=p.organization.id, decision_id=decision.id).order_by(Assumption.created_at.asc()).all()
    constraints = db.query(Constraint).filter_by(organization_id=p.organization.id, decision_id=decision.id).order_by(Constraint.created_at.asc()).all()
    confidence = _decision_confidence(db, p, decision, assumptions, constraints, alternatives)
    graph = mission_map(mission_id, p, db)
    related_edges = [e for e in graph['edges'] if e['source'] == decision.id or e['target'] == decision.id]
    node_by_id = {n['id']:n for n in graph['nodes']}
    foundations=[]
    for edge in related_edges:
        other_id = edge['source'] if edge['target'] == decision.id else edge['target']
        other=node_by_id.get(other_id)
        if other:
            foundations.append({'relation':edge['type'],'direction':'incoming' if edge['target']==decision.id else 'outgoing','object':other})
    selected = next((a for a in alternatives if a.status == 'selected'), None)
    risks = decision.risks if isinstance(decision.risks, list) else []
    review_required = any(a.status == 'refuted' for a in assumptions) or any(c.status == 'violated' for c in constraints)
    return {
        'decision': {
            'id':decision.id,'title':decision.title,'rationale':decision.rationale,
            'expected_outcome':decision.expected_outcome,'decided_at':decision.decided_at,
            'investigation_id':decision.investigation_id,
        },
        'confidence': confidence,
        'alternatives': [{'id':a.id,'title':a.title,'description':a.description,'status':a.status,'rejection_reason':a.rejection_reason,'criteria':a.criteria,'limitations':a.limitations} for a in alternatives],
        'selected_alternative_id': selected.id if selected else None,
        'assumptions': [{'id':a.id,'code':a.code,'statement':a.statement,'status':a.status,'limitations':a.limitations,'valid_to':a.valid_to} for a in assumptions],
        'constraints': [{'id':c.id,'code':c.code,'statement':c.statement,'status':c.status,'limitations':c.limitations,'valid_to':c.valid_to} for c in constraints],
        'risks': risks,
        'foundations': foundations,
        'review': {
            'required': review_required,
            'reason': 'A decisão depende de pressupostos refutados ou restrições violadas.' if review_required else 'Não existe gatilho estrutural crítico aberto.',
            'condition': 'Não declarada no modelo atual.'
        },
        'available_actions': ['review','impact','timeline'],
    }


@router.get("/missions/{mission_id}/focus/{object_type}/{object_id}")
def focus_object(object_type: str, object_id: str, mission_id: str, p: Principal = Depends(principal), db: Session = Depends(get_db)):
    tenant_get(db, p, Mission, mission_id)
    model = MODEL_MAP.get(object_type)
    if not model:
        raise HTTPException(404, "Tipo de objeto não suportado.")
    obj = tenant_get(db, p, model, object_id)
    if not belongs_to_mission(obj, mission_id, db, p):
        raise HTTPException(404, "O objeto não pertence a esta missão.")
    graph = mission_map(mission_id, p, db)
    node = next((n for n in graph["nodes"] if n["id"] == object_id), None)
    relations = [e for e in graph["edges"] if e["source"] == object_id or e["target"] == object_id]
    affected = [e for e in graph["edges"] if e["source"] == object_id]
    limitations = getattr(obj, "limitations", "") or "Não foram declaradas limitações adicionais neste objeto."
    return {
        "object": node or object_view(object_type, obj),
        "summary": str(getattr(obj, LABEL_FIELD[object_type], "")),
        "limitations": limitations,
        "relations": relations,
        "affected_count": len(affected),
        "available_actions": ["impact", "timeline", "review"] if object_type == "decision" else ["impact", "timeline"],
    }


@router.get("/missions/{mission_id}/timeline")
def mission_timeline(mission_id: str, p: Principal = Depends(principal), db: Session = Depends(get_db)):
    tenant_get(db, p, Mission, mission_id)
    nodes = mission_nodes(db, p, mission_id)
    moments = []
    type_titles = {
        "mission": "A missão foi criada",
        "investigation": "Foi aberta uma investigação",
        "observation": "A situação tornou-se visível",
        "evidence": "Foi acrescentada evidência",
        "hypothesis": "Foi formulada uma hipótese",
        "assumption": "Foi declarado um pressuposto",
        "decision": "Foi tomada uma decisão",
        "implementation": "A implementação avançou",
        "outcome": "Foi observado um resultado",
        "learning": "Foi preservada uma aprendizagem",
    }
    for node in nodes:
        if not node.get("created_at"):
            continue
        moments.append({
            "id": f"{node['type']}:{node['id']}",
            "object_id": node["id"],
            "object_type": node["type"],
            "title": type_titles.get(node["type"], "A missão foi atualizada"),
            "summary": node["label"],
            "occurred_at": node["created_at"],
            "significance": "high" if node["type"] in ("decision", "outcome", "learning") else "normal",
        })
    logs = db.query(AuditLog).filter_by(organization_id=p.organization.id).order_by(AuditLog.created_at.asc()).all()
    node_ids = {n["id"] for n in nodes}
    for log in logs:
        if log.resource_id in node_ids and log.action in ("refute", "state_change", "reuse", "posterior_recalculation"):
            moments.append({
                "id": f"audit:{log.id}",
                "object_id": log.resource_id,
                "object_type": log.resource_type,
                "title": {
                    "refute": "Nova evidência alterou o fundamento",
                    "state_change": "O estado foi revisto",
                    "reuse": "Uma aprendizagem foi reutilizada",
                    "posterior_recalculation": "A confiança entre hipóteses foi atualizada",
                }.get(log.action, "A missão foi atualizada"),
                "summary": log.action.replace("_", " "),
                "occurred_at": log.created_at,
                "significance": "high" if log.action == "refute" else "normal",
            })
    moments.sort(key=lambda x: x["occurred_at"] or datetime.min.replace(tzinfo=timezone.utc))
    return {"mission_id": mission_id, "mode": "logical", "moments": moments}


def _experience_snapshot(mission_id: str, p: Principal, db: Session) -> dict[str, Any]:
    """Return the three projections that must remain coherent after a domain change."""
    return {
        "mission_id": mission_id,
        "generated_at": datetime.now(timezone.utc),
        "entry": mission_entry(mission_id, p, db),
        "map": mission_map(mission_id, p, db),
        "timeline": mission_timeline(mission_id, p, db),
    }


@router.get("/missions/{mission_id}/snapshot")
def mission_snapshot(mission_id: str, p: Principal = Depends(principal), db: Session = Depends(get_db)):
    tenant_get(db, p, Mission, mission_id)
    return _experience_snapshot(mission_id, p, db)


GUIDANCE = {
    "understand": [
        {"id": "UND.OBS.001", "question": "O que aconteceu?", "purpose": "Separar observação de interpretação.", "creates": "observation"},
        {"id": "UND.METHOD.001", "question": "Como foi observado?", "purpose": "Preservar método e origem.", "creates": "observation"},
        {"id": "UND.LIMIT.001", "question": "O que esta observação não permite concluir?", "purpose": "Tornar a limitação explícita.", "creates": "observation"},
    ],
    "investigate": [
        {"id": "INV.Q.001", "question": "O que pretende explicar?", "purpose": "Definir a pergunta investigável.", "creates": "investigation"},
        {"id": "INV.HYP.001", "question": "Que explicações podem existir?", "purpose": "Criar hipóteses concorrentes.", "creates": "hypothesis"},
        {"id": "INV.COUNTER.001", "question": "O que poderia contrariar esta hipótese?", "purpose": "Evitar conclusão prematura.", "creates": "evidence"},
    ],
    "decide": [
        {"id": "DEC.Q.001", "question": "O que precisa de ser decidido?", "purpose": "Definir o compromisso.", "creates": "decision"},
        {"id": "DEC.ALT.001", "question": "Que alternativas foram consideradas?", "purpose": "Preservar opções e rejeições.", "creates": "alternative"},
        {"id": "DEC.REVIEW.001", "question": "O que faria rever esta decisão?", "purpose": "Definir condição de revisão.", "creates": "decision"},
    ],
    "review": [
        {"id": "REV.CHANGE.001", "question": "O que mudou?", "purpose": "Identificar o gatilho.", "creates": "relation"},
        {"id": "REV.IMPACT.001", "question": "Que parte do fundamento é afetada?", "purpose": "Avaliar impacto.", "creates": "relation"},
        {"id": "REV.RESULT.001", "question": "A decisão continua justificável?", "purpose": "Documentar a revisão humana.", "creates": "decision"},
    ],
    "learn": [
        {"id": "LRN.OBS.001", "question": "O que aconteceu?", "purpose": "Partir do resultado observado.", "creates": "learning"},
        {"id": "LRN.NON.001", "question": "O que não conseguimos concluir?", "purpose": "Limitar a aprendizagem.", "creates": "learning"},
        {"id": "LRN.REUSE.001", "question": "Em que condições pode ser reutilizado?", "purpose": "Preservar contexto de reutilização.", "creates": "learning"},
    ],
}


@router.get("/missions/{mission_id}/guidance/{intention}")
def guided_questions(intention: str, mission_id: str, p: Principal = Depends(principal), db: Session = Depends(get_db)):
    tenant_get(db, p, Mission, mission_id)
    questions = GUIDANCE.get(intention)
    if not questions:
        raise HTTPException(404, "Intenção desconhecida.")
    return {"mission_id": mission_id, "intention": intention, "version": "sees-guidance-0.2", "questions": questions}


def _split_items(value: str) -> list[str]:
    """Split a human answer into a small, deterministic list without NLP inference."""
    raw = value.replace("\r", "\n").replace(";", "\n")
    items = [part.strip(" -•\t") for part in raw.split("\n") if part.strip(" -•\t")]
    return items[:10] or [value.strip()]


def _materialize_guided_session(db: Session, p: Principal, row: GuidedReasoningSession) -> list[dict[str, str]]:
    """Create auditable domain objects only after the user completes the guided flow.

    The mapping is deterministic and deliberately conservative: no generative inference,
    no causal claims, and every created object carries an explicit limitation.
    """
    existing = []
    for answer in row.answers or []:
        existing.extend(answer.get("materialized_objects", []))
    if existing:
        return existing

    by_id = {item["question_id"]: item["answer"].strip() for item in (row.answers or [])}
    org_id = p.organization.id
    user_id = p.user.id if p.user else None
    created: list[tuple[str, Any]] = []

    def add(kind: str, obj: Any):
        db.add(obj); db.flush(); created.append((kind, obj)); return obj

    if row.intention == "understand":
        add("observation", Observation(
            organization_id=org_id, mission_id=row.mission_id,
            title=by_id["UND.OBS.001"][:240], method=by_id["UND.METHOD.001"],
            source="guided_reasoning", limitations=by_id["UND.LIMIT.001"],
            payload={"guided_session_id": row.id}, created_by=user_id,
        ))

    elif row.intention == "investigate":
        question = by_id["INV.Q.001"]
        inv = add("investigation", Investigation(
            organization_id=org_id, mission_id=row.mission_id, title=question[:240], question=question,
            owner_user_id=user_id, limitations="Investigação criada por raciocínio guiado; não estabelece causalidade.",
        ))
        hypotheses = []
        for statement in _split_items(by_id["INV.HYP.001"]):
            hypotheses.append(add("hypothesis", Hypothesis(
                organization_id=org_id, investigation_id=inv.id, statement=statement,
                prior=1.0 / max(1, len(_split_items(by_id["INV.HYP.001"]))),
                limitations="Hipótese proposta pelo utilizador; ainda não testada.",
            )))
        proposal = add("evidence_proposal", EvidenceProposal(
            organization_id=org_id, investigation_id=inv.id,
            title=by_id["INV.COUNTER.001"][:240], description=by_id["INV.COUNTER.001"],
            expected_effects={h.id: -1 for h in hypotheses},
            limitations="Proposta de evidência contrária; método, viabilidade e efeito ainda requerem validação.",
        ))
        for h in hypotheses:
            add("relation", Relation(organization_id=org_id, source_type="investigation", source_id=inv.id,
                target_type="hypothesis", target_id=h.id, relation_type="considers",
                explanation="Hipótese formulada na investigação guiada."))
        add("relation", Relation(organization_id=org_id, source_type="evidence_proposal", source_id=proposal.id,
            target_type="investigation", target_id=inv.id, relation_type="informs",
            explanation="Recolha proposta para contrariar ou discriminar hipóteses."))

    elif row.intention == "decide":
        decision = add("decision", Decision(
            organization_id=org_id, mission_id=row.mission_id, title=by_id["DEC.Q.001"][:240],
            rationale="Decisão estruturada por raciocínio guiado; fundamento detalhado ainda deve ser confirmado.",
            risks=[{"review_condition": by_id["DEC.REVIEW.001"]}], decided_by=user_id,
        ))
        for title in _split_items(by_id["DEC.ALT.001"]):
            alt = add("alternative", Alternative(
                organization_id=org_id, mission_id=row.mission_id, decision_id=decision.id,
                title=title[:240], description=title, limitations="Alternativa registada sem avaliação comparativa completa.",
            ))
            add("relation", Relation(organization_id=org_id, source_type="alternative", source_id=alt.id,
                target_type="decision", target_id=decision.id, relation_type="considered_by",
                explanation="Alternativa considerada no fluxo guiado de decisão."))

    elif row.intention == "review":
        observation = add("observation", Observation(
            organization_id=org_id, mission_id=row.mission_id, title=by_id["REV.CHANGE.001"][:240],
            method="Revisão humana guiada", source="guided_reasoning",
            limitations=by_id["REV.IMPACT.001"], payload={"review_conclusion": by_id["REV.RESULT.001"], "guided_session_id": row.id},
            created_by=user_id,
        ))
        # A review is preserved as evidence of human assessment, not as an automatic mutation of a prior decision.
        add("relation", Relation(organization_id=org_id, source_type="guided_reasoning_session", source_id=row.id,
            target_type="observation", target_id=observation.id, relation_type="produced",
            explanation="A sessão documentou uma alteração e a respetiva avaliação humana."))

    elif row.intention == "learn":
        add("learning", Learning(
            organization_id=org_id, statement=by_id["LRN.OBS.001"], status="emerging",
            confidence=0.0, limitations=(
                f"Não conclusões: {by_id['LRN.NON.001']} | "
                f"Condições de reutilização: {by_id['LRN.REUSE.001']}"
            ),
        ))

    result = [{"type": kind, "id": obj.id} for kind, obj in created if kind != "relation"]
    for kind, obj in created:
        if kind == "relation":
            continue
        add("relation", Relation(organization_id=org_id, source_type="guided_reasoning_session", source_id=row.id,
            target_type=kind, target_id=obj.id, relation_type="materialized",
            explanation="Objeto criado de forma determinística a partir de respostas confirmadas pelo utilizador."))
        record_audit(db, org_id, user_id, "guided_session.materialized", kind, obj.id,
                     after={"guided_session_id": row.id, "intention": row.intention})
    return result


class GuidedSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intention: str

class GuidedAnswerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: str
    answer: str = Field(min_length=1, max_length=10000)

class GuidedAnswerUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str = Field(min_length=1, max_length=10000)

def _guided_preview(row: GuidedReasoningSession) -> list[dict[str, Any]]:
    """Return the objects that will be created, without writing to the database."""
    by_id = {item["question_id"]: item["answer"].strip() for item in (row.answers or [])}
    if row.intention == "understand":
        return [{"type": "observation", "title": by_id.get("UND.OBS.001", ""), "details": {"method": by_id.get("UND.METHOD.001", ""), "limitations": by_id.get("UND.LIMIT.001", "")}}]
    if row.intention == "investigate":
        hypotheses = _split_items(by_id.get("INV.HYP.001", ""))
        return [
            {"type": "investigation", "title": by_id.get("INV.Q.001", ""), "details": {"hypotheses": len(hypotheses)}},
            *[{"type": "hypothesis", "title": item, "details": {"status": "proposed"}} for item in hypotheses],
            {"type": "evidence_proposal", "title": by_id.get("INV.COUNTER.001", ""), "details": {"purpose": "contradict_or_discriminate"}},
        ]
    if row.intention == "decide":
        alternatives = _split_items(by_id.get("DEC.ALT.001", ""))
        return [
            {"type": "decision", "title": by_id.get("DEC.Q.001", ""), "details": {"review_condition": by_id.get("DEC.REVIEW.001", "")}},
            *[{"type": "alternative", "title": item, "details": {"status": "considered"}} for item in alternatives],
        ]
    if row.intention == "review":
        return [{"type": "observation", "title": by_id.get("REV.CHANGE.001", ""), "details": {"affected_basis": by_id.get("REV.IMPACT.001", ""), "human_conclusion": by_id.get("REV.RESULT.001", "")}}]
    if row.intention == "learn":
        return [{"type": "learning", "title": by_id.get("LRN.OBS.001", ""), "details": {"non_conclusions": by_id.get("LRN.NON.001", ""), "reuse_conditions": by_id.get("LRN.REUSE.001", "")}}]
    return []


def _session_view(row: GuidedReasoningSession) -> dict[str, Any]:
    questions = GUIDANCE.get(row.intention, [])
    return {
        "id": row.id, "mission_id": row.mission_id, "intention": row.intention,
        "version": row.guidance_version, "status": row.status,
        "current_index": row.current_index, "answers": row.answers or [],
        "preview_objects": _guided_preview(row) if row.status == "awaiting_confirmation" else [],
        "materialized_objects": [obj for ans in (row.answers or []) for obj in ans.get("materialized_objects", [])],
        "questions": questions,
        "current_question": questions[row.current_index] if row.status == "active" and row.current_index < len(questions) else None,
        "started_at": row.started_at, "updated_at": row.updated_at, "completed_at": row.completed_at,
    }

@router.post("/missions/{mission_id}/guided-sessions")
def create_guided_session(mission_id: str, body: GuidedSessionCreate, p: Principal = Depends(principal), db: Session = Depends(get_db)):
    tenant_get(db, p, Mission, mission_id)
    if body.intention not in GUIDANCE:
        raise HTTPException(422, "Intenção desconhecida.")
    row = GuidedReasoningSession(organization_id=p.organization.id, mission_id=mission_id, user_id=p.user.id if p.user else None, intention=body.intention)
    db.add(row); db.flush()
    record_audit(db,p.organization.id,p.user.id if p.user else None,"guided_session.created","guided_reasoning_session",row.id,after={"mission_id":mission_id,"intention":body.intention})
    db.commit(); db.refresh(row)
    return _session_view(row)

@router.get("/guided-sessions/{session_id}")
def get_guided_session(session_id: str, p: Principal = Depends(principal), db: Session = Depends(get_db)):
    row=tenant_get(db,p,GuidedReasoningSession,session_id)
    return _session_view(row)

@router.post("/guided-sessions/{session_id}/answers")
def answer_guided_session(session_id: str, body: GuidedAnswerCreate, p: Principal = Depends(principal), db: Session = Depends(get_db)):
    row=tenant_get(db,p,GuidedReasoningSession,session_id)
    if row.status != "active": raise HTTPException(409,"A sessão já não está ativa.")
    questions=GUIDANCE.get(row.intention,[])
    if row.current_index >= len(questions): raise HTTPException(409,"A sessão já não possui perguntas pendentes.")
    expected=questions[row.current_index]
    if body.question_id != expected["id"]: raise HTTPException(409,"A resposta não corresponde à pergunta atual.")
    answers=list(row.answers or [])
    answers.append({"question_id":body.question_id,"answer":body.answer,"answered_at":datetime.now(timezone.utc).isoformat()})
    row.answers=answers; row.current_index += 1; row.updated_at=datetime.now(timezone.utc)
    if row.current_index >= len(questions):
        # Answers are complete, but no domain object exists until the user confirms the preview.
        row.status="awaiting_confirmation"
    record_audit(db,p.organization.id,p.user.id if p.user else None,"guided_session.answered","guided_reasoning_session",row.id,after={"question_id":body.question_id,"status":row.status})
    db.commit(); db.refresh(row)
    view = _session_view(row)
    return view

@router.patch("/guided-sessions/{session_id}/answers/{question_id}")
def update_guided_answer(session_id: str, question_id: str, body: GuidedAnswerUpdate, p: Principal = Depends(principal), db: Session = Depends(get_db)):
    row=tenant_get(db,p,GuidedReasoningSession,session_id)
    if row.status != "awaiting_confirmation":
        raise HTTPException(409,"As respostas só podem ser editadas antes da confirmação final.")
    answers=[dict(item) for item in (row.answers or [])]
    target=next((item for item in answers if item.get("question_id")==question_id),None)
    if not target:
        raise HTTPException(404,"Resposta não encontrada.")
    before=target.get("answer")
    target["answer"]=body.answer
    target["updated_at"]=datetime.now(timezone.utc).isoformat()
    row.answers=answers; row.updated_at=datetime.now(timezone.utc)
    flag_modified(row,"answers")
    record_audit(db,p.organization.id,p.user.id if p.user else None,"guided_session.answer_updated","guided_reasoning_session",row.id,before={"question_id":question_id,"answer":before},after={"question_id":question_id,"answer":body.answer})
    db.commit(); db.refresh(row)
    return _session_view(row)

@router.post("/guided-sessions/{session_id}/confirm")
def confirm_guided_session(session_id: str, p: Principal = Depends(principal), db: Session = Depends(get_db)):
    row=tenant_get(db,p,GuidedReasoningSession,session_id)
    if row.status == "completed":
        view=_session_view(row); view["experience_snapshot"]=_experience_snapshot(row.mission_id,p,db); return view
    if row.status != "awaiting_confirmation":
        raise HTTPException(409,"A sessão ainda não está pronta para confirmação.")
    materialized=_materialize_guided_session(db,p,row)
    answers=[dict(item) for item in (row.answers or [])]
    if answers:
        answers[-1]["materialized_objects"]=materialized
    row.answers=answers; flag_modified(row,"answers")
    row.status="completed"; row.completed_at=datetime.now(timezone.utc); row.updated_at=datetime.now(timezone.utc)
    record_audit(db,p.organization.id,p.user.id if p.user else None,"guided_session.confirmed","guided_reasoning_session",row.id,after={"intention":row.intention,"materialized_objects":materialized})
    db.commit(); db.refresh(row)
    view=_session_view(row); view["experience_snapshot"]=_experience_snapshot(row.mission_id,p,db)
    return view
