from __future__ import annotations

import time
from pathlib import Path

from .bridge import AtlasChatBridge


class InboxWatcher:
    def __init__(self, repository_root: Path, interval_seconds: int = 5) -> None:
        self.repository_root = repository_root.resolve()
        self.interval_seconds = interval_seconds
        self.bridge = AtlasChatBridge()
        self.seen: set[Path] = set()

    def run_forever(self, apply: bool = False) -> None:
        inbox = self.repository_root / "docs/atlas/chat-drop"
        processed = self.repository_root / "docs/atlas/chat-drop/processed"
        failed = self.repository_root / "docs/atlas/chat-drop/failed"
        inbox.mkdir(parents=True, exist_ok=True)
        processed.mkdir(parents=True, exist_ok=True)
        failed.mkdir(parents=True, exist_ok=True)

        print(f"Watching: {inbox}")
        while True:
            for path in sorted(inbox.iterdir()):
                if not path.is_file() or path.suffix.lower() not in {".md", ".txt", ".json"}:
                    continue
                if path in self.seen:
                    continue

                try:
                    receipt, _ = self.bridge.ingest_file(
                        source_file=path,
                        repository_root=self.repository_root,
                        apply=apply,
                    )
                    destination = processed / path.name
                    path.replace(destination)
                    print(f"Processed {path.name}: {receipt.status}")
                except Exception as exc:
                    destination = failed / path.name
                    path.replace(destination)
                    print(f"Failed {path.name}: {exc}")

                self.seen.add(path)

            time.sleep(self.interval_seconds)
