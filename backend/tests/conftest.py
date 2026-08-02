from __future__ import annotations

import os
import tempfile
from pathlib import Path


_session_root = Path(tempfile.mkdtemp(prefix="atlas-ci-tests-"))
_database_path = _session_root / "database" / "atlas-tests.db"
_repository_path = _session_root / "repository"

_database_path.parent.mkdir(parents=True, exist_ok=True)
_repository_path.mkdir(parents=True, exist_ok=True)

os.environ.setdefault(
    "ATLAS_DATABASE_URL",
    f"sqlite+pysqlite:///{_database_path.as_posix()}",
)
os.environ.setdefault(
    "ATLAS_JWT_SECRET",
    "atlas-ci-test-secret-change-before-production",
)
os.environ.setdefault(
    "ATLAS_REPOSITORY_ROOT",
    str(_repository_path),
)
os.environ.setdefault("ATLAS_ENV", "test")
