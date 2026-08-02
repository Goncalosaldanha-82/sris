from __future__ import annotations

import subprocess
from pathlib import Path

from .models import ApplyResult, ChangeType, RepositoryChangePlan


class RepositoryApplier:
    def __init__(self, repository_root: Path) -> None:
        self.repository_root = repository_root.resolve()

    def preview(self, plan: RepositoryChangePlan) -> str:
        import difflib
        chunks: list[str] = []
        for change in plan.changes:
            path = self.repository_root / change.path
            before = path.read_text(encoding="utf-8") if path.exists() else ""
            after = "" if change.change_type == ChangeType.DELETE else (change.content or "")
            chunks.extend(
                difflib.unified_diff(
                    before.splitlines(),
                    after.splitlines(),
                    fromfile=f"a/{change.path}",
                    tofile=f"b/{change.path}",
                    lineterm="",
                )
            )
        return "\n".join(chunks)

    def apply(
        self,
        plan: RepositoryChangePlan,
        *,
        create_branch: bool = False,
        commit: bool = False,
        push: bool = False,
    ) -> ApplyResult:
        if (commit or push) and not create_branch:
            raise ValueError("Commit/push requires create_branch=True")

        if create_branch:
            self._git("checkout", "-b", plan.branch_name)

        changed_paths: list[str] = []
        for change in plan.changes:
            target = (self.repository_root / change.path).resolve()
            if self.repository_root not in target.parents:
                raise ValueError(f"Unsafe path: {change.path}")

            if change.change_type == ChangeType.DELETE:
                if target.exists():
                    target.unlink()
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(change.content or "", encoding="utf-8")
            changed_paths.append(change.path)

        commit_hash = None
        if commit:
            self._git("add", "--", *changed_paths)
            self._git("commit", "-m", plan.commit_message)
            commit_hash = self._git("rev-parse", "HEAD").strip()

        if push:
            self._git("push", "-u", "origin", plan.branch_name)

        return ApplyResult(
            plan_id=plan.plan_id,
            changed_paths=changed_paths,
            branch_name=plan.branch_name,
            commit_hash=commit_hash,
            committed=commit,
            pushed=push,
        )

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self.repository_root,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return result.stdout
