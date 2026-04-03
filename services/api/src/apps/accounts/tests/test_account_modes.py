"""
Tests for account mode (owner_managed / personal) and password lifecycle.

Covers:
  - Account mode set on creation
  - owner_managed + force_password_change rejects
  - personal + force_password_change sets must_change_password
  - can_change_password() / can_self_reset() helpers
  - _session_payload includes account_mode and must_change_password
  - ChangePasswordView (personal-only, rejects owner_managed)
  - ForceChangePasswordView (must_change_password flag)
  - ForgotPasswordView gating (owner_managed auto-skips)
  - ResetPasswordView gating (owner_managed rejects)
  - reset_password owner endpoint sets must_change_password for personal
  - accounts_list includes account_mode per row
  - Audit log captures account_mode in details
"""
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework import status as http_status

from apps.accounts.models import Membership, AccountProfile, AccessAuditLog
from apps.billing.runtime import ResolvedSubscription
from apps.business.models import Business, Subscription

User = get_user_model()


def _make_resolved(source='v2', plan='pro', access_granted=True, legacy_sub=None):
    rs = MagicMock(spec=ResolvedSubscription)
    rs.source = source
    rs.plan = plan
    rs.access_granted = access_granted
    rs.legacy_sub = legacy_sub
    rs.status = 'active'
    rs.subscription_v2 = MagicMock() if source == 'v2' else None
    return rs


@override_settings(
    AUTHENTICATION_BACKENDS=['apps.accounts.auth_backends.UsernameOrEmailBackend'],
)
class AccountModeCreationTests(TestCase):
    """Tests for account_mode setting during member creation."""

    def setUp(self):
        self.business = Business.objects.create(
            name='Test HQ', default_service='gestion', status='active',
        )
        self.subscription = Subscription.objects.create(
            business=self.business, plan='pro', status='active', max_seats=10,
        )
        self.owner = User.objects.create_user(
            username='owner@test.com', email='owner@test.com',
            password='OwnerPass123', first_name='Owner', last_name='User',
        )
        Membership.objects.create(
            user=self.owner, business=self.business, role='owner',
        )
        self.client = APIClient()
        self.create_url = '/api/v1/owner/access/accounts/create/'

    def _payload(self, **overrides):
        defaults = {
            'first_name': 'Test', 'last_name': 'User',
            'username': 'testuser', 'password': 'SecurePass99',
            'role': 'cashier',
        }
        defaults.update(overrides)
        return defaults

    @patch('apps.accounts.services.resolve_subscription')
    def test_default_mode_is_owner_managed(self, mock_resolve):
        """Without account_mode, new member gets owner_managed."""
        mock_resolve.return_value = _make_resolved()
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(self.create_url, self._payload(), format='json')
        self.assertEqual(resp.status_code, http_status.HTTP_201_CREATED)

        profile = AccountProfile.objects.get(user__username='testuser')
        self.assertEqual(profile.account_mode, 'owner_managed')
        self.assertFalse(profile.must_change_password)

    @patch('apps.accounts.services.resolve_subscription')
    def test_personal_mode_set_on_creation(self, mock_resolve):
        """account_mode=personal is stored on the new user's profile."""
        mock_resolve.return_value = _make_resolved()
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(
            self.create_url,
            self._payload(account_mode='personal'),
            format='json',
        )
        self.assertEqual(resp.status_code, http_status.HTTP_201_CREATED)

        profile = AccountProfile.objects.get(user__username='testuser')
        self.assertEqual(profile.account_mode, 'personal')

    @patch('apps.accounts.services.resolve_subscription')
    def test_personal_with_force_password_change(self, mock_resolve):
        """personal + force_password_change=True sets must_change_password."""
        mock_resolve.return_value = _make_resolved()
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(
            self.create_url,
            self._payload(account_mode='personal', force_password_change=True),
            format='json',
        )
        self.assertEqual(resp.status_code, http_status.HTTP_201_CREATED)

        profile = AccountProfile.objects.get(user__username='testuser')
        self.assertEqual(profile.account_mode, 'personal')
        self.assertTrue(profile.must_change_password)

    @patch('apps.accounts.services.resolve_subscription')
    def test_owner_managed_force_password_change_rejects(self, mock_resolve):
        """owner_managed + force_password_change=True is rejected."""
        mock_resolve.return_value = _make_resolved()
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(
            self.create_url,
            self._payload(account_mode='owner_managed', force_password_change=True),
            format='json',
        )
        self.assertEqual(resp.status_code, http_status.HTTP_400_BAD_REQUEST)

    @patch('apps.accounts.services.resolve_subscription')
    def test_audit_log_captures_account_mode(self, mock_resolve):
        """Audit log details include account_mode and force_password_change."""
        mock_resolve.return_value = _make_resolved()
        self.client.force_authenticate(user=self.owner)
        self.client.post(
            self.create_url,
            self._payload(account_mode='personal', force_password_change=True),
            format='json',
        )

        log = AccessAuditLog.objects.filter(action='USER_CREATED').last()
        self.assertIsNotNone(log)
        self.assertEqual(log.details['account_mode'], 'personal')
        self.assertTrue(log.details['force_password_change'])


class AccountModeHelperTests(TestCase):
    """Tests for AccountProfile.can_change_password() and can_self_reset()."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='helper_test', password='Pass1234', email='helper@test.com',
        )
        self.profile = AccountProfile.objects.get(user=self.user)

    def test_can_change_password_owner_managed(self):
        """owner_managed accounts cannot change password."""
        self.profile.account_mode = 'owner_managed'
        self.profile.save(update_fields=['account_mode'])
        self.assertFalse(self.profile.can_change_password())

    def test_can_change_password_personal(self):
        """personal accounts can change password."""
        self.profile.account_mode = 'personal'
        self.profile.save(update_fields=['account_mode'])
        self.assertTrue(self.profile.can_change_password())

    def test_can_self_reset_personal_with_email(self):
        """personal accounts with email can self-reset."""
        self.profile.account_mode = 'personal'
        self.profile.save(update_fields=['account_mode'])
        self.assertTrue(self.profile.can_self_reset())

    def test_can_self_reset_personal_without_email(self):
        """personal accounts without email cannot self-reset."""
        self.user.email = ''
        self.user.save(update_fields=['email'])
        self.profile.account_mode = 'personal'
        self.profile.save(update_fields=['account_mode'])
        self.assertFalse(self.profile.can_self_reset())

    def test_can_self_reset_owner_managed(self):
        """owner_managed accounts cannot self-reset regardless of email."""
        self.profile.account_mode = 'owner_managed'
        self.profile.save(update_fields=['account_mode'])
        self.assertFalse(self.profile.can_self_reset())


@override_settings(
    AUTHENTICATION_BACKENDS=['apps.accounts.auth_backends.UsernameOrEmailBackend'],
)
class ChangePasswordViewTests(TestCase):
    """Tests for POST /api/v1/auth/change-password/."""

    def setUp(self):
        self.business = Business.objects.create(
            name='Test HQ', default_service='gestion', status='active',
        )
        Subscription.objects.create(
            business=self.business, plan='pro', status='active', max_seats=10,
        )
        self.user = User.objects.create_user(
            username='personal_user', password='OldPass123', email='personal@test.com',
        )
        Membership.objects.create(
            user=self.user, business=self.business, role='cashier',
        )
        self.profile = AccountProfile.objects.get(user=self.user)
        self.profile.account_mode = 'personal'
        self.profile.save(update_fields=['account_mode'])

        self.client = APIClient()
        self.url = '/api/v1/auth/change-password/'

    def test_personal_user_can_change_password(self):
        """Personal account can change password with correct current password."""
        self.client.force_authenticate(user=self.user)
        resp = self.client.post(self.url, {
            'current_password': 'OldPass123',
            'new_password': 'NewPass456',
        }, format='json')
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewPass456'))

    def test_owner_managed_user_cannot_change_password(self):
        """Owner-managed account is rejected from changing password."""
        self.profile.account_mode = 'owner_managed'
        self.profile.save(update_fields=['account_mode'])

        self.client.force_authenticate(user=self.user)
        resp = self.client.post(self.url, {
            'current_password': 'OldPass123',
            'new_password': 'NewPass456',
        }, format='json')
        self.assertEqual(resp.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_wrong_current_password_rejected(self):
        """Incorrect current password is rejected."""
        self.client.force_authenticate(user=self.user)
        resp = self.client.post(self.url, {
            'current_password': 'WrongPass',
            'new_password': 'NewPass456',
        }, format='json')
        self.assertEqual(resp.status_code, http_status.HTTP_400_BAD_REQUEST)

    def test_short_new_password_rejected(self):
        """New password under 8 chars is rejected."""
        self.client.force_authenticate(user=self.user)
        resp = self.client.post(self.url, {
            'current_password': 'OldPass123',
            'new_password': 'short',
        }, format='json')
        self.assertEqual(resp.status_code, http_status.HTTP_400_BAD_REQUEST)

    def test_change_password_clears_must_change_flag(self):
        """Changing password clears must_change_password."""
        self.profile.must_change_password = True
        self.profile.save(update_fields=['must_change_password'])

        self.client.force_authenticate(user=self.user)
        self.client.post(self.url, {
            'current_password': 'OldPass123',
            'new_password': 'NewPass456',
        }, format='json')

        self.profile.refresh_from_db()
        self.assertFalse(self.profile.must_change_password)

    def test_change_password_reissues_tokens(self):
        """Changing password returns new auth cookies."""
        self.client.force_authenticate(user=self.user)
        resp = self.client.post(self.url, {
            'current_password': 'OldPass123',
            'new_password': 'NewPass456',
        }, format='json')
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        # Cookies are set on the response
        cookie_names = {c for c in resp.cookies}
        self.assertIn('access_token', cookie_names)
        self.assertIn('refresh_token', cookie_names)


@override_settings(
    AUTHENTICATION_BACKENDS=['apps.accounts.auth_backends.UsernameOrEmailBackend'],
)
class ForceChangePasswordViewTests(TestCase):
    """Tests for POST /api/v1/auth/force-change-password/."""

    def setUp(self):
        self.business = Business.objects.create(
            name='Test HQ', default_service='gestion', status='active',
        )
        Subscription.objects.create(
            business=self.business, plan='pro', status='active', max_seats=10,
        )
        self.user = User.objects.create_user(
            username='force_user', password='TempPass123', email='force@test.com',
        )
        Membership.objects.create(
            user=self.user, business=self.business, role='cashier',
        )
        self.profile = AccountProfile.objects.get(user=self.user)
        self.profile.account_mode = 'personal'
        self.profile.must_change_password = True
        self.profile.save(update_fields=['account_mode', 'must_change_password'])

        self.client = APIClient()
        self.url = '/api/v1/auth/force-change-password/'

    def test_force_change_succeeds_when_flag_set(self):
        """User with must_change_password=True can change their password."""
        self.client.force_authenticate(user=self.user)
        resp = self.client.post(self.url, {
            'current_password': 'TempPass123',
            'new_password': 'NewSecure456',
        }, format='json')
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewSecure456'))

        self.profile.refresh_from_db()
        self.assertFalse(self.profile.must_change_password)

    def test_force_change_rejected_when_flag_not_set(self):
        """User without must_change_password=True is rejected."""
        self.profile.must_change_password = False
        self.profile.save(update_fields=['must_change_password'])

        self.client.force_authenticate(user=self.user)
        resp = self.client.post(self.url, {
            'current_password': 'TempPass123',
            'new_password': 'NewSecure456',
        }, format='json')
        self.assertEqual(resp.status_code, http_status.HTTP_400_BAD_REQUEST)

    def test_force_change_wrong_password_rejected(self):
        """Incorrect current password is rejected."""
        self.client.force_authenticate(user=self.user)
        resp = self.client.post(self.url, {
            'current_password': 'WrongPass',
            'new_password': 'NewSecure456',
        }, format='json')
        self.assertEqual(resp.status_code, http_status.HTTP_400_BAD_REQUEST)

    def test_force_change_audit_log(self):
        """Force change creates PASSWORD_FORCE_CHANGED audit log."""
        self.client.force_authenticate(user=self.user)
        self.client.post(self.url, {
            'current_password': 'TempPass123',
            'new_password': 'NewSecure456',
        }, format='json')

        log = AccessAuditLog.objects.filter(action='PASSWORD_FORCE_CHANGED').last()
        self.assertIsNotNone(log)
        self.assertEqual(log.actor, self.user)
        self.assertEqual(log.target_user, self.user)


@override_settings(
    AUTHENTICATION_BACKENDS=['apps.accounts.auth_backends.UsernameOrEmailBackend'],
)
class ForgotPasswordGatingTests(TestCase):
    """Tests for ForgotPasswordView account_mode gating."""

    def setUp(self):
        self.business = Business.objects.create(
            name='Test HQ', default_service='gestion', status='active',
        )
        Subscription.objects.create(
            business=self.business, plan='pro', status='active', max_seats=10,
        )
        self.user = User.objects.create_user(
            username='forgot_user', password='Pass1234', email='forgot@test.com',
        )
        Membership.objects.create(
            user=self.user, business=self.business, role='cashier',
        )
        self.profile = AccountProfile.objects.get(user=self.user)
        self.client = APIClient()
        self.url = '/api/v1/auth/forgot-password/'

    def test_personal_account_receives_reset_email(self):
        """Personal account triggers password reset email (anti-enumeration response)."""
        self.profile.account_mode = 'personal'
        self.profile.save(update_fields=['account_mode'])

        with patch('apps.accounts.views.EmailService') as mock_email:
            resp = self.client.post(self.url, {'email': 'forgot@test.com'}, format='json')

        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        # Email should have been sent
        mock_email.send_password_reset_email.assert_called_once()

    def test_owner_managed_account_skips_email_silently(self):
        """Owner-managed account returns same response but no email sent."""
        self.profile.account_mode = 'owner_managed'
        self.profile.save(update_fields=['account_mode'])

        with patch('apps.accounts.views.EmailService') as mock_email:
            resp = self.client.post(self.url, {'email': 'forgot@test.com'}, format='json')

        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        # Same response shape — anti-enumeration
        self.assertIn('status', resp.data)
        # Email should NOT have been sent
        mock_email.send_password_reset_email.assert_not_called()

    def test_nonexistent_email_returns_same_response(self):
        """Non-existent email returns same response (anti-enumeration)."""
        resp = self.client.post(self.url, {'email': 'nobody@test.com'}, format='json')
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertIn('status', resp.data)


@override_settings(
    AUTHENTICATION_BACKENDS=['apps.accounts.auth_backends.UsernameOrEmailBackend'],
)
class ResetPasswordGatingTests(TestCase):
    """Tests for ResetPasswordView account_mode gating."""

    def setUp(self):
        self.business = Business.objects.create(
            name='Test HQ', default_service='gestion', status='active',
        )
        Subscription.objects.create(
            business=self.business, plan='pro', status='active', max_seats=10,
        )
        self.user = User.objects.create_user(
            username='reset_user', password='Pass1234', email='reset@test.com',
        )
        Membership.objects.create(
            user=self.user, business=self.business, role='cashier',
        )
        self.profile = AccountProfile.objects.get(user=self.user)
        self.client = APIClient()
        self.url = '/api/v1/auth/reset-password/'

    def test_owner_managed_account_rejects_reset(self):
        """Owner-managed account with valid token is rejected."""
        self.profile.account_mode = 'owner_managed'
        self.profile.save(update_fields=['account_mode'])

        # Generate a valid reset token
        token = self.profile.generate_password_reset_token()

        resp = self.client.post(self.url, {
            'token': token,
            'new_password': 'NewPass456',
        }, format='json')
        self.assertEqual(resp.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_personal_account_resets_successfully(self):
        """Personal account with valid token resets password."""
        self.profile.account_mode = 'personal'
        self.profile.save(update_fields=['account_mode'])

        token = self.profile.generate_password_reset_token()

        resp = self.client.post(self.url, {
            'token': token,
            'new_password': 'NewPass456',
        }, format='json')
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewPass456'))

    def test_reset_clears_must_change_password(self):
        """Successful reset clears must_change_password flag."""
        self.profile.account_mode = 'personal'
        self.profile.must_change_password = True
        self.profile.save(update_fields=['account_mode', 'must_change_password'])

        token = self.profile.generate_password_reset_token()

        self.client.post(self.url, {
            'token': token,
            'new_password': 'NewPass456',
        }, format='json')

        self.profile.refresh_from_db()
        self.assertFalse(self.profile.must_change_password)


@override_settings(
    AUTHENTICATION_BACKENDS=['apps.accounts.auth_backends.UsernameOrEmailBackend'],
)
class OwnerResetPasswordModeTests(TestCase):
    """Tests for owner reset_password endpoint setting must_change_password for personal."""

    def setUp(self):
        self.business = Business.objects.create(
            name='Test HQ', default_service='gestion', status='active',
        )
        self.subscription = Subscription.objects.create(
            business=self.business, plan='pro', status='active', max_seats=10,
        )
        self.owner = User.objects.create_user(
            username='owner@test.com', email='owner@test.com',
            password='OwnerPass123',
        )
        Membership.objects.create(
            user=self.owner, business=self.business, role='owner',
        )

        self.target = User.objects.create_user(
            username='target_user', password='OldPass123', email='target@test.com',
        )
        Membership.objects.create(
            user=self.target, business=self.business, role='cashier',
        )
        self.target_profile = AccountProfile.objects.get(user=self.target)

        self.client = APIClient()
        self.url = f'/api/v1/owner/access/accounts/{self.target.pk}/reset-password/'

    def test_reset_personal_sets_must_change_password(self):
        """Owner resetting personal account sets must_change_password=True."""
        self.target_profile.account_mode = 'personal'
        self.target_profile.save(update_fields=['account_mode'])

        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(self.url, {'new_password': 'NewPass456'}, format='json')
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)

        self.target_profile.refresh_from_db()
        self.assertTrue(self.target_profile.must_change_password)

    def test_reset_owner_managed_does_not_set_must_change(self):
        """Owner resetting owner_managed account does NOT set must_change_password."""
        self.target_profile.account_mode = 'owner_managed'
        self.target_profile.save(update_fields=['account_mode'])

        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(self.url, {'new_password': 'NewPass456'}, format='json')
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)

        self.target_profile.refresh_from_db()
        self.assertFalse(self.target_profile.must_change_password)


@override_settings(
    AUTHENTICATION_BACKENDS=['apps.accounts.auth_backends.UsernameOrEmailBackend'],
)
class SessionPayloadModeTests(TestCase):
    """Tests for _session_payload including account_mode and must_change_password."""

    def setUp(self):
        self.business = Business.objects.create(
            name='Test HQ', default_service='gestion', status='active',
        )
        self.subscription = Subscription.objects.create(
            business=self.business, plan='starter', status='active', max_seats=5,
        )
        self.user = User.objects.create_user(
            username='session_user', email='session@test.com', password='Pass1234',
        )
        Membership.objects.create(
            user=self.user, business=self.business, role='cashier',
        )
        # Use reverse relation so self.profile IS the cached object on
        # self.user; otherwise _session_payload's getattr(user, 'account_profile')
        # returns a stale cached copy created by the post_save signal.
        self.profile = self.user.account_profile
        self.client = APIClient()

    def test_session_includes_account_mode(self):
        """GET /me/ payload includes account_mode in user dict."""
        self.profile.account_mode = 'personal'
        self.profile.save(update_fields=['account_mode'])

        self.client.force_authenticate(user=self.user)
        resp = self.client.get('/api/v1/auth/me/')
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertEqual(resp.data['user']['account_mode'], 'personal')

    def test_session_includes_must_change_password(self):
        """GET /me/ payload includes must_change_password in user dict."""
        self.profile.must_change_password = True
        self.profile.save(update_fields=['must_change_password'])

        self.client.force_authenticate(user=self.user)
        resp = self.client.get('/api/v1/auth/me/')
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertTrue(resp.data['user']['must_change_password'])

    def test_session_defaults_for_missing_profile(self):
        """When profile is missing, defaults are used (owner_managed, False)."""
        # Delete profile to test default path
        self.profile.delete()

        self.client.force_authenticate(user=self.user)
        resp = self.client.get('/api/v1/auth/me/')
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertEqual(resp.data['user']['account_mode'], 'owner_managed')
        self.assertFalse(resp.data['user']['must_change_password'])


@override_settings(
    AUTHENTICATION_BACKENDS=['apps.accounts.auth_backends.UsernameOrEmailBackend'],
)
class AccountsListModeTests(TestCase):
    """Tests for accounts_list including account_mode per row."""

    def setUp(self):
        self.business = Business.objects.create(
            name='Test HQ', default_service='gestion', status='active',
        )
        self.subscription = Subscription.objects.create(
            business=self.business, plan='pro', status='active', max_seats=10,
        )
        self.owner = User.objects.create_user(
            username='owner@test.com', email='owner@test.com', password='OwnerPass123',
        )
        Membership.objects.create(
            user=self.owner, business=self.business, role='owner',
        )
        # Create a personal account
        self.personal_user = User.objects.create_user(
            username='personal_acct', password='Pass1234',
        )
        Membership.objects.create(
            user=self.personal_user, business=self.business, role='cashier',
        )
        personal_profile = AccountProfile.objects.get(user=self.personal_user)
        personal_profile.account_mode = 'personal'
        personal_profile.save(update_fields=['account_mode'])

        self.client = APIClient()

    def test_accounts_list_includes_account_mode(self):
        """Each account in the list includes account_mode."""
        self.client.force_authenticate(user=self.owner)
        resp = self.client.get('/api/v1/owner/access/accounts/')
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)

        modes = {a['username']: a['account_mode'] for a in resp.data}
        self.assertEqual(modes['personal_acct'], 'personal')
        self.assertEqual(modes['owner@test.com'], 'owner_managed')
