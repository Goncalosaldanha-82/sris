from pathlib import Path

from app.atlas_agent.extractor import ChangeSetExtractor
from app.atlas_agent.service import AtlasRepositoryAgent


SOURCE = """# ATLAS update

## Decision

The GitHub repository becomes the official source of truth for Project ATLAS.
State: adopted.
Affected: ATLAS, ASM, SRIS.

## Hypothesis

Institutional justifiability may be a mechanism supporting reconstructability.
This remains provisional and affects TICC and SEE.

## Risk

Content dispersed in conversations can be lost.
"""


def seed_repo(root: Path) -> None:
    (root / "docs/atlas").mkdir(parents=True)
    (root / "PROJECT-STATE.md").write_text("# Project State\n", encoding="utf-8")
    (root / "docs/atlas/ATLAS-REGISTRY.md").write_text(
        "# Registry\n", encoding="utf-8"
    )
    (root / "docs/atlas/CHANGELOG-SCIENTIFIC.md").write_text(
        "# Changelog\n", encoding="utf-8"
    )


def test_markdown_extraction() -> None:
    changeset = ChangeSetExtractor().from_markdown(SOURCE, source_name="note.md")
    assert len(changeset.items) == 3
    assert changeset.items[0].kind.value == "decision"
    assert changeset.items[0].state.value == "adopted"
    assert "ATLAS" in changeset.items[0].affected_assets


def test_agent_preview_and_apply(tmp_path: Path) -> None:
    seed_repo(tmp_path)
    source = tmp_path / "input.md"
    source.write_text(SOURCE, encoding="utf-8")

    agent = AtlasRepositoryAgent()
    preview = agent.preview(source_file=source, repository_root=tmp_path)

    assert "ATLAS-REGISTRY.md" in preview
    assert "Pending human approval" in preview

    plan = agent.apply_local(source_file=source, repository_root=tmp_path)
    assert len(plan.mutations) == 4
    assert "Official source of truth" not in (tmp_path / "PROJECT-STATE.md").read_text(
        encoding="utf-8"
    )  # Agent summarizes/registers; it does not silently rewrite core doctrine.
    notes = list((tmp_path / "docs/atlas/agent-notes").glob("*.md"))
    assert len(notes) == 1
    assert "Human approval required" in notes[0].read_text(encoding="utf-8")


def test_json_round_trip(tmp_path: Path) -> None:
    extractor = ChangeSetExtractor()
    changeset = extractor.from_markdown(SOURCE, source_name="note.md")
    path = tmp_path / "changeset.json"
    path.write_text(changeset.model_dump_json(indent=2), encoding="utf-8")
    restored = extractor.from_file(path)
    assert restored.title == changeset.title
    assert len(restored.items) == len(changeset.items)
