from __future__ import annotations

import subprocess
import sys


def run_migrations() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    run_migrations()
