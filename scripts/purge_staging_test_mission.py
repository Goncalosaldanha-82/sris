from __future__ import annotations

import os

from app.atlas_platform.database import SessionLocal
from app.mission_intelligence.models import CanonicalMission


STAGING_ENVIRONMENT_ID = "625472d4-144c-460a-b152-d1890f1f80db"
TEST_MISSION_CODE = "MIS-001"
TEST_TITLE_PREFIX = "teste de avaliação"


def main() -> None:
    if os.getenv("RAILWAY_ENVIRONMENT_ID") != STAGING_ENVIRONMENT_ID:
        print("Temporary mission cleanup skipped: not SRIS staging.")
        return

    db = SessionLocal()
    try:
        rows = (
            db.query(CanonicalMission)
            .filter(CanonicalMission.code == TEST_MISSION_CODE)
            .all()
        )
        matches = [
            row for row in rows
            if (row.title or "").strip().casefold().startswith(TEST_TITLE_PREFIX)
        ]

        if not matches:
            print("Temporary mission cleanup: no matching MIS-001 test mission found.")
            return

        for row in matches:
            print(
                "Temporary mission cleanup: deleting "
                f"{row.code} · {row.title} · org={row.organization_id} · id={row.id}"
            )
            db.delete(row)

        db.commit()
        print(f"Temporary mission cleanup completed: {len(matches)} row(s) deleted.")
    except Exception as exc:
        # Cleanup must never prevent staging from starting. The UI independently hides
        # MIS-001, so a transient database cleanup failure is non-fatal.
        db.rollback()
        print(f"Temporary mission cleanup warning: {type(exc).__name__}: {exc}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
