from __future__ import annotations

from pathlib import Path

from .store import SQLiteMemoryStore


class MemoryReportBuilder:
    def __init__(self, repository_root: Path, store: SQLiteMemoryStore) -> None:
        self.repository_root = repository_root.resolve()
        self.store = store

    def build_status_report(self) -> Path:
        objects, relations, events = self.store.counts()
        by_type: dict[str, int] = {}
        by_state: dict[str, int] = {}

        for obj in self.store.all_objects():
            by_type[obj.type.value] = by_type.get(obj.type.value, 0) + 1
            by_state[obj.state.value] = by_state.get(obj.state.value, 0) + 1

        path = self.repository_root / "docs/atlas/knowledge-vault/AMOS-STATUS.md"
        lines = [
            "# AMOS Status Report",
            "",
            f"- **Objects:** {objects}",
            f"- **Relations:** {relations}",
            f"- **Events:** {events}",
            "",
            "## Objects by type",
            "",
            "| Type | Count |",
            "|---|---:|",
        ]
        for key, count in sorted(by_type.items()):
            lines.append(f"| {key} | {count} |")

        lines.extend([
            "",
            "## Objects by state",
            "",
            "| State | Count |",
            "|---|---:|",
        ])
        for key, count in sorted(by_state.items()):
            lines.append(f"| {key} | {count} |")

        lines.extend([
            "",
            "## Governance",
            "",
            "> AMOS indexes and relates institutional memory. It does not validate scientific truth, approve decisions, or merge changes without human authorization.",
            "",
        ])

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")
        return path
