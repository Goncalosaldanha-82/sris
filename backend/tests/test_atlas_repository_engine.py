from pathlib import Path

from app.atlas_repository_engine.engine import AtlasRepositoryEngine
from app.atlas_repository_engine.models import ChangeType, PlannedFileChange


def seed_repo(root: Path) -> None:
    (root / "docs/atlas/hypotheses").mkdir(parents=True)
    (root / "docs/atlas/missions").mkdir(parents=True)
    (root / "docs/atlas/hypotheses/HYP-001-test.md").write_text(
        "# HYP-001 — Test\n\nReferenced by MISSION-001.\n",
        encoding="utf-8",
    )
    (root / "docs/atlas/missions/MISSION-001-test.md").write_text(
        "# MISSION-001 — Test\n\nUses `HYP-001-test.md`.\n",
        encoding="utf-8",
    )


def test_scan_plan_preview_apply(tmp_path: Path) -> None:
    seed_repo(tmp_path)
    engine = AtlasRepositoryEngine(tmp_path)

    assets = engine.scan()
    assert len(assets) == 2
    assert (tmp_path / ".atlas/repository/index.json").exists()

    plan = engine.create_plan(
        title="Add second hypothesis",
        summary="Creates a governed hypothesis asset.",
        changes=[
            PlannedFileChange(
                change_type=ChangeType.CREATE,
                path="docs/atlas/hypotheses/HYP-002-new.md",
                content="# HYP-002 — New\n\nCandidate hypothesis.\n",
                reason="Approved knowledge workflow.",
            )
        ],
    )

    preview = engine.preview(plan)
    assert "HYP-002-new.md" in preview

    result = engine.apply(plan)
    assert result.changed_paths == ["docs/atlas/hypotheses/HYP-002-new.md"]
    assert (tmp_path / "docs/atlas/hypotheses/HYP-002-new.md").exists()


def test_delete_detects_dependants(tmp_path: Path) -> None:
    seed_repo(tmp_path)
    engine = AtlasRepositoryEngine(tmp_path)
    engine.scan()

    plan = engine.create_plan(
        title="Delete hypothesis",
        summary="Tests dependency impact.",
        changes=[
            PlannedFileChange(
                change_type=ChangeType.DELETE,
                path="docs/atlas/hypotheses/HYP-001-test.md",
                reason="Test deletion.",
            )
        ],
    )

    assert plan.impacts[0].risk_level in {"medium", "high"}
