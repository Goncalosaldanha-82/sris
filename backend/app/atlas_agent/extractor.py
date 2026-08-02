from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import ValidationError

from .models import (
    AtlasChangeItem,
    AtlasChangeSet,
    ChangeKind,
    EpistemicState,
)


HEADING_KIND: dict[str, ChangeKind] = {
    "decision": ChangeKind.DECISION,
    "decisão": ChangeKind.DECISION,
    "hypothesis": ChangeKind.HYPOTHESIS,
    "hipótese": ChangeKind.HYPOTHESIS,
    "concept": ChangeKind.CONCEPT,
    "conceito": ChangeKind.CONCEPT,
    "risk": ChangeKind.RISK,
    "risco": ChangeKind.RISK,
    "action": ChangeKind.ACTION,
    "ação": ChangeKind.ACTION,
    "observação": ChangeKind.OBSERVATION,
    "observation": ChangeKind.OBSERVATION,
    "architecture": ChangeKind.ARCHITECTURE,
    "arquitetura": ChangeKind.ARCHITECTURE,
    "correction": ChangeKind.CORRECTION,
    "correção": ChangeKind.CORRECTION,
}


class ChangeSetExtractor:
    """Deterministic v0.1 extractor.

    It accepts either:
    1. a structured JSON AtlasChangeSet; or
    2. Markdown/text with semantic headings such as "## Decision".
    """

    def from_file(self, path: Path) -> AtlasChangeSet:
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            try:
                return AtlasChangeSet.model_validate_json(text)
            except ValidationError as exc:
                raise ValueError(f"Invalid AtlasChangeSet JSON: {exc}") from exc
        return self.from_markdown(text, source_name=path.name)

    def from_markdown(self, text: str, *, source_name: str) -> AtlasChangeSet:
        title = self._first_title(text) or f"ATLAS update from {source_name}"
        sections = self._sections(text)
        items: list[AtlasChangeItem] = []

        for heading, body in sections:
            normalized = self._normalize_heading(heading)
            kind = self._kind_from_heading(normalized)
            if kind is None or not body.strip():
                continue
            items.append(
                AtlasChangeItem(
                    kind=kind,
                    title=heading.strip()[:180],
                    summary=self._compact(body),
                    state=self._infer_state(body),
                    affected_assets=self._infer_assets(body),
                    source_excerpt=body.strip()[:1000],
                )
            )

        if not items:
            items = [
                AtlasChangeItem(
                    kind=ChangeKind.OBSERVATION,
                    title=title[:180],
                    summary=self._compact(text),
                    state=EpistemicState.CANDIDATE,
                    source_excerpt=text.strip()[:1000],
                )
            ]

        return AtlasChangeSet(
            title=title,
            source_name=source_name,
            items=items,
            overall_summary=self._compact(text, limit=1800),
        )

    @staticmethod
    def _first_title(text: str) -> str | None:
        match = re.search(r"(?m)^#\s+(.+?)\s*$", text)
        return match.group(1).strip() if match else None

    @staticmethod
    def _sections(text: str) -> list[tuple[str, str]]:
        pattern = re.compile(r"(?m)^#{2,4}\s+(.+?)\s*$")
        matches = list(pattern.finditer(text))
        result: list[tuple[str, str]] = []
        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            result.append((match.group(1), text[start:end].strip()))
        return result

    @staticmethod
    def _normalize_heading(value: str) -> str:
        return re.sub(r"[^a-záàâãéêíóôõúç ]", " ", value.lower()).strip()

    @staticmethod
    def _kind_from_heading(heading: str) -> ChangeKind | None:
        for token, kind in HEADING_KIND.items():
            if token in heading:
                return kind
        return None

    @staticmethod
    def _compact(text: str, limit: int = 4000) -> str:
        value = re.sub(r"\s+", " ", text).strip()
        return value[:limit] if value else "No summary supplied."

    @staticmethod
    def _infer_state(text: str) -> EpistemicState:
        low = text.lower()
        mappings = (
            (("refuted", "refutada", "rejeitada"), EpistemicState.REFUTED),
            (("deprecated", "abandonada"), EpistemicState.DEPRECATED),
            (("adopted", "adotada", "aceite"), EpistemicState.ADOPTED),
            (("contested", "contestada", "em crítica"), EpistemicState.CONTESTED),
            (("active", "ativa"), EpistemicState.ACTIVE),
            (("proposed", "proposta"), EpistemicState.PROPOSED),
            (("working", "provisória", "de trabalho"), EpistemicState.WORKING),
        )
        for words, state in mappings:
            if any(word in low for word in words):
                return state
        return EpistemicState.CANDIDATE

    @staticmethod
    def _infer_assets(text: str) -> list[str]:
        candidates = re.findall(
            r"\b(?:ATLAS|TICC|SMK|SEE|SRIS|ASM|CISM|MISSION-\d+|IQ-\d+|RN-\d+|ADR-\d+)\b",
            text,
            flags=re.IGNORECASE,
        )
        return sorted({item.upper() for item in candidates})
