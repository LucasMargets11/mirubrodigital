"""
Tests for PR-2: Google OAuth end-to-end (token verification, user creation, linking, login, cookies).
"""
from unittest.mock import patch, MagicMock
from dataclasses import dataclass

from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework import status as http_status
from rest_framework.test import APIClient

from apps.accounts.models import AccountProfile, Membership
from apps.accounts.google_oauth_service import GoogleOAuthService, GoogleTokenPayload, GoogleVerifyResult
from apps.business.models import Business, Subscription

User = get_user_model()

GOOGLE_AUTH_URL = '/api/v1/auth/google/'

# Build override dict once — raise throttle ceiling so tests don't get rate-limited.
_THROTTLE_RATES = {**django_settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {}), 'auth_google': '1000/minute'}
_DRF_OVERRIDE = {**django_settings.REST_FRAMEWORK, 'DEFAULT_THROTTLE_RATES': _THROTTLE_RATES}

# Reusable fake Google payloads
FAKE_SUB = '110248495921238986420'
FAKE_EMAIL = 'googleuser@gmail.com'

def _make_google_payload(**overrides):
    defaults = dict(
        sub=FAKE_SUB,
        email=FAKE_EMAIL,
        email_verified=True,
        name='Test User',
        given_name='Test',
        family_name='User',
        picture='',
    )
    defaults.update(overrides)
    return GoogleTokenPayload(**defaults)


def _make_success_result(**overrides):
    return GoogleVerifyResult(valid=True, payload=_make_google_payload(**overrides))


def _create_existing_user(email='existing@test.com', google_sub=None, email_verified=False, is_active=True):
    """Helper: create a user with business + membership."""
    user = User.objects.create_user(username=email, email=email, password='SecurePass123!')
    user.is_active = is_active
    user.save(update_fields=['is_active'])
    profile = user.account_profile
    profile.email_verified = email_verified
    if google_sub:
        profile.google_sub = google_sub
    profile.save(update_fields=['email_verified', 'google_sub'])
    business = Business.objects.create(name='Test HQ', default_service='gestion', status='active')
    Subscription.objects.create(business=business, plan='starter', status='active', max_seats=5)
    Membership.objects.create(user=user, business=business, role='owner')
    return user, profile


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests: GoogleOAuthService
# ─────────────────────────────────────────────────────────────────────────────

class GoogleOAuthServiceTests(TestCase):
    """Unit tests for token verification service."""

    @override_settings(GOOGLE_OAUTH_CLIENT_ID='')
    def test_missing_client_id_returns_error(self):
        result = GoogleOAuthService.verify_token('some-token')
        self.assertFalse(result.valid)
        self.assertEqual(result.error, 'server_config')

    @override_settings(GOOGLE_OAUTH_CLIENT_ID='test-client-id.apps.googleusercontent.com')
    @patch('apps.accounts.google_oauth_service.id_token.verify_oauth2_token')
    def test_invalid_token_returns_error(self, mock_verify):
        mock_verify.side_effect = ValueError('Token is not valid')
        result = GoogleOAuthService.verify_token('bad-token')
        self.assertFalse(result.valid)
        self.assertEqual(result.error, 'invalid_token')

    @override_settings(GOOGLE_OAUTH_CLIENT_ID='test-client-id.apps.googleusercontent.com')
    @patch('apps.accounts.google_oauth_service.id_token.verify_oauth2_token')
    def test_valid_token_returns_payload(self, mock_verify):
        mock_verify.return_value = {
            'sub': FAKE_SUB,
            'email': FAKE_EMAIL,
            'email_verified': True,
            'name': 'Test User',
            'given_name': 'Test',
            'family_name': 'User',
            'picture': 'https://photo.url/pic.jpg',
        }
        result = GoogleOAuthService.verify_token('good-token')
        self.assertTrue(result.valid)
        self.assertEqual(result.payload.sub, FAKE_SUB)
        self.assertEqual(result.payload.email, FAKE_EMAIL)
        self.assertTrue(result.payload.email_verified)

    @override_settings(GOOGLE_OAUTH_CLIENT_ID='test-client-id.apps.googleusercontent.com')
    @patch('apps.accounts.google_oauth_service.id_token.verify_oauth2_token')
    def test_missing_sub_returns_error(self, mock_verify):
        mock_verify.return_value = {'email': FAKE_EMAIL, 'email_verified': True}
        result = GoogleOAuthService.verify_token('token-no-sub')
        self.assertFalse(result.valid)
        self.assertEqual(result.error, 'missing_claims')


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests: GoogleAuthView — new user
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(GOOGLE_OAUTH_CLIENT_ID='test-client-id.apps.googleusercontent.com', REST_FRAMEWORK=_DRF_OVERRIDE)
class GoogleAuthNewUserTests(TestCase):
    """POST /api/v1/auth/google/ — creates a new user when no match found."""

    def setUp(self):
        self.client = APIClient()

    @patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token')
    def test_creates_new_user(self, mock_verify):
        mock_verify.return_value = _make_success_result()
        resp = self.client.post(GOOGLE_AUTH_URL, {'credential': 'valid-token'})
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], 'ok')
        self.assertTrue(resp.data['is_new_user'])

        user = User.objects.get(email__iexact=FAKE_EMAIL)
        self.assertFalse(user.has_usable_password())
        profile = user.account_profile
        self.assertEqual(profile.auth_provider, 'google')
        self.assertEqual(profile.google_sub, FAKE_SUB)
        self.assertTrue(profile.email_verified)

    @patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token')
    def test_new_user_gets_cookies(self, mock_verify):
        mock_verify.return_value = _make_success_result()
        resp = self.client.post(GOOGLE_AUTH_URL, {'credential': 'valid-token'})
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertIn('access_token', resp.cookies)
        self.assertIn('refresh_token', resp.cookies)

    @patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token')
    def test_new_user_gets_business_and_membership(self, mock_verify):
        mock_verify.return_value = _make_success_result()
        self.client.post(GOOGLE_AUTH_URL, {'credential': 'valid-token'})
        user = User.objects.get(email__iexact=FAKE_EMAIL)
        membership = Membership.objects.get(user=user)
        self.assertEqual(membership.role, 'owner')
        self.assertEqual(membership.business.status, 'onboarding')

    @patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token')
    def test_new_user_onboarding_flag(self, mock_verify):
        mock_verify.return_value = _make_success_result()
        resp = self.client.post(GOOGLE_AUTH_URL, {'credential': 'valid-token'})
        self.assertTrue(resp.data['onboarding'])

    @patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token')
    def test_new_user_first_name_last_name(self, mock_verify):
        mock_verify.return_value = _make_success_result(given_name='Carlos', family_name='García')
        self.client.post(GOOGLE_AUTH_URL, {'credential': 'valid-token'})
        user = User.objects.get(email__iexact=FAKE_EMAIL)
        self.assertEqual(user.first_name, 'Carlos')
        self.assertEqual(user.last_name, 'García')


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests: GoogleAuthView — existing user by google_sub
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(GOOGLE_OAUTH_CLIENT_ID='test-client-id.apps.googleusercontent.com', REST_FRAMEWORK=_DRF_OVERRIDE)
class GoogleAuthExistingBySubTests(TestCase):
    """POST /api/v1/auth/google/ — login existing user found by google_sub."""

    def setUp(self):
        self.client = APIClient()
        self.user, self.profile = _create_existing_user(
            email=FAKE_EMAIL, google_sub=FAKE_SUB, email_verified=True,
        )

    @patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token')
    def test_login_existing_user_by_sub(self, mock_verify):
        mock_verify.return_value = _make_success_result()
        resp = self.client.post(GOOGLE_AUTH_URL, {'credential': 'valid-token'})
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertFalse(resp.data['is_new_user'])
        self.assertIn('access_token', resp.cookies)


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests: GoogleAuthView — existing user by email (linking)
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(GOOGLE_OAUTH_CLIENT_ID='test-client-id.apps.googleusercontent.com', REST_FRAMEWORK=_DRF_OVERRIDE)
class GoogleAuthLinkingTests(TestCase):
    """POST /api/v1/auth/google/ — link google_sub to existing user found by email."""

    def setUp(self):
        self.client = APIClient()
        self.user, self.profile = _create_existing_user(
            email=FAKE_EMAIL, google_sub=None, email_verified=False,
        )

    @patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token')
    def test_links_google_sub_to_existing_user(self, mock_verify):
        mock_verify.return_value = _make_success_result()
        resp = self.client.post(GOOGLE_AUTH_URL, {'credential': 'valid-token'})
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertFalse(resp.data['is_new_user'])

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.google_sub, FAKE_SUB)

    @patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token')
    def test_linking_marks_email_verified(self, mock_verify):
        """User had email_verified=False; linking via Google marks it True."""
        self.assertFalse(self.profile.email_verified)
        mock_verify.return_value = _make_success_result()
        self.client.post(GOOGLE_AUTH_URL, {'credential': 'valid-token'})
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.email_verified)


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests: GoogleAuthView — error cases
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(GOOGLE_OAUTH_CLIENT_ID='test-client-id.apps.googleusercontent.com', REST_FRAMEWORK=_DRF_OVERRIDE)
class GoogleAuthErrorTests(TestCase):
    """Error scenarios for POST /api/v1/auth/google/."""

    def setUp(self):
        self.client = APIClient()

    def test_missing_credential_returns_400(self):
        resp = self.client.post(GOOGLE_AUTH_URL, {})
        self.assertEqual(resp.status_code, http_status.HTTP_400_BAD_REQUEST)

    @patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token')
    def test_invalid_token_returns_400(self, mock_verify):
        mock_verify.return_value = GoogleVerifyResult(valid=False, error='invalid_token')
        resp = self.client.post(GOOGLE_AUTH_URL, {'credential': 'bad-token'})
        self.assertEqual(resp.status_code, http_status.HTTP_400_BAD_REQUEST)

    @patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token')
    def test_email_not_verified_returns_400(self, mock_verify):
        mock_verify.return_value = _make_success_result(email_verified=False)
        resp = self.client.post(GOOGLE_AUTH_URL, {'credential': 'token-unverified'})
        self.assertEqual(resp.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertIn('verificado', resp.data['detail'].lower())

    @patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token')
    def test_inactive_user_returns_403(self, mock_verify):
        _create_existing_user(email=FAKE_EMAIL, google_sub=FAKE_SUB, is_active=False)
        mock_verify.return_value = _make_success_result()
        resp = self.client.post(GOOGLE_AUTH_URL, {'credential': 'valid-token'})
        self.assertEqual(resp.status_code, http_status.HTTP_403_FORBIDDEN)


# ─────────────────────────────────────────────────────────────────────────────
# Throttle config
# ─────────────────────────────────────────────────────────────────────────────

class GoogleAuthThrottleConfigTests(TestCase):
    def test_google_scope_defined(self):
        from rest_framework.settings import api_settings
        rates = api_settings.DEFAULT_THROTTLE_RATES or {}
        self.assertIn('auth_google', rates)
