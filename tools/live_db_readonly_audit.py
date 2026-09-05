from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from sqlalchemy import create_engine, inspect, text

DB_URL = (os.getenv("ATLAS_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()
if not DB_URL:
    raise SystemExit("SRIS_DB_AUDIT_FATAL: no ATLAS_DATABASE_URL/DATABASE_URL configured")

engine = create_engine(DB_URL, pool_pre_ping=True)
report = {
    "started_at": datetime.now(timezone.utc).isoformat(),
    "database_dialect": engine.dialect.name,
    "counts": {},
    "grouped": {},
    "checks": [],
    "findings": [],
}


def finding(severity: str, title: str, detail: str = "", evidence=None):
    report["findings"].append({"severity": severity, "title": title, "detail": detail, "evidence": evidence})


def check(name: str, ok: bool, detail: str = "", severity: str = "major", evidence=None):
    report["checks"].append({"name": name, "ok": bool(ok), "detail": detail, "severity": severity, "evidence": evidence})
    if not ok:
        finding(severity, name, detail, evidence)
    return bool(ok)


with engine.connect() as conn:
    tx = conn.begin()
    if engine.dialect.name == "postgresql":
        conn.execute(text("SET TRANSACTION READ ONLY"))
        conn.execute(text("SET LOCAL statement_timeout = '20s'"))
        conn.execute(text("SET LOCAL lock_timeout = '3s'"))

    inspector = inspect(conn)
    tables = set(inspector.get_table_names())
    report["table_count"] = len(tables)

    def exists(table: str) -> bool:
        return table in tables

    def columns(table: str) -> set[str]:
        return {c["name"] for c in inspector.get_columns(table)} if exists(table) else set()

    def scalar(sql: str, params=None, default=0):
        value = conn.execute(text(sql), params or {}).scalar()
        return default if value is None else value

    def rows(sql: str, params=None):
        return [dict(r) for r in conn.execute(text(sql), params or {}).mappings().all()]

    candidate_tables = [
        "users", "organizations", "memberships", "audit_events", "knowledge_objects",
        "user_invitations", "password_reset_tokens", "password_recovery_uses",
        "pilot_release_acceptances", "mi_missions", "mi_mission_attachments",
        "pilot_evidence_graph_nodes", "pilot_evidence_graph_edges",
        "pilot_alternative_matrices", "pilot_business_cases", "pilot_business_case_items",
        "pilot_validation_protocols", "pilot_validation_measurements", "pilot_decision_cycles",
        "pilot_learning_packets", "pilot_mission_governance_policies", "pilot_mission_module_reviews",
        "pilot_portfolios", "pilot_programs", "pilot_charters", "pilot_scorecards",
    ]
    for table in candidate_tables:
        if exists(table):
            report["counts"][table] = int(scalar(f'SELECT COUNT(*) FROM "{table}"'))

    if exists("alembic_version"):
        revisions = [str(r["version_num"]) for r in rows("SELECT version_num FROM alembic_version ORDER BY version_num")]
        report["alembic_versions"] = revisions
        check("Exactly one Alembic revision is active", len(revisions) == 1, json.dumps(revisions), "critical")

    if all(exists(t) for t in ("memberships", "users", "organizations")):
        orphan_users = int(scalar("SELECT COUNT(*) FROM memberships m LEFT JOIN users u ON u.id=m.user_id WHERE u.id IS NULL"))
        orphan_orgs = int(scalar("SELECT COUNT(*) FROM memberships m LEFT JOIN organizations o ON o.id=m.organization_id WHERE o.id IS NULL"))
        check("Memberships reference existing users", orphan_users == 0, f"orphans={orphan_users}", "critical")
        check("Memberships reference existing organizations", orphan_orgs == 0, f"orphans={orphan_orgs}", "critical")
        multi = rows("SELECT user_id, COUNT(*) AS memberships FROM memberships GROUP BY user_id HAVING COUNT(*)>1 ORDER BY memberships DESC, user_id")
        report["grouped"]["users_with_multiple_workspaces"] = {"count": len(multi), "membership_distribution": sorted(int(r["memberships"]) for r in multi)}

    if all(exists(t) for t in ("organizations", "memberships", "mi_missions")):
        by_org = rows("""
            SELECT o.id AS organization_id, COUNT(DISTINCT m.id) AS mission_count,
                   COUNT(DISTINCT mb.user_id) AS member_count
            FROM organizations o
            LEFT JOIN mi_missions m ON m.organization_id=o.id
            LEFT JOIN memberships mb ON mb.organization_id=o.id
            GROUP BY o.id ORDER BY mission_count DESC, member_count DESC, o.id
        """)
        report["grouped"]["organizations"] = by_org
        report["grouped"]["organization_summary"] = {
            "total": len(by_org),
            "mission_bearing": sum(1 for r in by_org if int(r["mission_count"] or 0)>0),
            "zero_mission": sum(1 for r in by_org if int(r["mission_count"] or 0)==0),
        }
        duplicate_codes = rows("SELECT organization_id, code, COUNT(*) AS total FROM mi_missions GROUP BY organization_id, code HAVING COUNT(*)>1 ORDER BY total DESC")
        check("Mission codes are unique within each organization", len(duplicate_codes)==0, f"duplicate_groups={len(duplicate_codes)}", "critical", duplicate_codes[:20])
        orphan_mission_org = int(scalar("SELECT COUNT(*) FROM mi_missions m LEFT JOIN organizations o ON o.id=m.organization_id WHERE o.id IS NULL"))
        check("Missions reference existing organizations", orphan_mission_org==0, f"orphans={orphan_mission_org}", "critical")
        orgs_no_members = int(scalar("SELECT COUNT(*) FROM organizations o WHERE NOT EXISTS (SELECT 1 FROM memberships mb WHERE mb.organization_id=o.id)"))
        check("Organizations have at least one member", orgs_no_members==0, f"organizations_without_members={orgs_no_members}", "major")
        mission_orgs_no_members = int(scalar("SELECT COUNT(DISTINCT m.organization_id) FROM mi_missions m WHERE NOT EXISTS (SELECT 1 FROM memberships mb WHERE mb.organization_id=m.organization_id)"))
        check("Mission-bearing organizations have at least one member", mission_orgs_no_members==0, f"mission_orgs_without_members={mission_orgs_no_members}", "critical")
        patterns = rows("""
            WITH member_orgs AS (
                SELECT mb.user_id, mb.organization_id, COUNT(m.id) AS mission_count
                FROM memberships mb LEFT JOIN mi_missions m ON m.organization_id=mb.organization_id
                GROUP BY mb.user_id, mb.organization_id
            ), per_user AS (
                SELECT user_id, COUNT(*) AS workspaces,
                       SUM(CASE WHEN mission_count>0 THEN 1 ELSE 0 END) AS mission_workspaces,
                       SUM(mission_count) AS missions_total
                FROM member_orgs GROUP BY user_id HAVING COUNT(*)>1
            )
            SELECT workspaces, mission_workspaces, missions_total, COUNT(*) AS users
            FROM per_user GROUP BY workspaces, mission_workspaces, missions_total
            ORDER BY users DESC, workspaces DESC
        """)
        report["grouped"]["multi_workspace_patterns"] = patterns
        at_risk_users = int(scalar("""
            WITH member_orgs AS (
                SELECT mb.user_id, mb.organization_id, COUNT(m.id) AS mission_count
                FROM memberships mb LEFT JOIN mi_missions m ON m.organization_id=mb.organization_id
                GROUP BY mb.user_id, mb.organization_id
            ), per_user AS (
                SELECT user_id, COUNT(*) AS workspaces,
                       SUM(CASE WHEN mission_count>0 THEN 1 ELSE 0 END) AS mission_workspaces
                FROM member_orgs GROUP BY user_id
            )
            SELECT COUNT(*) FROM per_user WHERE workspaces>1 AND mission_workspaces>0 AND mission_workspaces<workspaces
        """))
        report["grouped"]["workspace_continuity_risk_users"] = at_risk_users
        if at_risk_users:
            finding("major", "Live data contains multi-workspace users with missions in only some workspaces", f"users={at_risk_users}; this data shape can surface an empty portfolio if workspace selection is lost")

    def mission_tenant_check(table: str):
        if not (exists(table) and exists("mi_missions")):
            return
        cols = columns(table)
        if not {"mission_id", "organization_id"}.issubset(cols):
            return
        orphan = int(scalar(f'SELECT COUNT(*) FROM "{table}" t LEFT JOIN mi_missions m ON m.id=t.mission_id WHERE m.id IS NULL'))
        mismatch = int(scalar(f'SELECT COUNT(*) FROM "{table}" t JOIN mi_missions m ON m.id=t.mission_id WHERE t.organization_id<>m.organization_id'))
        check(f"{table}: mission references resolve", orphan==0, f"orphans={orphan}", "critical")
        check(f"{table}: organization matches mission tenant", mismatch==0, f"cross_tenant={mismatch}", "critical")

    for table in ("mi_mission_attachments", "pilot_evidence_graph_nodes", "pilot_alternative_matrices", "pilot_business_cases", "pilot_validation_protocols", "pilot_validation_measurements", "pilot_mission_governance_policies", "pilot_mission_module_reviews"):
        mission_tenant_check(table)

    if exists("mi_mission_attachments") and "extraction_status" in columns("mi_mission_attachments"):
        extraction = rows("SELECT extraction_status, COUNT(*) AS total FROM mi_mission_attachments GROUP BY extraction_status ORDER BY total DESC, extraction_status")
        report["grouped"]["attachment_extraction_status"] = extraction
        failed = sum(int(r["total"] or 0) for r in extraction if str(r["extraction_status"] or "").lower() in {"failed", "error"})
        check("No attachment extraction is in failed/error state", failed==0, f"failed_or_error={failed}", "major", extraction)

    if all(exists(t) for t in ("pilot_evidence_graph_edges", "pilot_evidence_graph_nodes")):
        ec = columns("pilot_evidence_graph_edges")
        from_col = "from_node_id" if "from_node_id" in ec else ("source_node_id" if "source_node_id" in ec else None)
        to_col = "to_node_id" if "to_node_id" in ec else ("target_node_id" if "target_node_id" in ec else None)
        if from_col and to_col:
            orphan_from = int(scalar(f'SELECT COUNT(*) FROM pilot_evidence_graph_edges e LEFT JOIN pilot_evidence_graph_nodes n ON n.id=e."{from_col}" WHERE n.id IS NULL'))
            orphan_to = int(scalar(f'SELECT COUNT(*) FROM pilot_evidence_graph_edges e LEFT JOIN pilot_evidence_graph_nodes n ON n.id=e."{to_col}" WHERE n.id IS NULL'))
            check("Evidence graph edges resolve both endpoints", orphan_from==0 and orphan_to==0, f"orphan_from={orphan_from}, orphan_to={orphan_to}", "critical")
            if "organization_id" in ec:
                cross = int(scalar(f'SELECT COUNT(*) FROM pilot_evidence_graph_edges e JOIN pilot_evidence_graph_nodes a ON a.id=e."{from_col}" JOIN pilot_evidence_graph_nodes b ON b.id=e."{to_col}" WHERE a.organization_id<>b.organization_id OR e.organization_id<>a.organization_id OR e.organization_id<>b.organization_id'))
                check("Evidence graph edges remain within one tenant", cross==0, f"cross_tenant_edges={cross}", "critical")

    if all(exists(t) for t in ("pilot_business_case_items", "pilot_business_cases")):
        ic, cc = columns("pilot_business_case_items"), columns("pilot_business_cases")
        key = "business_case_id" if "business_case_id" in ic else ("case_id" if "case_id" in ic else None)
        if key:
            orphan = int(scalar(f'SELECT COUNT(*) FROM pilot_business_case_items i LEFT JOIN pilot_business_cases c ON c.id=i."{key}" WHERE c.id IS NULL'))
            check("Business-case items reference an existing case", orphan==0, f"orphans={orphan}", "critical")
            if "organization_id" in ic and "organization_id" in cc:
                mismatch = int(scalar(f'SELECT COUNT(*) FROM pilot_business_case_items i JOIN pilot_business_cases c ON c.id=i."{key}" WHERE i.organization_id<>c.organization_id'))
                check("Business-case items match case tenant", mismatch==0, f"cross_tenant={mismatch}", "critical")

    if exists("pilot_decision_cycles") and exists("mi_missions"):
        dc = columns("pilot_decision_cycles")
        if {"organization_id", "mission_code"}.issubset(dc):
            unresolved = int(scalar("SELECT COUNT(*) FROM pilot_decision_cycles d LEFT JOIN mi_missions m ON m.organization_id=d.organization_id AND m.code=d.mission_code WHERE m.id IS NULL"))
            check("Decision cycles resolve a mission in the same tenant", unresolved==0, f"unresolved={unresolved}", "critical")
        if "status" in dc:
            report["grouped"]["decision_cycle_status"] = rows("SELECT status, COUNT(*) AS total FROM pilot_decision_cycles GROUP BY status ORDER BY total DESC, status")

    if exists("pilot_learning_packets"):
        lp = columns("pilot_learning_packets")
        if exists("mi_missions") and {"organization_id", "source_mission_id"}.issubset(lp):
            bad = int(scalar("SELECT COUNT(*) FROM pilot_learning_packets p LEFT JOIN mi_missions m ON m.id=p.source_mission_id WHERE m.id IS NULL OR m.organization_id<>p.organization_id"))
            check("Learning packets resolve source mission in same tenant", bad==0, f"invalid={bad}", "critical")
        if exists("pilot_evidence_graph_nodes") and {"organization_id", "source_learning_node_id"}.issubset(lp):
            bad = int(scalar("SELECT COUNT(*) FROM pilot_learning_packets p LEFT JOIN pilot_evidence_graph_nodes n ON n.id=p.source_learning_node_id WHERE n.id IS NULL OR n.organization_id<>p.organization_id"))
            check("Learning packets resolve learning node in same tenant", bad==0, f"invalid={bad}", "critical")

    if exists("user_invitations"):
        c = columns("user_invitations")
        if "delivery_status" in c:
            report["grouped"]["invitation_delivery_status"] = rows("SELECT delivery_status, COUNT(*) AS total FROM user_invitations GROUP BY delivery_status ORDER BY total DESC, delivery_status")
        if {"expires_at", "accepted_at", "revoked_at"}.issubset(c):
            report["grouped"]["expired_unaccepted_invitations"] = int(scalar("SELECT COUNT(*) FROM user_invitations WHERE accepted_at IS NULL AND revoked_at IS NULL AND expires_at<CURRENT_TIMESTAMP"))

    if exists("password_reset_tokens"):
        c = columns("password_reset_tokens")
        if "delivery_status" in c:
            report["grouped"]["password_reset_delivery_status"] = rows("SELECT delivery_status, COUNT(*) AS total FROM password_reset_tokens GROUP BY delivery_status ORDER BY total DESC, delivery_status")
        if {"expires_at", "used_at", "revoked_at"}.issubset(c):
            report["grouped"]["expired_unused_password_resets"] = int(scalar("SELECT COUNT(*) FROM password_reset_tokens WHERE used_at IS NULL AND revoked_at IS NULL AND expires_at<CURRENT_TIMESTAMP"))

    if exists("pilot_release_acceptances") and {"build", "check_key", "accepted"}.issubset(columns("pilot_release_acceptances")):
        report["grouped"]["release_acceptances_by_build"] = rows("""
            SELECT build, COUNT(*) AS records,
                   SUM(CASE WHEN accepted THEN 1 ELSE 0 END) AS accepted,
                   COUNT(DISTINCT check_key) AS distinct_checks,
                   COUNT(DISTINCT organization_id) AS organizations
            FROM pilot_release_acceptances GROUP BY build ORDER BY build DESC LIMIT 20
        """)

    if exists("audit_events"):
        total = int(report["counts"].get("audit_events", scalar("SELECT COUNT(*) FROM audit_events")))
        check("Audit trail contains records", total>0, f"audit_events={total}", "major")

    tx.rollback()

report["completed_at"] = datetime.now(timezone.utc).isoformat()
rank = {"critical": 0, "major": 1, "minor": 2, "info": 3}
report["findings"].sort(key=lambda f: rank.get(f["severity"], 9))
report["summary"] = {
    "checks": len(report["checks"]),
    "passed": sum(1 for c in report["checks"] if c["ok"]),
    "failed": sum(1 for c in report["checks"] if not c["ok"]),
    "critical": sum(1 for f in report["findings"] if f["severity"]=="critical"),
    "major": sum(1 for f in report["findings"] if f["severity"]=="major"),
    "minor": sum(1 for f in report["findings"] if f["severity"]=="minor"),
}
print("SRIS_DB_AUDIT_START")
print(json.dumps(report, ensure_ascii=False, sort_keys=True, default=str))
print("SRIS_DB_AUDIT_END")
