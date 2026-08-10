from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from urllib.parse import quote, urlparse


class AuthDeliveryError(RuntimeError):
    """Authentication email could not be delivered safely."""


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
    managed = any(
        os.getenv(name)
        for name in (
            "RAILWAY_ENVIRONMENT_ID",
            "RAILWAY_PROJECT_ID",
            "RAILWAY_SERVICE_ID",
        )
    )
    production = os.getenv("ATLAS_ENV", "").strip().lower() in {
        "production",
        "prod",
    }
    return managed or production


def smtp_configuration() -> SMTPConfiguration | None:
    host = os.getenv("SRIS_SMTP_HOST", "").strip()
    username = os.getenv("SRIS_SMTP_USERNAME", "").strip()
    password = os.getenv("SRIS_SMTP_PASSWORD", "")
    from_email = os.getenv("SRIS_SMTP_FROM_EMAIL", "").strip()
    from_name = _clean_header(os.getenv("SRIS_SMTP_FROM_NAME", "SRIS")) or "SRIS"
    public_base_url = _normalized_base_url(
        os.getenv("SRIS_PUBLIC_BASE_URL", "")
    )
    security = os.getenv("SRIS_SMTP_SECURITY", "starttls").strip().lower()

    if security not in {"starttls", "ssl", "none"}:
        return None
    if not host or not from_email or not public_base_url:
        return None
    if "\r" in host or "\n" in host or "@" not in from_email:
        return None
    if bool(username) is not bool(password):
        return None
    if _managed_or_production() and (
        security == "none" or not public_base_url.startswith("https://")
    ):
        return None

    default_port = 465 if security == "ssl" else 587
    return SMTPConfiguration(
        host=host,
        port=_bounded_integer("SRIS_SMTP_PORT", default_port, 1, 65535),
        security=security,
        username=username,
        password=password,
        from_email=from_email,
        from_name=from_name,
        public_base_url=public_base_url,
        timeout_seconds=_bounded_integer("SRIS_SMTP_TIMEOUT_SECONDS", 12, 3, 30),
    )


def auth_email_delivery_ready() -> bool:
    return smtp_configuration() is not None


def build_auth_link(flow: str, raw_token: str) -> str:
    configuration = smtp_configuration()
    if configuration is None:
        raise AuthDeliveryError("Authentication email is not configured")
    if flow not in {"invite", "reset"}:
        raise ValueError("Unsupported authentication flow")
    # The secret stays in the URL fragment. Browsers do not send fragments in
    # HTTP requests, so reverse proxies and ordinary access logs never receive it.
    return (
        f"{configuration.public_base_url}/account.html"
        f"#{flow}={quote(raw_token, safe='')}"
    )


def send_transactional_email(
    *,
    recipient: str,
    subject: str,
    text_body: str,
    html_body: str,
) -> None:
    configuration = smtp_configuration()
    if configuration is None:
        raise AuthDeliveryError("Authentication email is not configured")

    message = EmailMessage()
    message["From"] = formataddr(
        (configuration.from_name, configuration.from_email)
    )
    message["To"] = _clean_header(recipient)
    message["Subject"] = _clean_header(subject)
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    tls_context = ssl.create_default_context()
    try:
        if configuration.security == "ssl":
            smtp: smtplib.SMTP = smtplib.SMTP_SSL(
                configuration.host,
                configuration.port,
                timeout=configuration.timeout_seconds,
                context=tls_context,
            )
        else:
            smtp = smtplib.SMTP(
                configuration.host,
                configuration.port,
                timeout=configuration.timeout_seconds,
            )
        with smtp:
            smtp.ehlo()
            if configuration.security == "starttls":
                smtp.starttls(context=tls_context)
                smtp.ehlo()
            if configuration.username:
                smtp.login(configuration.username, configuration.password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise AuthDeliveryError("Authentication email delivery failed") from exc
