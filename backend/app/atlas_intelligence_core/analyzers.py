from __future__ import annotations

from datetime import datetime, timezone
from itertools import combinations
from uuid import UUID

from app.amos.models import MemoryObject, MemoryObjectType, MemoryState

from .models import FindingType, IntelligenceFinding, Severity
from .text import contains_negation, cosine_similarity


class DuplicateAnalyzer:
    def analyze(self, objects: list[MemoryObject]) -> list[IntelligenceFinding]:
        findings: list[IntelligenceFinding] = []
        for left, right in combinations(objects, 2):
            score = cosine_similarity(
                f"{left.title} {left.summary}",
                f"{right.title} {right.summary}",
            )
            if score < 0.82:
                continue
            findings.append(
                IntelligenceFinding(
                    type=FindingType.DUPLICATION,
                    severity=Severity.MEDIUM,
                    title=f"Possible duplicate knowledge: {left.title} / {right.title}",
                    summary="Two memory objects contain highly similar language and may represent duplicate or overlapping knowledge.",
                    object_ids=[left.object_id, right.object_id],
                    source_paths=[p for p in (left.source_path, right.source_path) if p],
                    rationale=f"Lexical cosine similarity={score:.3f}.",
                    recommended_action="Review both objects; merge, distinguish or explicitly relate them.",
                    confidence=min(0.95, score),
                )
            )
        return findings


class ContradictionAnalyzer:
    def analyze(self, objects: list[MemoryObject]) -> list[IntelligenceFinding]:
        findings: list[IntelligenceFinding] = []
        for left, right in combinations(objects, 2):
            if left.type != right.type:
                continue
            similarity = cosine_similarity(left.summary, right.summary)
            if similarity < 0.50:
                continue
            if contains_negation(left.summary) == contains_negation(right.summary):
                continue
            findings.append(
                IntelligenceFinding(
                    type=FindingType.CONTRADICTION,
                    severity=Severity.HIGH,
                    title=f"Potential contradiction: {left.title} / {right.title}",
                    summary="The objects discuss similar content but differ in polarity or rejection language.",
                    object_ids=[left.object_id, right.object_id],
                    source_paths=[p for p in (left.source_path, right.source_path) if p],
                    rationale=f"Shared semantic vocabulary={similarity:.3f}; opposite negation signature.",
                    recommended_action="Perform human comparison and record whether this is a true contradiction, revision or contextual distinction.",
                    confidence=min(0.85, 0.45 + similarity / 2),
                )
            )
        return findings


class OrphanAnalyzer:
    RELATION_SENSITIVE = {
        MemoryObjectType.HYPOTHESIS,
        MemoryObjectType.MISSION,
        MemoryObjectType.THEORY,
        MemoryObjectType.EXPERIMENT,
        MemoryObjectType.VALIDATION,
        MemoryObjectType.DECISION,
    }

    def analyze(
        self,
        objects: list[MemoryObject],
        graph: dict[UUID, list[tuple[UUID, str]]],
    ) -> list[IntelligenceFinding]:
        findings: list[IntelligenceFinding] = []
        for obj in objects:
            if obj.type not in self.RELATION_SENSITIVE:
                continue
            if graph.get(obj.object_id):
                continue
            findings.append(
                IntelligenceFinding(
                    type=FindingType.ORPHAN,
                    severity=Severity.MEDIUM,
                    title=f"Unconnected memory object: {obj.title}",
                    summary="The object has no explicit relation to another AMOS memory object.",
                    object_ids=[obj.object_id],
                    source_paths=[obj.source_path] if obj.source_path else [],
                    rationale="No incoming or outgoing memory relation exists.",
                    recommended_action="Add explicit references or a governed relation to its source, evidence, mission or dependent asset.",
                    confidence=0.98,
                )
            )
        return findings


class ValidationGapAnalyzer:
    def analyze(
        self,
        objects: list[MemoryObject],
        graph: dict[UUID, list[tuple[UUID, str]]],
    ) -> list[IntelligenceFinding]:
        by_id = {obj.object_id: obj for obj in objects}
        findings: list[IntelligenceFinding] = []

        for obj in objects:
            if obj.type not in {MemoryObjectType.HYPOTHESIS, MemoryObjectType.THEORY}:
                continue
            connected = [by_id[target] for target, _ in graph.get(obj.object_id, []) if target in by_id]
            has_validation = any(
                linked.type in {MemoryObjectType.EXPERIMENT, MemoryObjectType.VALIDATION}
                for linked in connected
            )
            if has_validation:
                continue
            severity = (
                Severity.HIGH
                if obj.state in {MemoryState.ADOPTED, MemoryState.ACTIVE}
                else Severity.MEDIUM
            )
            findings.append(
                IntelligenceFinding(
                    type=FindingType.MISSING_VALIDATION,
                    severity=severity,
                    title=f"No validation path: {obj.title}",
                    summary="The hypothesis or theory has no explicit relation to an experiment or validation object.",
                    object_ids=[obj.object_id],
                    source_paths=[obj.source_path] if obj.source_path else [],
                    rationale=f"Object type={obj.type.value}; state={obj.state.value}; no experiment/validation relation.",
                    recommended_action="Link existing evidence or open a validation mission. Do not present the object as empirically supported.",
                    confidence=0.96,
                )
            )
        return findings


class StalenessAnalyzer:
    def __init__(self, threshold_days: int = 180) -> None:
        self.threshold_days = threshold_days

    def analyze(self, objects: list[MemoryObject]) -> list[IntelligenceFinding]:
        now = datetime.now(timezone.utc)
        findings: list[IntelligenceFinding] = []
        for obj in objects:
            age = (now - obj.updated_at).days
            if age < self.threshold_days:
                continue
            findings.append(
                IntelligenceFinding(
                    type=FindingType.STALENESS,
                    severity=Severity.LOW if age < 365 else Severity.MEDIUM,
                    title=f"Potentially stale object: {obj.title}",
                    summary=f"The memory object has not been updated for {age} days.",
                    object_ids=[obj.object_id],
                    source_paths=[obj.source_path] if obj.source_path else [],
                    rationale=f"updated_at={obj.updated_at.isoformat()}, threshold={self.threshold_days} days.",
                    recommended_action="Review whether the object remains valid, needs revision, or should be archived.",
                    confidence=0.99,
                )
            )
        return findings


class ProvenanceAnalyzer:
    def analyze(self, objects: list[MemoryObject]) -> list[IntelligenceFinding]:
        findings: list[IntelligenceFinding] = []
        for obj in objects:
            if obj.source_path or obj.source_id:
                continue
            findings.append(
                IntelligenceFinding(
                    type=FindingType.MISSING_PROVENANCE,
                    severity=Severity.HIGH,
                    title=f"Missing provenance: {obj.title}",
                    summary="The memory object has neither a source path nor a source identifier.",
                    object_ids=[obj.object_id],
                    rationale="source_path and source_id are both absent.",
                    recommended_action="Attach a source, origin record or explicit unknown-provenance declaration.",
                    confidence=1.0,
                )
            )
        return findings
