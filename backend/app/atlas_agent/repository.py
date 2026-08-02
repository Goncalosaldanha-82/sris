from __future__ import annotations

import difflib
from pathlib import Path

from .models import AgentPlan


class LocalRepository:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def preview(self, plan: AgentPlan) -> str:
        diffs: list[str] = []
        for mutation in plan.mutations:
            path = self.root / mutation.path
            before = path.read_text(encoding="utf-8") if path.exists() else ""
            diff = difflib.unified_diff(
                before.splitlines(),
                mutation.content.splitlines(),
                fromfile=f"a/{mutation.path}",
                tofile=f"b/{mutation.path}",
                lineterm="",
            )
            diffs.extend(diff)
        return "\n".join(diffs)

    def apply(self, plan: AgentPlan) -> list[Path]:
        written: list[Path] = []
        for mutation in plan.mutations:
            path = (self.root / mutation.path).resolve()
            if self.root not in path.parents and path != self.root:
                raise ValueError(f"Refusing to write outside repository: {mutation.path}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(mutation.content, encoding="utf-8")
            written.append(path)
        return written
