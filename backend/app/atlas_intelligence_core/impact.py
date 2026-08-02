from __future__ import annotations

from collections import deque
from uuid import UUID

from app.amos.models import MemoryObject

from .models import ImpactNode, ImpactReport


class ImpactAnalyzer:
    def analyze(
        self,
        root_object_id: UUID,
        objects: list[MemoryObject],
        graph: dict[UUID, list[tuple[UUID, str]]],
        max_depth: int = 3,
    ) -> ImpactReport:
        by_id = {obj.object_id: obj for obj in objects}
        root = by_id.get(root_object_id)
        if root is None:
            raise KeyError(f"Unknown memory object: {root_object_id}")

        affected: list[ImpactNode] = []
        queue = deque([(root_object_id, 0)])
        seen = {root_object_id}

        while queue:
            current, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for target, relation in graph.get(current, []):
                if target in seen or target not in by_id:
                    continue
                seen.add(target)
                obj = by_id[target]
                affected.append(
                    ImpactNode(
                        object_id=obj.object_id,
                        title=obj.title,
                        relation=relation,
                        depth=depth + 1,
                        source_path=obj.source_path,
                    )
                )
                queue.append((target, depth + 1))

        return ImpactReport(
            root_object_id=root.object_id,
            root_title=root.title,
            affected=affected,
        )
