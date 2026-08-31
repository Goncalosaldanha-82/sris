import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from contact_server import (
    RateLimiter,
    build_email,
    is_allowed_origin,
    is_valid_email,
    send_contact_email,
    send_via_resend,
    send_via_smtp,
    validate_contact,
)


def valid_payload(**overrides):
    payload = {
        "name": "Ana Martins",
        "email": "ana@example.org",
        "organization": "Organização Exemplo",
        "purpose": "presentation",
        "message": "Pretendo explorar um caso-piloto concreto com a equipa.",
        "website": "",
        "privacy": True,
        "elapsed_ms": 5_000,
    }
    payload.update(overrides)
    return payload


class ValidationTests(unittest.TestCase):
    def test_valid_payload(self):
        data, error = validate_contact(valid_payload())
        self.assertIsNone(error)
        self.assertFalse(data["spam"])

    def test_invalid_email(self):
        _, error = validate_contact(valid_payload(email="not-an-email"))
        self.assertEqual(error, "Indique um email válido.")

    def test_privacy_is_required(self):
        _, error = validate_contact(valid_payload(privacy=False))
        self.assertIn("Privacidade", error)

    def test_message_length_is_checked(self):
        _, error = validate_contact(valid_payload(message="Curta"))
        self.assertIn("20", error)

    def test_contact_purpose_is_required_and_restricted(self):
        _, missing_error = validate_contact(valid_payload(purpose=""))
        _, unknown_error = validate_contact(valid_payload(purpose="free-consulting"))
        self.assertIn("motivo", missing_error)
        self.assertIn("motivo", unknown_error)

    def test_submission_cannot_be_instant(self):
        _, error = validate_contact(valid_payload(elapsed_ms=100))
        self.assertIn("depressa", error)

    def test_honeypot_is_silently_accepted(self):
        data, error = validate_contact(valid_payload(website="spam.example"))
        self.assertIsNone(error)
        self.assertTrue(data["spam"])

    def test_email_validator(self):
        self.assertTrue(is_valid_email("contact@sris.io"))
        self.assertFalse(is_valid_email("Contact <contact@sris.io>"))


class EmailTests(unittest.TestCase):
    def test_html_is_escaped_and_reply_to_is_visitor(self):
        data, error = validate_contact(
            valid_payload(name="<script>alert(1)</script>", message="Mensagem válida <b>sem HTML ativo</b>.")
        )
        self.assertIsNone(error)
        email = build_email(data, "contact@sris.io", "website@mail.sris.io")
        self.assertNotIn("<script>", email["html"])
        self.assertIn("&lt;script&gt;", email["html"])
        self.assertEqual(email["reply_to"], "ana@example.org")
        self.assertEqual(email["to"], ["contact@sris.io"])
        self.assertIn("Agendar apresentação", email["subject"])

    @patch.dict("os.environ", {}, clear=True)
    def test_delivery_requires_api_key(self):
        with self.assertRaisesRegex(RuntimeError, "RESEND_API_KEY"):
            send_via_resend(valid_payload())

    @patch("contact_server.urlopen")
    @patch.dict(
        "os.environ",
        {
            "RESEND_API_KEY": "test-key",
            "SRIS_EMAIL_FROM": "verified@sris.io",
        },
        clear=True,
    )
    def test_resend_reuses_shared_verified_sender(self, urlopen):
        response = MagicMock()
        response.__enter__.return_value.status = 200
        urlopen.return_value = response

        send_via_resend(valid_payload())

        request = urlopen.call_args.args[0]
        self.assertIn(b"verified@sris.io", request.data)

    @patch("contact_server.smtplib.SMTP")
    @patch.dict(
        "os.environ",
        {
            "SRIS_CONTACT_EMAIL_PROVIDER": "smtp",
            "SRIS_SMTP_HOST": "smtp.example.org",
            "SRIS_SMTP_USER": "legacy-user",
            "SRIS_SMTP_PASSWORD": "secret",
            "SRIS_SMTP_FROM_EMAIL": "website@sris.io",
        },
        clear=True,
    )
    def test_smtp_supports_legacy_username(self, smtp):
        connection = smtp.return_value.__enter__.return_value

        send_via_smtp(valid_payload())

        smtp.assert_called_once_with("smtp.example.org", 587, timeout=10)
        connection.starttls.assert_called_once()
        connection.login.assert_called_once_with("legacy-user", "secret")
        connection.send_message.assert_called_once()

    @patch("contact_server.send_via_smtp")
    @patch.dict(
        "os.environ", {"SRIS_CONTACT_EMAIL_PROVIDER": "smtp"}, clear=True
    )
    def test_contact_provider_can_select_smtp(self, smtp):
        send_contact_email(valid_payload())
        smtp.assert_called_once()


class OriginTests(unittest.TestCase):
    def test_canonical_origin_is_allowed(self):
        self.assertTrue(
            is_allowed_origin(
                "https://sris.io", "sris.io", "https://sris.io,https://www.sris.io"
            )
        )

    def test_same_origin_railway_host_is_allowed(self):
        self.assertTrue(
            is_allowed_origin(
                "https://sris-mission-intelligence.up.railway.app",
                "sris-mission-intelligence.up.railway.app",
                "https://sris.io,https://www.sris.io",
            )
        )

    def test_external_origin_is_rejected(self):
        self.assertFalse(
            is_allowed_origin(
                "https://example.org",
                "sris-mission-intelligence.up.railway.app",
                "https://sris.io,https://www.sris.io",
            )
        )


class SiteAlignmentTests(unittest.TestCase):
    def test_tourism_context_and_commercial_boundary_are_explicit(self):
        page = Path("site/index.html").read_text(encoding="utf-8")
        self.assertIn("Alojamento · sustentabilidade · eficiência de recursos", page)
        self.assertIn("Ver demonstração para alojamento", page)
        self.assertIn("Condições definidas antes do início", page)
        self.assertNotIn("Diagnóstico inicial sem custo", page)
        self.assertNotIn("gratuit", page.lower())

    def test_public_pages_use_month_level_update_reference_and_return_to_form(self):
        page = Path("site/index.html").read_text(encoding="utf-8")
        privacy = Path("site/privacidade.html").read_text(encoding="utf-8")

        self.assertNotIn("20260831", page)
        self.assertIn("© 2026 SRIS", page)
        self.assertIn("Última atualização: agosto de 2026", privacy)
        self.assertNotIn("30 de agosto de 2026", privacy)
        self.assertNotIn("20260831", privacy)
        self.assertIn("© 2026 SRIS", privacy)
        self.assertIn('href="/#contacto">Voltar ao formulário</a>', privacy)
        self.assertIn('href="/#contacto">Formulário de contacto</a>', privacy)

        for dated_label in (
            "Forbes Green ESG Awards 2026",
            "Prémio Nacional de Inovação 2026",
            "Prémios Líderes do Turismo 2026",
        ):
            self.assertIn(dated_label, page)


class RateLimiterTests(unittest.TestCase):
    def test_limit_and_window(self):
        limiter = RateLimiter(limit=2, window=10)
        self.assertTrue(limiter.allow("client", now=0))
        self.assertTrue(limiter.allow("client", now=1))
        self.assertFalse(limiter.allow("client", now=2))
        self.assertTrue(limiter.allow("client", now=11))


if __name__ == "__main__":
    unittest.main()
