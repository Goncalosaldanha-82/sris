from __future__ import annotations

import json
import logging
import os
import secrets
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.analytics_access import require_analytics_owner
from app.atlas_platform.auth import current_user
from app.atlas_platform.database import Base, SessionLocal, get_db
from app.atlas_platform.models import User

LOGGER = logging.getLogger("sris.internal_analytics")

router = APIRouter(prefix="/api/internal-analytics", tags=["internal-analytics"])
dashboard_router = APIRouter()

ALLOWED_EVENTS = {
    "site_view",
    "demo_view",
    "app_entry_view",
    "app_view",
    "site_to_demo",
    "demo_to_app",
    "login_success",
    "pilot_started",
    "pilot_created",
    "mission_started",
    "mission_created",
}
ALLOWED_SURFACES = {"site", "demo", "app"}


class InternalAnalyticsEvent(Base):
    __tablename__ = "sris_internal_analytics_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    event_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    surface: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    host: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    path: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    source: Mapped[str] = mapped_column(String(128), nullable=False, default="direct", index=True)
    medium: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    campaign: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    referrer_host: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class CollectPayload(BaseModel):
    event_name: str = Field(min_length=2, max_length=64)
    surface: str = Field(min_length=2, max_length=32)
    host: str = Field(default="", max_length=255)
    path: str = Field(default="", max_length=512)
    source: str = Field(default="", max_length=128)
    medium: str = Field(default="", max_length=128)
    campaign: str = Field(default="", max_length=256)
    referrer_host: str = Field(default="", max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)


def _clean(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().replace("\x00", "")[:limit]


def _referrer_host(value: str) -> str:
    if not value:
        return ""
    try:
        return (urlparse(value).hostname or "").lower()[:255]
    except ValueError:
        return ""


def _classify_source(explicit: str, referrer_host: str) -> str:
    explicit = _clean(explicit, 128).lower()
    if explicit:
        return explicit
    host = referrer_host.lower()
    if not host:
        return "direct"
    if "linkedin." in host or host.endswith("linkedin.com"):
        return "linkedin"
    if host.startswith("google.") or ".google." in host:
        return "google"
    if host.endswith("sris.io") or "sris-mission-intelligence.up.railway.app" in host:
        return "sris"
    return host[:128]


def _metadata_json(metadata: dict[str, Any] | None) -> str:
    safe: dict[str, Any] = {}
    for key, value in (metadata or {}).items():
        clean_key = _clean(str(key), 64)
        if not clean_key:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[clean_key] = _clean(value, 240) if isinstance(value, str) else value
    return json.dumps(safe, ensure_ascii=False, separators=(",", ":"))[:4000]


def _add_event(
    db: Session,
    *,
    event_name: str,
    surface: str,
    host: str = "",
    path: str = "",
    source: str = "",
    medium: str = "",
    campaign: str = "",
    referrer_host: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    if event_name not in ALLOWED_EVENTS or surface not in ALLOWED_SURFACES:
        raise ValueError("unsupported analytics event")
    referrer_host = _clean(referrer_host, 255).lower()
    db.add(
        InternalAnalyticsEvent(
            event_name=event_name,
            surface=surface,
            host=_clean(host, 255).lower(),
            path=_clean(path, 512),
            source=_classify_source(source, referrer_host),
            medium=_clean(medium, 128),
            campaign=_clean(campaign, 256),
            referrer_host=referrer_host,
            metadata_json=_metadata_json(metadata),
        )
    )


def safe_track_request(
    request: Request,
    *,
    event_name: str,
    surface: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Record an aggregate event without storing IP addresses, user agents or cookies."""

    try:
        params = request.query_params
        ref_host = _referrer_host(request.headers.get("referer", ""))
        with SessionLocal() as db:
            _add_event(
                db,
                event_name=event_name,
                surface=surface,
                host=request.url.hostname or request.headers.get("host", ""),
                path=request.url.path,
                source=params.get("utm_source") or params.get("src") or "",
                medium=params.get("utm_medium") or "",
                campaign=params.get("utm_campaign") or "",
                referrer_host=ref_host,
                metadata=metadata,
            )
            db.commit()
    except Exception:
        LOGGER.exception("Internal analytics event could not be recorded")


def _require_admin(user: User, db: Session) -> None:
    # Tenant ownership must never authorize reading platform-wide metrics.
    require_analytics_owner(user, db)


@router.post("/collect", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False)
def collect_event(
    payload: CollectPayload,
    x_sris_analytics_token: str = Header(default=""),
    db: Session = Depends(get_db),
) -> Response:
    configured = os.getenv("SRIS_ANALYTICS_INGEST_TOKEN", "").strip()
    if not configured or not secrets.compare_digest(x_sris_analytics_token, configured):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid analytics token")
    if payload.event_name not in ALLOWED_EVENTS or payload.surface not in ALLOWED_SURFACES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported event")
    _add_event(
        db,
        event_name=payload.event_name,
        surface=payload.surface,
        host=payload.host,
        path=payload.path,
        source=payload.source,
        medium=payload.medium,
        campaign=payload.campaign,
        referrer_host=payload.referrer_host,
        metadata=payload.metadata,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/summary", include_in_schema=False)
def analytics_summary(
    days: int = Query(default=30, ge=1, le=90),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_admin(user, db)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(InternalAnalyticsEvent)
        .filter(InternalAnalyticsEvent.occurred_at >= since)
        .order_by(InternalAnalyticsEvent.occurred_at.asc())
        .all()
    )

    event_totals = Counter(row.event_name for row in rows)
    surface_totals = Counter(
        row.surface for row in rows if row.event_name in {"site_view", "demo_view", "app_view"}
    )
    source_totals = Counter(
        row.source for row in rows if row.event_name in {"site_view", "demo_view", "app_view"}
    )
    daily: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        day = row.occurred_at.date().isoformat()
        daily[day][row.event_name] += 1

    site_views = event_totals.get("site_view", 0)
    demo_views = event_totals.get("demo_view", 0)
    app_views = event_totals.get("app_view", 0)
    site_to_demo = event_totals.get("site_to_demo", 0)
    demo_to_app = event_totals.get("demo_to_app", 0)

    return {
        "period_days": days,
        "privacy": {
            "cookies": False,
            "raw_ip_stored": False,
            "user_agent_stored": False,
            "personal_profiles": False,
        },
        "views": {
            "site": site_views,
            "demo": demo_views,
            "app": app_views,
        },
        "events": dict(sorted(event_totals.items())),
        "funnel": {
            "site_to_demo_events": site_to_demo,
            "demo_to_app_events": demo_to_app,
            "site_to_demo_rate_pct": round(site_to_demo / site_views * 100, 1) if site_views else 0.0,
            "demo_to_app_rate_pct": round(demo_to_app / demo_views * 100, 1) if demo_views else 0.0,
        },
        "sources": [
            {"source": source, "views": count}
            for source, count in source_totals.most_common(12)
        ],
        "daily": [
            {
                "date": day,
                "site": counts.get("site_view", 0),
                "demo": counts.get("demo_view", 0),
                "app": counts.get("app_view", 0),
                "login": counts.get("login_success", 0),
                "pilots": counts.get("pilot_created", 0),
                "missions": counts.get("mission_created", 0),
            }
            for day, counts in sorted(daily.items())
        ],
        "total_events": len(rows),
        "surface_totals": dict(surface_totals),
    }


_DASHBOARD_HTML = """<!doctype html>
<html lang="pt-PT"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>SRIS · Analytics interno</title><style>
:root{color-scheme:light;background:#f5f3ec;color:#102c24;font-family:Inter,system-ui,sans-serif}body{margin:0}.wrap{max-width:1100px;margin:auto;padding:36px 22px 70px}.top{display:flex;justify-content:space-between;gap:20px;align-items:end;margin-bottom:24px}h1{font-family:Georgia,serif;font-size:42px;font-weight:500;margin:5px 0}.eyebrow{letter-spacing:.16em;text-transform:uppercase;font-size:12px;color:#9b792f;font-weight:700}.muted{color:#66756f}.controls{display:flex;gap:8px}.controls button{border:1px solid #ccd3ce;background:#fff;border-radius:999px;padding:9px 14px;cursor:pointer}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.card,.panel{background:#fff;border:1px solid #dde2de;border-radius:18px;padding:20px;box-shadow:0 8px 25px rgba(16,44,36,.04)}.value{font-family:Georgia,serif;font-size:44px;margin-top:8px}.grid{display:grid;grid-template-columns:1.25fr .75fr;gap:14px;margin-top:14px}table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:10px 8px;border-bottom:1px solid #edf0ed}th{font-size:11px;text-transform:uppercase;letter-spacing:.1em;color:#728079}.funnel{display:grid;gap:12px}.step{padding:14px;border:1px solid #e1e5e2;border-radius:14px}.step b{font-size:24px}.privacy{margin-top:14px;font-size:12px;color:#718079}.error{padding:18px;background:#fff0ed;border:1px solid #efc5bd;border-radius:14px;color:#7d2d20}@media(max-width:760px){.cards,.grid{grid-template-columns:1fr}.top{align-items:start;flex-direction:column}h1{font-size:34px}}
</style></head><body><main class="wrap"><div class="top"><div><div class="eyebrow">SRIS · uso interno</div><h1>Leitura de interesse</h1><div class="muted">Site → demonstração → aplicação. Sem cookies, IP bruto ou perfis pessoais.</div><p><a href="/app">Voltar à aplicação</a></p></div><div class="controls"><button data-days="7">7 dias</button><button data-days="30">30 dias</button><button data-days="90">90 dias</button></div></div><div id="content"><div class="muted">A verificar a autorização do proprietário da plataforma…</div></div></main><script src="/analytics-dashboard-v43.js?v=__ANALYTICS_DIGEST__" defer></script></body></html>"""


@dashboard_router.get("/admin/analytics", include_in_schema=False)
def analytics_dashboard() -> HTMLResponse:
    # This shell contains no private data. The summary API authenticates and
    # authorizes every read, including direct navigation to this URL.
    frontend = Path(__file__).resolve().parents[2] / "frontend" / "pilot-v1"
    digest = sha256((frontend / "analytics-dashboard-v43.js").read_bytes()).hexdigest()[:16]
    return HTMLResponse(
        _DASHBOARD_HTML.replace("__ANALYTICS_DIGEST__", digest),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                 "X-Robots-Tag": "noindex, nofollow"},
    )
