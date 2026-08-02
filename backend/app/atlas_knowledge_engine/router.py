from __future__ import annotations

from dataclasses import dataclass

from .models import KnowledgeItem, KnowledgeType


@dataclass(frozen=True)
class Route:
    folder: str
    prefix: str


ROUTES = {
    KnowledgeType.DECISION: Route("docs/atlas/research-notes", "DR"),
    KnowledgeType.HYPOTHESIS: Route("docs/atlas/hypotheses", "HYP"),
    KnowledgeType.CONCEPT: Route("docs/atlas/ontology", "CONCEPT"),
    KnowledgeType.MISSION: Route("docs/atlas/missions", "MISSION"),
    KnowledgeType.RESEARCH_NOTE: Route("docs/atlas/research-notes", "RN"),
    KnowledgeType.THEORY: Route("docs/atlas/theories", "THEORY"),
    KnowledgeType.ONTOLOGY: Route("docs/atlas/ontology", "ONT"),
    KnowledgeType.EXPERIMENT: Route("docs/atlas/experiments", "EXP"),
    KnowledgeType.VALIDATION: Route("docs/atlas/validation", "VAL"),
    KnowledgeType.RISK: Route("docs/atlas/research-notes", "RISK"),
    KnowledgeType.ACTION: Route("docs/atlas/missions", "ACTION"),
    KnowledgeType.OBSERVATION: Route("docs/atlas/research-notes", "OBS"),
    KnowledgeType.CORRECTION: Route("docs/atlas/research-notes", "CORR"),
    KnowledgeType.ARCHITECTURE: Route("docs/atlas/research-notes", "ARCH"),
}


class KnowledgeRouter:
    def route(self, item: KnowledgeItem) -> Route:
        return ROUTES[item.type]
