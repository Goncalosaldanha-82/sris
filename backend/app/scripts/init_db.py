from __future__ import annotations

from pathlib import Path

from app.core.db import Base, engine
import app.models.models  # noqa: F401


def apply_postgres_migrations() -> None:
    if engine.dialect.name != "postgresql":
        return
    migrations_dir = Path(__file__).resolve().parents[3] / "migrations"
    raw = engine.raw_connection()
    try:
        cursor = raw.cursor()
        for path in sorted(migrations_dir.glob("*.sql")):
            sql = path.read_text(encoding="utf-8")
            cursor.execute(sql)
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


def main():
    Base.metadata.create_all(engine)
    apply_postgres_migrations()


if __name__ == "__main__":
    main()
