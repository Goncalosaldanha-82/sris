from __future__ import annotations

from pathlib import Path
from uuid import UUID

from app.amos.orchestrator import AMOSOrchestrator

from .analyzers import (
    ContradictionAnalyzer,
    DuplicateAnalyzer,
    OrphanAnalyzer,
    ProvenanceAnalyzer,
    StalenessAnalyzer,
    ValidationGapAnalyzer,
)
from .impact import ImpactAnalyzer
from .models import IntelligenceReport
from .priorities import PriorityEngine
from .reporting import IntelligenceReportWriter
from .store_adapter import AMOSReadAdapter


class AtlasIntelligenceCore:
    def __init__(self, repository_root: Path) -> None:
        self.repository_root = repository_root.resolve()
        self.amos = AMOSOrchestrator(self.repository_root)
        self.adapter = AMOSReadAdapter(self.repository_root / ".atlas/amos/amos.db")
        self.duplicate = DuplicateAnalyzer()
        self.contradiction = ContradictionAnalyzer()
        self.orphan = OrphanAnalyzer()
        self.validation = ValidationGapAnalyzer()
        self.staleness = StalenessAnalyzer()
        self.provenance = ProvenanceAnalyzer()
        self.impact_analyzer = ImpactAnalyzer()
        self.priorities = PriorityEngine()
        self.writer = IntelligenceReportWriter(self.repository_root)

    def analyze(self, refresh_memory: bool = True) -> IntelligenceReport:
        if refresh_memory:
            self.amos.refresh()

        objects = self.adapter.objects()
        relations = self.adapter.relations()
        graph = self.adapter.relation_graph()

        findings = []
        findings.extend(self.duplicate.analyze(objects))
        findings.extend(self.contradiction.analyze(objects))
        findings.extend(self.orphan.analyze(objects, graph))
        findings.extend(self.validation.analyze(objects, graph))
        findings.extend(self.staleness.analyze(objects))
        findings.extend(self.provenance.analyze(objects))

        priorities = self.priorities.rank(findings)
        high = sum(1 for item in findings if item.severity.value in {"high", "critical"})
        summary = (
            f"AIC analysed {len(objects)} memory objects and {len(relations)} relations. "
            f"It produced {len(findings)} findings, including {high} high/critical items. "
            "All findings require human review."
        )
        report = IntelligenceReport(
            object_count=len(objects),
            relation_count=len(relations),
            finding_count=len(findings),
            findings=findings,
            priorities=priorities,
            summary=summary,
        )
        self.writer.write(report)
        return report

    def impact(self, object_id: UUID, max_depth: int = 3):
        return self.impact_analyzer.analyze(
            object_id,
            self.adapter.objects(),
            self.adapter.relation_graph(),
            max_depth=max_depth,
        )
