from __future__ import annotations

import re


_GENERATED_TITLE_FIXES = (
    (re.compile(r"\bdados\s+(?:real|reai)\b", re.IGNORECASE), "dados reais"),
)


def normalize_generated_title(value: str | None) -> str:
    """Correct narrow language defects in generated display/index titles.

    Human-authored bodies remain unchanged so the audit trail continues to
    reflect exactly what was entered. This helper is only for derived labels.
    """
    title = str(value or "")
    for pattern, replacement in _GENERATED_TITLE_FIXES:
        title = pattern.sub(replacement, title)
    return title
