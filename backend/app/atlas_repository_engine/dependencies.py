from __future__ import annotations

from pathlib import Path

from .models import DependencyImpact, PlannedFileChange, RepositoryAsset


class DependencyAnalyzer:
    def analyze(
        self,
        changes: list[PlannedFileChange],
        assets: list[RepositoryAsset],
    ) -> list[DependencyImpact]:
        by_path = {asset.path: asset for asset in assets}
        impacts: list[DependencyImpact] = []

        for change in changes:
            existing = by_path.get(change.path)
            broken: list[str] = []

            if change.change_type.value == "delete" and existing:
                broken = list(existing.referenced_by)

            risk = "high" if broken else ("medium" if existing and existing.referenced_by else change.risk_level)
            impacts.append(
                DependencyImpact(
                    path=change.path,
                    direct_dependants=existing.referenced_by if existing else [],
                    referenced_assets=existing.references if existing else [],
                    broken_references=broken,
                    risk_level=risk,
                )
            )
        return impacts
