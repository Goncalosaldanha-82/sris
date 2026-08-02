from __future__ import annotations

import base64
from dataclasses import dataclass

import httpx

from .models import AgentPlan


@dataclass(frozen=True)
class GitHubConfig:
    token: str
    repository: str  # owner/name
    base_branch: str = "feature/ske-core"
    api_url: str = "https://api.github.com"


class GitHubPullRequestClient:
    """Minimal GitHub Contents/Refs/Pulls client.

    Safety policy:
    - never pushes directly to the base branch;
    - creates a dedicated branch;
    - always opens a pull request;
    - requires human merge.
    """

    def __init__(self, config: GitHubConfig) -> None:
        self.config = config
        self.client = httpx.Client(
            base_url=config.api_url,
            headers={
                "Authorization": f"Bearer {config.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "atlas-repository-agent-v0.1",
            },
            timeout=30.0,
        )

    def close(self) -> None:
        self.client.close()

    def publish(self, plan: AgentPlan) -> str:
        branch = plan.branch_name
        base_sha = self._branch_sha(self.config.base_branch)
        self._create_branch(branch, base_sha)

        for mutation in plan.mutations:
            self._put_file(
                path=mutation.path,
                content=mutation.content,
                branch=branch,
                message=plan.commit_message,
            )

        response = self.client.post(
            f"/repos/{self.config.repository}/pulls",
            json={
                "title": plan.pull_request_title,
                "head": branch,
                "base": self.config.base_branch,
                "body": plan.pull_request_body,
                "draft": True,
            },
        )
        self._raise(response)
        return response.json()["html_url"]

    def _branch_sha(self, branch: str) -> str:
        response = self.client.get(
            f"/repos/{self.config.repository}/git/ref/heads/{branch}"
        )
        self._raise(response)
        return response.json()["object"]["sha"]

    def _create_branch(self, branch: str, sha: str) -> None:
        response = self.client.post(
            f"/repos/{self.config.repository}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": sha},
        )
        self._raise(response)

    def _get_file_sha(self, path: str, branch: str) -> str | None:
        response = self.client.get(
            f"/repos/{self.config.repository}/contents/{path}",
            params={"ref": branch},
        )
        if response.status_code == 404:
            return None
        self._raise(response)
        return response.json()["sha"]

    def _put_file(self, *, path: str, content: str, branch: str, message: str) -> None:
        sha = self._get_file_sha(path, branch)
        payload = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha
        response = self.client.put(
            f"/repos/{self.config.repository}/contents/{path}",
            json=payload,
        )
        self._raise(response)

    @staticmethod
    def _raise(response: httpx.Response) -> None:
        if response.is_error:
            raise RuntimeError(
                f"GitHub API error {response.status_code}: {response.text[:1000]}"
            )
