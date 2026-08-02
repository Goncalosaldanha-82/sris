from __future__ import annotations

import re
from pathlib import Path

from .models import ConflictFinding, KnowledgePacket


class ConflictDetector:
    def scan(self, packet: KnowledgePacket, repository_root: Path) -> list[ConflictFinding]:
        findings: list[ConflictFinding] = []
        known_titles = self._known_titles(repository_root)

        for item in packet.items:
            normalized = self._normalize(item.title)
            if normalized in known_titles:
                findings.append(
                    ConflictFinding(
                        severity="warning",
                        code="DUPLICATE_TITLE",
                        message=f"Possible duplicate title: {item.title}",
                        related_paths=[known_titles[normalized]],
                    )
                )

            if item.state.value == "adopted" and item.confidence.value == "low":
                findings.append(
                    ConflictFinding(
                        severity="warning",
                        code="STATE_CONFIDENCE_MISMATCH",
                        message=f"Adopted item has low confidence: {item.title}",
                    )
                )

            if item.type.value in {"hypothesis", "theory"} and not item.limitations:
                findings.append(
                    ConflictFinding(
                        severity="info",
                        code="MISSING_LIMITATIONS",
                        message=f"No explicit limitations supplied for {item.title}",
                    )
                )
        return findings

    def _known_titles(self, root: Path) -> dict[str, str]:
        values: dict[str, str] = {}
        atlas_root = root / "docs/atlas"
        if not atlas_root.exists():
            return values

        for path in atlas_root.rglob("*.md"):
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            match = re.search(r"(?m)^#\s+(.+?)\s*$", text)
            if match:
                values[self._normalize(match.group(1))] = str(path.relative_to(root))
        return values

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", value.lower())
