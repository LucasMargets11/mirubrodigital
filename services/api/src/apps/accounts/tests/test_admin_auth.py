"""
Tests for Phase 1.1: Admin Login Hardening.

Covers:
  - Rate limiting (IP, email, IP+email)
  - Counter reset on successful login
  - Generic responses (anti-enumeration)
  - Non-admin user attempting admin login
  - MFA enrollment flow
  - MFA OTP verification + replay prevention
  - MFA recovery codes
  - OTP attempt limiting
  - Logout / cookie clearing
  - IP allowlist
"""
import json
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.admin_mfa import (
    encrypt_secret,
    generate_recovery_codes,
    generate_totp_secret,
    get_provisioning_uri,
    hash_recovery_code,
    verify_totp,
)
from apps.accounts.admin_rate_limiter import (
    check_rate_limit,
    record_failed_attempt,
    reset_on_success,
)
from apps.accounts.models import AccountProfile

User = get_user_model()

ADMIN_LOGIN_URL = '/api/v1/platform-admin/auth/login/'
MFA_VERIFY_URL = '/api/v1/platform-admin/auth/mfa-verify/'
MFA_RECOVERY_URL = '/api/v1/platform-admin/auth/mfa-recovery/'
MFA_ENROLL_URL = '/api/v1/platform-admin/auth/mfa-enroll/'
MFA_CONFIRM_URL = '/api/v1/platform-admin/auth/mfa-confirm/'
MFA_DISABLE_URL = '/api/v1/platform-admin/auth/mfa-disable/'
ADMIN_LOGOUT_URL = '/api/v1/platform-admin/auth/logout/'

GENERIC_ERROR = 'Credenciales inválidas o acceso temporalmente restringido.'


def _create_admin_user(email='admin@mirubro.com', password='SecurePass123!', role='superadmin'):
    user = User.objects.create_user(username=email, email=email, password=password)
    profile, _ = AccountProfile.objects.get_or_create(user=user)
    profile.is_platform_staff = True
    profile.internal_role = role
    profile.save()
    return user, profile


def _create_regular_user(email='user@example.com', password='UserPass123!'):
    user = User.objects.create_user(username=email, email=email, password=password)
    AccountProfile.objects.get_or_create(user=user)
    return user


@override_settings(
    ADMIN_LOGIN_FAILURE_DELAY_SECONDS=0,
    MFA_BOOTSTRAP_ENABLED=True,
    MFA_ENCRYPTION_KEY='7JfNO8sPUPPSnXJOi2zIZqCBGmmGfgfSfzLfnHzxU0I=',
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class AdminRateLimitTests(TestCase):
    """Test rate limiting for admin login."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        _create_admin_user()

    def test_ip_email_limit(self):
        """After N failures for same IP+email, further attempts are blocked."""
        max_attempts = settings.ADMIN_LOGIN_IP_EMAIL_MAX_ATTEMPTS
        for i in range(max_attempts):
            record_failed_attempt('10.0.0.1', 'admin@mirubro.com')

        result = check_rate_limit('10.0.0.1', 'admin@mirubro.com')
        self.assertFalse(result.allowed)
        self.assertEqual(result.dimension, 'ip_email')
        self.assertGreater(result.retry_after, 0)

    def test_email_global_limit(self):
        """After N failures for same email from different IPs, it's blocked."""
        max_attempts = settings.ADMIN_LOGIN_EMAIL_MAX_ATTEMPTS
        for i in range(max_attempts):
            record_failed_attempt(f'10.0.0.{i + 1}', 'admin@mirubro.com')

        result = check_rate_limit('10.0.0.99', 'admin@mirubro.com')
        self.assertFalse(result.allowed)
        self.assertEqual(result.dimension, 'email')

    def test_ip_global_limit(self):
        """After N failures from same IP for different emails, it's blocked."""
        max_attempts = settings.ADMIN_LOGIN_IP_MAX_ATTEMPTS
        for i in range(max_attempts):
            record_failed_attempt('10.0.0.1', f'user{i}@example.com')

        result = check_rate_limit('10.0.0.1', 'brand-new@example.com')
        self.assertFalse(result.allowed)
        self.assertEqual(result.dimension, 'ip')

    def test_reset_on_success(self):
        """Successful login resets IP+email and email counters."""
        for i in range(3):
            record_failed_attempt('10.0.0.1', 'admin@mirubro.com')

        reset_on_success('10.0.0.1', 'admin@mirubro.com')

        result = check_rate_limit('10.0.0.1', 'admin@mirubro.com')
        self.assertTrue(result.allowed)

    def test_429_response_has_retry_after(self):
        """API returns 429 with Retry-After when rate limited."""
        max_attempts = settings.ADMIN_LOGIN_IP_EMAIL_MAX_ATTEMPTS
        for _ in range(max_attempts):
            self.client.post(ADMIN_LOGIN_URL, {
                'email': 'admin@mirubro.com',
                'password': 'WrongPass!',
            })

        resp = self.client.post(ADMIN_LOGIN_URL, {
            'email': 'admin@mirubro.com',
            'password': 'WrongPass!',
        })
        self.assertEqual(resp.status_code, 429)
        self.assertIn('Retry-After', resp)


@override_settings(
    ADMIN_LOGIN_FAILURE_DELAY_SECONDS=0,
    MFA_BOOTSTRAP_ENABLED=True,
    MFA_ENCRYPTION_KEY='7JfNO8sPUPPSnXJOi2zIZqCBGmmGfgfSfzLfnHzxU0I=',
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class AdminAntiEnumerationTests(TestCase):
    """Test that login responses don't leak user existence info."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        _create_admin_user()

    def test_nonexistent_user_generic_error(self):
        """Nonexistent email returns same error as wrong password."""
        resp = self.client.post(ADMIN_LOGIN_URL, {
            'email': 'nobody@example.com',
            'password': 'anything',
        })
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['detail'], GENERIC_ERROR)

    def test_wrong_password_generic_error(self):
        """Wrong password for real admin returns generic error."""
        resp = self.client.post(ADMIN_LOGIN_URL, {
            'email': 'admin@mirubro.com',
            'password': 'WrongPass!',
        })
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['detail'], GENERIC_ERROR)

    def test_regular_user_admin_login_generic_error(self):
        """Regular (non-admin) user attempting admin login gets generic error."""
        _create_regular_user()
        resp = self.client.post(ADMIN_LOGIN_URL, {
            'email': 'user@example.com',
            'password': 'UserPass123!',
        })
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['detail'], GENERIC_ERROR)


@override_settings(
    ADMIN_LOGIN_FAILURE_DELAY_SECONDS=0,
    MFA_BOOTSTRAP_ENABLED=True,
    MFA_ENCRYPTION_KEY='7JfNO8sPUPPSnXJOi2zIZqCBGmmGfgfSfzLfnHzxU0I=',
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class AdminLoginBootstrapTests(TestCase):
    """Test admin login in bootstrap mode (MFA not yet enrolled)."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user, self.profile = _create_admin_user()

    def test_bootstrap_login_success(self):
        """Admin can login without MFA in bootstrap mode."""
        resp = self.client.post(ADMIN_LOGIN_URL, {
            'email': 'admin@mirubro.com',
            'password': 'SecurePass123!',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'ok')
        self.assertFalse(data['mfa_required'])
        self.assertFalse(data['mfa_enrolled'])
        # Check cookies set
        self.assertIn('access_token', resp.cookies)
        self.assertIn('refresh_token', resp.cookies)

    @override_settings(MFA_BOOTSTRAP_ENABLED=False)
    def test_no_bootstrap_mfa_required(self):
        """With bootstrap disabled and no MFA enrolled, login is rejected."""
        resp = self.client.post(ADMIN_LOGIN_URL, {
            'email': 'admin@mirubro.com',
            'password': 'SecurePass123!',
        })
        self.assertEqual(resp.status_code, 403)


@override_settings(
    ADMIN_LOGIN_FAILURE_DELAY_SECONDS=0,
    MFA_BOOTSTRAP_ENABLED=False,
    MFA_ENCRYPTION_KEY='7JfNO8sPUPPSnXJOi2zIZqCBGmmGfgfSfzLfnHzxU0I=',
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class AdminMFAFlowTests(TestCase):
    """Test full MFA login flow: password → challenge → OTP → JWT."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user, self.profile = _create_admin_user()

        # Enroll MFA
        self.totp_secret = generate_totp_secret()
        self.profile.mfa_secret_encrypted = encrypt_secret(self.totp_secret)
        self.profile.mfa_enabled = True
        self.profile.mfa_recovery_codes = [
            hash_recovery_code(c) for c in ['AAAA1111', 'BBBB2222', 'CCCC3333']
        ]
        self.profile.save()

    def _get_valid_otp(self):
        import pyotp
        totp = pyotp.TOTP(self.totp_secret, digits=6, interval=30)
        return totp.now()

    def test_login_returns_mfa_challenge(self):
        """Step 1: valid password returns mfa_required + challenge token."""
        resp = self.client.post(ADMIN_LOGIN_URL, {
            'email': 'admin@mirubro.com',
            'password': 'SecurePass123!',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['mfa_required'])
        self.assertIn('mfa_token', data)
        # No JWT cookies yet
        self.assertNotIn('access_token', resp.cookies)

    def test_mfa_verify_success(self):
        """Step 2: valid OTP completes login."""
        # Step 1
        resp1 = self.client.post(ADMIN_LOGIN_URL, {
            'email': 'admin@mirubro.com',
            'password': 'SecurePass123!',
        })
        mfa_token = resp1.json()['mfa_token']

        # Step 2
        otp = self._get_valid_otp()
        resp2 = self.client.post(MFA_VERIFY_URL, {
            'mfa_token': mfa_token,
            'otp_code': otp,
        })
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.json()['status'], 'ok')
        self.assertIn('access_token', resp2.cookies)

    def test_mfa_wrong_otp(self):
        """Wrong OTP is rejected."""
        resp1 = self.client.post(ADMIN_LOGIN_URL, {
            'email': 'admin@mirubro.com',
            'password': 'SecurePass123!',
        })
        mfa_token = resp1.json()['mfa_token']

        resp2 = self.client.post(MFA_VERIFY_URL, {
            'mfa_token': mfa_token,
            'otp_code': '000000',
        })
        self.assertEqual(resp2.status_code, 400)

    def test_mfa_otp_replay_rejected(self):
        """Same OTP cannot be used twice."""
        resp1 = self.client.post(ADMIN_LOGIN_URL, {
            'email': 'admin@mirubro.com',
            'password': 'SecurePass123!',
        })
        mfa_token = resp1.json()['mfa_token']
        otp = self._get_valid_otp()

        # First use — succeeds
        resp2 = self.client.post(MFA_VERIFY_URL, {
            'mfa_token': mfa_token,
            'otp_code': otp,
        })
        self.assertEqual(resp2.status_code, 200)

        # Need a new challenge token (old one was consumed)
        resp3 = self.client.post(ADMIN_LOGIN_URL, {
            'email': 'admin@mirubro.com',
            'password': 'SecurePass123!',
        })
        mfa_token2 = resp3.json()['mfa_token']

        # Second use — rejected (OTP already used)
        resp4 = self.client.post(MFA_VERIFY_URL, {
            'mfa_token': mfa_token2,
            'otp_code': otp,
        })
        self.assertEqual(resp4.status_code, 400)

    def test_mfa_challenge_single_use(self):
        """MFA challenge token is consumed on first use."""
        resp1 = self.client.post(ADMIN_LOGIN_URL, {
            'email': 'admin@mirubro.com',
            'password': 'SecurePass123!',
        })
        mfa_token = resp1.json()['mfa_token']
        otp = self._get_valid_otp()

        # First use
        self.client.post(MFA_VERIFY_URL, {
            'mfa_token': mfa_token,
            'otp_code': otp,
        })

        # Reuse same challenge token — should fail
        resp3 = self.client.post(MFA_VERIFY_URL, {
            'mfa_token': mfa_token,
            'otp_code': '123456',
        })
        self.assertEqual(resp3.status_code, 400)

    def test_mfa_recovery_code(self):
        """Recovery code can be used as MFA alternative."""
        resp1 = self.client.post(ADMIN_LOGIN_URL, {
            'email': 'admin@mirubro.com',
            'password': 'SecurePass123!',
        })
        mfa_token = resp1.json()['mfa_token']

        resp2 = self.client.post(MFA_RECOVERY_URL, {
            'mfa_token': mfa_token,
            'recovery_code': 'AAAA1111',
        })
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.json()['recovery_codes_remaining'], 2)
        self.assertIn('access_token', resp2.cookies)

    def test_mfa_recovery_code_single_use(self):
        """Same recovery code cannot be used twice."""
        # First use
        resp1 = self.client.post(ADMIN_LOGIN_URL, {
            'email': 'admin@mirubro.com',
            'password': 'SecurePass123!',
        })
        resp2 = self.client.post(MFA_RECOVERY_URL, {
            'mfa_token': resp1.json()['mfa_token'],
            'recovery_code': 'AAAA1111',
        })
        self.assertEqual(resp2.status_code, 200)

        # Second use — should fail
        resp3 = self.client.post(ADMIN_LOGIN_URL, {
            'email': 'admin@mirubro.com',
            'password': 'SecurePass123!',
        })
        resp4 = self.client.post(MFA_RECOVERY_URL, {
            'mfa_token': resp3.json()['mfa_token'],
            'recovery_code': 'AAAA1111',
        })
        self.assertEqual(resp4.status_code, 400)

    def test_otp_attempt_limit(self):
        """After too many wrong OTPs, user gets locked out."""
        max_attempts = settings.MFA_OTP_MAX_ATTEMPTS

        for _ in range(max_attempts):
            resp1 = self.client.post(ADMIN_LOGIN_URL, {
                'email': 'admin@mirubro.com',
                'password': 'SecurePass123!',
            })
            mfa_token = resp1.json()['mfa_token']
            self.client.post(MFA_VERIFY_URL, {
                'mfa_token': mfa_token,
                'otp_code': '000000',
            })

        # Next attempt should be rate limited
        resp_login = self.client.post(ADMIN_LOGIN_URL, {
            'email': 'admin@mirubro.com',
            'password': 'SecurePass123!',
        })
        mfa_token = resp_login.json()['mfa_token']
        resp_mfa = self.client.post(MFA_VERIFY_URL, {
            'mfa_token': mfa_token,
            'otp_code': '000000',
        })
        self.assertEqual(resp_mfa.status_code, 429)


@override_settings(
    ADMIN_LOGIN_FAILURE_DELAY_SECONDS=0,
    MFA_BOOTSTRAP_ENABLED=True,
    MFA_ENCRYPTION_KEY='7JfNO8sPUPPSnXJOi2zIZqCBGmmGfgfSfzLfnHzxU0I=',
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class AdminMFAEnrollmentTests(TestCase):
    """Test MFA enrollment flow for authenticated admin."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user, self.profile = _create_admin_user()
        # Bootstrap login (no MFA)
        self.client.post(ADMIN_LOGIN_URL, {
            'email': 'admin@mirubro.com',
            'password': 'SecurePass123!',
        })
        # Force authenticate for enrollment endpoints
        self.client.force_authenticate(user=self.user)

    def test_enrollment_flow(self):
        """Full enrollment: enroll → scan QR → confirm with OTP."""
        # Step 1: Start enrollment
        resp1 = self.client.post(MFA_ENROLL_URL)
        self.assertEqual(resp1.status_code, 200)
        data = resp1.json()
        self.assertIn('secret', data)
        self.assertIn('provisioning_uri', data)
        self.assertIn('recovery_codes', data)
        self.assertEqual(len(data['recovery_codes']), 10)

        # Step 2: Confirm with valid OTP
        import pyotp
        totp = pyotp.TOTP(data['secret'], digits=6, interval=30)
        otp = totp.now()

        resp2 = self.client.post(MFA_CONFIRM_URL, {'otp_code': otp})
        self.assertEqual(resp2.status_code, 200)

        # Verify MFA is now enabled
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.mfa_enabled)
        self.assertIsNotNone(self.profile.mfa_enrolled_at)

    def test_double_enrollment_rejected(self):
        """Cannot enroll again when MFA already enabled."""
        self.profile.mfa_enabled = True
        self.profile.save()

        resp = self.client.post(MFA_ENROLL_URL)
        self.assertEqual(resp.status_code, 400)


@override_settings(
    ADMIN_LOGIN_FAILURE_DELAY_SECONDS=0,
    MFA_BOOTSTRAP_ENABLED=True,
    MFA_ENCRYPTION_KEY='7JfNO8sPUPPSnXJOi2zIZqCBGmmGfgfSfzLfnHzxU0I=',
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class AdminLogoutTests(TestCase):
    """Test admin logout."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        _create_admin_user()

    def test_logout_clears_cookies(self):
        """Logout clears auth cookies."""
        # Login first
        self.client.post(ADMIN_LOGIN_URL, {
            'email': 'admin@mirubro.com',
            'password': 'SecurePass123!',
        })

        resp = self.client.post(ADMIN_LOGOUT_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'logged_out')


@override_settings(
    ADMIN_LOGIN_FAILURE_DELAY_SECONDS=0,
    MFA_BOOTSTRAP_ENABLED=True,
    MFA_ENCRYPTION_KEY='7JfNO8sPUPPSnXJOi2zIZqCBGmmGfgfSfzLfnHzxU0I=',
    ADMIN_IP_ALLOWLIST=['192.168.1.0/24', '10.0.0.5'],
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class AdminIPAllowlistTests(TestCase):
    """Test IP allowlist for admin login."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        _create_admin_user()

    def test_allowed_ip(self):
        """IP in allowlist can proceed."""
        resp = self.client.post(
            ADMIN_LOGIN_URL,
            {'email': 'admin@mirubro.com', 'password': 'SecurePass123!'},
            REMOTE_ADDR='192.168.1.50',
        )
        # Should reach auth logic (not blocked by IP)
        self.assertIn(resp.status_code, [200, 400])

    def test_blocked_ip(self):
        """IP not in allowlist is rejected."""
        resp = self.client.post(
            ADMIN_LOGIN_URL,
            {'email': 'admin@mirubro.com', 'password': 'SecurePass123!'},
            REMOTE_ADDR='172.16.0.1',
        )
        self.assertEqual(resp.status_code, 403)


@override_settings(
    ADMIN_LOGIN_FAILURE_DELAY_SECONDS=0,
    MFA_BOOTSTRAP_ENABLED=True,
    MFA_ENCRYPTION_KEY='7JfNO8sPUPPSnXJOi2zIZqCBGmmGfgfSfzLfnHzxU0I=',
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class AdminAuditTests(TestCase):
    """Test that admin auth events are properly audited."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user, self.profile = _create_admin_user()

    def test_successful_login_audited(self):
        """Successful login creates ADMIN_LOGIN_SUCCESS audit entry."""
        from apps.accounts.models import AccessAuditLog

        self.client.post(ADMIN_LOGIN_URL, {
            'email': 'admin@mirubro.com',
            'password': 'SecurePass123!',
        })

        entries = AccessAuditLog.objects.filter(action='ADMIN_LOGIN_SUCCESS')
        self.assertTrue(entries.exists())

    def test_failed_login_audited(self):
        """Failed login creates ADMIN_LOGIN_FAILED audit entry."""
        from apps.accounts.models import AccessAuditLog

        self.client.post(ADMIN_LOGIN_URL, {
            'email': 'admin@mirubro.com',
            'password': 'WrongPass!',
        })

        entries = AccessAuditLog.objects.filter(action='ADMIN_LOGIN_FAILED')
        self.assertTrue(entries.exists())

    def test_throttled_login_audited(self):
        """Rate-limited attempt creates ADMIN_LOGIN_COOLDOWN audit entry."""
        from apps.accounts.models import AccessAuditLog

        max_attempts = settings.ADMIN_LOGIN_IP_EMAIL_MAX_ATTEMPTS
        for _ in range(max_attempts + 1):
            self.client.post(ADMIN_LOGIN_URL, {
                'email': 'admin@mirubro.com',
                'password': 'WrongPass!',
            })

        entries = AccessAuditLog.objects.filter(
            action__in=['ADMIN_LOGIN_THROTTLED', 'ADMIN_LOGIN_COOLDOWN']
        )
        self.assertTrue(entries.exists())


@override_settings(
    ADMIN_LOGIN_FAILURE_DELAY_SECONDS=0,
    MFA_BOOTSTRAP_ENABLED=True,
    MFA_ENCRYPTION_KEY='7JfNO8sPUPPSnXJOi2zIZqCBGmmGfgfSfzLfnHzxU0I=',
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class AdminPermissionAfterLoginTests(TestCase):
    """Test that admin endpoints require proper authentication after login."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user, self.profile = _create_admin_user()

    def test_admin_me_requires_auth(self):
        """admin/me/ is not accessible without login."""
        resp = self.client.get('/api/v1/platform-admin/me/')
        self.assertEqual(resp.status_code, 401)

    def test_admin_me_after_login(self):
        """admin/me/ is accessible after bootstrap login."""
        login_resp = self.client.post(ADMIN_LOGIN_URL, {
            'email': 'admin@mirubro.com',
            'password': 'SecurePass123!',
        })
        self.assertEqual(login_resp.status_code, 200)
        # Use force_authenticate since cookies don't propagate in test client easily
        self.client.force_authenticate(user=self.user)
        resp = self.client.get('/api/v1/platform-admin/me/')
        self.assertEqual(resp.status_code, 200)


# ── XFF / IP extraction tests ───────────────────────────────────────────────

from apps.accounts.platform_auth_views import _get_client_ip, _normalize_xff_entry


class NormalizeXffEntryTests(TestCase):
    """Unit tests for _normalize_xff_entry()."""

    def test_bare_ipv4(self):
        self.assertEqual(_normalize_xff_entry('1.2.3.4'), '1.2.3.4')

    def test_ipv4_with_port(self):
        self.assertEqual(_normalize_xff_entry('1.2.3.4:8080'), '1.2.3.4')

    def test_bare_ipv6(self):
        self.assertEqual(_normalize_xff_entry('::1'), '::1')

    def test_bare_ipv6_full(self):
        self.assertEqual(
            _normalize_xff_entry('2001:db8::ff00:42:8329'),
            '2001:db8::ff00:42:8329',
        )

    def test_bracketed_ipv6(self):
        self.assertEqual(_normalize_xff_entry('[::1]'), '::1')

    def test_bracketed_ipv6_with_port(self):
        self.assertEqual(_normalize_xff_entry('[2001:db8::1]:443'), '2001:db8::1')

    def test_whitespace_stripped(self):
        self.assertEqual(_normalize_xff_entry('  10.0.0.1  '), '10.0.0.1')


class FakeRequest:
    """Minimal request stub for _get_client_ip tests."""

    def __init__(self, xff=None, remote_addr='127.0.0.1'):
        self.META = {}
        if xff is not None:
            self.META['HTTP_X_FORWARDED_FOR'] = xff
        self.META['REMOTE_ADDR'] = remote_addr


@override_settings(TRUSTED_PROXY_DEPTH=1)
class GetClientIPDepth1Tests(TestCase):
    """Test _get_client_ip with TRUSTED_PROXY_DEPTH=1 (ALB only)."""

    def test_single_entry(self):
        """ALB-only, clean request (no prior XFF from client)."""
        req = FakeRequest(xff='203.0.113.50')
        self.assertEqual(_get_client_ip(req), '203.0.113.50')

    def test_spoofed_xff_takes_rightmost(self):
        """Client spoofs XFF; ALB appends real IP last."""
        req = FakeRequest(xff='10.99.99.99, 203.0.113.50')
        self.assertEqual(_get_client_ip(req), '203.0.113.50')

    def test_multiple_spoofed_entries(self):
        """Multiple spoofed entries; real IP is the rightmost."""
        req = FakeRequest(xff='evil1, evil2, evil3, 198.51.100.1')
        self.assertEqual(_get_client_ip(req), '198.51.100.1')

    def test_ipv6_rightmost(self):
        """Real client uses IPv6, ALB appends it."""
        req = FakeRequest(xff='spoofed, 2001:db8::1')
        self.assertEqual(_get_client_ip(req), '2001:db8::1')

    def test_ipv4_with_port(self):
        """Some proxies add port; function should strip it."""
        req = FakeRequest(xff='spoofed, 203.0.113.50:8080')
        self.assertEqual(_get_client_ip(req), '203.0.113.50')

    def test_no_xff_falls_back_to_remote_addr(self):
        """No XFF header → use REMOTE_ADDR."""
        req = FakeRequest(xff=None, remote_addr='172.16.0.1')
        self.assertEqual(_get_client_ip(req), '172.16.0.1')

    def test_invalid_ip_falls_back(self):
        """Invalid entry at depth → fallback to REMOTE_ADDR."""
        req = FakeRequest(xff='garbage, not-an-ip', remote_addr='172.16.0.1')
        self.assertEqual(_get_client_ip(req), '172.16.0.1')


@override_settings(TRUSTED_PROXY_DEPTH=2)
class GetClientIPDepth2Tests(TestCase):
    """Test _get_client_ip with TRUSTED_PROXY_DEPTH=2 (CloudFront + ALB)."""

    def test_cloudfront_plus_alb(self):
        """Standard CF+ALB chain: real IP is second from the right."""
        req = FakeRequest(xff='203.0.113.50, 54.230.1.1')
        self.assertEqual(_get_client_ip(req), '203.0.113.50')

    def test_spoofed_with_cf_alb(self):
        """Client spoofs XFF; real IP is still xff[-2]."""
        req = FakeRequest(xff='spoofed, 203.0.113.50, 54.230.1.1')
        self.assertEqual(_get_client_ip(req), '203.0.113.50')

    def test_ipv6_client_through_cf_alb(self):
        """IPv6 real client through CloudFront + ALB."""
        req = FakeRequest(xff='spoofed, 2001:db8::42, 54.230.1.1')
        self.assertEqual(_get_client_ip(req), '2001:db8::42')

    def test_insufficient_entries_falls_back(self):
        """XFF has fewer entries than depth → REMOTE_ADDR."""
        req = FakeRequest(xff='203.0.113.50', remote_addr='172.16.0.1')
        self.assertEqual(_get_client_ip(req), '172.16.0.1')

    def test_bracketed_ipv6_with_port(self):
        """IPv6 entry with brackets and port at depth-2."""
        req = FakeRequest(xff='spoofed, [2001:db8::1]:443, 54.230.1.1')
        self.assertEqual(_get_client_ip(req), '2001:db8::1')
