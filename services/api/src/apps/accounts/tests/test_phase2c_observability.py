"""
Phase 2C tests — structured logging, security events, CSP report-only.

Test IDs:
  T2C.1  — JSON formatter is configured when LOG_FORMAT=json
  T2C.2  — text formatter is configured when LOG_FORMAT=text
  T2C.3  — security events emit with correct fields, no secrets
  T2C.4  — login success emits auth.login.success event
  T2C.5  — login failed emits auth.login.failed event
  T2C.6  — logout emits auth.logout.success event
  T2C.7  — refresh success emits auth.refresh.success event
  T2C.8  — refresh failed emits auth.refresh.failed event
  T2C.9  — rate-limit emits auth.ratelimit.triggered event
  T2C.10 — CSP report-only header present on API responses
  T2C.11 — security events never contain password or raw token
"""
import logging
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory, override_settings
from rest_framework.test import APIClient

from apps.accounts import security_events
from config.middleware import CSPReportOnlyMiddleware

User = get_user_model()


class StructuredLoggingConfigTests(TestCase):
    """T2C.1 / T2C.2 — LOGGING configuration."""

    def test_json_formatter_exists(self):
        """T2C.1: json formatter is declared in LOGGING."""
        self.assertIn('json', settings.LOGGING['formatters'])
        json_fmt = settings.LOGGING['formatters']['json']
        # Must use the pythonjsonlogger factory
        self.assertIn('pythonjsonlogger', json_fmt.get('()', ''))

    def test_text_formatter_exists(self):
        """T2C.2: verbose (text) formatter is still declared."""
        self.assertIn('verbose', settings.LOGGING['formatters'])

    def test_security_logger_declared(self):
        """apps.accounts.security logger is declared in LOGGING config."""
        self.assertIn('apps.accounts.security', settings.LOGGING['loggers'])


class SecurityEventEmissionTests(TestCase):
    """T2C.3–T2C.9 — security_events module emits structured events."""

    def setUp(self):
        self.log_output = []
        # Capture all records emitted to apps.accounts.security
        self.handler = logging.Handler()
        self.handler.emit = lambda record: self.log_output.append(record)
        security_events.security_logger.addHandler(self.handler)
        security_events.security_logger.setLevel(logging.DEBUG)

    def tearDown(self):
        security_events.security_logger.removeHandler(self.handler)

    def test_login_success_event(self):
        """T2C.4: login_success emits correct event name and fields."""
        security_events.login_success(user_id=42, email='a@b.com', ip='1.2.3.4')
        self.assertEqual(len(self.log_output), 1)
        rec = self.log_output[0]
        self.assertEqual(rec.event, 'auth.login.success')
        self.assertEqual(rec.outcome, 'success')
        self.assertEqual(rec.user_id, 42)
        self.assertEqual(rec.email, 'a@b.com')
        self.assertEqual(rec.ip, '1.2.3.4')

    def test_login_failed_event(self):
        """T2C.5: login_failed emits correct event name and reason."""
        security_events.login_failed(email='x@y.com', ip='5.6.7.8')
        rec = self.log_output[0]
        self.assertEqual(rec.event, 'auth.login.failed')
        self.assertEqual(rec.outcome, 'failed')
        self.assertEqual(rec.reason, 'invalid_credentials')

    def test_logout_success_event(self):
        """T2C.6: logout_success emits correct event."""
        security_events.logout_success(user_id=7, ip='10.0.0.1')
        rec = self.log_output[0]
        self.assertEqual(rec.event, 'auth.logout.success')

    def test_refresh_success_event(self):
        """T2C.7: refresh_success emits correct event."""
        security_events.refresh_success(user_id=7, ip='10.0.0.1')
        rec = self.log_output[0]
        self.assertEqual(rec.event, 'auth.refresh.success')

    def test_refresh_failed_event(self):
        """T2C.8: refresh_failed emits correct event."""
        security_events.refresh_failed(ip='10.0.0.1', reason='expired')
        rec = self.log_output[0]
        self.assertEqual(rec.event, 'auth.refresh.failed')
        self.assertEqual(rec.reason, 'expired')

    def test_ratelimit_triggered_event(self):
        """T2C.9: ratelimit_triggered emits correct event."""
        security_events.ratelimit_triggered(ip='10.0.0.1', email='rl@test.com', reason='ip_ident')
        rec = self.log_output[0]
        self.assertEqual(rec.event, 'auth.ratelimit.triggered')
        self.assertEqual(rec.outcome, 'blocked')

    def test_no_secrets_in_events(self):
        """T2C.11: security events must not contain password or token fields."""
        security_events.login_success(user_id=1, email='a@b.com', ip='1.1.1.1')
        security_events.login_failed(email='a@b.com', ip='1.1.1.1')
        security_events.refresh_failed(ip='1.1.1.1')
        for rec in self.log_output:
            self.assertFalse(hasattr(rec, 'password'), 'password leaked into log record')
            self.assertFalse(hasattr(rec, 'token'), 'token leaked into log record')
            self.assertFalse(hasattr(rec, 'refresh_token'), 'refresh_token leaked into log record')


class CSPReportOnlyTests(TestCase):
    """T2C.10 — CSP report-only header on API responses."""

    def test_csp_header_present_on_login_endpoint(self):
        """T2C.10: Content-Security-Policy-Report-Only appears in API responses."""
        client = APIClient()
        response = client.post('/api/v1/auth/login/', {'email': 'x', 'password': 'y'})
        csp = response.get('Content-Security-Policy-Report-Only', '')
        self.assertIn("default-src 'self'", csp)
        self.assertIn("script-src", csp)
        self.assertIn("frame-ancestors 'none'", csp)

    def test_csp_header_not_enforce(self):
        """CSP must be report-only, not enforcing."""
        client = APIClient()
        response = client.post('/api/v1/auth/login/', {'email': 'x', 'password': 'y'})
        self.assertIsNone(response.get('Content-Security-Policy'))


class IntegrationSecurityEventTests(TestCase):
    """Integration: views actually emit security events."""

    def setUp(self):
        self.log_output = []
        self.handler = logging.Handler()
        self.handler.emit = lambda record: self.log_output.append(record)
        security_events.security_logger.addHandler(self.handler)
        security_events.security_logger.setLevel(logging.DEBUG)
        self.client = APIClient()

    def tearDown(self):
        security_events.security_logger.removeHandler(self.handler)

    def _create_user(self, email='integ@test.com', password='TestPass123!'):
        user = User.objects.create_user(username=email, email=email, password=password)
        return user, password

    def test_login_view_emits_success_event(self):
        user, pwd = self._create_user()
        self.client.post('/api/v1/auth/login/', {'email': user.email, 'password': pwd})
        events = [r for r in self.log_output if getattr(r, 'event', '') == 'auth.login.success']
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].user_id, user.pk)

    def test_login_view_emits_failed_event(self):
        self._create_user()
        self.client.post('/api/v1/auth/login/', {'email': 'integ@test.com', 'password': 'wrong'})
        events = [r for r in self.log_output if getattr(r, 'event', '') == 'auth.login.failed']
        self.assertEqual(len(events), 1)

    def test_logout_view_emits_event(self):
        user, pwd = self._create_user()
        resp = self.client.post('/api/v1/auth/login/', {'email': user.email, 'password': pwd})
        self.client.post('/api/v1/auth/logout/')
        events = [r for r in self.log_output if getattr(r, 'event', '') == 'auth.logout.success']
        self.assertEqual(len(events), 1)

    def test_refresh_view_emits_success_event(self):
        user, pwd = self._create_user()
        self.client.post('/api/v1/auth/login/', {'email': user.email, 'password': pwd})
        self.client.post('/api/v1/auth/refresh/')
        events = [r for r in self.log_output if getattr(r, 'event', '') == 'auth.refresh.success']
        self.assertEqual(len(events), 1)

    def test_refresh_view_emits_failed_event(self):
        self.client.cookies.load({'refresh_token': 'garbage'})
        self.client.post('/api/v1/auth/refresh/')
        events = [r for r in self.log_output if getattr(r, 'event', '') == 'auth.refresh.failed']
        self.assertEqual(len(events), 1)
