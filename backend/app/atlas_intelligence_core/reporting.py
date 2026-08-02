from __future__ import annotations

import json
from pathlib import Path

from .models import IntelligenceReport


class IntelligenceReportWriter:
    def __init__(self, repository_root: Path) -> None:
        self.repository_root = repository_root.resolve()

    def write(self, report: IntelligenceReport) -> tuple[Path, Path]:
        folder = self.repository_root / "docs/atlas/intelligence"
        folder.mkdir(parents=True, exist_ok=True)

        markdown_path = folder / "AIC-STATUS.md"
        json_path = folder / "AIC-LATEST.json"

        markdown_path.write_text(self._markdown(report), encoding="utf-8")
        json_path.write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return markdown_path, json_path

    def _markdown(self, report: IntelligenceReport) -> str:
        lines = [
            "# ATLAS Intelligence Core — Status",
            "",
            f"**Generated:** `{report.generated_at.isoformat()}`  ",
            f"**Memory objects:** `{report.object_count}`  ",
            f"**Relations:** `{report.relation_count}`  ",
            f"**Findings:** `{report.finding_count}`  ",
            "",
            "## Executive summary",
            "",
            report.summary,
            "",
            "## Priorities",
            "",
            "| Score | Severity | Finding | Recommended action |",
            "|---:|---|---|---|",
        ]
        for item in report.priorities[:20]:
            lines.append(
                f"| {item.score:.2f} | {item.severity.value} | "
                f"{self._escape(item.title)} | {self._escape(item.recommended_action)} |"
            )

        lines.extend([
            "",
            "## Findings",
            "",
        ])
        for finding in report.findings:
            lines.extend([
                f"### {finding.severity.value.upper()} — {finding.title}",
                "",
                finding.summary,
                "",
                f"- **Type:** `{finding.type.value}`",
                f"- **Confidence:** `{finding.confidence:.2f}`",
                f"- **Rationale:** {finding.rationale}",
                f"- **Recommended action:** {finding.recommended_action}",
                f"- **Sources:** {', '.join(finding.source_paths) or 'Not supplied'}",
                "",
            ])

        lines.extend([
            "## Governance notice",
            "",
            "> The ATLAS Intelligence Core produces analytical findings, not scientific proof or authorized decisions. Human review is mandatory.",
            "",
        ])
        return "\n".join(lines)

    @staticmethod
    def _escape(value: str) -> str:
        return value.replace("|", "\\|").replace("\n", " ")
