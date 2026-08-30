import unittest
from unittest.mock import patch

from contact_server import RateLimiter, build_email, is_valid_email, send_via_resend, validate_contact


def valid_payload(**overrides):
    payload = {
        "name": "Ana Martins",
        "email": "ana@example.org",
        "organization": "Organização Exemplo",
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
        self.assertIn("autorizar", error)

    def test_message_length_is_checked(self):
        _, error = validate_contact(valid_payload(message="Curta"))
        self.assertIn("20", error)

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

    @patch.dict("os.environ", {}, clear=True)
    def test_delivery_requires_api_key(self):
        with self.assertRaisesRegex(RuntimeError, "RESEND_API_KEY"):
            send_via_resend(valid_payload())


class RateLimiterTests(unittest.TestCase):
    def test_limit_and_window(self):
        limiter = RateLimiter(limit=2, window=10)
        self.assertTrue(limiter.allow("client", now=0))
        self.assertTrue(limiter.allow("client", now=1))
        self.assertFalse(limiter.allow("client", now=2))
        self.assertTrue(limiter.allow("client", now=11))


if __name__ == "__main__":
    unittest.main()
