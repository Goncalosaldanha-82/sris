from __future__ import annotations

from pathlib import Path

from .applier import RepositoryApplier
from .index import RepositoryIndex
from .models import PlannedFileChange, RepositoryChangePlan
from .planner import RepositoryChangePlanner
from .scanner import RepositoryScanner


class AtlasRepositoryEngine:
    def __init__(self, repository_root: Path) -> None:
        self.repository_root = repository_root.resolve()
        self.scanner = RepositoryScanner(self.repository_root)
        self.index = RepositoryIndex(self.repository_root)
        self.planner = RepositoryChangePlanner()
        self.applier = RepositoryApplier(self.repository_root)

    def scan(self):
        assets = self.scanner.scan()
        self.index.save(assets)
        return assets

    def create_plan(
        self,
        *,
        title: str,
        summary: str,
        changes: list[PlannedFileChange],
    ) -> RepositoryChangePlan:
        assets = self.index.load() or self.scan()
        return self.planner.plan(
            title=title,
            summary=summary,
            changes=changes,
            assets=assets,
        )

    def preview(self, plan: RepositoryChangePlan) -> str:
        return self.applier.preview(plan)

    def apply(self, plan: RepositoryChangePlan, **kwargs):
        return self.applier.apply(plan, **kwargs)
