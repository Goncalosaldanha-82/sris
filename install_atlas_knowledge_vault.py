from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def copy_tree(source: Path, target: Path, force: bool = False) -> tuple[int, int]:
    created = 0
    skipped = 0

    for source_file in source.rglob("*"):
        if not source_file.is_file():
            continue

        relative = source_file.relative_to(source)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)

        if destination.exists() and not force:
            skipped += 1
            print(f"SKIP existing: {relative}")
            continue

        shutil.copy2(source_file, destination)
        created += 1
        print(f"WRITE: {relative}")

    return created, skipped


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install the ATLAS Knowledge Vault without overwriting existing files."
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Root of the SRIS repository.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files. Use only after reviewing conflicts.",
    )
    args = parser.parse_args()

    bundle_root = Path(__file__).resolve().parent
    payload = bundle_root / "docs"
    repo = args.repo.resolve()

    if not (repo / ".git").exists():
        raise SystemExit(f"Not a Git repository: {repo}")

    created, skipped = copy_tree(payload, repo / "docs", force=args.force)

    print()
    print(f"Installed files: {created}")
    print(f"Skipped existing files: {skipped}")
    print("Review changes in GitHub Desktop before committing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
