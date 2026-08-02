from __future__ import annotations

from pathlib import Path

from .classifier import KnowledgeClassifier
from .models import KnowledgePlan
from .planner import KnowledgePlanner
from .repository import KnowledgeRepository


class AtlasKnowledgeEngine:
    def __init__(self) -> None:
        self.classifier = KnowledgeClassifier()
        self.planner = KnowledgePlanner()

    def plan(self, *, source_file: Path, repository_root: Path) -> KnowledgePlan:
        packet = self.classifier.from_file(source_file)
        return self.planner.build_plan(packet, repository_root)

    def preview(self, *, source_file: Path, repository_root: Path) -> str:
        plan = self.plan(source_file=source_file, repository_root=repository_root)
        return KnowledgeRepository(repository_root).preview(plan)

    def apply_local(self, *, source_file: Path, repository_root: Path) -> KnowledgePlan:
        plan = self.plan(source_file=source_file, repository_root=repository_root)
        KnowledgeRepository(repository_root).apply(plan)
        return plan
