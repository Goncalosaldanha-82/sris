from __future__ import annotations

from collections import Counter, deque
from .contracts import (
    AlternativeView,
    ConfidenceFactor,
    ConfidenceLevel,
    ContextAssessment,
    ContextDossier,
    DeterministicReport,
    Gap,
    MissionDocumentV13,
    MissionStatus,
    MissionTrend,
    RecordKind,
)


ENGINE_VERSION = "mission-intelligence-deterministic-1.2"


def _active(record) -> bool:
    return record.state not in {"resolved", "refuted", "rejected", "completed"}


def _count_phrase(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _assessment(value: float) -> str:
    if value >= 0.8:
        return "strong"
    if value >= 0.5:
        return "partial"
    return "weak"


def _baseline_requirement(document: MissionDocumentV13) -> str:
    requirements = document.metadata.get("analysis_requirements") or {}
    baseline = requirements.get("baseline") or {}
    value = str(baseline.get("applicability") or "undetermined")
    return value if value in {"required", "not_applicable", "undetermined"} else "undetermined"


def _has_explicit_baseline(document: MissionDocumentV13) -> bool:
    """Return true only for an explicit canonical baseline marker.

    A phrase in free text is never enough. A baseline must be represented by a
    record whose metadata declares its role, or by an explicit relation in the
    canonical graph.
    """

    if any(
        record.metadata.get("is_baseline") is True
        or record.metadata.get("measurement_role") == "baseline"
        for record in document.records
    ):
        return True
    return any(
        relation.relation_type in {"establishes_baseline", "is_baseline_for"}
        for relation in document.relations
    )


def _context_research_required(document: MissionDocumentV13) -> bool:
    requirements = document.metadata.get("analysis_requirements") or {}
    context_requirement = requirements.get("context_research") or {}
    return context_requirement.get("required") is True


def _context_assessment(document: MissionDocumentV13) -> ContextAssessment:
    required = _context_research_required(document)
    raw = document.metadata.get("context_dossier")
    if not raw:
        return ContextAssessment(
            status="not_started" if required else "not_required",
            boundary=(
                "A envolvente da missão ainda não foi investigada de forma estruturada."
                if required
                else "A investigação contextual não foi definida como requisito desta análise."
            ),
        )
    try:
        dossier = ContextDossier.model_validate(raw)
    except ValueError:
        return ContextAssessment(
            status="not_started",
            boundary=(
                "Existe um dossier contextual inválido; nenhum dos seus conteúdos foi "
                "usado como suporte da análise."
            ),
        )
    supported = sum(
        claim.epistemic_status in {"supported", "partially_supported"}
        for claim in dossier.claims
    )
    hypotheses = sum(claim.epistemic_status == "hypothesis" for claim in dossier.claims)
    unverified = sum(claim.epistemic_status == "unverified" for claim in dossier.claims)
    critical_gaps = sum(gap.priority in {"critical", "high"} for gap in dossier.gaps)
    return ContextAssessment(
        status=dossier.research_status,
        domains=dossier.domains,
        source_count=len(dossier.sources),
        supported_claim_count=supported,
        hypothesis_count=hypotheses,
        unverified_claim_count=unverified,
        critical_gap_count=critical_gaps,
        synthesis=dossier.synthesis,
        boundary=(
            "O dossier contextual organiza fontes, alegações e lacunas; não converte "
            "proximidade geográfica, tradição oral ou plausibilidade histórica em causalidade."
        ),
    )


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
    # Rejected alternatives remain part of the decision record. Removing them
    # would erase precisely the discarded options that SRIS must preserve.
    alternatives = by_kind[RecordKind.ALTERNATIVE]
    rejected_alternatives = [item for item in alternatives if item.state == "rejected"]
    decisions = by_kind[RecordKind.DECISION]
    actions = by_kind[RecordKind.ACTION]
    outcomes = by_kind[RecordKind.OUTCOME]
    learnings = by_kind[RecordKind.LEARNING]

    unresolved_assumptions = [item for item in assumptions if _active(item)]
    unresolved_constraints = [item for item in constraints if _active(item)]
    violated_constraints = [item for item in constraints if item.state == "violated"]
    refuted_assumptions = [item for item in assumptions if item.state == "refuted"]
    selected_decisions = [item for item in decisions if item.state in {"selected", "completed"}]

    # Only an explicit canonical marker can establish a baseline. Free text
    # supplied in the analysis form remains contextual and must not silently
    # become evidence. Baseline requirements are mission-specific: a grant
    # application, for example, must not inherit a field-intervention rule.
    baseline_requirement = _baseline_requirement(document)
    baseline_required = baseline_requirement == "required"
    has_baseline = _has_explicit_baseline(document)
    context_assessment = _context_assessment(document)

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
        if assumptions else None
    )
    constraint_value = (
        (len(constraints) - len(unresolved_constraints)) / len(constraints)
        if constraints else None
    )
    alternative_value = min(len(alternatives) / 3.0, 1.0)
    decision_value = 1.0 if selected_decisions else (0.35 if decisions else 0.0)
    confidence_components = [
        (evidence_value, 0.30),
        (alternative_value, 0.15),
        (decision_value, 0.15),
    ]
    if assumption_value is not None:
        confidence_components.append((assumption_value, 0.20))
    if constraint_value is not None:
        confidence_components.append((constraint_value, 0.20))
    confidence_weight = sum(weight for _, weight in confidence_components)
    confidence_score = (
        sum(value * weight for value, weight in confidence_components) / confidence_weight
        if confidence_weight else 0.0
    )
    if not decisions:
        decision_confidence = ConfidenceLevel.NOT_EVALUABLE
    elif confidence_score >= 0.70:
        decision_confidence = ConfidenceLevel.HIGH
    elif confidence_score >= 0.30:
        decision_confidence = ConfidenceLevel.MODERATE
    else:
        decision_confidence = ConfidenceLevel.LOW

    alternatives_required = bool(decisions) or str(
        document.metadata.get("decision_stage") or ""
    ) in {"open", "selected", "completed"}
    context_factor = (
        "not_applicable"
        if context_assessment.status == "not_required"
        else "weak"
        if context_assessment.status == "not_started"
        else "strong"
        if context_assessment.status == "reviewed"
        and context_assessment.critical_gap_count == 0
        else "partial"
    )

    factors = [
        ConfidenceFactor(
            factor="evidence",
            assessment=evidence_assessment,
            explanation=(
                "Os registos existentes preservam origem, método e limitações. Isto "
                "avalia qualidade documental, não suficiência para decidir."
                if evidence_assessment == "strong"
                else "A base observacional é útil, mas não resolve todas as lacunas materiais."
                if evidence_assessment == "partial"
                else "A base observacional é insuficiente para sustentar uma escolha."
            ),
        ),
        ConfidenceFactor(
            factor="assumptions",
            assessment=(
                _assessment(assumption_value)
                if assumption_value is not None
                else "not_applicable"
            ),
            explanation=(
                f"{_count_phrase(len(unresolved_assumptions), 'pressuposto', 'pressupostos')} "
                f"{'permanece' if len(unresolved_assumptions) == 1 else 'permanecem'} por resolver."
                if assumption_value is not None
                else "Nenhum pressuposto canónico foi registado; este fator não é pontuado."
            ),
        ),
        ConfidenceFactor(
            factor="constraints",
            assessment=(
                _assessment(constraint_value)
                if constraint_value is not None
                else "not_applicable"
            ),
            explanation=(
                f"{_count_phrase(len(unresolved_constraints), 'restrição', 'restrições')} "
                f"{'permanece' if len(unresolved_constraints) == 1 else 'permanecem'} por avaliar."
                if constraint_value is not None
                else "Nenhuma restrição canónica foi registada; este fator não é pontuado."
            ),
        ),
        ConfidenceFactor(
            factor="alternatives",
            assessment=(
                "not_applicable"
                if not alternatives_required
                else "strong"
                if len(alternatives) >= 3
                else "partial"
                if alternatives
                else "weak"
            ),
            explanation=(
                "Ainda não existe um objeto de decisão; comparar alternativas não é "
                "aplicável nesta fase."
                if not alternatives_required
                else "1 alternativa está explicitamente representada."
                if len(alternatives) == 1
                else (
                    f"{len(alternatives)} alternativas estão explicitamente representadas"
                    + (
                        f", das quais {len(rejected_alternatives)} rejeitadas."
                        if rejected_alternatives
                        else "."
                    )
                )
            ),
        ),
        ConfidenceFactor(
            factor="decision_readiness",
            assessment="strong" if selected_decisions else "partial" if decisions else "not_applicable",
            explanation=(
                "Existe uma decisão selecionada."
                if selected_decisions
                else "Existe uma decisão em aberto, sem alternativa selecionada."
                if decisions
                else "Ainda não existe um objeto de decisão; a fundamentação da decisão não é avaliável."
            ),
        ),
        ConfidenceFactor(
            factor="context_coverage",
            assessment=context_factor,
            explanation=(
                "A investigação contextual não foi definida como requisito desta missão."
                if context_assessment.status == "not_required"
                else "A envolvente da missão ainda não foi investigada de forma estruturada."
                if context_assessment.status == "not_started"
                else (
                    f"O dossier cobre {len(context_assessment.domains)} domínio(s), "
                    f"{context_assessment.source_count} fonte(s) e mantém "
                    f"{context_assessment.critical_gap_count} lacuna(s) prioritária(s) explícita(s)."
                )
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
                explanation="A legitimidade ou viabilidade da decisão ou execução permanece condicionada.",
                affected_ids=[item.canonical_id for item in unresolved_constraints],
                evidence_needed="Confirmação documental específica para cada restrição, verificada por fonte competente.",
            )
        )
    if baseline_required and not has_baseline and not outcomes:
        gaps.append(
            Gap(
                code="MI-NO-BASELINE",
                severity="medium",
                title="Linha de base não demonstrada",
                explanation="Sem medição anterior, um resultado futuro não poderá ser atribuído rigorosamente à intervenção.",
                evidence_needed="Definir variáveis, método, frequência e período de medição antes da execução.",
            )
        )
    if baseline_required and outcomes and not has_baseline:
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
    if alternatives_required and not alternatives:
        gaps.append(
            Gap(
                code="MI-NO-ALTERNATIVES",
                severity="high",
                title="Alternativas não estruturadas",
                explanation="Não é possível auditar uma escolha quando as opções consideradas não estão representadas.",
                evidence_needed="Registar pelo menos a opção de não agir e as alternativas materialmente viáveis.",
            )
        )
    if _context_research_required(document) and context_assessment.status == "not_started":
        gaps.append(
            Gap(
                code="MI-CONTEXT-NOT-RESEARCHED",
                severity="high",
                title="Envolvente da missão não investigada",
                explanation=(
                    "A análise conhece apenas os registos inseridos e pode omitir relações "
                    "históricas, territoriais, legais, científicas ou institucionais materiais."
                ),
                evidence_needed=(
                    "Executar investigação contextual com fontes rastreáveis e revisão humana."
                ),
            )
        )
    elif context_assessment.status in {"preliminary", "in_review"}:
        gaps.append(
            Gap(
                code="MI-CONTEXT-REVIEW-PENDING",
                severity="medium",
                title="Dossier contextual ainda não revisto",
                explanation=(
                    "As fontes e alegações foram estruturadas, mas ainda não foram aceites "
                    "como conhecimento canónico da missão."
                ),
                evidence_needed=(
                    "Revisão humana das fontes, da formulação das alegações e dos limites."
                ),
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

    if violated_constraints or (baseline_required and outcomes and not has_baseline):
        mission_status = MissionStatus.CRITICAL
    elif any(gap.severity == "high" for gap in gaps):
        mission_status = MissionStatus.REQUIRES_ATTENTION
    elif outcomes and learnings and selected_decisions:
        mission_status = MissionStatus.COMPLETED
    else:
        mission_status = MissionStatus.ON_TRACK

    mission_trend = MissionTrend.NOT_EVALUABLE

    next_actions: list[str] = []
    if baseline_required and not has_baseline and not outcomes:
        next_actions.append("Criar e documentar a linha de base antes de qualquer intervenção")
    if _context_research_required(document) and context_assessment.status in {
        "not_started",
        "preliminary",
        "in_review",
    }:
        next_actions.append("aprofundar e rever a envolvente contextual da missão")
    if unresolved_constraints:
        constraint_refs = "; ".join(
            f"{item.canonical_id} — {item.title}" for item in unresolved_constraints[:3]
        )
        next_actions.append(f"avaliar as restrições abertas: {constraint_refs}")
    if unresolved_assumptions:
        next_actions.append("definir testes dirigidos aos pressupostos materiais")
    if alternatives_required and not alternatives:
        next_actions.append("estruturar alternativas comparáveis, incluindo não agir")
    if not decisions and not next_actions:
        next_actions.append("definir se existe um objeto de decisão legítimo e qual é o seu âmbito")
    if not next_actions:
        next_actions.append("submeter a cadeia atual a revisão humana documentada")
    next_decision_body = "; ".join(next_actions[:3])
    next_decision = next_decision_body[:1].upper() + next_decision_body[1:] + "."

    if baseline_required and outcomes and not has_baseline:
        principal_risk = "Confundir um resultado observado com efeito atribuível à intervenção."
    elif unresolved_constraints:
        principal_risk = "Avançar para uma decisão antes de confirmar as condições de legitimidade e viabilidade."
    elif baseline_required and not has_baseline:
        principal_risk = "Intervir antes de medir e perder a capacidade de interpretar o resultado futuro."
    elif not decisions:
        principal_risk = (
            "Tratar um caso identificado como decisão madura antes de estruturar "
            "o respetivo objeto."
        )
    else:
        principal_risk = (
            "Apresentar a fundamentação como mais sólida do que os registos "
            "auditáveis permitem."
        )

    if selected_decisions:
        headline = "A decisão existe, mas a sua sustentação deve permanecer sob revisão."
    elif decisions:
        headline = "Ainda não existe base suficiente para selecionar uma alternativa."
    else:
        headline = "A missão ainda não chegou ao ponto de decisão."

    summary = (
        f"A missão contém {_count_phrase(len(observations), 'observação', 'observações')}, "
        f"{_count_phrase(len(evidence), 'evidência', 'evidências')}, "
        f"{_count_phrase(len(alternatives), 'alternativa', 'alternativas')}, "
        f"{_count_phrase(len(unresolved_assumptions), 'pressuposto por resolver', 'pressupostos por resolver')} "
        f"e {_count_phrase(len(unresolved_constraints), 'restrição por avaliar', 'restrições por avaliar')}. "
        "O resultado preserva estes limites e não transforma ausência de informação em certeza."
    )

    non_inferences = [
        "A tendência da missão não é avaliável sem pelo menos dois estados temporais comparáveis.",
    ]
    if not selected_decisions:
        non_inferences.append("Nenhuma alternativa é apresentada como selecionada.")
    if not actions:
        non_inferences.append("Não se infere execução sem um registo de ação.")
    if not outcomes:
        non_inferences.append("Não se infere resultado nem impacto sem observação posterior.")
    if baseline_required and not has_baseline:
        non_inferences.append("Não se infere atribuição causal sem linha de base comparável.")

    return DeterministicReport(
        methodology_version=ENGINE_VERSION,
        mission_status=mission_status,
        mission_trend=mission_trend,
        decision_confidence=decision_confidence,
        context_assessment=context_assessment,
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
