from __future__ import annotations

import difflib
from pathlib import Path

from .models import KnowledgePlan


class KnowledgeRepository:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def preview(self, plan: KnowledgePlan) -> str:
        chunks: list[str] = []
        for mutation in plan.mutations:
            path = self.root / mutation.path
            before = path.read_text(encoding="utf-8") if path.exists() else ""
            chunks.extend(
                difflib.unified_diff(
                    before.splitlines(),
                    mutation.content.splitlines(),
                    fromfile=f"a/{mutation.path}",
                    tofile=f"b/{mutation.path}",
                    lineterm="",
                )
            )
        return "\n".join(chunks)

    def apply(self, plan: KnowledgePlan) -> list[Path]:
        written: list[Path] = []
        for mutation in plan.mutations:
            target = (self.root / mutation.path).resolve()
            if self.root not in target.parents and target != self.root:
                raise ValueError(f"Refusing to write outside repository: {mutation.path}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(mutation.content, encoding="utf-8")
            written.append(target)
        return written
