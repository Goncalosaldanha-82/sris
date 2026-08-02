from __future__ import annotations

import argparse
import os
from pathlib import Path

from .github_client import GitHubConfig, GitHubPullRequestClient
from .service import AtlasRepositoryAgent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atlas-repository-agent",
        description="Prepare governed ATLAS documentation updates from Markdown or JSON.",
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--repo", default=Path.cwd(), type=Path)
    parser.add_argument(
        "--mode",
        choices=("preview", "local", "github"),
        default="preview",
    )
    parser.add_argument("--base-branch", default="feature/ske-core")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    agent = AtlasRepositoryAgent()
    plan = agent.plan(source_file=args.input, repository_root=args.repo)

    if args.mode == "preview":
        print(agent.preview(source_file=args.input, repository_root=args.repo))
        return 0

    if args.mode == "local":
        agent.apply_local(source_file=args.input, repository_root=args.repo)
        print(f"Applied {len(plan.mutations)} mutations locally.")
        print(f"Suggested branch: {plan.branch_name}")
        print(f"Suggested commit: {plan.commit_message}")
        return 0

    token = os.getenv("GITHUB_TOKEN")
    repository = os.getenv("GITHUB_REPOSITORY")
    if not token or not repository:
        raise SystemExit(
            "GITHUB_TOKEN and GITHUB_REPOSITORY=owner/name are required for github mode."
        )

    client = GitHubPullRequestClient(
        GitHubConfig(
            token=token,
            repository=repository,
            base_branch=args.base_branch,
        )
    )
    try:
        url = client.publish(plan)
    finally:
        client.close()
    print(f"Draft pull request created: {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
