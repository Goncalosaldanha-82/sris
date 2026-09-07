from __future__ import annotations

import json
import os
from sqlalchemy import create_engine, text

DB_URL = (os.getenv("ATLAS_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()
report = {"workspace_id": "a47c7c7e-24cf-4cd6-92f1-ac6f84a91db5", "owners": []}
if DB_URL:
    engine = create_engine(DB_URL, pool_pre_ping=True)
    with engine.connect() as conn:
        tx = conn.begin()
        if engine.dialect.name == "postgresql":
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text("SET LOCAL statement_timeout='10s'"))
        rows = conn.execute(
            text(
                """
                SELECT u.email, u.full_name, m.role, u.last_login_at,
                       o.id AS organization_id, o.name AS organization_name
                FROM memberships m
                JOIN users u ON u.id=m.user_id
                JOIN organizations o ON o.id=m.organization_id
                WHERE o.id=:organization_id AND m.role='owner'
                ORDER BY m.created_at ASC
                """
            ),
            {"organization_id": report["workspace_id"]},
        ).mappings().all()
        report["owners"] = [dict(row) for row in rows]
        tx.rollback()
print("SRIS_STAGING_OWNER_PROBE_START")
print(json.dumps(report, ensure_ascii=False, default=str, sort_keys=True))
print("SRIS_STAGING_OWNER_PROBE_END")
