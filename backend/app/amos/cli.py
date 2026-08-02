from __future__ import annotations

import argparse
import json
from pathlib import Path

from .orchestrator import AMOSOrchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="amos",
        description="ATLAS Memory Operating System",
    )
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("bootstrap")
    sub.add_parser("refresh")
    sub.add_parser("status")
    sub.add_parser("snapshot")

    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=20)

    ingest = sub.add_parser("ingest-chat")
    ingest.add_argument("--input", required=True, type=Path)
    ingest.add_argument("--apply", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    amos = AMOSOrchestrator(args.repo)

    if args.command == "bootstrap":
        print(amos.bootstrap().model_dump_json(indent=2))
        return 0

    if args.command == "refresh":
        print(amos.refresh().model_dump_json(indent=2))
        return 0

    if args.command == "status":
        print(amos.status().model_dump_json(indent=2))
        return 0

    if args.command == "snapshot":
        print(amos.snapshot())
        return 0

    if args.command == "search":
        print(json.dumps(
            [item.model_dump(mode="json") for item in amos.search(args.query, args.limit)],
            ensure_ascii=False,
            indent=2,
        ))
        return 0

    receipt, preview = amos.ingest_chat_file(args.input, apply=args.apply)
    print(receipt.model_dump_json(indent=2))
    if not args.apply:
        print("\n# Preview\n")
        print(preview)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
