from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import case, create_engine
from sqlalchemy.orm import DeclarativeBase, Query, Session, sessionmaker

from .workspace_scope import get_active_organization_id
from sqlalchemy.pool import StaticPool

from .config import ensure_sqlite_parent, settings


ensure_sqlite_parent(settings.database_url)

is_sqlite = settings.database_url.startswith("sqlite")
is_memory_sqlite = settings.database_url in {
    "sqlite://",
    "sqlite+pysqlite:///:memory:",
    "sqlite:///:memory:",
}

engine_kwargs: dict = {"pool_pre_ping": True}

if is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}

if is_memory_sqlite:
    engine_kwargs["poolclass"] = StaticPool

engine = create_engine(settings.database_url, **engine_kwargs)

class WorkspaceAwareQuery(Query):
    """Prioritise the explicitly selected workspace without weakening RBAC.

    Existing Pilot modules historically selected the first membership by date.
    The request header only changes ordering among memberships that already
    belong to the authenticated user; it cannot create or bypass membership.
    """

    def first(self):
        organization_id = get_active_organization_id()
        if organization_id:
            try:
                from .models import Membership

                entities = {
                    description.get("entity")
                    for description in self.column_descriptions
                }
            except Exception:
                entities = set()
            if Membership in entities:
                ordered = self.order_by(None).order_by(
                    case(
                        (Membership.organization_id == organization_id, 0),
                        else_=1,
                    ),
                    Membership.created_at.asc(),
                )
                return Query.first(ordered)
        return Query.first(self)


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    query_cls=WorkspaceAwareQuery,
)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
