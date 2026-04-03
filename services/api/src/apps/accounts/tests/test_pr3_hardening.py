"""
PR-3 Hardening / Cleanup tests.

Covers:
  - ForgotPasswordView logs PASSWORD_RESET_REQUESTED (not PASSWORD_RESET_CONFIRMED)
  - VerifyEmailView still works after dead-code removal
  - disable_account sets Membership.status = 'suspended'
  - re-enable via disable_account sets Membership.status = 'active'
  - PASSWORD_RESET_REQUESTED is a valid audit action choice
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework import status as http_status

from apps.accounts.models import Membership, AccountProfile, AccessAuditLog
from apps.business.models import Business, Subscription

User = get_user_model()


# ── ForgotPasswordView audit action ──────────────────────────────────────────

@override_settings(
    AUTHENTICATION_BACKENDS=['apps.accounts.auth_backends.UsernameOrEmailBackend'],
)
class ForgotPasswordAuditActionTests(TestCase):
    """ForgotPasswordView must log PASSWORD_RESET_REQUESTED."""

    def setUp(self):
        self.business = Business.objects.create(
            name='Test HQ', default_service='gestion', status='active',
        )
        self.user = User.objects.create_user(
            username='forgot_audit', password='Pass1234', email='forgot_audit@test.com',
        )
        Membership.objects.create(
            user=self.user, business=self.business, role='owner',
        )
        profile = AccountProfile.objects.get(user=self.user)
        profile.account_mode = 'personal'
        profile.save(update_fields=['account_mode'])

        self.client = APIClient()
        self.url = '/api/v1/auth/forgot-password/'

    @patch('apps.accounts.views.EmailService')
    def test_forgot_password_logs_password_reset_requested(self, _mock_email):
        """The audit entry uses PASSWORD_RESET_REQUESTED, not CONFIRMED."""
        resp = self.client.post(self.url, {'email': 'forgot_audit@test.com'}, format='json')
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)

        log = AccessAuditLog.objects.filter(
            target_user=self.user,
            action='PASSWORD_RESET_REQUESTED',
        ).first()
        self.assertIsNotNone(log, "Expected PASSWORD_RESET_REQUESTED audit log entry")
        self.assertEqual(log.details.get('source'), 'self_service')

    @patch('apps.accounts.views.EmailService')
    def test_no_password_reset_confirmed_on_request(self, _mock_email):
        """PASSWORD_RESET_CONFIRMED must NOT appear on the request step."""
        self.client.post(self.url, {'email': 'forgot_audit@test.com'}, format='json')

        count = AccessAuditLog.objects.filter(
            target_user=self.user,
            action='PASSWORD_RESET_CONFIRMED',
        ).count()
        self.assertEqual(count, 0)


# ── VerifyEmailView after dead-code removal ──────────────────────────────────

@override_settings(
    AUTHENTICATION_BACKENDS=['apps.accounts.auth_backends.UsernameOrEmailBackend'],
)
class VerifyEmailAfterCleanupTests(TestCase):
    """VerifyEmailView still works correctly after dead-code removal."""

    def setUp(self):
        self.business = Business.objects.create(
            name='Test HQ', default_service='gestion', status='active',
        )
        self.user = User.objects.create_user(
            username='verify_user', password='Pass1234', email='verify@test.com',
        )
        Membership.objects.create(
            user=self.user, business=self.business, role='owner',
        )
        self.profile = AccountProfile.objects.get(user=self.user)
        self.client = APIClient()
        self.url = '/api/v1/auth/verify-email/'

    def test_valid_token_verifies_email(self):
        """A valid verification token marks the email as verified."""
        token = self.profile.generate_verification_token()
        resp = self.client.post(self.url, {'token': token}, format='json')
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], 'verified')

        self.profile.refresh_from_db()
        self.assertTrue(self.profile.email_verified)

    def test_invalid_token_returns_400(self):
        """An invalid token returns 400 without leaking info."""
        resp = self.client.post(self.url, {'token': 'bogus-token-value'}, format='json')
        self.assertEqual(resp.status_code, http_status.HTTP_400_BAD_REQUEST)

    def test_used_token_cannot_be_reused(self):
        """After successful verification the same token is rejected."""
        token = self.profile.generate_verification_token()
        self.client.post(self.url, {'token': token}, format='json')
        resp = self.client.post(self.url, {'token': token}, format='json')
        self.assertEqual(resp.status_code, http_status.HTTP_400_BAD_REQUEST)


# ── disable_account syncs Membership.status ──────────────────────────────────

@override_settings(
    AUTHENTICATION_BACKENDS=['apps.accounts.auth_backends.UsernameOrEmailBackend'],
)
class DisableAccountMembershipSyncTests(TestCase):
    """disable_account must sync Membership.status alongside is_active."""

    def setUp(self):
        self.business = Business.objects.create(
            name='Test HQ', default_service='gestion', status='active',
        )
        Subscription.objects.create(
            business=self.business, plan='pro', status='active', max_seats=10,
        )
        self.owner = User.objects.create_user(
            username='owner@test.com', email='owner@test.com', password='OwnerPass123',
        )
        Membership.objects.create(
            user=self.owner, business=self.business, role='owner',
        )
        self.staff = User.objects.create_user(
            username='staff@test.com', email='staff@test.com', password='StaffPass123',
        )
        self.staff_membership = Membership.objects.create(
            user=self.staff, business=self.business, role='staff',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)
        self.disable_url = f'/api/v1/owner/access/accounts/{self.staff.id}/disable/'

    def test_disable_sets_membership_suspended(self):
        """Disabling a user sets Membership.status = 'suspended'."""
        resp = self.client.post(self.disable_url)
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertFalse(resp.data['is_active'])

        self.staff_membership.refresh_from_db()
        self.assertEqual(self.staff_membership.status, 'suspended')

    def test_reenable_sets_membership_active(self):
        """Re-enabling a disabled user sets Membership.status = 'active'."""
        # Disable first
        self.client.post(self.disable_url)
        self.staff_membership.refresh_from_db()
        self.assertEqual(self.staff_membership.status, 'suspended')

        # Re-enable
        resp = self.client.post(self.disable_url)
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertTrue(resp.data['is_active'])

        self.staff_membership.refresh_from_db()
        self.assertEqual(self.staff_membership.status, 'active')

    def test_disable_preserves_audit_log(self):
        """disable_account still creates ACCOUNT_DISABLED audit entries."""
        self.client.post(self.disable_url)
        log = AccessAuditLog.objects.filter(
            target_user=self.staff,
            action='ACCOUNT_DISABLED',
        ).first()
        self.assertIsNotNone(log)


# ── Audit action choice validity ─────────────────────────────────────────────

class AuditActionChoiceTests(TestCase):
    """Newly used audit actions are valid ACTION_CHOICES entries."""

    def test_password_reset_requested_is_valid(self):
        valid_actions = {c[0] for c in AccessAuditLog.ACTION_CHOICES}
        self.assertIn('PASSWORD_RESET_REQUESTED', valid_actions)

    def test_password_changed_is_valid(self):
        valid_actions = {c[0] for c in AccessAuditLog.ACTION_CHOICES}
        self.assertIn('PASSWORD_CHANGED', valid_actions)

    def test_password_force_changed_is_valid(self):
        valid_actions = {c[0] for c in AccessAuditLog.ACTION_CHOICES}
        self.assertIn('PASSWORD_FORCE_CHANGED', valid_actions)

    def test_password_reset_confirmed_still_valid(self):
        """Legacy PASSWORD_RESET_CONFIRMED remains in choices for history."""
        valid_actions = {c[0] for c in AccessAuditLog.ACTION_CHOICES}
        self.assertIn('PASSWORD_RESET_CONFIRMED', valid_actions)
