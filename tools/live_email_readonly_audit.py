from __future__ import annotations

# Temporary staging-only audit. Performs no email send and no data mutation.

import json
import os
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from sqlalchemy import create_engine, inspect, text

from app.atlas_platform.auth_delivery import auth_delivery_configuration

report = {
    "started_at": datetime.now(timezone.utc).isoformat(),
    "configuration": {},
    "provider_probe": {},
    "reset_history": [],
    "findings": [],
}

cfg = auth_delivery_configuration()
if cfg is None:
    report["configuration"] = {"ready": False}
    report["findings"].append({"severity": "critical", "title": "Transactional email configuration does not resolve"})
else:
    from_domain = cfg.from_email.rsplit("@", 1)[-1].lower() if "@" in cfg.from_email else ""
    report["configuration"] = {
        "ready": True,
        "provider": cfg.provider,
        "from_domain": from_domain,
        "public_host": urlparse(cfg.public_base_url).hostname or "",
        "timeout_seconds": cfg.timeout_seconds,
    }

    if cfg.provider == "resend":
        key = os.getenv("RESEND_API_KEY", "").strip()
        if not key:
            report["provider_probe"] = {"provider": "resend", "ok": False, "reason": "key_missing"}
        else:
            req = Request(
                "https://api.resend.com/domains",
                headers={"Authorization": f"Bearer {key}", "User-Agent": "SRIS-readonly-audit/1.0"},
                method="GET",
            )
            try:
                with urlopen(req, timeout=12) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                    domains = payload.get("data", []) if isinstance(payload, dict) else []
                    sanitized = [
                        {
                            "name": str(item.get("name", "")).lower(),
                            "status": item.get("status"),
                            "region": item.get("region"),
                        }
                        for item in domains
                    ]
                    matching = [item for item in sanitized if item["name"] == from_domain or from_domain.endswith("." + item["name"])]
                    report["provider_probe"] = {
                        "provider": "resend",
                        "ok": 200 <= int(getattr(response, "status", 0) or 0) < 300,
                        "http_status": int(getattr(response, "status", 0) or 0),
                        "configured_domain_count": len(sanitized),
                        "matching_from_domain": matching,
                    }
                    if not matching:
                        report["findings"].append({"severity": "critical", "title": "SRIS_EMAIL_FROM domain is not present in the Resend domain inventory", "detail": from_domain})
                    elif not any(str(item.get("status", "")).lower() == "verified" for item in matching):
                        report["findings"].append({"severity": "critical", "title": "SRIS_EMAIL_FROM domain exists in Resend but is not verified", "detail": json.dumps(matching)})
            except HTTPError as exc:
                body = ""
                try:
                    body = exc.read().decode("utf-8", errors="replace")[:500]
                except Exception:
                    pass
                report["provider_probe"] = {"provider": "resend", "ok": False, "http_status": exc.code, "error": body}
                report["findings"].append({"severity": "critical", "title": "Resend API credentials/domain probe failed", "detail": f"HTTP {exc.code}"})
            except (URLError, OSError, ValueError) as exc:
                report["provider_probe"] = {"provider": "resend", "ok": False, "error": type(exc).__name__}
                report["findings"].append({"severity": "critical", "title": "Resend API could not be reached", "detail": type(exc).__name__})
    elif cfg.provider == "brevo":
        report["provider_probe"] = {"provider": "brevo", "ok": None, "reason": "non_sending_probe_not_implemented"}
    elif cfg.provider == "smtp":
        report["provider_probe"] = {"provider": "smtp", "ok": None, "reason": "no_network_write_attempt_performed"}

DB_URL = (os.getenv("ATLAS_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()
if DB_URL:
    engine = create_engine(DB_URL, pool_pre_ping=True)
    with engine.connect() as conn:
        tx = conn.begin()
        if engine.dialect.name == "postgresql":
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text("SET LOCAL statement_timeout='10s'"))
        inspector = inspect(conn)
        tables = set(inspector.get_table_names())
        if "password_reset_tokens" in tables:
            cols = {c["name"] for c in inspector.get_columns("password_reset_tokens")}
            date_col = "created_at" if "created_at" in cols else None
            if date_col and "delivery_status" in cols:
                report["reset_history"] = [
                    dict(row)
                    for row in conn.execute(text(f"""
                        SELECT DATE_TRUNC('day', {date_col}) AS day, delivery_status, COUNT(*) AS total,
                               MIN({date_col}) AS first_at, MAX({date_col}) AS last_at
                        FROM password_reset_tokens
                        GROUP BY DATE_TRUNC('day', {date_col}), delivery_status
                        ORDER BY day DESC, delivery_status
                    """)).mappings().all()
                ]
        tx.rollback()

report["completed_at"] = datetime.now(timezone.utc).isoformat()
print("SRIS_EMAIL_AUDIT_START")
print(json.dumps(report, ensure_ascii=False, default=str, sort_keys=True))
print("SRIS_EMAIL_AUDIT_END")
