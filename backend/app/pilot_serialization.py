from __future__ import annotations


def as_iso(value: object | None) -> str | None:
    """Serialize mapped SQL date values consistently on SQLite and Postgres."""
    if value is None:
        return None
    formatter = getattr(value, "isoformat", None)
    return formatter() if callable(formatter) else str(value)
