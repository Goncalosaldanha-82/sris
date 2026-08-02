from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from re import sub

from .dependencies import DependencyAnalyzer
from .models import (
    ChangeType,
    PlannedFileChange,
    RepositoryChangePlan,
    RepositoryAsset,
)


class RepositoryChangePlanner:
    def __init__(self) -> None:
        self.dependencies = DependencyAnalyzer()

    def plan(
        self,
        *,
        title: str,
        summary: str,
        changes: list[PlannedFileChange],
        assets: list[RepositoryAsset],
    ) -> RepositoryChangePlan:
        impacts = self.dependencies.analyze(changes, assets)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        slug = sub(r"[^a-zA-Z0-9]+", "-", title).strip("-").lower()[:48] or "change"
        branch = f"atlas/repository-{slug}-{stamp}"

        risks = [impact for impact in impacts if impact.risk_level in {"medium", "high", "critical"}]
        body = self._pr_body(summary, changes, impacts, risks)

        return RepositoryChangePlan(
            title=title,
            summary=summary,
            branch_name=branch,
            commit_message=f"ARE: {title[:65]}",
            pull_request_title=f"[ARE] {title}",
            pull_request_body=body,
            changes=changes,
            impacts=impacts,
        )

    @staticmethod
    def _pr_body(summary, changes, impacts, risks) -> str:
        change_lines = "\n".join(
            f"- `{change.change_type.value}` `{change.path}` — {change.reason}"
            for change in changes
        )
        risk_lines = "\n".join(
            f"- `{impact.path}` — {impact.risk_level}; dependants: "
            f"{', '.join(impact.direct_dependants) or 'none'}"
            for impact in risks
        ) or "- No medium/high dependency risks detected."

        return f"""## ATLAS Repository Engine

{summary}

### Planned changes
{change_lines}

### Dependency impact
{risk_lines}

### Mandatory review
- [ ] File destinations are correct.
- [ ] Generated content is accurate.
- [ ] No protected or foundational asset is altered without authority.
- [ ] Tests pass.
- [ ] Migration impact was reviewed, if applicable.
- [ ] Human approval is recorded before merge.
"""
