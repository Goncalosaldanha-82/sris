from __future__ import annotations

import json
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


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
        provider=provider,
        from_email=from_email,
        from_name=from_name,
        public_base_url=public_base_url,
        timeout_seconds=_bounded_integer("SRIS_EMAIL_TIMEOUT_SECONDS", 12, 3, 30),
    )


def auth_delivery_configuration() -> AuthDeliveryConfiguration | None:
    """Resolve exactly one transactional-email transport and fail closed.

    The identity lifecycle uses this single resolver for invitations and
    password recovery.  Provider and credentials remain server-side details.
    """

    available: dict[str, AuthDeliveryConfiguration] = {}
    smtp = smtp_configuration()
    if smtp is not None:
        available["smtp"] = AuthDeliveryConfiguration(
            provider="smtp",
            from_email=smtp.from_email,
            from_name=smtp.from_name,
            public_base_url=smtp.public_base_url,
            timeout_seconds=smtp.timeout_seconds,
            smtp=smtp,
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
    configuration = auth_delivery_configuration()
    if configuration is None:
        raise AuthDeliveryError("Authentication email is not configured")

    if configuration.provider == "resend":
        _send_api_email(
            configuration,
            "https://api.resend.com/emails",
            {
                "from": formataddr((configuration.from_name, configuration.from_email)),
                "to": [_clean_header(recipient)],
                "subject": _clean_header(subject),
                "text": text_body,
                "html": html_body,
            },
            {"Authorization": f"Bearer {os.environ['RESEND_API_KEY'].strip()}"},
        )
        return
    if configuration.provider == "brevo":
        _send_api_email(
            configuration,
            "https://api.brevo.com/v3/smtp/email",
            {
                "sender": {"name": configuration.from_name, "email": configuration.from_email},
                "to": [{"email": _clean_header(recipient)}],
                "subject": _clean_header(subject),
                "textContent": text_body,
                "htmlContent": html_body,
            },
            {"api-key": os.environ["BREVO_API_KEY"].strip()},
        )
        return

    smtp_configuration_value = configuration.smtp
    if smtp_configuration_value is None:
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
        if smtp_configuration_value.security == "ssl":
            smtp: smtplib.SMTP = smtplib.SMTP_SSL(
                smtp_configuration_value.host,
                smtp_configuration_value.port,
                timeout=smtp_configuration_value.timeout_seconds,
                context=tls_context,
            )
        else:
            smtp = smtplib.SMTP(
                smtp_configuration_value.host,
                smtp_configuration_value.port,
                timeout=smtp_configuration_value.timeout_seconds,
            )
        with smtp:
            smtp.ehlo()
            if smtp_configuration_value.security == "starttls":
                smtp.starttls(context=tls_context)
                smtp.ehlo()
            if smtp_configuration_value.username:
                smtp.login(smtp_configuration_value.username, smtp_configuration_value.password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise AuthDeliveryError("Authentication email delivery failed") from exc


def _send_api_email(
    configuration: AuthDeliveryConfiguration,
    url: str,
    payload: dict,
    authorization_headers: dict[str, str],
) -> None:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **authorization_headers},
        method="POST",
    )
    try:
        with urlopen(request, timeout=configuration.timeout_seconds) as response:
            status_code = int(getattr(response, "status", 0) or 0)
            if status_code < 200 or status_code >= 300:
                raise AuthDeliveryError("Authentication email delivery failed")
    except AuthDeliveryError:
        raise
    except HTTPError as exc:
        # Resend/Brevo return a small JSON error envelope. Preserve only its
        # public error code and message: never headers, request data or keys.
        provider_name = "Resend" if configuration.provider == "resend" else "Brevo"
        provider_code = ""
        provider_message = ""
        try:
            body = exc.read(4096).decode("utf-8", errors="replace")
            payload = json.loads(body)
            if isinstance(payload, dict):
                provider_code = _clean_header(
                    str(payload.get("name") or payload.get("code") or "")
                )[:80]
                provider_message = _clean_header(
                    str(payload.get("message") or "")
                )[:320]
        except (OSError, UnicodeError, ValueError, TypeError):
            pass
        detail = f"{provider_name} recusou o envio (HTTP {exc.code})"
        if provider_code:
            detail += f" · {provider_code}"
        if provider_message:
            detail += f": {provider_message}"
        raise AuthDeliveryError(f"{detail}.") from exc
    except URLError as exc:
        raise AuthDeliveryError(
            "Não foi possível contactar o fornecedor de email."
        ) from exc
    except (OSError, ValueError) as exc:
        raise AuthDeliveryError(
            "O fornecedor de email não concluiu o envio."
        ) from exc
