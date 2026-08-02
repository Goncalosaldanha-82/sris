from __future__ import annotations

import re
from pathlib import Path

from pydantic import ValidationError

from .models import (
    ConfidenceLevel,
    KnowledgeItem,
    KnowledgePacket,
    KnowledgeState,
    KnowledgeType,
)


SECTION_MAP = {
    "decision": KnowledgeType.DECISION,
    "decisão": KnowledgeType.DECISION,
    "hypothesis": KnowledgeType.HYPOTHESIS,
    "hipótese": KnowledgeType.HYPOTHESIS,
    "concept": KnowledgeType.CONCEPT,
    "conceito": KnowledgeType.CONCEPT,
    "mission": KnowledgeType.MISSION,
    "missão": KnowledgeType.MISSION,
    "research note": KnowledgeType.RESEARCH_NOTE,
    "nota de investigação": KnowledgeType.RESEARCH_NOTE,
    "theory": KnowledgeType.THEORY,
    "teoria": KnowledgeType.THEORY,
    "ontology": KnowledgeType.ONTOLOGY,
    "ontologia": KnowledgeType.ONTOLOGY,
    "experiment": KnowledgeType.EXPERIMENT,
    "experiência": KnowledgeType.EXPERIMENT,
    "validation": KnowledgeType.VALIDATION,
    "validação": KnowledgeType.VALIDATION,
    "risk": KnowledgeType.RISK,
    "risco": KnowledgeType.RISK,
    "action": KnowledgeType.ACTION,
    "ação": KnowledgeType.ACTION,
    "observation": KnowledgeType.OBSERVATION,
    "observação": KnowledgeType.OBSERVATION,
    "correction": KnowledgeType.CORRECTION,
    "correção": KnowledgeType.CORRECTION,
    "architecture": KnowledgeType.ARCHITECTURE,
    "arquitetura": KnowledgeType.ARCHITECTURE,
}


class KnowledgeClassifier:
    def from_file(self, path: Path) -> KnowledgePacket:
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            try:
                return KnowledgePacket.model_validate_json(text)
            except ValidationError as exc:
                raise ValueError(f"Invalid KnowledgePacket JSON: {exc}") from exc
        return self.from_markdown(text, source_name=path.name)

    def from_markdown(self, text: str, *, source_name: str) -> KnowledgePacket:
        title = self._first_title(text) or f"ATLAS knowledge intake from {source_name}"
        items: list[KnowledgeItem] = []

        for heading, body in self._sections(text):
            kind = self._type_from_heading(heading)
            if kind is None or not body.strip():
                continue
            items.append(
                KnowledgeItem(
                    type=kind,
                    title=heading.strip()[:180],
                    summary=self._compact(body),
                    state=self._infer_state(body),
                    confidence=self._infer_confidence(body),
                    source_excerpt=body.strip()[:1200],
                    affected_assets=self._infer_assets(body),
                    related_concepts=self._infer_concepts(body),
                    tags=self._infer_tags(body),
                    limitations=self._infer_limitations(body),
                )
            )

        if not items:
            items.append(
                KnowledgeItem(
                    type=KnowledgeType.OBSERVATION,
                    title=title[:180],
                    summary=self._compact(text),
                    confidence=ConfidenceLevel.LOW,
                    source_excerpt=text.strip()[:1200],
                )
            )

        return KnowledgePacket(
            title=title,
            source_name=source_name,
            overall_summary=self._compact(text, limit=2200),
            items=items,
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
    def _normalize(value: str) -> str:
        return re.sub(r"[^a-záàâãéêíóôõúç ]", " ", value.lower()).strip()

    def _type_from_heading(self, heading: str) -> KnowledgeType | None:
        normalized = self._normalize(heading)
        for token, kind in SECTION_MAP.items():
            if token in normalized:
                return kind
        return None

    @staticmethod
    def _compact(text: str, limit: int = 5000) -> str:
        value = re.sub(r"\s+", " ", text).strip()
        return value[:limit] if value else "No summary supplied."

    @staticmethod
    def _infer_state(text: str) -> KnowledgeState:
        low = text.lower()
        mappings = (
            (("refuted", "refutada", "rejeitada"), KnowledgeState.REFUTED),
            (("deprecated", "abandonada"), KnowledgeState.DEPRECATED),
            (("adopted", "adotada", "aceite"), KnowledgeState.ADOPTED),
            (("contested", "contestada", "em crítica"), KnowledgeState.CONTESTED),
            (("active", "ativa"), KnowledgeState.ACTIVE),
            (("proposed", "proposta"), KnowledgeState.PROPOSED),
            (("working", "provisória", "de trabalho"), KnowledgeState.WORKING),
        )
        for words, state in mappings:
            if any(word in low for word in words):
                return state
        return KnowledgeState.CANDIDATE

    @staticmethod
    def _infer_confidence(text: str) -> ConfidenceLevel:
        low = text.lower()
        if any(x in low for x in ("high confidence", "confiança elevada")):
            return ConfidenceLevel.HIGH
        if any(x in low for x in ("low confidence", "confiança baixa", "incerto")):
            return ConfidenceLevel.LOW
        return ConfidenceLevel.MODERATE

    @staticmethod
    def _infer_assets(text: str) -> list[str]:
        values = re.findall(
            r"\b(?:ATLAS|TICC|SMK|SEE|SRIS|ASM|CISM|MISSION-\d+|IQ-\d+|RN-\d+|ADR-\d+)\b",
            text,
            flags=re.IGNORECASE,
        )
        return sorted({value.upper() for value in values})

    @staticmethod
    def _infer_concepts(text: str) -> list[str]:
        known = (
            "Omega",
            "CISM",
            "Justificabilidade",
            "Reconstruibilidade",
            "Meaning Asset",
            "Mission",
            "Authority",
            "Doctrine",
            "Evidence",
            "Provenance",
        )
        low = text.lower()
        return sorted({item for item in known if item.lower() in low})

    @staticmethod
    def _infer_tags(text: str) -> list[str]:
        low = text.lower()
        candidates = {
            "governance": ("governance", "governação"),
            "continuity": ("continuity", "continuidade"),
            "knowledge": ("knowledge", "conhecimento"),
            "research": ("research", "investigação"),
            "architecture": ("architecture", "arquitetura"),
            "validation": ("validation", "validação"),
            "authority": ("authority", "autoridade"),
            "evidence": ("evidence", "evidência"),
        }
        return sorted(
            tag for tag, words in candidates.items()
            if any(word in low for word in words)
        )

    @staticmethod
    def _infer_limitations(text: str) -> list[str]:
        limitations: list[str] = []
        for line in text.splitlines():
            low = line.lower().strip()
            if low.startswith(("- limitação", "- limitation", "limitation:", "limitação:")):
                limitations.append(line.lstrip("- ").split(":", 1)[-1].strip())
        return limitations
