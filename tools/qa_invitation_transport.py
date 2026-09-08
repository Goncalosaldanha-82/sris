"""No real sends: exercise the same HTTP transport used by invites and resets."""
from __future__ import annotations

import importlib.util
import io
import json
import logging
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sris_auth_transport_qa", ROOT / "backend/app/atlas_platform/auth_delivery.py")
delivery = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = delivery
spec.loader.exec_module(delivery)


class Reply:
    status = 200
    def __init__(self, body=b'{"id":"provider-receipt-test"}'):
        self.body = body
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, size=-1): return self.body[:size] if size >= 0 else self.body


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.cfg = delivery.AuthDeliveryConfiguration("resend", "noreply@example.com", "SRIS", "https://app.example.com", 12)
        self.env = patch.dict(os.environ, {"RESEND_API_KEY":"test-key-not-real"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.resolve = patch.object(delivery, "auth_delivery_configuration", return_value=self.cfg)
        self.resolve.start()
        self.addCleanup(self.resolve.stop)

    def send(self, text="test", subject="Convite para workspace no SRIS"):
        return delivery.send_transactional_email(recipient="person@example.com", subject=subject, text_body=text, html_body="<p>test</p>")

    def test_explicit_user_agent_for_real_invitation_transport(self):
        with patch.object(delivery,"urlopen",return_value=Reply()) as mock:
            self.assertEqual(self.send(),"provider-receipt-test")
        req=mock.call_args.args[0]
        self.assertEqual(req.get_header("User-agent"),delivery.USER_AGENT)
        self.assertEqual(req.get_method(),"POST")
        self.assertEqual(json.loads(req.data)["to"],["person@example.com"])

    def test_same_token_and_content_are_idempotent(self):
        with patch.object(delivery,"urlopen",side_effect=[Reply(),Reply()]) as mock:
            self.send("#invite=same");self.send("#invite=same")
        self.assertEqual(mock.call_args_list[0].args[0].get_header("Idempotency-key"), mock.call_args_list[1].args[0].get_header("Idempotency-key"))

    def test_new_token_changes_idempotency_key(self):
        with patch.object(delivery,"urlopen",side_effect=[Reply(),Reply()]) as mock:
            self.send("#invite=first");self.send("#invite=second")
        self.assertNotEqual(mock.call_args_list[0].args[0].get_header("Idempotency-key"), mock.call_args_list[1].args[0].get_header("Idempotency-key"))

    def test_edge_rejection_is_classified_without_body(self):
        error=HTTPError("https://api.resend.com/emails",403,"Forbidden",{},io.BytesIO(b"error code: 1010 sensitive@example.com SECRET"))
        with patch.object(delivery,"urlopen",side_effect=error):
            with self.assertRaisesRegex(delivery.AuthDeliveryError,"^provider_http_403:edge_1010$"):
                self.send()

    def test_json_error_is_classified_without_private_message(self):
        error=HTTPError("https://api.resend.com/emails",403,"Forbidden",{},io.BytesIO(b'{"name":"validation_error","message":"person@example.com SECRET"}'))
        with patch.object(delivery,"urlopen",side_effect=error):
            with self.assertRaisesRegex(delivery.AuthDeliveryError,"^provider_http_403:validation_error$"):
                self.send()

    def test_missing_receipt_is_not_reported_as_sent(self):
        with patch.object(delivery,"urlopen",return_value=Reply(b'{}')):
            with self.assertRaisesRegex(delivery.AuthDeliveryError,"provider_receipt_missing"):
                self.send()

    def test_invalid_response_is_not_reported_as_sent(self):
        with patch.object(delivery,"urlopen",return_value=Reply(b'not json')):
            with self.assertRaises(delivery.AuthDeliveryError): self.send()

    def test_network_error_does_not_expose_exception_body(self):
        with patch.object(delivery,"urlopen",side_effect=URLError("SECRET")):
            with self.assertRaisesRegex(delivery.AuthDeliveryError,"^provider_transport_URLError$"):
                self.send()

    def test_reset_email_uses_fixed_transport_too(self):
        with patch.object(delivery,"urlopen",return_value=Reply()) as mock:
            self.send("#reset=secret", "Recuperar a palavra-passe do SRIS")
        self.assertEqual(mock.call_args.args[0].get_header("User-agent"),delivery.USER_AGENT)

    def test_token_stays_in_fragment(self):
        from urllib.parse import urlparse
        url=delivery.build_auth_link("invite","personal-token")
        parsed=urlparse(url)
        self.assertEqual(parsed.path,"/account.html")
        self.assertEqual(parsed.fragment,"invite=personal-token")
        self.assertEqual(parsed.query,"")

    def test_failure_closed_when_not_configured(self):
        with patch.object(delivery,"auth_delivery_configuration",return_value=None):
            with self.assertRaises(delivery.AuthDeliveryError): self.send()

    def test_logs_never_contain_email_token_or_key(self):
        with self.assertLogs(delivery.LOGGER,level=logging.WARNING) as logs:
            with patch.object(delivery,"urlopen",return_value=Reply()): self.send("#invite=SECRET-TOKEN")
        output="\n".join(logs.output)
        self.assertNotIn("person@example.com",output)
        self.assertNotIn("SECRET-TOKEN",output)
        self.assertNotIn("test-key",output)
        self.assertIn("provider_accepted",output)


if __name__ == "__main__":
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TransportTests))
    print("SRIS_INVITATION_TRANSPORT_QA "+json.dumps({"tests":result.testsRun,"failed":len(result.failures)+len(result.errors),"email":"mocked; no real sends"}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
