from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import settings


is_sqlite = settings.database_url.startswith("sqlite")
is_memory_sqlite = settings.database_url in {
    "sqlite://",
    "sqlite+pysqlite:///:memory:",
    "sqlite:///:memory:",
}

engine_kwargs: dict = {
    "pool_pre_ping": True,
}

if is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}

if is_memory_sqlite:
    engine_kwargs["poolclass"] = StaticPool

engine = create_engine(
    settings.database_url,
    **engine_kwargs,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
