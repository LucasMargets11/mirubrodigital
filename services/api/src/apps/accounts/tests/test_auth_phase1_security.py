"""
Tests for Phase 1 Security Hardening: Public Auth Rate Limiting & Anti-Enumeration.

Covers:
  - T1.1: DRF throttling on all public auth endpoints
  - T1.2: Anti-enumeration in RegisterView
  - T1.3: DEBUG=False default
  - T1.4: 3D rate limiter for login (IP + identifier + combo)
  - Redis fail-open behavior
  - _get_client_ip XFF hardening
"""
from unittest.mock import patch, MagicMock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError
from django.test import TestCase, override_settings
from rest_framework import status as http_status
from rest_framework.test import APIClient

from apps.accounts.auth_rate_limiter import (
    check_rate_limit,
    record_failed_attempt,
    reset_on_success,
)
from apps.accounts.models import AccountProfile

User = get_user_model()

LOGIN_URL = '/api/v1/auth/login/'
REGISTER_URL = '/api/v1/auth/register/'
FORGOT_URL = '/api/v1/auth/forgot-password/'
RESET_URL = '/api/v1/auth/reset-password/'
VERIFY_URL = '/api/v1/auth/verify-email/'
REFRESH_URL = '/api/v1/auth/refresh/'


def _create_user(email='owner@example.com', password='SecurePass123!'):
    user = User.objects.create_user(username=email, email=email, password=password)
    AccountProfile.objects.get_or_create(user=user)
    return user


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class AuthRateLimiterUnitTests(TestCase):
    """Unit tests for auth_rate_limiter module (3D rate limiter for owner login)."""

    def setUp(self):
        cache.clear()

    # ── check_rate_limit allows initial requests ─────────────────────────────

    def test_allows_initial_request(self):
        result = check_rate_limit('1.2.3.4', 'user@example.com')
        self.assertTrue(result.allowed)
        self.assertEqual(result.retry_after, 0)

    # ── record_failed_attempt increments counters ────────────────────────────

    def test_returns_none_below_threshold(self):
        result = record_failed_attempt('1.2.3.4', 'user@example.com')
        self.assertIsNone(result)

    @override_settings(AUTH_LOGIN_IP_IDENT_MAX_ATTEMPTS=3)
    def test_ip_ident_threshold_triggers_cooldown(self):
        for _ in range(2):
            record_failed_attempt('1.2.3.4', 'user@example.com')
        result = record_failed_attempt('1.2.3.4', 'user@example.com')
        self.assertIsNotNone(result)
        self.assertFalse(result.allowed)
        self.assertEqual(result.dimension, 'ip_ident')
        self.assertGreater(result.retry_after, 0)

    @override_settings(AUTH_LOGIN_IP_IDENT_MAX_ATTEMPTS=3)
    def test_check_blocks_after_cooldown_set(self):
        for _ in range(3):
            record_failed_attempt('1.2.3.4', 'user@example.com')
        result = check_rate_limit('1.2.3.4', 'user@example.com')
        self.assertFalse(result.allowed)
        self.assertGreater(result.retry_after, 0)

    @override_settings(AUTH_LOGIN_IDENT_MAX_ATTEMPTS=3)
    def test_ident_threshold_across_ips(self):
        """Identifier limit triggers regardless of source IP."""
        record_failed_attempt('1.1.1.1', 'target@example.com')
        record_failed_attempt('2.2.2.2', 'target@example.com')
        result = record_failed_attempt('3.3.3.3', 'target@example.com')
        self.assertIsNotNone(result)
        self.assertEqual(result.dimension, 'ident')

    @override_settings(AUTH_LOGIN_IP_MAX_ATTEMPTS=3)
    def test_ip_threshold_across_identifiers(self):
        """IP limit triggers regardless of target identifier."""
        record_failed_attempt('1.2.3.4', 'user1@example.com')
        record_failed_attempt('1.2.3.4', 'user2@example.com')
        result = record_failed_attempt('1.2.3.4', 'user3@example.com')
        self.assertIsNotNone(result)
        self.assertEqual(result.dimension, 'ip')

    # ── reset_on_success ─────────────────────────────────────────────────────

    @override_settings(AUTH_LOGIN_IP_IDENT_MAX_ATTEMPTS=5)
    def test_reset_clears_ip_ident_and_ident_but_not_ip(self):
        for _ in range(3):
            record_failed_attempt('1.2.3.4', 'user@example.com')
        reset_on_success('1.2.3.4', 'user@example.com')

        # IP+ident and ident counters should be cleared
        result = check_rate_limit('1.2.3.4', 'user@example.com')
        self.assertTrue(result.allowed)

    @override_settings(AUTH_LOGIN_IP_MAX_ATTEMPTS=5)
    def test_reset_preserves_ip_counter(self):
        """Global IP counter is NOT reset on success (by design)."""
        for _ in range(4):
            record_failed_attempt('1.2.3.4', f'user{_}@example.com')
        # Reset with one of the identifiers
        reset_on_success('1.2.3.4', 'user0@example.com')
        # The IP counter should still be at 4
        result = record_failed_attempt('1.2.3.4', 'userX@example.com')
        # This was attempt #5, should trigger
        self.assertIsNotNone(result)
        self.assertEqual(result.dimension, 'ip')

    # ── identifier normalization ─────────────────────────────────────────────

    @override_settings(AUTH_LOGIN_IP_IDENT_MAX_ATTEMPTS=2)
    def test_case_insensitive_identifier(self):
        record_failed_attempt('1.2.3.4', 'User@Example.COM')
        result = record_failed_attempt('1.2.3.4', 'user@example.com')
        self.assertIsNotNone(result)
        self.assertEqual(result.dimension, 'ip_ident')

    @override_settings(AUTH_LOGIN_IP_IDENT_MAX_ATTEMPTS=2)
    def test_unicode_nfkc_normalization(self):
        """NFKC-equivalent strings must hash to the same key."""
        # NFC form: é as single codepoint U+00E9
        nfc = 'caf\u00e9@example.com'
        # NFD form: é as e + combining acute U+0301
        nfd = 'cafe\u0301@example.com'
        record_failed_attempt('1.2.3.4', nfc)
        result = record_failed_attempt('1.2.3.4', nfd)
        self.assertIsNotNone(result)
        self.assertEqual(result.dimension, 'ip_ident')

    def test_redis_failure_fails_open_check(self):
        """check_rate_limit returns allowed=True and logs when Redis is unavailable."""
        with patch('apps.accounts.auth_rate_limiter.cache') as mock_cache:
            mock_cache.get.side_effect = ConnectionError('Redis down')
            with self.assertLogs('apps.accounts.auth_rate_limiter', level='ERROR') as cm:
                result = check_rate_limit('1.2.3.4', 'user@example.com')
            self.assertTrue(result.allowed)
            self.assertTrue(
                any('RATE_LIMIT_REDIS_UNAVAILABLE' in msg for msg in cm.output),
            )

    def test_redis_failure_fails_open_record(self):
        """record_failed_attempt returns None and logs when Redis is unavailable."""
        with patch('apps.accounts.auth_rate_limiter.cache') as mock_cache:
            mock_cache.incr.side_effect = ConnectionError('Redis down')
            mock_cache.set.side_effect = ConnectionError('Redis down')
            with self.assertLogs('apps.accounts.auth_rate_limiter', level='ERROR') as cm:
                result = record_failed_attempt('1.2.3.4', 'user@example.com')
            self.assertIsNone(result)
            self.assertTrue(
                any('RATE_LIMIT_REDIS_UNAVAILABLE' in msg for msg in cm.output),
            )


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
    AUTH_LOGIN_IP_IDENT_MAX_ATTEMPTS=100,
    AUTH_LOGIN_IDENT_MAX_ATTEMPTS=100,
    AUTH_LOGIN_IP_MAX_ATTEMPTS=100,
)
class LoginViewThrottleTests(TestCase):
    """Integration tests for LoginView with throttling + 3D rate limiter."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        _create_user()

    @override_settings(
        REST_FRAMEWORK={
            **settings.REST_FRAMEWORK,
            'DEFAULT_THROTTLE_RATES': {
                **settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {}),
                'auth_login': '3/minute',
            },
        },
    )
    def test_login_throttled_after_limit(self):
        """DRF throttle kicks in after N requests per IP."""
        for _ in range(3):
            self.client.post(LOGIN_URL, {'email': 'bad@bad.com', 'password': 'wrong'})
        resp = self.client.post(LOGIN_URL, {'email': 'bad@bad.com', 'password': 'wrong'})
        self.assertEqual(resp.status_code, http_status.HTTP_429_TOO_MANY_REQUESTS)

    def test_login_success_returns_ok(self):
        resp = self.client.post(LOGIN_URL, {'email': 'owner@example.com', 'password': 'SecurePass123!'})
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], 'ok')

    def test_login_failure_returns_generic_error(self):
        resp = self.client.post(LOGIN_URL, {'email': 'owner@example.com', 'password': 'wrong'})
        self.assertEqual(resp.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data['detail'], 'Credenciales inválidas')

    def test_inactive_user_returns_generic_error(self):
        """Inactive users get the same generic error (no information leak)."""
        user = User.objects.get(email='owner@example.com')
        user.is_active = False
        user.save()
        resp = self.client.post(LOGIN_URL, {'email': 'owner@example.com', 'password': 'SecurePass123!'})
        self.assertEqual(resp.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data['detail'], 'Credenciales inválidas')

    @override_settings(AUTH_LOGIN_IP_IDENT_MAX_ATTEMPTS=3)
    def test_3d_rate_limit_blocks_after_threshold(self):
        """3D rate limiter returns 429 with Retry-After header."""
        for _ in range(3):
            self.client.post(LOGIN_URL, {'email': 'owner@example.com', 'password': 'wrong'})
        resp = self.client.post(LOGIN_URL, {'email': 'owner@example.com', 'password': 'SecurePass123!'})
        self.assertEqual(resp.status_code, http_status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn('Retry-After', resp.headers)

    @override_settings(AUTH_LOGIN_IP_IDENT_MAX_ATTEMPTS=5)
    def test_successful_login_resets_counters(self):
        """A successful login clears the ip+ident and ident counters."""
        for _ in range(3):
            self.client.post(LOGIN_URL, {'email': 'owner@example.com', 'password': 'wrong'})
        # Successful login resets counters
        resp = self.client.post(LOGIN_URL, {'email': 'owner@example.com', 'password': 'SecurePass123!'})
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        # Should be able to fail again without immediate block
        for _ in range(3):
            self.client.post(LOGIN_URL, {'email': 'owner@example.com', 'password': 'wrong'})
        resp = self.client.post(LOGIN_URL, {'email': 'owner@example.com', 'password': 'wrong'})
        self.assertEqual(resp.status_code, http_status.HTTP_400_BAD_REQUEST)  # Not 429 yet


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class RegisterViewAntiEnumerationTests(TestCase):
    """T1.2: RegisterView must not reveal whether an email already exists."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def test_new_user_returns_201(self):
        resp = self.client.post(REGISTER_URL, {
            'email': 'new@example.com',
            'password': 'SecurePass123!',
        })
        self.assertEqual(resp.status_code, http_status.HTTP_201_CREATED)
        self.assertEqual(resp.data['status'], 'created')
        self.assertIn('message', resp.data)
        # Email and user id should NOT be in the response
        self.assertNotIn('user', resp.data)

    def test_existing_user_returns_same_201(self):
        """When email already exists, the response is identical to new registration."""
        _create_user(email='existing@example.com')
        resp = self.client.post(REGISTER_URL, {
            'email': 'existing@example.com',
            'password': 'AnotherPass123!',
        })
        # MUST be 201, not 400 (anti-enumeration)
        self.assertEqual(resp.status_code, http_status.HTTP_201_CREATED)
        self.assertEqual(resp.data['status'], 'created')
        self.assertIn('message', resp.data)

    def test_responses_are_identical_shape(self):
        """Both paths return exactly the same keys to prevent fingerprinting."""
        _create_user(email='victim@example.com')

        resp_dup = self.client.post(REGISTER_URL, {
            'email': 'victim@example.com',
            'password': 'SecurePass123!',
        })
        resp_new = self.client.post(REGISTER_URL, {
            'email': 'brand_new@example.com',
            'password': 'SecurePass123!',
        })
        self.assertEqual(set(resp_dup.data.keys()), set(resp_new.data.keys()))
        self.assertEqual(resp_dup.status_code, resp_new.status_code)

    def test_case_insensitive_duplicate_detection(self):
        _create_user(email='test@example.com')
        resp = self.client.post(REGISTER_URL, {
            'email': 'TEST@Example.COM',
            'password': 'SecurePass123!',
        })
        self.assertEqual(resp.status_code, http_status.HTTP_201_CREATED)
        # Only one user should exist
        self.assertEqual(User.objects.filter(email__iexact='test@example.com').count(), 1)

    @override_settings(
        REST_FRAMEWORK={
            **settings.REST_FRAMEWORK,
            'DEFAULT_THROTTLE_RATES': {
                **settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {}),
                'auth_register': '2/minute',
            },
        },
    )
    def test_register_throttled(self):
        for _ in range(2):
            self.client.post(REGISTER_URL, {
                'email': f'user{_}@example.com',
                'password': 'SecurePass123!',
            })
        resp = self.client.post(REGISTER_URL, {
            'email': 'user99@example.com',
            'password': 'SecurePass123!',
        })
        self.assertEqual(resp.status_code, http_status.HTTP_429_TOO_MANY_REQUESTS)

    @patch('apps.accounts.services.EmailService.send_verification_email')
    @patch('apps.accounts.views.send_verification_email_task')
    def test_new_user_dispatches_celery_task_not_sync_email(self, mock_task, mock_sync_email):
        """Registration enqueues a Celery task; EmailService is NOT called synchronously."""
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(REGISTER_URL, {
                'email': 'celery_test@example.com',
                'password': 'SecurePass123!',
            })
        self.assertEqual(resp.status_code, http_status.HTTP_201_CREATED)
        mock_task.delay.assert_called_once()
        args = mock_task.delay.call_args[0]
        self.assertIsInstance(args[0], int)   # user_id
        self.assertIsInstance(args[1], str)   # token
        mock_sync_email.assert_not_called()

    @patch('apps.accounts.views.send_verification_email_task')
    def test_existing_user_does_not_dispatch_task(self, mock_task):
        """Duplicate registration must NOT enqueue any email task."""
        _create_user(email='dup_task@example.com')
        resp = self.client.post(REGISTER_URL, {
            'email': 'dup_task@example.com',
            'password': 'SecurePass123!',
        })
        self.assertEqual(resp.status_code, http_status.HTTP_201_CREATED)
        mock_task.delay.assert_not_called()

    @patch('apps.accounts.views.send_verification_email_task')
    def test_integrity_error_returns_safe_response(self, mock_task):
        """Concurrent duplicate (IntegrityError) returns 201 anti-enumeration response."""
        with patch('django.contrib.auth.models.UserManager.create_user', side_effect=IntegrityError):
            resp = self.client.post(REGISTER_URL, {
                'email': 'race@example.com',
                'password': 'SecurePass123!',
            })
        self.assertEqual(resp.status_code, http_status.HTTP_201_CREATED)
        self.assertEqual(resp.data['status'], 'created')
        mock_task.delay.assert_not_called()


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class OtherAuthEndpointThrottleTests(TestCase):
    """T1.1: Verify throttles are wired on forgot-password, reset-password, verify-email, refresh."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()

    @override_settings(
        REST_FRAMEWORK={
            **settings.REST_FRAMEWORK,
            'DEFAULT_THROTTLE_RATES': {
                **settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {}),
                'auth_forgot_password': '2/minute',
            },
        },
    )
    def test_forgot_password_throttled(self):
        for _ in range(2):
            self.client.post(FORGOT_URL, {'email': 'user@example.com'})
        resp = self.client.post(FORGOT_URL, {'email': 'user@example.com'})
        self.assertEqual(resp.status_code, http_status.HTTP_429_TOO_MANY_REQUESTS)

    @override_settings(
        REST_FRAMEWORK={
            **settings.REST_FRAMEWORK,
            'DEFAULT_THROTTLE_RATES': {
                **settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {}),
                'auth_reset_password': '2/minute',
            },
        },
    )
    def test_reset_password_throttled(self):
        for _ in range(2):
            self.client.post(RESET_URL, {'token': 'fake', 'new_password': 'NewPass123!'})
        resp = self.client.post(RESET_URL, {'token': 'fake', 'new_password': 'NewPass123!'})
        self.assertEqual(resp.status_code, http_status.HTTP_429_TOO_MANY_REQUESTS)

    @override_settings(
        REST_FRAMEWORK={
            **settings.REST_FRAMEWORK,
            'DEFAULT_THROTTLE_RATES': {
                **settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {}),
                'auth_verify_email': '2/minute',
            },
        },
    )
    def test_verify_email_throttled(self):
        for _ in range(2):
            self.client.post(VERIFY_URL, {'token': 'fake'})
        resp = self.client.post(VERIFY_URL, {'token': 'fake'})
        self.assertEqual(resp.status_code, http_status.HTTP_429_TOO_MANY_REQUESTS)

    @override_settings(
        REST_FRAMEWORK={
            **settings.REST_FRAMEWORK,
            'DEFAULT_THROTTLE_RATES': {
                **settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {}),
                'auth_refresh': '2/minute',
            },
        },
    )
    def test_refresh_throttled(self):
        for _ in range(2):
            self.client.post(REFRESH_URL)
        resp = self.client.post(REFRESH_URL)
        self.assertEqual(resp.status_code, http_status.HTTP_429_TOO_MANY_REQUESTS)

    def test_forgot_password_anti_enumeration(self):
        """Forgot-password always returns 200 regardless of email existence."""
        resp1 = self.client.post(FORGOT_URL, {'email': 'nonexistent@example.com'})
        self.assertEqual(resp1.status_code, http_status.HTTP_200_OK)

        _create_user(email='real@example.com')
        resp2 = self.client.post(FORGOT_URL, {'email': 'real@example.com'})
        self.assertEqual(resp2.status_code, http_status.HTTP_200_OK)

        # Same response structure
        self.assertEqual(resp1.data['status'], resp2.data['status'])


class DebugDefaultTests(TestCase):
    """T1.3: Verify DEBUG defaults to False."""

    def test_debug_default_is_false(self):
        """The running Django settings.DEBUG must be False (CI/test default)."""
        self.assertFalse(settings.DEBUG)


@override_settings(TRUSTED_PROXY_DEPTH=1)
class GetClientIpTests(TestCase):
    """Verify _get_client_ip uses rightmost XFF entry, not leftmost (spoofable)."""

    def _make_request(self, xff=None, remote_addr='10.0.0.1'):
        from apps.accounts.views import _get_client_ip
        from rest_framework.test import APIRequestFactory
        factory = APIRequestFactory()
        req = factory.get('/')
        req.META['REMOTE_ADDR'] = remote_addr
        if xff is not None:
            req.META['HTTP_X_FORWARDED_FOR'] = xff
        return _get_client_ip(req)

    def test_no_xff_uses_remote_addr(self):
        ip = self._make_request(remote_addr='192.168.1.1')
        self.assertEqual(ip, '192.168.1.1')

    def test_single_xff_entry(self):
        ip = self._make_request(xff='203.0.113.50')
        self.assertEqual(ip, '203.0.113.50')

    def test_spoofed_xff_uses_rightmost(self):
        """Attacker prepends fake IP; we must take the rightmost (proxy-added) entry."""
        ip = self._make_request(xff='1.2.3.4, 203.0.113.50')
        self.assertEqual(ip, '203.0.113.50')

    @override_settings(TRUSTED_PROXY_DEPTH=2)
    def test_depth_2_skips_proxy(self):
        ip = self._make_request(xff='1.2.3.4, 203.0.113.50, 10.0.0.2')
        self.assertEqual(ip, '203.0.113.50')

    def test_xff_with_port_stripped(self):
        ip = self._make_request(xff='203.0.113.50:8080')
        self.assertEqual(ip, '203.0.113.50')

    def test_fewer_entries_than_depth_falls_back(self):
        """If XFF has fewer entries than expected, fall back to REMOTE_ADDR."""
        with override_settings(TRUSTED_PROXY_DEPTH=3):
            ip = self._make_request(xff='1.2.3.4, 5.6.7.8', remote_addr='10.0.0.1')
            self.assertEqual(ip, '10.0.0.1')

    def test_ipv6_pure(self):
        """Pure IPv6 address in XFF is returned correctly."""
        ip = self._make_request(xff='2001:db8::1')
        self.assertEqual(ip, '2001:db8::1')

    def test_ipv6_bracketed_with_port(self):
        """IPv6 address in brackets with port is normalized correctly."""
        ip = self._make_request(xff='[2001:db8::1]:8080')
        self.assertEqual(ip, '2001:db8::1')

    def test_ipv4_mapped_ipv6(self):
        """IPv4-mapped IPv6 address is accepted and returned."""
        ip = self._make_request(xff='::ffff:192.168.1.1')
        self.assertEqual(ip, '::ffff:192.168.1.1')
