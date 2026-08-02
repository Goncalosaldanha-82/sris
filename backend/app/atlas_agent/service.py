from __future__ import annotations

from pathlib import Path

from .document_updater import AtlasDocumentPlanner
from .extractor import ChangeSetExtractor
from .models import AgentPlan
from .repository import LocalRepository


class AtlasRepositoryAgent:
    def __init__(self) -> None:
        self.extractor = ChangeSetExtractor()
        self.planner = AtlasDocumentPlanner()

    def plan(self, *, source_file: Path, repository_root: Path) -> AgentPlan:
        changeset = self.extractor.from_file(source_file)
        return self.planner.build_plan(changeset, repository_root)

    def preview(self, *, source_file: Path, repository_root: Path) -> str:
        plan = self.plan(source_file=source_file, repository_root=repository_root)
        return LocalRepository(repository_root).preview(plan)

    def apply_local(self, *, source_file: Path, repository_root: Path) -> AgentPlan:
        plan = self.plan(source_file=source_file, repository_root=repository_root)
        LocalRepository(repository_root).apply(plan)
        return plan
