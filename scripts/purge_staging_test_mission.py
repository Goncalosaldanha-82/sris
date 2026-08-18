from __future__ import annotations

import os

from app.atlas_platform.database import SessionLocal
from app.mission_intelligence.models import CanonicalMission


STAGING_ENVIRONMENT_ID = "625472d4-144c-460a-b152-d1890f1f80db"
TEST_MISSION_CODE = "MIS-001"
TEST_TITLE_PREFIX = "teste de avalia"


def main() -> None:
    # Hard safety boundary: this cleanup is allowed only in the known Railway
    # staging environment. It must never run against production or local/CI DBs.
    if os.getenv("RAILWAY_ENVIRONMENT_ID") != STAGING_ENVIRONMENT_ID:
        print("Staging test mission purge skipped: environment is not SRIS staging.")
        return

    db = SessionLocal()
    try:
        row = (
            db.query(CanonicalMission)
            .filter(CanonicalMission.code == TEST_MISSION_CODE)
            .one_or_none()
        )
        if row is None:
            print(f"Staging test mission purge: {TEST_MISSION_CODE} not present.")
            return

        title = (row.title or "").strip().casefold()
        if not title.startswith(TEST_TITLE_PREFIX):
            print(
                "Staging test mission purge refused: MIS-001 exists but its title "
                "does not match the known test mission."
            )
            return

        mission_id = row.id
        mission_title = row.title
        db.delete(row)
        db.commit()
        print(
            f"Staging test mission purged: {TEST_MISSION_CODE} · "
            f"{mission_title} · {mission_id}"
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
