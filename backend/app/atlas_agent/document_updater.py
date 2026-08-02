from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from re import sub

from .models import AgentPlan, AtlasChangeSet, FileMutation


ALLOWED_TARGETS = {
    "PROJECT-STATE.md",
    "docs/atlas/ATLAS-REGISTRY.md",
    "docs/atlas/CHANGELOG-SCIENTIFIC.md",
}


class AtlasDocumentPlanner:
    """Produces deterministic repository mutations for human review."""

    def build_plan(self, changeset: AtlasChangeSet, repository_root: Path) -> AgentPlan:
        stamp = changeset.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d")
        short_id = str(changeset.id).split("-")[0]
        branch = f"atlas/agent-{stamp}-{short_id}"
        note_slug = self._slug(changeset.title)
        note_path = f"docs/atlas/agent-notes/{stamp}-{short_id}-{note_slug}.md"

        mutations = [
            FileMutation(
                path=note_path,
                content=self._render_note(changeset),
                reason="Create immutable agent-prepared change note.",
            ),
            FileMutation(
                path="docs/atlas/ATLAS-REGISTRY.md",
                content=self._update_registry(
                    self._read(repository_root, "docs/atlas/ATLAS-REGISTRY.md"),
                    changeset,
                    note_path,
                ),
                reason="Register the change set and its source note.",
            ),
            FileMutation(
                path="docs/atlas/CHANGELOG-SCIENTIFIC.md",
                content=self._update_changelog(
                    self._read(repository_root, "docs/atlas/CHANGELOG-SCIENTIFIC.md"),
                    changeset,
                    note_path,
                ),
                reason="Preserve scientific and architectural genealogy.",
            ),
            FileMutation(
                path="PROJECT-STATE.md",
                content=self._update_project_state(
                    self._read(repository_root, "PROJECT-STATE.md"),
                    changeset,
                    note_path,
                ),
                reason="Update the official current-state ledger.",
            ),
        ]

        return AgentPlan(
            changeset=changeset,
            mutations=mutations,
            branch_name=branch,
            commit_message=f"ATLAS agent: {changeset.title[:60]}",
            pull_request_title=f"[ATLAS Agent] {changeset.title}",
            pull_request_body=self._render_pr_body(changeset, note_path),
        )

    @staticmethod
    def _read(root: Path, relative: str) -> str:
        path = root / relative
        if not path.exists():
            return f"# {Path(relative).stem.replace('-', ' ')}\n"
        return path.read_text(encoding="utf-8")

    @staticmethod
    def _slug(value: str) -> str:
        value = sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
        return value[:70] or "update"

    def _render_note(self, changeset: AtlasChangeSet) -> str:
        lines = [
            f"# Agent Note — {changeset.title}",
            "",
            f"**Change Set:** `{changeset.id}`  ",
            f"**Source:** `{changeset.source_name}`  ",
            f"**Created:** `{changeset.created_at.isoformat()}`  ",
            f"**Author:** {changeset.author}  ",
            f"**Human approval required:** `{changeset.requires_human_approval}`",
            "",
            "## Overall summary",
            "",
            changeset.overall_summary,
            "",
            "## Extracted items",
            "",
        ]
        for item in changeset.items:
            lines.extend(
                [
                    f"### {item.kind.value.title()} — {item.title}",
                    "",
                    f"- **State:** `{item.state.value}`",
                    f"- **Affected assets:** {', '.join(item.affected_assets) or 'Not identified'}",
                    f"- **Summary:** {item.summary}",
                    f"- **Basis:** {item.evidence_or_basis or 'Not supplied'}",
                    f"- **Limitations:** {', '.join(item.limitations) or 'Not supplied'}",
                    "",
                ]
            )
        lines.extend(
            [
                "## Governance notice",
                "",
                "> This note was prepared automatically. It is not an adopted ATLAS decision until reviewed and merged by an authorized human.",
                "",
            ]
        )
        return "\n".join(lines)

    def _update_registry(self, current: str, changeset: AtlasChangeSet, note_path: str) -> str:
        block = [
            "",
            f"## Agent change set — {changeset.created_at.date()} — `{str(changeset.id)[:8]}`",
            "",
            f"- **Title:** {changeset.title}",
            f"- **Source:** `{changeset.source_name}`",
            f"- **Note:** `{note_path}`",
            f"- **Approval:** Pending human review",
            "",
            "| Kind | Title | State | Affected assets |",
            "|---|---|---|---|",
        ]
        for item in changeset.items:
            block.append(
                f"| {item.kind.value} | {self._escape(item.title)} | "
                f"{item.state.value} | {self._escape(', '.join(item.affected_assets) or '—')} |"
            )
        return current.rstrip() + "\n" + "\n".join(block) + "\n"

    def _update_changelog(self, current: str, changeset: AtlasChangeSet, note_path: str) -> str:
        bullets = "\n".join(
            f"- `{item.kind.value}` — **{item.title}**: {item.summary}"
            for item in changeset.items
        )
        entry = (
            f"\n## {changeset.created_at.date()} — Agent-prepared change `{str(changeset.id)[:8]}`\n\n"
            f"**Source:** `{changeset.source_name}`  \n"
            f"**Review note:** `{note_path}`  \n"
            f"**Status:** Pending human approval\n\n"
            f"{bullets}\n"
        )
        return current.rstrip() + "\n" + entry

    def _update_project_state(self, current: str, changeset: AtlasChangeSet, note_path: str) -> str:
        marker = "## Agent-prepared updates"
        if marker not in current:
            current = current.rstrip() + f"\n\n{marker}\n"
        entry = (
            f"\n### {changeset.created_at.date()} — {changeset.title}\n\n"
            f"- Change set: `{str(changeset.id)}`\n"
            f"- Source: `{changeset.source_name}`\n"
            f"- Review note: `{note_path}`\n"
            f"- Status: **Pending human approval**\n"
        )
        return current.rstrip() + "\n" + entry

    def _render_pr_body(self, changeset: AtlasChangeSet, note_path: str) -> str:
        assets = sorted(
            {asset for item in changeset.items for asset in item.affected_assets}
        )
        return (
            "## ATLAS Repository Agent v0.1\n\n"
            f"Prepared change set `{changeset.id}` from `{changeset.source_name}`.\n\n"
            f"**Summary:** {changeset.overall_summary}\n\n"
            f"**Affected assets:** {', '.join(assets) or 'Not automatically identified'}\n\n"
            f"**Review note:** `{note_path}`\n\n"
            "### Mandatory human checks\n"
            "- [ ] Extracted meaning is faithful to the source.\n"
            "- [ ] States and affected assets are correct.\n"
            "- [ ] No scientific claim is presented as validated without evidence.\n"
            "- [ ] Registry, changelog and project state remain coherent.\n"
            "- [ ] Merge is explicitly approved by an authorized human.\n"
        )

    @staticmethod
    def _escape(value: str) -> str:
        return value.replace("|", "\\|").replace("\n", " ")
