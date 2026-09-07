"""SRIS public site server with privacy-minimized first-party analytics.

This wrapper keeps the existing contact and demonstration proxy behaviour intact,
while recording aggregate navigation events server-side. It stores no raw IP,
user-agent, cookie identifier or individual visitor profile.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from contact_server import ContactHandler

LOGGER = logging.getLogger("sris.site_analytics")


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


def _post_event(payload: dict[str, object]) -> None:
    endpoint = os.environ.get("SRIS_ANALYTICS_ENDPOINT", "").strip()
    token = os.environ.get("SRIS_ANALYTICS_INGEST_TOKEN", "").strip()
    if not endpoint or not token:
        return
    request = Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-SRIS-Analytics-Token": token,
            "User-Agent": "SRIS-Internal-Analytics/1.0",
        },
    )
    try:
        with urlopen(request, timeout=2.0) as response:
            if response.status not in (200, 201, 202, 204):
                LOGGER.warning("Analytics ingest returned HTTP %s", response.status)
    except (HTTPError, URLError, TimeoutError, OSError):
        LOGGER.debug("Analytics ingest temporarily unavailable", exc_info=True)


class AnalyticsContactHandler(ContactHandler):
    def _analytics_event(self, event_name: str, surface: str) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query, keep_blank_values=False)
        ref_host = _referrer_host(self.headers.get("Referer", ""))
        explicit_source = (
            (query.get("utm_source") or query.get("src") or [""])[0]
        )
        payload = {
            "event_name": event_name,
            "surface": surface,
            "host": _clean(self.headers.get("Host", "").split(":", 1)[0], 255).lower(),
            "path": _clean(parsed.path, 512),
            "source": _classify_source(explicit_source, ref_host),
            "medium": _clean((query.get("utm_medium") or [""])[0], 128),
            "campaign": _clean((query.get("utm_campaign") or [""])[0], 256),
            "referrer_host": ref_host,
            "metadata": {},
        }
        threading.Thread(target=_post_event, args=(payload,), daemon=True).start()

    def do_GET(self) -> None:
        host = (self.headers.get("Host") or "").split(":", 1)[0].lower()
        parsed = urlparse(self.path)
        path = parsed.path

        # Avoid double counting the www -> apex redirect.
        if host != "www.sris.io":
            if path in {"/", "/index.html"}:
                self._analytics_event("site_view", "site")
            elif path in {"/demonstracao", "/demonstracao/"}:
                ref_host = _referrer_host(self.headers.get("Referer", ""))
                if ref_host in {
                    "sris.io",
                    "www.sris.io",
                    "sris-mission-intelligence.up.railway.app",
                }:
                    self._analytics_event("site_to_demo", "site")

        super().do_GET()


def main() -> None:
    mimetypes.add_type("image/svg+xml", ".svg")
    mimetypes.add_type("image/webp", ".webp")
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), AnalyticsContactHandler)
    LOGGER.info("SRIS website + internal analytics listening on port %s", port)
    server.serve_forever()


if __name__ == "__main__":
    main()
