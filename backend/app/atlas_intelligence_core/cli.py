from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import UUID

from .orchestrator import AtlasIntelligenceCore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atlas-intelligence-core",
        description="Analyze AMOS memory for contradictions, gaps, impact and priorities.",
    )
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze")
    analyze.add_argument("--no-refresh", action="store_true")

    impact = sub.add_parser("impact")
    impact.add_argument("object_id", type=UUID)
    impact.add_argument("--depth", type=int, default=3)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    core = AtlasIntelligenceCore(args.repo)

    if args.command == "analyze":
        report = core.analyze(refresh_memory=not args.no_refresh)
        print(report.model_dump_json(indent=2))
        return 0

    report = core.impact(args.object_id, max_depth=args.depth)
    print(report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
