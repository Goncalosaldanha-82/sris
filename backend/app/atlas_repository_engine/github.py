from __future__ import annotations

import httpx

from .models import RepositoryChangePlan


class GitHubPullRequestClient:
    def __init__(self, *, token: str, repository: str, base_branch: str) -> None:
        self.repository = repository
        self.base_branch = base_branch
        self.client = httpx.Client(
            base_url="https://api.github.com",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "atlas-repository-engine-v0.1",
            },
            timeout=30,
        )

    def create_draft_pull_request(self, plan: RepositoryChangePlan) -> str:
        response = self.client.post(
            f"/repos/{self.repository}/pulls",
            json={
                "title": plan.pull_request_title,
                "head": plan.branch_name,
                "base": self.base_branch,
                "body": plan.pull_request_body,
                "draft": True,
            },
        )
        if response.is_error:
            raise RuntimeError(f"GitHub API error {response.status_code}: {response.text[:1000]}")
        return response.json()["html_url"]

    def close(self) -> None:
        self.client.close()
