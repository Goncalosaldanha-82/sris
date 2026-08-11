from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
from dataclasses import dataclass
from urllib.parse import quote, urlparse

from .config import settings


_CODE_PATTERN = re.compile(r"^[A-Z2-7]{16}$")


@dataclass(frozen=True)
class InstitutionalAccessGate:
    """Server-derived, one-time proof for the first institutional owner.

    The Railway value never leaves the server.  A human-friendly proof is
    derived with the application's JWT secret and may be disclosed only in the
    privileged deployment log.  Reusing the same Railway values produces the
    same proof, allowing the database ledger to make the flow single-use across
    restarts.
    """

    email: str
    code: str
    normalized_code: str
    ledger_hash: str


def normalize_activation_code(value: str) -> str:
    return "".join(character for character in value.upper() if character.isalnum())


def institutional_access_gate() -> InstitutionalAccessGate | None:
    email = os.getenv("SRIS_ACCESS_ACTIVATION_EMAIL", "").strip().lower()
    server_nonce = os.getenv("SRIS_ACCESS_ACTIVATION_TOKEN", "").strip()
    if not email or "@" not in email or not server_nonce:
        return None

    message = f"sris_browser_owner_activation_v2\0{email}\0{server_nonce}"
    digest = hmac.new(
        settings.jwt_secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).digest()[:10]
    normalized_code = base64.b32encode(digest).decode("ascii").rstrip("=")
    if not _CODE_PATTERN.fullmatch(normalized_code):  # defensive invariant
        return None
    code = "-".join(
        normalized_code[index : index + 4]
        for index in range(0, len(normalized_code), 4)
    )
    ledger_hash = hashlib.sha256(
        f"sris_browser_owner_activation_v2\0{email}\0{normalized_code}".encode(
            "utf-8"
        )
    ).hexdigest()
    return InstitutionalAccessGate(
        email=email,
        code=code,
        normalized_code=normalized_code,
        ledger_hash=ledger_hash,
    )


def institutional_activation_url(code: str) -> str | None:
    public_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip().strip("/")
    base_url = f"https://{public_domain}" if public_domain else ""
    if not base_url:
        base_url = os.getenv("SRIS_PUBLIC_BASE_URL", "").strip().rstrip("/")

    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if parsed.query or parsed.fragment:
        return None
    return f"{base_url}/account.html#activate={quote(code, safe='-')}"
