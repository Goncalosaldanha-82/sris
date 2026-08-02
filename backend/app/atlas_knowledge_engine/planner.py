from __future__ import annotations

from datetime import timezone
from pathlib import Path
from re import sub

from .conflicts import ConflictDetector
from .id_allocator import IdAllocator
from .models import KnowledgePacket, KnowledgePlan, PlannedMutation
from .router import KnowledgeRouter


class KnowledgePlanner:
    def __init__(self) -> None:
        self.router = KnowledgeRouter()
        self.ids = IdAllocator()
        self.conflicts = ConflictDetector()

    def build_plan(self, packet: KnowledgePacket, repository_root: Path) -> KnowledgePlan:
        mutations: list[PlannedMutation] = []
        registry_rows: list[str] = []

        for item in packet.items:
            route = self.router.route(item)
            folder = repository_root / route.folder
            asset_id = self.ids.next_id(folder, route.prefix)
            path = f"{route.folder}/{asset_id}-{self._slug(item.title)}.md"

            mutations.append(
                PlannedMutation(
                    path=path,
                    content=self._render_asset(asset_id, packet, item),
                    reason=f"Create governed {item.type.value} asset.",
                )
            )
            registry_rows.append(
                f"| {asset_id} | {item.type.value} | {self._escape(item.title)} | "
                f"{item.state.value} | `{path}` | "
                f"{self._escape(', '.join(item.affected_assets) or '—')} |"
            )

        mutations.extend(self._index_mutations(packet, repository_root, registry_rows))
        conflicts = self.conflicts.scan(packet, repository_root)

        stamp = packet.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d")
        short = str(packet.packet_id).split("-")[0]

        return KnowledgePlan(
            packet=packet,
            mutations=mutations,
            conflicts=conflicts,
            branch_name=f"atlas/knowledge-{stamp}-{short}",
            commit_message=f"ATLAS knowledge: {packet.title[:60]}",
            pull_request_title=f"[ATLAS Knowledge] {packet.title}",
            pull_request_body=self._render_pr(packet, conflicts),
        )

    def _index_mutations(
        self,
        packet: KnowledgePacket,
        root: Path,
        registry_rows: list[str],
    ) -> list[PlannedMutation]:
        asset_registry_path = "docs/atlas/registry/ASSET-REGISTRY.md"
        master_index_path = "docs/atlas/knowledge-vault/MASTER-INDEX.md"
        capture_log_path = "docs/atlas/knowledge-vault/CAPTURE-LOG.md"

        asset_registry = self._read(root, asset_registry_path, "# ATLAS Asset Registry\n")
        master_index = self._read(root, master_index_path, "# ATLAS Knowledge Vault — Master Index\n")
        capture_log = self._read(root, capture_log_path, "# ATLAS Knowledge Capture Log\n")

        date = packet.created_at.date()
        registry_block = (
            f"\n## Intake {date} — `{str(packet.packet_id)[:8]}`\n\n"
            "| ID | Type | Title | State | Location | Affected assets |\n"
            "|---|---|---|---|---|---|\n"
            + "\n".join(registry_rows)
            + "\n"
        )
        index_block = (
            f"\n## Latest intake — {date}\n\n"
            f"- **Packet:** `{packet.packet_id}`\n"
            f"- **Title:** {packet.title}\n"
            f"- **Source:** `{packet.source_name}`\n"
            f"- **Items:** {len(packet.items)}\n"
            f"- **Approval:** Pending human review\n"
        )
        log_block = (
            f"\n## {date} — {packet.title}\n\n"
            f"- Packet: `{packet.packet_id}`\n"
            f"- Source: `{packet.source_name}`\n"
            f"- Summary: {packet.overall_summary}\n"
            f"- Status: Pending human review\n"
        )

        return [
            PlannedMutation(
                path=asset_registry_path,
                content=asset_registry.rstrip() + "\n" + registry_block,
                reason="Update official asset registry.",
            ),
            PlannedMutation(
                path=master_index_path,
                content=master_index.rstrip() + "\n" + index_block,
                reason="Update Knowledge Vault master index.",
            ),
            PlannedMutation(
                path=capture_log_path,
                content=capture_log.rstrip() + "\n" + log_block,
                reason="Preserve knowledge capture genealogy.",
            ),
        ]

    def _render_asset(self, asset_id: str, packet: KnowledgePacket, item) -> str:
        return f"""# {asset_id} — {item.title}

**Type:** `{item.type.value}`  
**State:** `{item.state.value}`  
**Confidence:** `{item.confidence.value}`  
**Source:** `{packet.source_name}`  
**Packet:** `{packet.packet_id}`  
**Created:** `{packet.created_at.isoformat()}`  
**Human approval required:** `{item.requires_human_approval}`  

## Summary

{item.summary}

## Basis

{item.basis or "Not supplied."}

## Affected assets

{self._bullets(item.affected_assets)}

## Related concepts

{self._bullets(item.related_concepts)}

## Limitations

{self._bullets(item.limitations)}

## Source excerpt

{item.source_excerpt or "Not supplied."}

## Governance notice

> This asset was prepared automatically. It is not adopted until reviewed and merged by an authorized human.
"""

    def _render_pr(self, packet: KnowledgePacket, conflicts) -> str:
        findings = "\n".join(
            f"- **{finding.severity} / {finding.code}:** {finding.message}"
            for finding in conflicts
        ) or "- No structural conflicts detected by v0.1 rules."

        return f"""## ATLAS Knowledge Engine v0.1

Prepared packet `{packet.packet_id}` from `{packet.source_name}`.

**Summary:** {packet.overall_summary}

### Extracted knowledge
- Items: {len(packet.items)}
- Human approval required: {packet.requires_human_approval}

### Automated checks
{findings}

### Mandatory human review
- [ ] Classification is correct.
- [ ] IDs and destinations are appropriate.
- [ ] Claims are not presented as validated without evidence.
- [ ] No duplicate or contradictory asset was created.
- [ ] Registry and Master Index remain coherent.
- [ ] Merge is explicitly approved.
"""

    @staticmethod
    def _read(root: Path, relative: str, fallback: str) -> str:
        path = root / relative
        return path.read_text(encoding="utf-8") if path.exists() else fallback

    @staticmethod
    def _slug(value: str) -> str:
        value = sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
        return value[:70] or "knowledge"

    @staticmethod
    def _escape(value: str) -> str:
        return value.replace("|", "\\|").replace("\n", " ")

    @staticmethod
    def _bullets(values: list[str]) -> str:
        return "\n".join(f"- {value}" for value in values) if values else "- None supplied."
