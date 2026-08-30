"""Static SRIS website and secure contact-form delivery endpoint."""

from __future__ import annotations

import html
import json
import logging
import mimetypes
import os
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from email.utils import parseaddr
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MAX_BODY_BYTES = 16_384
RATE_LIMIT_COUNT = 5
RATE_LIMIT_WINDOW = 60 * 60
MIN_FORM_TIME_MS = 1_200
MAX_FORM_TIME_MS = 24 * 60 * 60 * 1_000
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; "
        "connect-src 'self'; object-src 'none'; base-uri 'none'; "
        "frame-ancestors 'none'; form-action 'self'"
    ),
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger("sris.contact")


class RateLimiter:
    def __init__(self, limit: int = RATE_LIMIT_COUNT, window: int = RATE_LIMIT_WINDOW):
        self.limit = limit
        self.window = window
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        timestamp = time.monotonic() if now is None else now
        cutoff = timestamp - self.window
        with self._lock:
            attempts = self._requests[key]
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if len(attempts) >= self.limit:
                return False
            attempts.append(timestamp)
            return True


RATE_LIMITER = RateLimiter()


def clean_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().replace("\x00", "")


def is_valid_email(value: str) -> bool:
    _, parsed = parseaddr(value)
    return parsed == value and len(value) <= 254 and bool(EMAIL_RE.fullmatch(value))


def validate_contact(payload: object) -> tuple[dict[str, object] | None, str | None]:
    if not isinstance(payload, dict):
        return None, "Pedido inválido."

    data: dict[str, object] = {
        "name": clean_text(payload.get("name")),
        "email": clean_text(payload.get("email")),
        "organization": clean_text(payload.get("organization")),
        "message": clean_text(payload.get("message")),
        "website": clean_text(payload.get("website")),
        "privacy": payload.get("privacy") is True,
        "elapsed_ms": payload.get("elapsed_ms"),
    }

    if data["website"]:
        data["spam"] = True
        return data, None
    if not 2 <= len(data["name"]) <= 100:
        return None, "Indique um nome válido."
    if not is_valid_email(data["email"]):
        return None, "Indique um email válido."
    if len(data["organization"]) > 120:
        return None, "O nome da organização é demasiado longo."
    if not 20 <= len(data["message"]) <= 4_000:
        return None, "A mensagem deve ter entre 20 e 4000 caracteres."
    if not data["privacy"]:
        return None, "É necessário autorizar o tratamento dos dados para respondermos."
    elapsed = data["elapsed_ms"]
    if not isinstance(elapsed, (int, float)) or isinstance(elapsed, bool):
        return None, "Pedido inválido. Atualize a página e tente novamente."
    if not MIN_FORM_TIME_MS <= elapsed <= MAX_FORM_TIME_MS:
        return None, "Pedido enviado demasiado depressa. Aguarde um momento e tente novamente."
    data["spam"] = False
    return data, None


def build_email(data: dict[str, object], to_email: str, from_email: str) -> dict[str, object]:
    name = str(data["name"])
    email_address = str(data["email"])
    organization = str(data["organization"]) or "Não indicada"
    message = str(data["message"])
    subject_source = str(data["organization"]) or name
    subject_source = re.sub(r"[\r\n]+", " ", subject_source)[:120]
    escaped_message = html.escape(message).replace("\n", "<br>")

    text_body = (
        "Novo contacto recebido através de sris.io\n\n"
        f"Nome: {name}\nEmail: {email_address}\nOrganização: {organization}\n\n"
        f"Mensagem:\n{message}\n\n"
        "O remetente autorizou o tratamento destes dados exclusivamente para resposta a este contacto."
    )
    html_body = (
        "<h2>Novo contacto recebido através de sris.io</h2>"
        f"<p><strong>Nome:</strong> {html.escape(name)}<br>"
        f"<strong>Email:</strong> {html.escape(email_address)}<br>"
        f"<strong>Organização:</strong> {html.escape(organization)}</p>"
        f"<p><strong>Mensagem:</strong><br>{escaped_message}</p>"
        "<p><small>O remetente autorizou o tratamento destes dados exclusivamente "
        "para resposta a este contacto.</small></p>"
    )
    return {
        "from": f"SRIS Website <{from_email}>",
        "to": [to_email],
        "reply_to": email_address,
        "subject": f"Novo contacto SRIS — {subject_source}",
        "text": text_body,
        "html": html_body,
    }


def send_via_resend(data: dict[str, object]) -> None:
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("RESEND_API_KEY is not configured")
    to_email = os.environ.get("SRIS_CONTACT_TO_EMAIL", "contact@sris.io").strip()
    from_email = os.environ.get("SRIS_CONTACT_FROM_EMAIL", "website@mail.sris.io").strip()
    payload = json.dumps(build_email(data, to_email, from_email)).encode("utf-8")
    request = Request(
        "https://api.resend.com/emails",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": secrets.token_hex(16),
            "User-Agent": "SRIS-Website/1.0",
        },
    )
    try:
        with urlopen(request, timeout=10) as response:
            if response.status not in (HTTPStatus.OK, HTTPStatus.CREATED):
                raise RuntimeError(f"Unexpected Resend status {response.status}")
    except (HTTPError, URLError, TimeoutError) as error:
        raise RuntimeError("Email delivery failed") from error


class ContactHandler(SimpleHTTPRequestHandler):
    server_version = "SRISWebsite/1.0"

    def __init__(self, *args, **kwargs):
        site_dir = os.environ.get("SITE_DIR") or str(Path(__file__).with_name("site"))
        super().__init__(*args, directory=site_dir, **kwargs)

    def end_headers(self) -> None:
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        path = self.path.split("?", 1)[0]
        if path.endswith(".html") or path == "/":
            self.send_header("Cache-Control", "no-cache")
        elif "?" in self.path and path.rsplit(".", 1)[-1] in {"css", "js"}:
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        super().end_headers()

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self._json(HTTPStatus.OK, {"status": "ok"})
            return
        if path == "/backups" or path.startswith("/backups/"):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        super().do_GET()

    def do_HEAD(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/backups" or path.startswith("/backups/"):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        super().do_HEAD()

    def do_POST(self) -> None:
        if self.path.split("?", 1)[0] != "/api/contact":
            self._json(HTTPStatus.NOT_FOUND, {"error": "Recurso não encontrado."})
            return

        allowed_origins = {
            value.strip().rstrip("/")
            for value in os.environ.get(
                "SRIS_ALLOWED_ORIGINS", "https://sris.io,https://www.sris.io"
            ).split(",")
            if value.strip()
        }
        origin = (self.headers.get("Origin") or "").rstrip("/")
        if origin not in allowed_origins:
            self._json(HTTPStatus.FORBIDDEN, {"error": "Origem do pedido não autorizada."})
            return

        content_type = self.headers.get_content_type()
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_type != "application/json" or not 0 < content_length <= MAX_BODY_BYTES:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "Pedido inválido."})
            return

        try:
            payload = json.loads(self.rfile.read(content_length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "Pedido inválido."})
            return

        data, validation_error = validate_contact(payload)
        if validation_error:
            self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": validation_error})
            return
        if data and data.get("spam"):
            self._json(HTTPStatus.OK, {"ok": True})
            return

        client_ip = self._client_ip()
        if not RATE_LIMITER.allow(client_ip):
            self._json(
                HTTPStatus.TOO_MANY_REQUESTS,
                {"error": "Foram enviados demasiados pedidos. Tente novamente mais tarde."},
            )
            return

        try:
            send_via_resend(data)
        except RuntimeError:
            LOGGER.exception("Contact delivery failed")
            self._json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "Não foi possível enviar agora. Tente novamente dentro de alguns minutos."},
            )
            return

        LOGGER.info("Contact request delivered")
        self._json(HTTPStatus.OK, {"ok": True})

    def _client_ip(self) -> str:
        connecting_ip = self.headers.get("CF-Connecting-IP")
        if connecting_ip:
            return connecting_ip.strip()[:64]
        forwarded = self.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",", 1)[0].strip()[:64]
        return self.client_address[0]

    def _json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format_string: str, *args: object) -> None:
        LOGGER.info("%s - %s", self.client_address[0], format_string % args)


def main() -> None:
    mimetypes.add_type("image/svg+xml", ".svg")
    mimetypes.add_type("image/webp", ".webp")
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), ContactHandler)
    LOGGER.info("SRIS website listening on port %s", port)
    server.serve_forever()


if __name__ == "__main__":
    main()
