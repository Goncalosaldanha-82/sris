from __future__ import annotations

from contextvars import ContextVar, Token


_active_organization_id: ContextVar[str | None] = ContextVar(
    "sris_active_organization_id",
    default=None,
)


def _normalise(value: str | None) -> str | None:
    cleaned = str(value or "").strip()
    return cleaned[:128] or None


def set_active_organization_id(value: str | None) -> Token:
    """Bind the requested workspace to the current HTTP request context."""

    return _active_organization_id.set(_normalise(value))


def reset_active_organization_id(token: Token) -> None:
    _active_organization_id.reset(token)


def get_active_organization_id() -> str | None:
    return _active_organization_id.get()
