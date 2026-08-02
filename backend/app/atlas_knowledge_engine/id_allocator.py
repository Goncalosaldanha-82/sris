from __future__ import annotations

import re
from pathlib import Path


class IdAllocator:
    def next_id(self, folder: Path, prefix: str) -> str:
        folder.mkdir(parents=True, exist_ok=True)
        pattern = re.compile(rf"^{re.escape(prefix)}-(\d{{3,}})")
        highest = 0
        for path in folder.glob(f"{prefix}-*.md"):
            match = pattern.match(path.name)
            if match:
                highest = max(highest, int(match.group(1)))
        return f"{prefix}-{highest + 1:03d}"
