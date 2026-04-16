"""
Unit tests for _verify_mp_signature() — billing/webhook_processor.py

Covers:
  1. Valid HMAC-SHA256 signature → True
  2. Invalid signature (wrong v1) → False
  3. Malformed x-signature header (missing ts or v1) → False
  4. Empty x-signature header → False
  5. No MP_WEBHOOK_SECRET + DEBUG=True → True (dev bypass)
  6. No MP_WEBHOOK_SECRET + DEBUG=False → False (production reject)
"""
import hashlib
import hmac
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from apps.billing.webhook_processor import _verify_mp_signature


def _build_request(data_id: str = 'preapp-123'):
    """Build a minimal mock request with data.id."""
    request = MagicMock()
    request.data = {'data': {'id': data_id}}
    return request


def _sign(secret: str, data_id: str, x_request_id: str, ts: str) -> str:
    """Compute the HMAC-SHA256 signature the same way MP does."""
    manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts}"
    return hmac.new(
        secret.encode('utf-8'),
        manifest.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()


SECRET = 'test-webhook-secret-abc123'


@override_settings(MP_WEBHOOK_SECRET=SECRET, DEBUG=False)
class VerifyMpSignatureTests(SimpleTestCase):
    """Unit tests for _verify_mp_signature (secret configured, non-DEBUG)."""

    def test_valid_signature_returns_true(self):
        data_id = 'preapp-999'
        x_request_id = 'req-001'
        ts = '1713300000'
        v1 = _sign(SECRET, data_id, x_request_id, ts)
        x_signature = f'ts={ts},v1={v1}'

        request = _build_request(data_id)
        result = _verify_mp_signature(request, x_request_id, x_signature)

        self.assertTrue(result)

    def test_invalid_signature_returns_false(self):
        data_id = 'preapp-999'
        x_request_id = 'req-001'
        ts = '1713300000'
        x_signature = f'ts={ts},v1=deadbeef0000'

        request = _build_request(data_id)
        result = _verify_mp_signature(request, x_request_id, x_signature)

        self.assertFalse(result)

    def test_malformed_header_missing_v1_returns_false(self):
        request = _build_request('preapp-999')
        x_signature = 'ts=1713300000'

        result = _verify_mp_signature(request, 'req-001', x_signature)

        self.assertFalse(result)

    def test_malformed_header_missing_ts_returns_false(self):
        request = _build_request('preapp-999')
        x_signature = 'v1=abcdef123456'

        result = _verify_mp_signature(request, 'req-001', x_signature)

        self.assertFalse(result)

    def test_empty_signature_header_returns_false(self):
        request = _build_request('preapp-999')

        result = _verify_mp_signature(request, 'req-001', '')

        self.assertFalse(result)

    def test_tampered_data_id_fails(self):
        """Signature computed with one data_id, request contains another."""
        x_request_id = 'req-002'
        ts = '1713300000'
        v1 = _sign(SECRET, 'preapp-original', x_request_id, ts)
        x_signature = f'ts={ts},v1={v1}'

        request = _build_request('preapp-tampered')
        result = _verify_mp_signature(request, x_request_id, x_signature)

        self.assertFalse(result)


@override_settings(MP_WEBHOOK_SECRET=None, DEBUG=True)
class VerifyMpSignatureDevBypassTests(SimpleTestCase):
    """When secret is not set and DEBUG=True, signature check is bypassed."""

    def test_no_secret_debug_true_returns_true(self):
        request = _build_request('preapp-dev')
        result = _verify_mp_signature(request, 'req-dev', '')

        self.assertTrue(result)


@override_settings(MP_WEBHOOK_SECRET=None, DEBUG=False)
class VerifyMpSignatureProdRejectTests(SimpleTestCase):
    """When secret is not set and DEBUG=False, all webhooks are rejected."""

    def test_no_secret_debug_false_returns_false(self):
        request = _build_request('preapp-prod')
        result = _verify_mp_signature(request, 'req-prod', '')

        self.assertFalse(result)


@override_settings(MP_WEBHOOK_SECRET='', DEBUG=False)
class VerifyMpSignatureEmptySecretTests(SimpleTestCase):
    """Empty string secret in non-DEBUG must also reject."""

    def test_empty_string_secret_debug_false_returns_false(self):
        request = _build_request('preapp-empty')
        result = _verify_mp_signature(request, 'req-empty', '')

        self.assertFalse(result)
