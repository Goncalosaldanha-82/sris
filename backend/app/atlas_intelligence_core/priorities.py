from __future__ import annotations

from .models import IntelligenceFinding, PriorityItem, Severity


SEVERITY_WEIGHT = {
    Severity.INFO: 10.0,
    Severity.LOW: 25.0,
    Severity.MEDIUM: 50.0,
    Severity.HIGH: 75.0,
    Severity.CRITICAL: 100.0,
}


class PriorityEngine:
    def rank(self, findings: list[IntelligenceFinding]) -> list[PriorityItem]:
        items: list[PriorityItem] = []
        for finding in findings:
            score = SEVERITY_WEIGHT[finding.severity]
            score += finding.confidence * 15.0
            score += min(len(finding.object_ids), 5) * 2.0
            if finding.type.value in {"contradiction", "missing_validation", "missing_provenance"}:
                score += 10.0
            items.append(
                PriorityItem(
                    finding_id=finding.finding_id,
                    title=finding.title,
                    severity=finding.severity,
                    score=round(score, 2),
                    reason=f"{finding.type.value}; confidence={finding.confidence:.2f}",
                    recommended_action=finding.recommended_action,
                )
            )
        return sorted(items, key=lambda item: item.score, reverse=True)
