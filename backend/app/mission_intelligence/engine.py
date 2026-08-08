from __future__ import annotations

from collections import Counter, deque
from typing import Iterable

from .contracts import (
    AlternativeView,
    ConfidenceFactor,
    ConfidenceLevel,
    DeterministicReport,
    Gap,
    MissionDocumentV13,
    MissionStatus,
    MissionTrend,
    RecordKind,
)


ENGINE_VERSION = "mission-intelligence-deterministic-1.0"


def _contains_any(text: str, needles: Iterable[str]) -> bool:
    value = text.casefold()
    return any(needle.casefold() in value for needle in needles)


def _active(record) -> bool:
    return record.state not in {"resolved", "refuted", "rejected", "completed"}


def propagate_review(
    document: MissionDocumentV13,
    root_ids: set[str],
    *,
    max_depth: int = 8,
) -> set[str]:
    """Return downstream records that require review after a material change."""

    adjacency: dict[str, list[str]] = {}
    for relation in document.relations:
        adjacency.setdefault(relation.source_id, []).append(relation.target_id)
    queue = deque((root, 0) for root in root_ids)
    visited = set(root_ids)
    while queue:
        current, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for target in adjacency.get(current, []):
            if target not in visited:
                visited.add(target)
                queue.append((target, depth + 1))
    return visited


def analyze_mission(document: MissionDocumentV13) -> DeterministicReport:
    records = document.records
    by_kind = {kind: [item for item in records if item.kind == kind] for kind in RecordKind}
    counts = Counter(item.kind.value for item in records)

    observations = by_kind[RecordKind.OBSERVATION]
    evidence = by_kind[RecordKind.EVIDENCE]
    assumptions = by_kind[RecordKind.ASSUMPTION]
    constraints = by_kind[RecordKind.CONSTRAINT]
    alternatives = [item for item in by_kind[RecordKind.ALTERNATIVE] if item.state != "rejected"]
    decisions = by_kind[RecordKind.DECISION]
    actions = by_kind[RecordKind.ACTION]
    outcomes = by_kind[RecordKind.OUTCOME]
    learnings = by_kind[RecordKind.LEARNING]

    unresolved_assumptions = [item for item in assumptions if _active(item)]
    unresolved_constraints = [item for item in constraints if _active(item)]
    violated_constraints = [item for item in constraints if item.state == "violated"]
    refuted_assumptions = [item for item in assumptions if item.state == "refuted"]
    selected_decisions = [item for item in decisions if item.state in {"selected", "completed"}]

    # Only canonical records can establish a baseline. Free text supplied in the
    # analysis form remains contextual and must not silently become evidence.
    evidence_text = " ".join(
        f"{item.title} {item.description}" for item in observations + evidence
    )
    has_baseline = _contains_any(
        evidence_text,
        ["linha de base medida", "baseline measured", "série temporal de base"],
    )

    auditable = [
        item
        for item in observations + evidence
        if item.provenance.source and item.provenance.method and item.provenance.limitations
    ]
    evidence_population = observations + evidence
    provenance_ratio = len(auditable) / len(evidence_population) if evidence_population else 0.0

    if evidence:
        evidence_assessment = "strong" if provenance_ratio >= 0.8 else "partial"
        evidence_value = 1.0 if evidence_assessment == "strong" else 0.65
    elif len(observations) >= 2:
        evidence_assessment = "partial"
        evidence_value = 0.55
    elif observations:
        evidence_assessment = "weak"
        evidence_value = 0.25
    else:
        evidence_assessment = "weak"
        evidence_value = 0.0

    assumption_value = (
        (len(assumptions) - len(unresolved_assumptions)) / len(assumptions)
        if assumptions else 0.4
    )
    constraint_value = (
        (len(constraints) - len(unresolved_constraints)) / len(constraints)
        if constraints else 0.35
    )
    alternative_value = min(len(alternatives) / 3.0, 1.0)
    decision_value = 1.0 if selected_decisions else (0.35 if decisions else 0.0)
    confidence_score = (
        evidence_value * 0.30
        + assumption_value * 0.20
        + constraint_value * 0.20
        + alternative_value * 0.15
        + decision_value * 0.15
    )
    if confidence_score >= 0.70:
        decision_confidence = ConfidenceLevel.HIGH
    elif confidence_score >= 0.30:
        decision_confidence = ConfidenceLevel.MODERATE
    else:
        decision_confidence = ConfidenceLevel.LOW

    factors = [
        ConfidenceFactor(
            factor="evidence",
            assessment=evidence_assessment,
            explanation=(
                "Existem registos com origem, método e limitações suficientes."
                if evidence_assessment == "strong"
                else "A base observacional é útil, mas não resolve todas as lacunas materiais."
                if evidence_assessment == "partial"
                else "A base observacional é insuficiente para sustentar uma escolha."
            ),
        ),
        ConfidenceFactor(
            factor="assumptions",
            assessment="strong" if assumption_value == 1 else "partial" if assumption_value >= 0.5 else "weak",
            explanation=f"{len(unresolved_assumptions)} pressuposto(s) permanece(m) por resolver.",
        ),
        ConfidenceFactor(
            factor="constraints",
            assessment="strong" if constraint_value == 1 else "partial" if constraint_value >= 0.5 else "weak",
            explanation=f"{len(unresolved_constraints)} restrição(ões) permanece(m) por avaliar.",
        ),
        ConfidenceFactor(
            factor="alternatives",
            assessment="strong" if len(alternatives) >= 3 else "partial" if alternatives else "weak",
            explanation=f"{len(alternatives)} alternativa(s) ativa(s) está(ão) explicitamente representada(s).",
        ),
        ConfidenceFactor(
            factor="decision_readiness",
            assessment="strong" if selected_decisions else "partial" if decisions else "weak",
            explanation=(
                "Existe uma decisão selecionada."
                if selected_decisions
                else "Existe uma decisão em aberto, sem alternativa selecionada."
                if decisions
                else "Ainda não existe um objeto de decisão."
            ),
        ),
    ]

    gaps: list[Gap] = []
    if unresolved_assumptions:
        gaps.append(
            Gap(
                code="MI-ASSUMPTIONS-OPEN",
                severity="high",
                title="Pressupostos materiais por verificar",
                explanation="Uma decisão apoiada nestes pressupostos pode perder sustentação se algum for refutado.",
                affected_ids=[item.canonical_id for item in unresolved_assumptions],
                evidence_needed="Testes ou fontes independentes dirigidos a cada pressuposto.",
            )
        )
    if unresolved_constraints:
        gaps.append(
            Gap(
                code="MI-CONSTRAINTS-OPEN",
                severity="high",
                title="Restrições ainda não avaliadas",
                explanation="A legitimidade ou viabilidade da intervenção permanece condicionada.",
                affected_ids=[item.canonical_id for item in unresolved_constraints],
                evidence_needed="Confirmação documental junto dos titulares e entidades competentes.",
            )
        )
    if not has_baseline and not outcomes:
        gaps.append(
            Gap(
                code="MI-NO-BASELINE",
                severity="medium",
                title="Linha de base não demonstrada",
                explanation="Sem medição anterior, um resultado futuro não poderá ser atribuído rigorosamente à intervenção.",
                evidence_needed="Definir variáveis, método, frequência e período de medição antes da execução.",
            )
        )
    if outcomes and not has_baseline:
        gaps.append(
            Gap(
                code="MI-OUTCOME-NO-BASELINE",
                severity="high",
                title="Resultado sem linha de base comparável",
                explanation="O resultado existe, mas a atribuição causal não é sustentada.",
                affected_ids=[item.canonical_id for item in outcomes],
                evidence_needed="Baseline comparável ou desenho alternativo de atribuição com limitações explícitas.",
            )
        )
    if not alternatives:
        gaps.append(
            Gap(
                code="MI-NO-ALTERNATIVES",
                severity="high",
                title="Alternativas não estruturadas",
                explanation="Não é possível auditar uma escolha quando as opções consideradas não estão representadas.",
                evidence_needed="Registar pelo menos a opção de não agir e as alternativas materialmente viáveis.",
            )
        )
    if evidence_population and provenance_ratio < 0.8:
        missing = [item.canonical_id for item in evidence_population if item not in auditable]
        gaps.append(
            Gap(
                code="MI-PROVENANCE-INCOMPLETE",
                severity="medium",
                title="Proveniência incompleta",
                explanation="Alguns registos não preservam simultaneamente origem, método e limitações.",
                affected_ids=missing,
                evidence_needed="Completar os metadados de proveniência antes da revisão institucional.",
            )
        )
    if refuted_assumptions:
        impacted = propagate_review(document, {item.canonical_id for item in refuted_assumptions})
        gaps.append(
            Gap(
                code="MI-REFUTATION-REVIEW",
                severity="high",
                title="Refutação exige revisão a jusante",
                explanation="Os objetos dependentes não são apagados; ficam sinalizados para reavaliação.",
                affected_ids=sorted(impacted),
                evidence_needed="Rever cada dependência e registar a decisão de manter, substituir ou retirar.",
            )
        )

    if violated_constraints or (outcomes and not has_baseline):
        mission_status = MissionStatus.CRITICAL
    elif any(gap.severity == "high" for gap in gaps):
        mission_status = MissionStatus.REQUIRES_ATTENTION
    elif outcomes and learnings and selected_decisions:
        mission_status = MissionStatus.COMPLETED
    else:
        mission_status = MissionStatus.ON_TRACK

    mission_trend = MissionTrend.NOT_EVALUABLE

    next_actions: list[str] = []
    if not has_baseline and not outcomes:
        next_actions.append("Criar e documentar a linha de base antes de qualquer intervenção")
    if unresolved_constraints:
        next_actions.append("confirmar licenciamento, titularidade e demais restrições aplicáveis")
    if unresolved_assumptions:
        next_actions.append("definir testes dirigidos aos pressupostos materiais")
    if not alternatives:
        next_actions.append("estruturar alternativas comparáveis, incluindo não agir")
    if not next_actions:
        next_actions.append("submeter a cadeia atual a revisão humana documentada")
    next_decision = "; ".join(next_actions[:3]) + "."

    if outcomes and not has_baseline:
        principal_risk = "Confundir um resultado observado com efeito atribuível à intervenção."
    elif unresolved_constraints:
        principal_risk = "Selecionar ou executar uma alternativa antes de confirmar a legitimidade e as condições da intervenção."
    elif not has_baseline:
        principal_risk = "Intervir antes de medir e perder a capacidade de interpretar o resultado futuro."
    else:
        principal_risk = "Aumentar a confiança declarada para além do que os registos auditáveis permitem."

    if selected_decisions:
        headline = "A decisão existe, mas a sua sustentação deve permanecer sob revisão."
    elif decisions:
        headline = "Ainda não existe base suficiente para selecionar uma alternativa."
    else:
        headline = "A missão ainda não chegou ao ponto de decisão."

    summary = (
        f"A missão contém {len(observations)} observação(ões), {len(evidence)} evidência(s), "
        f"{len(alternatives)} alternativa(s), {len(unresolved_assumptions)} pressuposto(s) por resolver "
        f"e {len(unresolved_constraints)} restrição(ões) por avaliar. "
        "O resultado preserva estes limites e não transforma ausência de informação em certeza."
    )

    non_inferences = [
        "Mission Trend não é avaliável sem pelo menos dois estados temporais comparáveis.",
    ]
    if not selected_decisions:
        non_inferences.append("Nenhuma alternativa é apresentada como selecionada.")
    if not actions:
        non_inferences.append("Não se infere execução sem um registo de ação.")
    if not outcomes:
        non_inferences.append("Não se infere resultado nem impacto sem observação posterior.")
    if not has_baseline:
        non_inferences.append("Não se infere atribuição causal sem linha de base comparável.")

    return DeterministicReport(
        methodology_version=ENGINE_VERSION,
        mission_status=mission_status,
        mission_trend=mission_trend,
        decision_confidence=decision_confidence,
        confidence_factors=factors,
        headline=headline,
        summary=summary,
        principal_risk=principal_risk,
        next_decision=next_decision,
        gaps=gaps,
        assumptions_to_test=[
            f"{item.canonical_id} — {item.title}" for item in unresolved_assumptions
        ],
        alternatives=[
            AlternativeView(
                canonical_id=item.canonical_id,
                title=item.title,
                state=item.state,
                description=item.description,
            )
            for item in alternatives
        ],
        non_inferences=non_inferences,
        counts=dict(sorted(counts.items())),
    )
