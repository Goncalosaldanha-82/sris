from pathlib import Path

from app.amos.orchestrator import AMOSOrchestrator


def seed_repo(root: Path) -> None:
    files = {
        "docs/atlas/hypotheses/HYP-001-test.md": """# HYP-001 — Test hypothesis

**State:** `working`

Institutional memory may support continuity.
""",
        "docs/atlas/missions/MISSION-001-test.md": """# MISSION-001 — Test mission

This mission investigates HYP-001.
""",
        "docs/atlas/knowledge-vault/MASTER-INDEX.md": "# Master Index\n",
        "docs/atlas/registry/ASSET-REGISTRY.md": "# Asset Registry\n",
    }
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def test_bootstrap_indexes_and_relates(tmp_path: Path) -> None:
    seed_repo(tmp_path)
    amos = AMOSOrchestrator(tmp_path)
    status = amos.bootstrap()

    assert status.object_count >= 4
    assert status.relation_count >= 1
    assert status.event_count >= 5
    assert (tmp_path / ".atlas/amos/amos.db").exists()
    assert (tmp_path / "docs/atlas/knowledge-vault/AMOS-STATUS.md").exists()
    assert status.last_snapshot is not None


def test_search_returns_memory_object(tmp_path: Path) -> None:
    seed_repo(tmp_path)
    amos = AMOSOrchestrator(tmp_path)
    amos.bootstrap()
    results = amos.search("continuity")
    assert results
    assert "hypothesis" in results[0].title.lower()


def test_refresh_is_idempotent_for_objects(tmp_path: Path) -> None:
    seed_repo(tmp_path)
    amos = AMOSOrchestrator(tmp_path)
    first = amos.bootstrap()
    second = amos.refresh()
    assert second.object_count == first.object_count + 1  # AMOS-STATUS.md becomes indexed
