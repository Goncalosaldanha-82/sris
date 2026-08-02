from __future__ import annotations

import argparse
import json
from pathlib import Path

from .engine import AtlasRepositoryEngine
from .models import PlannedFileChange, RepositoryChangePlan


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="atlas-repository-engine")
    p.add_argument("--repo", type=Path, default=Path.cwd())
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("scan")

    preview = sub.add_parser("preview")
    preview.add_argument("--plan", required=True, type=Path)

    apply = sub.add_parser("apply")
    apply.add_argument("--plan", required=True, type=Path)
    apply.add_argument("--branch", action="store_true")
    apply.add_argument("--commit", action="store_true")
    apply.add_argument("--push", action="store_true")
    return p


def main() -> int:
    args = parser().parse_args()
    engine = AtlasRepositoryEngine(args.repo)

    if args.command == "scan":
        assets = engine.scan()
        print(json.dumps([a.model_dump(mode="json") for a in assets], indent=2))
        return 0

    plan = RepositoryChangePlan.model_validate_json(args.plan.read_text(encoding="utf-8"))
    if args.command == "preview":
        print(engine.preview(plan))
        return 0

    result = engine.apply(
        plan,
        create_branch=args.branch,
        commit=args.commit,
        push=args.push,
    )
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
