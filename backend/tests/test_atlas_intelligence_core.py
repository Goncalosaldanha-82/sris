from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.amos.models import MemoryObject, MemoryObjectType, MemoryState
from app.amos.store import SQLiteMemoryStore
from app.atlas_intelligence_core.analyzers import (
    DuplicateAnalyzer,
    OrphanAnalyzer,
    ValidationGapAnalyzer,
)
from app.atlas_intelligence_core.orchestrator import AtlasIntelligenceCore


def seed_repo(root: Path) -> None:
    files = {
        "docs/atlas/hypotheses/HYP-001-continuity.md": """# HYP-001 — Continuity hypothesis

**State:** `working`

Institutional reconstructability supports continuity.
""",
        "docs/atlas/hypotheses/HYP-002-continuity-copy.md": """# HYP-002 — Continuity hypothesis duplicate

**State:** `working`

Institutional reconstructability supports institutional continuity.
""",
        "docs/atlas/missions/MISSION-001-validation.md": """# MISSION-001 — Validation mission

Investigate HYP-001 through a future experiment.
""",
        "docs/atlas/knowledge-vault/MASTER-INDEX.md": "# Master Index\n",
        "docs/atlas/registry/ASSET-REGISTRY.md": "# Asset Registry\n",
    }
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def test_duplicate_analyzer_detects_similarity() -> None:
    now = datetime.now(timezone.utc)
    left = MemoryObject(
        type=MemoryObjectType.HYPOTHESIS,
        title="Continuity hypothesis",
        summary="Institutional reconstructability supports continuity.",
        source_path="a.md",
        created_at=now,
        updated_at=now,
    )
    right = MemoryObject(
        type=MemoryObjectType.HYPOTHESIS,
        title="Continuity hypothesis copy",
        summary="Institutional reconstructability supports institutional continuity.",
        source_path="b.md",
        created_at=now,
        updated_at=now,
    )
    findings = DuplicateAnalyzer().analyze([left, right])
    assert findings
    assert findings[0].type.value == "duplication"


def test_orphan_and_validation_gap() -> None:
    now = datetime.now(timezone.utc)
    hypothesis = MemoryObject(
        type=MemoryObjectType.HYPOTHESIS,
        title="Unvalidated hypothesis",
        summary="A candidate hypothesis.",
        source_path="hyp.md",
        created_at=now,
        updated_at=now,
    )
    graph = {}
    assert OrphanAnalyzer().analyze([hypothesis], graph)
    assert ValidationGapAnalyzer().analyze([hypothesis], graph)


def test_full_analysis_generates_reports(tmp_path: Path) -> None:
    seed_repo(tmp_path)
    core = AtlasIntelligenceCore(tmp_path)
    core.amos.bootstrap()
    report = core.analyze(refresh_memory=False)

    assert report.object_count >= 5
    assert report.finding_count >= 1
    assert (tmp_path / "docs/atlas/intelligence/AIC-STATUS.md").exists()
    assert (tmp_path / "docs/atlas/intelligence/AIC-LATEST.json").exists()
