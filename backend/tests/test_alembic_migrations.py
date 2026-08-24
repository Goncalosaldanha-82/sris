import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine, inspect, text


def run_alembic(repo_root: Path, *args: str, database_url: str) -> None:
    env = os.environ.copy()
    env["ATLAS_DATABASE_URL"] = database_url
    env["PYTHONPATH"] = str(repo_root / "backend")

    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + "\n" + result.stderr


def table_names(database_url: str) -> set[str]:
    engine = create_engine(database_url)

    try:
        with engine.connect() as connection:
            return set(inspect(connection).get_table_names())
    finally:
        # Essential on Windows: closes pooled SQLite handles before
        # TemporaryDirectory attempts to delete the database file.
        engine.dispose()


def column_names(database_url: str, table_name: str) -> set[str]:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            return {
                column["name"]
                for column in inspect(connection).get_columns(table_name)
            }
    finally:
        engine.dispose()


def test_upgrade_and_downgrade_initial_schema() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    with TemporaryDirectory(prefix="atlas-migrations-") as tmp:
        database_path = Path(tmp) / "fresh-atlas-migrations.db"
        database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"

        run_alembic(
            repo_root,
            "upgrade",
            "head",
            database_url=database_url,
        )

        tables = table_names(database_url)

        expected = {
            "alembic_version",
            "users",
            "organizations",
            "memberships",
            "knowledge_objects",
            "audit_events",
            "password_recovery_uses",
            "password_reset_tokens",
            "user_invitations",
            "workflows",
            "workflow_candidates",
            "workflow_history",
            "repository_changes",
            "mi_missions",
            "mi_mission_revisions",
            "mi_intelligence_runs",
            "mi_ai_organization_policies",
            "mi_ai_usage_periods",
            "mi_ai_usage_events",
            "pilot_validation_protocols",
            "pilot_validation_measurements",
            "pilot_validation_events",
        }

        assert expected.issubset(tables)
        assert {
            "web_search_calls",
            "reserved_web_search_calls",
        }.issubset(column_names(database_url, "mi_ai_usage_periods"))
        assert {
            "reserved_web_search_calls",
            "web_search_calls",
            "web_search_cost_microusd",
            "web_search_rate_microusd_per_call",
        }.issubset(column_names(database_url, "mi_ai_usage_events"))
        assert {"auth_version", "last_login_at"}.issubset(
            column_names(database_url, "users")
        )
        assert {
            "parent_mission_id",
            "mission_kind",
            "domain",
            "priority",
            "sort_order",
        }.issubset(column_names(database_url, "mi_missions"))
        assert "enforce_monthly_limits" in column_names(
            database_url,
            "mi_ai_organization_policies",
        )

        run_alembic(
            repo_root,
            "downgrade",
            "base",
            database_url=database_url,
        )

        remaining = table_names(database_url)
        assert remaining in (set(), {"alembic_version"})


def test_document_source_migration_repairs_only_automatic_verification() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    with TemporaryDirectory(prefix="atlas-source-integrity-") as tmp:
        database_path = Path(tmp) / "source-integrity.db"
        database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"

        run_alembic(
            repo_root,
            "upgrade",
            "20260824_0015",
            database_url=database_url,
        )
        engine = create_engine(database_url)
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        CREATE TABLE pilot_evidence_graph_nodes (
                            id VARCHAR(64) PRIMARY KEY,
                            node_type VARCHAR(40) NOT NULL,
                            status VARCHAR(40) NOT NULL,
                            source_kind VARCHAR(80),
                            provenance_json TEXT NOT NULL DEFAULT '{}',
                            updated_at DATETIME
                        )
                        """
                    )
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO pilot_evidence_graph_nodes
                            (id, node_type, status, source_kind, provenance_json)
                        VALUES
                            (:automatic, 'evidence', 'verified', 'document_chunk', :automatic_provenance),
                            (:reviewed, 'evidence', 'verified', 'document_chunk', :reviewed_provenance)
                        """
                    ),
                    {
                        "automatic": "automatic-document-evidence",
                        "reviewed": "human-reviewed-evidence",
                        "automatic_provenance": json.dumps(
                            {"human_promoted": True, "authoritative_source": True}
                        ),
                        "reviewed_provenance": json.dumps(
                            {
                                "human_promoted": True,
                                "authoritative_source": True,
                                "factual_review_completed": True,
                                "factual_validation": "verified",
                            }
                        ),
                    },
                )
        finally:
            engine.dispose()

        run_alembic(repo_root, "upgrade", "head", database_url=database_url)

        engine = create_engine(database_url)
        try:
            with engine.connect() as connection:
                rows = {
                    row["id"]: row
                    for row in connection.execute(
                        text(
                            """
                            SELECT id, status, provenance_json
                            FROM pilot_evidence_graph_nodes
                            ORDER BY id
                            """
                        )
                    ).mappings()
                }
            automatic = rows["automatic-document-evidence"]
            automatic_provenance = json.loads(automatic["provenance_json"])
            assert automatic["status"] == "proposed"
            assert automatic_provenance["source_integrity_verified"] is True
            assert automatic_provenance["factual_validation"] == "not_assessed"
            assert automatic_provenance["authoritative_source"] is False
            assert rows["human-reviewed-evidence"]["status"] == "verified"
        finally:
            engine.dispose()
