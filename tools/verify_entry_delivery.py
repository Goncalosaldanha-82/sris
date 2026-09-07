"""GET-only verification of the public staging entry and its actual auth asset.

May run before a deployment: an old live revision is reported, not mistaken
for the candidate. Re-run after rollout to require matching public evidence.
No credentials, database reads, API POSTs, invitations or emails are used.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

HOSTS = ("app.sris.io", "sris-pilot-v1-staging.up.railway.app")
ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 256 * 1024


class SameHostRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new = urlsplit(req.full_url), urlsplit(newurl)
        if old.hostname != new.hostname or new.scheme != "https":
            raise ValueError("Unexpected redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class AuthSourceParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sources = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            src = dict(attrs).get("src", "")
            if urlsplit(src).path == "/auth.js":
                self.sources.append(src)


def fetch(url: str):
    request = Request(url, headers={
        "User-Agent": "SRIS-entry-delivery-check/1.0",
        "Cache-Control": "no-cache",
    }, method="GET")
    with build_opener(SameHostRedirect()).open(request, timeout=12) as response:
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError("Response exceeds verification limit")
        return body, dict(response.headers), response.status


def main():
    if (
        os.getenv("RAILWAY_SERVICE_ID") != "5adcd02c-c875-499f-bd3b-b4d5ea256258"
        or os.getenv("RAILWAY_ENVIRONMENT_ID") != "625472d4-144c-460a-b152-d1890f1f80db"
    ):
        raise SystemExit("Verification is restricted to the SRIS Pilot staging service")
    expected = sha256((ROOT / "frontend/pilot-v1/auth.js").read_bytes()).hexdigest()
    report = {"at": datetime.now(timezone.utc).isoformat(), "expected_sha256": expected, "hosts": []}
    for host in HOSTS:
        row = {"host": host, "verified": False}
        try:
            origin = f"https://{host}/"
            html, headers, code = fetch(origin)
            parser = AuthSourceParser()
            parser.feed(html.decode("utf-8"))
            if len(parser.sources) != 1:
                raise ValueError("Expected exactly one auth asset")
            src = parser.sources[0]
            script_url = urljoin(origin, src)
            parsed = urlsplit(script_url)
            if parsed.scheme != "https" or parsed.hostname != host or parsed.port not in (None, 443):
                raise ValueError("Auth source must stay on the same HTTPS host")
            script, js_headers, js_code = fetch(script_url)
            header_map = {key.lower(): value for key, value in headers.items()}
            js_map = {key.lower(): value for key, value in js_headers.items()}
            digest = sha256(script).hexdigest()
            row.update({
                "html_status": code, "script_status": js_code,
                "script_src": src, "served_sha256": digest,
                "html_cache_control": header_map.get("cache-control", ""),
                "script_cache_control": js_map.get("cache-control", ""),
                "content_matches_candidate": digest == expected,
                "url_contains_content_hash": expected[:16] in src,
                "old_async_reset_absent": b"e.currentTarget.reset()" not in script,
            })
            row["verified"] = all((
                code == 200, js_code == 200,
                row["content_matches_candidate"], row["url_contains_content_hash"],
                row["old_async_reset_absent"],
                "no-store" in row["html_cache_control"],
                "no-store" in row["script_cache_control"],
            ))
        except Exception as error:
            row["error_type"] = type(error).__name__
            if isinstance(error, HTTPError):
                row["http_status"] = error.code
        report["hosts"].append(row)
    report["all_public_hosts_verified"] = all(row["verified"] for row in report["hosts"])
    print("SRIS_ENTRY_DELIVERY " + json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
