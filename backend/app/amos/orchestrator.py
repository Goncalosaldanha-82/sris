from __future__ import annotations

from pathlib import Path

from app.atlas_chat_bridge.bridge import AtlasChatBridge

from .indexer import RepositoryMemoryIndexer
from .models import AMOSStatus
from .relations import RelationBuilder
from .reporting import MemoryReportBuilder
from .snapshot import SnapshotManager
from .store import SQLiteMemoryStore


class AMOSOrchestrator:
    def __init__(self, repository_root: Path) -> None:
        self.repository_root = repository_root.resolve()
        database_path = self.repository_root / ".atlas/amos/amos.db"
        self.store = SQLiteMemoryStore(database_path)
        self.indexer = RepositoryMemoryIndexer(self.repository_root, self.store)
        self.relations = RelationBuilder(self.repository_root, self.store)
        self.snapshots = SnapshotManager(self.repository_root, self.store)
        self.reports = MemoryReportBuilder(self.repository_root, self.store)
        self.chat_bridge = AtlasChatBridge()

    def bootstrap(self) -> AMOSStatus:
        self.indexer.index_all()
        self.relations.rebuild()
        self.reports.build_status_report()
        snapshot = self.snapshots.create_snapshot()
        return self.status(last_snapshot=str(snapshot.relative_to(self.repository_root)))

    def ingest_chat_file(self, source_file: Path, apply: bool = False):
        receipt, preview = self.chat_bridge.ingest_file(
            source_file=source_file,
            repository_root=self.repository_root,
            apply=apply,
        )
        self.indexer.index_all()
        self.relations.rebuild()
        self.reports.build_status_report()
        return receipt, preview

    def refresh(self) -> AMOSStatus:
        self.indexer.index_all()
        self.relations.rebuild()
        self.reports.build_status_report()
        return self.status()

    def search(self, query: str, limit: int = 20):
        return self.store.search(query, limit=limit)

    def snapshot(self) -> Path:
        return self.snapshots.create_snapshot()

    def status(self, last_snapshot: str | None = None) -> AMOSStatus:
        objects, relations, events = self.store.counts()
        if last_snapshot is None:
            latest = self.snapshots.latest_snapshot()
            last_snapshot = (
                str(latest.relative_to(self.repository_root)) if latest else None
            )
        return AMOSStatus(
            status="ok",
            repository_root=str(self.repository_root),
            database_path=str(self.store.database_path),
            object_count=objects,
            relation_count=relations,
            event_count=events,
            last_snapshot=last_snapshot,
        )
