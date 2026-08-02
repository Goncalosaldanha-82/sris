from __future__ import annotations

import argparse
from pathlib import Path

from .bridge import AtlasChatBridge
from .watcher import InboxWatcher


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atlas-chat-bridge",
        description="Bridge chat exports into the ATLAS Knowledge Engine.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest")
    ingest.add_argument("--input", required=True, type=Path)
    ingest.add_argument("--repo", default=Path.cwd(), type=Path)
    ingest.add_argument("--apply", action="store_true")

    watch = sub.add_parser("watch")
    watch.add_argument("--repo", default=Path.cwd(), type=Path)
    watch.add_argument("--interval", default=5, type=int)
    watch.add_argument("--apply", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.command == "ingest":
        bridge = AtlasChatBridge()
        receipt, preview = bridge.ingest_file(
            source_file=args.input,
            repository_root=args.repo,
            apply=args.apply,
        )
        print(receipt.model_dump_json(indent=2))
        if not args.apply:
            print("\n# Preview\n")
            print(preview)
        return 0

    watcher = InboxWatcher(args.repo, interval_seconds=args.interval)
    watcher.run_forever(apply=args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
