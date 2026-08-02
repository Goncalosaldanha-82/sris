from pathlib import Path

from app.atlas_knowledge_engine.classifier import KnowledgeClassifier
from app.atlas_knowledge_engine.engine import AtlasKnowledgeEngine


SOURCE = """# ATLAS Knowledge Intake

## Hypothesis

Institutional reconstructability may support continuity.
State: candidate.
- Limitation: no empirical evidence exists.
Affected: TICC, SEE.

## Concept

Justificabilidade means the ability to reconstruct reasons, evidence and authority.
State: working.
Affected: TICC, SMK.

## Risk

Conversation-only knowledge may be lost.
State: active.

## Action

Create governed assets and update the Knowledge Vault.
"""


def seed_repo(root: Path) -> None:
    paths = [
        "docs/atlas/hypotheses",
        "docs/atlas/ontology",
        "docs/atlas/research-notes",
        "docs/atlas/missions",
        "docs/atlas/registry",
        "docs/atlas/knowledge-vault",
    ]
    for path in paths:
        (root / path).mkdir(parents=True, exist_ok=True)

    (root / "docs/atlas/registry/ASSET-REGISTRY.md").write_text(
        "# ATLAS Asset Registry\n", encoding="utf-8"
    )
    (root / "docs/atlas/knowledge-vault/MASTER-INDEX.md").write_text(
        "# ATLAS Knowledge Vault — Master Index\n", encoding="utf-8"
    )


def test_classifier_extracts_items() -> None:
    packet = KnowledgeClassifier().from_markdown(SOURCE, source_name="input.md")
    assert len(packet.items) == 4
    assert packet.items[0].type.value == "hypothesis"
    assert packet.items[1].type.value == "concept"
    assert packet.items[0].limitations


def test_engine_preview_and_apply(tmp_path: Path) -> None:
    seed_repo(tmp_path)
    source = tmp_path / "input.md"
    source.write_text(SOURCE, encoding="utf-8")

    engine = AtlasKnowledgeEngine()
    preview = engine.preview(source_file=source, repository_root=tmp_path)
    assert "HYP-001" in preview
    assert "CONCEPT-001" in preview
    assert "ASSET-REGISTRY.md" in preview

    plan = engine.apply_local(source_file=source, repository_root=tmp_path)
    assert len(plan.mutations) == 7
    assert len(list((tmp_path / "docs/atlas/hypotheses").glob("HYP-*.md"))) == 1
    assert len(list((tmp_path / "docs/atlas/ontology").glob("CONCEPT-*.md"))) == 1
    assert (tmp_path / "docs/atlas/knowledge-vault/CAPTURE-LOG.md").exists()


def test_json_round_trip(tmp_path: Path) -> None:
    classifier = KnowledgeClassifier()
    packet = classifier.from_markdown(SOURCE, source_name="input.md")
    path = tmp_path / "packet.json"
    path.write_text(packet.model_dump_json(indent=2), encoding="utf-8")
    restored = classifier.from_file(path)
    assert restored.title == packet.title
    assert len(restored.items) == len(packet.items)
