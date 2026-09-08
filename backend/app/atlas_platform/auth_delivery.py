from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


LOGGER = logging.getLogger("sris.auth_delivery")
USER_AGENT = "SRIS-transactional-email/1.1"


class AuthDeliveryError(RuntimeError):
    """Authentication email could not be delivered safely.

    Error text contains only a bounded machine code, never the provider body,
    recipient address, credentials or a personal activation URL.
    """


@dataclass(frozen=True)
class SMTPConfiguration:
    host: str
    port: int
    security: str
    username: str
    password: str
    from_email: str
    from_name: str
    public_base_url: str
    timeout_seconds: int


@dataclass(frozen=True)
class AuthDeliveryConfiguration:
    provider: str
    from_email: str
    from_name: str
    public_base_url: str
    timeout_seconds: int
    smtp: SMTPConfiguration | None = None


def _bounded_integer(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _clean_header(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ").strip()


def _normalized_base_url(raw_value: str) -> str:
    value = raw_value.strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    if parsed.query or parsed.fragment:
        return ""
    return value


def _managed_or_production() -> bool:
    managed = any(os.getenv(name) for name in (
        "RAILWAY_ENVIRONMENT_ID", "RAILWAY_PROJECT_ID", "RAILWAY_SERVICE_ID",
    ))
    production = os.getenv("ATLAS_ENV", "").strip().lower() in {"production", "prod"}
    return managed or production


def smtp_configuration() -> SMTPConfiguration | None:
    host = os.getenv("SRIS_SMTP_HOST", "").strip()
    username = os.getenv("SRIS_SMTP_USERNAME", "").strip()
    password = os.getenv("SRIS_SMTP_PASSWORD", "")
    from_email = os.getenv("SRIS_SMTP_FROM_EMAIL", "").strip()
    from_name = _clean_header(os.getenv("SRIS_SMTP_FROM_NAME", "SRIS")) or "SRIS"
    public_base_url = _normalized_base_url(os.getenv("SRIS_PUBLIC_BASE_URL", ""))
    security = os.getenv("SRIS_SMTP_SECURITY", "starttls").strip().lower()
    if security not in {"starttls", "ssl", "none"}:
        return None
    if not host or not from_email or not public_base_url:
        return None
    if "\r" in host or "\n" in host or "@" not in from_email:
        return None
    if bool(username) is not bool(password):
        return None
    if _managed_or_production() and (security == "none" or not public_base_url.startswith("https://")):
        return None
    return SMTPConfiguration(
        host=host,
        port=_bounded_integer("SRIS_SMTP_PORT", 465 if security == "ssl" else 587, 1, 65535),
        security=security, username=username, password=password,
        from_email=from_email, from_name=from_name, public_base_url=public_base_url,
        timeout_seconds=_bounded_integer("SRIS_SMTP_TIMEOUT_SECONDS", 12, 3, 30),
    )


def auth_email_delivery_ready() -> bool:
    return auth_delivery_configuration() is not None


def _api_delivery_configuration(provider: str) -> AuthDeliveryConfiguration | None:
    public_base_url = _normalized_base_url(os.getenv("SRIS_PUBLIC_BASE_URL", ""))
    from_email = os.getenv("SRIS_EMAIL_FROM", "").strip()
    from_name = _clean_header(os.getenv("SRIS_EMAIL_FROM_NAME", "SRIS")) or "SRIS"
    key_name = "RESEND_API_KEY" if provider == "resend" else "BREVO_API_KEY"
    if not os.getenv(key_name, "").strip() or not public_base_url or "@" not in from_email:
        return None
    if _managed_or_production() and not public_base_url.startswith("https://"):
        return None
    return AuthDeliveryConfiguration(
        provider=provider, from_email=from_email, from_name=from_name,
        public_base_url=public_base_url,
        timeout_seconds=_bounded_integer("SRIS_EMAIL_TIMEOUT_SECONDS", 12, 3, 30),
    )


def auth_delivery_configuration() -> AuthDeliveryConfiguration | None:
    """Resolve exactly one transactional transport; never guess credentials."""
    available: dict[str, AuthDeliveryConfiguration] = {}
    smtp = smtp_configuration()
    if smtp is not None:
        available["smtp"] = AuthDeliveryConfiguration(
            provider="smtp", from_email=smtp.from_email, from_name=smtp.from_name,
            public_base_url=smtp.public_base_url, timeout_seconds=smtp.timeout_seconds, smtp=smtp,
        )
    for provider in ("resend", "brevo"):
        configured = _api_delivery_configuration(provider)
        if configured is not None:
            available[provider] = configured
    selected = os.getenv("SRIS_EMAIL_PROVIDER", "").strip().lower()
    if selected:
        return available.get(selected) if selected in {"smtp", "resend", "brevo"} else None
    if len(available) != 1:
        return None
    return next(iter(available.values()))


def build_auth_link(flow: str, raw_token: str) -> str:
    configuration = auth_delivery_configuration()
    if configuration is None:
        raise AuthDeliveryError("Authentication email is not configured")
    if flow not in {"invite", "reset"}:
        raise ValueError("Unsupported authentication flow")
    # Fragments never reach ordinary HTTP/proxy access logs.
    return f"{configuration.public_base_url}/account.html#{flow}={quote(raw_token, safe='')}"


def send_transactional_email(
    *, recipient: str, subject: str, text_body: str, html_body: str,
) -> str | None:
    configuration = auth_delivery_configuration()
    if configuration is None:
        raise AuthDeliveryError("Authentication email is not configured")
    if configuration.provider == "resend":
        return _send_api_email(configuration, "https://api.resend.com/emails", {
            "from": formataddr((configuration.from_name, configuration.from_email)),
            "to": [_clean_header(recipient)], "subject": _clean_header(subject),
            "text": text_body, "html": html_body,
        }, {"Authorization": f"Bearer {os.environ['RESEND_API_KEY'].strip()}"})
    if configuration.provider == "brevo":
        return _send_api_email(configuration, "https://api.brevo.com/v3/smtp/email", {
            "sender": {"name": configuration.from_name, "email": configuration.from_email},
            "to": [{"email": _clean_header(recipient)}], "subject": _clean_header(subject),
            "textContent": text_body, "htmlContent": html_body,
        }, {"api-key": os.environ["BREVO_API_KEY"].strip()})
    smtp_cfg = configuration.smtp
    if smtp_cfg is None:
        raise AuthDeliveryError("Authentication email is not configured")
    message = EmailMessage()
    message["From"] = formataddr((configuration.from_name, configuration.from_email))
    message["To"] = _clean_header(recipient)
    message["Subject"] = _clean_header(subject)
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")
    tls_context = ssl.create_default_context()
    try:
        if smtp_cfg.security == "ssl":
            smtp: smtplib.SMTP = smtplib.SMTP_SSL(
                smtp_cfg.host, smtp_cfg.port, timeout=smtp_cfg.timeout_seconds, context=tls_context)
        else:
            smtp = smtplib.SMTP(smtp_cfg.host, smtp_cfg.port, timeout=smtp_cfg.timeout_seconds)
        with smtp:
            smtp.ehlo()
            if smtp_cfg.security == "starttls":
                smtp.starttls(context=tls_context)
                smtp.ehlo()
            if smtp_cfg.username:
                smtp.login(smtp_cfg.username, smtp_cfg.password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise AuthDeliveryError("Authentication email delivery failed") from exc
    return None


def _provider_error_code(error: HTTPError) -> str:
    """Bounded diagnostic classification; the raw response is never logged."""
    code = f"provider_http_{error.code}"
    try:
        body = error.read(4096).decode("utf-8", errors="replace")
        if "1010" in body and error.code == 403:
            return code + ":edge_1010"
        data = json.loads(body)
        name = data.get("name", "") if isinstance(data, dict) else ""
        if re.fullmatch(r"[a-z][a-z0-9_]{0,59}", str(name)):
            code += ":" + str(name)
    except Exception:
        pass
    return code


def _send_api_email(
    configuration: AuthDeliveryConfiguration, url: str, payload: dict,
    authorization_headers: dict[str, str],
) -> str | None:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    # Explicit application identity is required by the email API edge. The
    # previous urllib-default transport was rejected before reaching the API.
    headers = {"Content-Type": "application/json", "Accept": "application/json",
               "User-Agent": USER_AGENT, **authorization_headers}
    if configuration.provider == "resend":
        # The same recipient/content/token retries with the same key. A newly
        # issued token changes the payload and therefore gets a different key.
        headers["Idempotency-Key"] = "sris-auth/" + hashlib.sha256(body).hexdigest()
    request = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=configuration.timeout_seconds) as response:
            status_code = int(getattr(response, "status", 0) or 0)
            if not 200 <= status_code < 300:
                raise AuthDeliveryError(f"provider_http_{status_code}")
            result = json.loads(response.read(16384))
            field = "id" if configuration.provider == "resend" else "messageId"
            receipt = result.get(field) if isinstance(result, dict) else None
            if not isinstance(receipt, str) or not receipt.strip():
                raise AuthDeliveryError("provider_receipt_missing")
            receipt = _clean_header(receipt)[:200]
            LOGGER.warning("SRIS_AUTH_EMAIL provider=%s status=provider_accepted provider_id=%s",
                           configuration.provider, receipt)
            return receipt
    except HTTPError as exc:
        code = _provider_error_code(exc)
        LOGGER.warning("SRIS_AUTH_EMAIL provider=%s status=failed code=%s", configuration.provider, code)
        raise AuthDeliveryError(code) from None
    except AuthDeliveryError:
        raise
    except (URLError, OSError, ValueError) as exc:
        code = "provider_transport_" + type(exc).__name__
        LOGGER.warning("SRIS_AUTH_EMAIL provider=%s status=failed code=%s", configuration.provider, code)
        raise AuthDeliveryError(code) from None
