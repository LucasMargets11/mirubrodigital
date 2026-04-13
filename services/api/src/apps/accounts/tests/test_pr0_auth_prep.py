"""
Tests for PR-0: auth preparation (model fields, session payload, throttles, resend-verification async).
"""
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework import status as http_status
from rest_framework.test import APIClient

from apps.accounts.models import AccountProfile, Membership
from apps.business.models import Business, Subscription

User = get_user_model()

RESEND_URL = '/api/v1/auth/resend-verification/'
ME_URL = '/api/v1/auth/me/'


def _setup_user_with_business(
    email='pr0@test.com',
    password='SecurePass123!',
    email_verified=False,
    auth_provider='email',
):
    """Helper: create User + AccountProfile + Business + Membership + Subscription."""
    user = User.objects.create_user(username=email, email=email, password=password)
    profile = user.account_profile
    profile.email_verified = email_verified
    profile.auth_provider = auth_provider
    profile.save(update_fields=['email_verified', 'auth_provider'])
    business = Business.objects.create(name='Test HQ', default_service='gestion', status='active')
    Subscription.objects.create(business=business, plan='starter', status='active', max_seats=5)
    Membership.objects.create(user=user, business=business, role='owner')
    return user, profile, business


# ─────────────────────────────────────────────────────────────────────────────
# Migration / Model field tests
# ─────────────────────────────────────────────────────────────────────────────

class AccountProfileNewFieldsTests(TestCase):
    """Verify auth_provider and google_sub fields on AccountProfile."""

    def test_default_auth_provider_is_email(self):
        user = User.objects.create_user(username='field@test.com', email='field@test.com', password='Pass1234')
        profile = user.account_profile
        self.assertEqual(profile.auth_provider, 'email')

    def test_google_sub_defaults_to_none(self):
        user = User.objects.create_user(username='field2@test.com', email='field2@test.com', password='Pass1234')
        profile = user.account_profile
        self.assertIsNone(profile.google_sub)

    def test_google_sub_unique_constraint(self):
        u1 = User.objects.create_user(username='g1@test.com', email='g1@test.com', password='Pass1234')
        u1.account_profile.google_sub = 'google-sub-123'
        u1.account_profile.save(update_fields=['google_sub'])

        u2 = User.objects.create_user(username='g2@test.com', email='g2@test.com', password='Pass1234')
        u2.account_profile.google_sub = 'google-sub-123'
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            u2.account_profile.save(update_fields=['google_sub'])

    def test_auth_provider_choices(self):
        user = User.objects.create_user(username='ch@test.com', email='ch@test.com', password='Pass1234')
        profile = user.account_profile
        for value in ('email', 'otp', 'google'):
            profile.auth_provider = value
            profile.save(update_fields=['auth_provider'])
            profile.refresh_from_db()
            self.assertEqual(profile.auth_provider, value)


# ─────────────────────────────────────────────────────────────────────────────
# Session payload tests
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(
    AUTHENTICATION_BACKENDS=['apps.accounts.auth_backends.UsernameOrEmailBackend'],
)
class SessionPayloadNewFieldsTests(TestCase):
    """GET /auth/me/ must include auth_provider, has_google_linked, has_password."""

    def setUp(self):
        self.user, self.profile, _ = _setup_user_with_business(email_verified=True)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_includes_auth_provider(self):
        resp = self.client.get(ME_URL)
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertEqual(resp.data['user']['auth_provider'], 'email')

    def test_includes_has_google_linked_false(self):
        resp = self.client.get(ME_URL)
        self.assertFalse(resp.data['user']['has_google_linked'])

    def test_includes_has_google_linked_true(self):
        self.profile.google_sub = 'google-sub-abc'
        self.profile.save(update_fields=['google_sub'])
        resp = self.client.get(ME_URL)
        self.assertTrue(resp.data['user']['has_google_linked'])

    def test_includes_has_password_true(self):
        resp = self.client.get(ME_URL)
        self.assertTrue(resp.data['user']['has_password'])

    def test_includes_has_password_false_for_unusable(self):
        self.user.set_unusable_password()
        self.user.save()
        resp = self.client.get(ME_URL)
        self.assertFalse(resp.data['user']['has_password'])

    def test_defaults_when_profile_missing(self):
        """When AccountProfile doesn't exist, new fields use safe defaults."""
        self.profile.delete()
        resp = self.client.get(ME_URL)
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertEqual(resp.data['user']['auth_provider'], 'email')
        self.assertFalse(resp.data['user']['has_google_linked'])
        # has_password should still work — it reads from User, not profile
        self.assertTrue(resp.data['user']['has_password'])


# ─────────────────────────────────────────────────────────────────────────────
# Throttle rate configuration tests
# ─────────────────────────────────────────────────────────────────────────────

class ThrottleRateConfigTests(TestCase):
    """Verify all auth throttle scopes are defined in DEFAULT_THROTTLE_RATES."""

    def test_all_auth_scopes_defined(self):
        rates = settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {})
        expected_scopes = [
            'auth_login',
            'auth_register',
            'auth_forgot_password',
            'auth_reset_password',
            'auth_verify_email',
            'auth_refresh',
        ]
        for scope in expected_scopes:
            self.assertIn(scope, rates, f"Throttle scope '{scope}' missing from DEFAULT_THROTTLE_RATES")
            # Verify rate is parseable (e.g. '20/minute')
            rate = rates[scope]
            self.assertRegex(rate, r'^\d+/(second|minute|hour|day)$', f"Invalid rate format for '{scope}': {rate}")


# ─────────────────────────────────────────────────────────────────────────────
# ResendVerificationView async tests
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(
    AUTHENTICATION_BACKENDS=['apps.accounts.auth_backends.UsernameOrEmailBackend'],
)
class ResendVerificationAsyncTests(TestCase):
    """ResendVerificationView must dispatch email via Celery, not synchronously."""

    def setUp(self):
        self.user, self.profile, _ = _setup_user_with_business(email_verified=False)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch('apps.accounts.views.send_verification_email_task')
    def test_resend_dispatches_celery_task(self, mock_task):
        resp = self.client.post(RESEND_URL)
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], 'queued')
        mock_task.delay.assert_called_once()
        args = mock_task.delay.call_args[0]
        self.assertEqual(args[0], self.user.id)
        # Second arg is the token string (non-empty)
        self.assertTrue(len(args[1]) > 10)

    @patch('apps.accounts.views.send_verification_email_task')
    def test_resend_does_not_call_email_service_directly(self, mock_task):
        """Ensure EmailService.send_verification_email is NOT called in the view."""
        with patch('apps.accounts.views.EmailService.send_verification_email') as mock_sync:
            resp = self.client.post(RESEND_URL)
            self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
            mock_sync.assert_not_called()

    def test_resend_rejects_already_verified(self):
        self.profile.email_verified = True
        self.profile.save(update_fields=['email_verified'])
        resp = self.client.post(RESEND_URL)
        self.assertEqual(resp.status_code, http_status.HTTP_400_BAD_REQUEST)

    def test_resend_requires_auth(self):
        anon_client = APIClient()
        resp = anon_client.post(RESEND_URL)
        self.assertIn(resp.status_code, (401, 403))
