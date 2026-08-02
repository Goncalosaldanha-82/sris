from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .models import RepositoryAsset, RepositoryAssetType


TEXT_EXTENSIONS = {
    ".md", ".txt", ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yml", ".yaml",
    ".toml", ".ini", ".cfg", ".sql", ".html", ".css", ".sh", ".cmd", ".ps1",
}

IGNORED_PARTS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "dist", "build",
}


class RepositoryScanner:
    def __init__(self, repository_root: Path) -> None:
        self.repository_root = repository_root.resolve()

    def scan(self) -> list[RepositoryAsset]:
        assets: list[RepositoryAsset] = []
        for path in self.repository_root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(self.repository_root)
            if any(part in IGNORED_PARTS for part in relative.parts):
                continue
            if path.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            assets.append(self._asset(path))
        return self._attach_backlinks(assets)

    def _asset(self, path: Path) -> RepositoryAsset:
        content = path.read_text(encoding="utf-8", errors="replace")
        relative = str(path.relative_to(self.repository_root)).replace("\\", "/")
        return RepositoryAsset(
            path=relative,
            asset_type=self._type(path),
            title=self._title(path, content),
            checksum=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            size_bytes=len(content.encode("utf-8")),
            references=self._references(content),
            metadata={"extension": path.suffix.lower()},
        )

    @staticmethod
    def _type(path: Path) -> RepositoryAssetType:
        rel = str(path).replace("\\", "/")
        if "/tests/" in rel or path.name.startswith("test_"):
            return RepositoryAssetType.TEST
        if "/migrations/" in rel:
            return RepositoryAssetType.MIGRATION
        if "/.github/workflows/" in rel:
            return RepositoryAssetType.WORKFLOW
        if path.suffix.lower() in {".py", ".js", ".ts", ".tsx", ".jsx"}:
            return RepositoryAssetType.CODE
        if path.suffix.lower() in {".yml", ".yaml", ".toml", ".ini", ".cfg", ".json"}:
            return RepositoryAssetType.CONFIGURATION
        if path.suffix.lower() in {".md", ".txt"}:
            return RepositoryAssetType.DOCUMENT
        return RepositoryAssetType.OTHER

    @staticmethod
    def _title(path: Path, content: str) -> str:
        match = re.search(r"(?m)^#\s+(.+?)\s*$", content)
        return match.group(1).strip() if match else path.name

    @staticmethod
    def _references(content: str) -> list[str]:
        refs = set()
        refs.update(re.findall(r"\b(?:HYP|MISSION|RN|ADR|THEORY|CONCEPT|VAL|EXP|DR)-\d{3,}\b", content))
        refs.update(re.findall(r"`([^`]+\.(?:md|py|json|yml|yaml|sql|html))`", content))
        return sorted(refs)

    def _attach_backlinks(self, assets: list[RepositoryAsset]) -> list[RepositoryAsset]:
        by_path = {asset.path: asset for asset in assets}
        by_name = {Path(asset.path).name: asset for asset in assets}

        for source in assets:
            for reference in source.references:
                target = by_path.get(reference) or by_name.get(Path(reference).name)
                if target and source.path not in target.referenced_by:
                    target.referenced_by.append(source.path)

        for asset in assets:
            asset.referenced_by = sorted(asset.referenced_by)
        return assets
