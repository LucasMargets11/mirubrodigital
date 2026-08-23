"""
ADMIN-CLIENTES 04C — POST /api/v1/auth/google/preauthorized/

Independent endpoint for owners already provisioned by a platform admin to
log in with Google WITHOUT any autocreation (User, AccountProfile, Business,
Membership, SubscriptionV2). Reuses the canonical `GoogleOAuthService.verify_token`
boundary, `AccountProfile.google_sub`, JWT/cookie helpers and business-cookie
selection — no parallel identity model, no changes to `/api/v1/auth/google/`.

Only `GoogleOAuthService.verify_token` is mocked (same canonical structure
mocked by test_pr2_google_oauth.py and test_admin_clientes_04b...). Owners
are provisioned via the real 03A HTTP endpoint (force_authenticate as
superadmin — avoids a second unrelated auth flow).
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.db import transaction as db_transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status as http_status
from rest_framework.test import APIClient

from apps.accounts.google_oauth_service import GoogleTokenPayload, GoogleVerifyResult
from apps.accounts.models import AccessAuditLog, AccountProfile, Membership
from apps.billing.models import Plan, Subscription, SubscriptionV2
from apps.business.models import Business

User = get_user_model()

PROVISION_URL = '/api/v1/platform-admin/clients/'
GOOGLE_AUTH_URL = '/api/v1/auth/google/'
PREAUTH_URL = '/api/v1/auth/google/preauthorized/'
ME_URL = '/api/v1/auth/me/'

_THROTTLE_RATES = {**django_settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {}), 'auth_google': '1000/minute'}
_DRF_OVERRIDE = {**django_settings.REST_FRAMEWORK, 'DEFAULT_THROTTLE_RATES': _THROTTLE_RATES}

STABLE_SUB = '104839201983740192837'


def _make_superadmin():
    user = User.objects.create_user(
        username=f'superadmin-{uuid.uuid4().hex}',
        email=f'superadmin-{uuid.uuid4().hex}@mirubro.internal',
        password='SecurePass123!',
    )
    profile = user.account_profile
    profile.is_platform_staff = True
    profile.internal_role = AccountProfile.InternalRole.SUPERADMIN
    profile.save(update_fields=['is_platform_staff', 'internal_role'])
    return user


def _ensure_plan(code='gestion_pro'):
    plan, _ = Plan.objects.get_or_create(
        code=code,
        defaults={
            'name': 'Gestión Pro',
            'price': Decimal('50000.00'),
            'interval': 'monthly',
            'currency': 'ARS',
            'frequency': 1,
            'frequency_type': 'months',
            'plan_status': 'active',
        },
    )
    return plan


def _google_payload(**overrides):
    defaults = dict(
        sub=STABLE_SUB,
        email='owner@empresa.example',
        email_verified=True,
        name='Owner Provisionado',
        given_name='Owner',
        family_name='Provisionado',
        picture='',
    )
    defaults.update(overrides)
    return GoogleTokenPayload(**defaults)


def _google_success(**overrides):
    return GoogleVerifyResult(valid=True, payload=_google_payload(**overrides))


def _provision(superadmin, plan, starts_at, ends_at, **overrides):
    """Module-level so both TestCase and TransactionTestCase suites share it."""
    payload = {
        'business_name': 'Comercio 04C',
        'business_slug': f'comercio-04c-{uuid.uuid4().hex[:10]}',
        'service_type': 'gestion',
        'country': 'AR',
        'currency': 'ARS',
        'owner_email': f'owner-04c-{uuid.uuid4().hex[:10]}@empresa.example',
        'plan_code': plan.code,
        'complimentary_start': starts_at.isoformat(),
        'complimentary_end': ends_at.isoformat(),
        'grant_reason': 'ADMIN-CLIENTES 04C — fixture de integración',
    }
    payload.update(overrides)
    client = APIClient()
    client.force_authenticate(user=superadmin)
    response = client.post(PROVISION_URL, payload, format='json')
    assert response.status_code == 201, response.data
    return response


@override_settings(GOOGLE_OAUTH_CLIENT_ID='test-client-id.apps.googleusercontent.com', REST_FRAMEWORK=_DRF_OVERRIDE)
class AdminClientes04CBaseTest(TestCase):
    """Shared provisioning fixtures for the 04C preauthorized-endpoint slice."""

    def setUp(self):
        self.superadmin = _make_superadmin()
        self.plan = _ensure_plan()
        self.starts_at = timezone.now().replace(microsecond=0)
        self.ends_at = self.starts_at + timedelta(days=180)

    def _provision(self, **overrides):
        return _provision(self.superadmin, self.plan, self.starts_at, self.ends_at, **overrides)

    def _assert_rejected(self, resp):
        self.assertEqual(resp.status_code, http_status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(resp.data['code'], 'google_account_not_authorized')
        self.assertNotIn('access_token', resp.cookies)
        self.assertNotIn('refresh_token', resp.cookies)
        self.assertNotIn('bid', resp.cookies)


# ─────────────────────────────────────────────────────────────────────────────
# Flujo provisionado (happy path)
# ─────────────────────────────────────────────────────────────────────────────

class GooglePreauthorizedProvisionedOwnerTests(AdminClientes04CBaseTest):

    def setUp(self):
        super().setUp()
        provision = self._provision()
        self.business_id = provision.data['business']['id']
        self.owner_email = provision.data['owner']['email']
        self.owner = User.objects.get(pk=provision.data['owner']['id'])
        self.membership = Membership.objects.get(business_id=self.business_id, user=self.owner)
        self.subscription = SubscriptionV2.objects.get(business_id=self.business_id)
        self.profile = AccountProfile.objects.get(user=self.owner)

    @patch('apps.billing.mp_service.MercadoPagoService', side_effect=AssertionError('MP must not be called'))
    @patch('apps.accounts.tasks.send_verification_email_task.delay')
    @patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token')
    def test_provisioned_owner_logs_in_reuses_user_links_sub_and_keeps_state(
        self, mock_verify, verification_task, mercado_pago,
    ):
        mock_verify.return_value = _google_success(email=self.owner_email)
        client = APIClient()

        resp = client.post(PREAUTH_URL, {'credential': 'valid-token'})

        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertEqual(set(resp.data), {'status', 'onboarding', 'is_new_user'})
        self.assertFalse(resp.data['is_new_user'])
        self.assertEqual(User.objects.filter(email__iexact=self.owner_email).count(), 1)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.google_sub, STABLE_SUB)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.email, self.owner_email)
        self.assertFalse(self.owner.has_usable_password())
        self.assertFalse(self.profile.is_platform_staff)
        self.assertIsNone(self.profile.internal_role)

        self.membership.refresh_from_db()
        self.assertEqual(self.membership.role, 'owner')
        self.assertEqual(self.membership.status, Membership.Status.ACTIVE)
        self.assertEqual(self.membership.business_id, self.business_id)

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.provider, SubscriptionV2.Provider.MANUAL)
        self.assertEqual(self.subscription.status, SubscriptionV2.Status.TRIALING)

        self.assertIn('access_token', resp.cookies)
        self.assertIn('refresh_token', resp.cookies)
        self.assertIn('bid', resp.cookies)
        self.assertEqual(resp.cookies['bid'].value, str(self.business_id))
        access_cookie = resp.cookies['access_token']
        self.assertTrue(access_cookie['httponly'])
        self.assertEqual(access_cookie['samesite'], django_settings.AUTH_COOKIE_SAMESITE)
        self.assertEqual(bool(access_cookie['secure']), django_settings.AUTH_COOKIE_SECURE)
        rendered_body = str(resp.data)
        self.assertNotIn(STABLE_SUB, rendered_body)
        self.assertNotIn('google_sub', rendered_body)

        mercado_pago.assert_not_called()
        verification_task.assert_not_called()
        self.assertEqual(len(mail.outbox), 0)

    @patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token')
    def test_auth_me_confirms_same_owner_and_business(self, mock_verify):
        mock_verify.return_value = _google_success(email=self.owner_email)
        client = APIClient()
        login_resp = client.post(PREAUTH_URL, {'credential': 'valid-token'})
        self.assertEqual(login_resp.status_code, http_status.HTTP_200_OK)

        me_resp = client.get(ME_URL)

        self.assertEqual(me_resp.status_code, http_status.HTTP_200_OK)
        self.assertEqual(me_resp.data['user']['email'], self.owner_email)
        self.assertEqual(me_resp.data['current']['business']['id'], self.business_id)


# ─────────────────────────────────────────────────────────────────────────────
# Compatibilidad
# ─────────────────────────────────────────────────────────────────────────────

class GooglePreauthorizedCompatibilityTests(AdminClientes04CBaseTest):

    def test_01_preexisting_eligible_owner_logs_in_without_password_change(self):
        email = f'preexisting-{uuid.uuid4().hex[:8]}@empresa.example'
        existing_user = User.objects.create_user(username=email, email=email, password='SecurePass123!')
        provision = self._provision(owner_email=email.upper())
        self.assertFalse(provision.data['owner']['created'])

        with patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token') as mock_verify:
            mock_verify.return_value = _google_success(email=email, sub='sub-preexisting-001')
            resp = APIClient().post(PREAUTH_URL, {'credential': 'valid-token'})

        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        existing_user.refresh_from_db()
        self.assertTrue(existing_user.has_usable_password())
        profile = AccountProfile.objects.get(user=existing_user)
        self.assertEqual(profile.google_sub, 'sub-preexisting-001')

    def test_02_google_workspace_email_logs_in(self):
        email = f'owner-{uuid.uuid4().hex[:8]}@miempresa.com.ar'
        self._provision(owner_email=email)

        with patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token') as mock_verify:
            mock_verify.return_value = _google_success(email=email, sub='sub-workspace-001')
            resp = APIClient().post(PREAUTH_URL, {'credential': 'valid-token'})

        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        profile = AccountProfile.objects.get(user__email__iexact=email)
        self.assertEqual(profile.google_sub, 'sub-workspace-001')

    def test_03_case_insensitive_email_matches(self):
        email = f'owner-case-{uuid.uuid4().hex[:8]}@empresa.example'
        self._provision(owner_email=email)

        with patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token') as mock_verify:
            mock_verify.return_value = _google_success(email=email.upper(), sub='sub-case-001')
            resp = APIClient().post(PREAUTH_URL, {'credential': 'valid-token'})

        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertEqual(User.objects.filter(email__iexact=email).count(), 1)
        profile = AccountProfile.objects.get(user__email__iexact=email)
        self.assertEqual(profile.google_sub, 'sub-case-001')

    def test_04_second_login_same_sub_produces_no_new_writes(self):
        provision = self._provision()
        owner_email = provision.data['owner']['email']

        with patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token') as mock_verify:
            mock_verify.return_value = _google_success(email=owner_email, sub='sub-idempotent-001')
            APIClient().post(PREAUTH_URL, {'credential': 'valid-token'})

        users_before = User.objects.count()
        memberships_before = Membership.objects.count()
        profiles_before = AccountProfile.objects.count()

        with patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token') as mock_verify2:
            mock_verify2.return_value = _google_success(email=owner_email, sub='sub-idempotent-001')
            resp2 = APIClient().post(PREAUTH_URL, {'credential': 'valid-token'})

        self.assertEqual(resp2.status_code, http_status.HTTP_200_OK)
        self.assertIn('access_token', resp2.cookies)
        self.assertEqual(User.objects.count(), users_before)
        self.assertEqual(Membership.objects.count(), memberships_before)
        self.assertEqual(AccountProfile.objects.count(), profiles_before)

    def test_05_same_sub_different_email_resolves_original_user(self):
        provision = self._provision()
        owner_email = provision.data['owner']['email']
        owner = User.objects.get(pk=provision.data['owner']['id'])
        sub = 'sub-stable-001'

        with patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token') as mock_verify:
            mock_verify.return_value = _google_success(email=owner_email, sub=sub)
            APIClient().post(PREAUTH_URL, {'credential': 'valid-token'})

        other_email = f'different-claim-{uuid.uuid4().hex[:8]}@otra-empresa.example'
        with patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token') as mock_verify2:
            mock_verify2.return_value = _google_success(email=other_email, sub=sub)
            client2 = APIClient()
            resp2 = client2.post(PREAUTH_URL, {'credential': 'valid-token'})

        self.assertEqual(resp2.status_code, http_status.HTTP_200_OK)
        owner.refresh_from_db()
        self.assertEqual(owner.email, owner_email)  # User.email never touched
        self.assertFalse(User.objects.filter(email__iexact=other_email).exists())

        me_resp = client2.get(ME_URL)
        self.assertEqual(me_resp.data['user']['email'], owner_email)

    def test_06_manual_or_expired_subscription_does_not_block_login(self):
        provision = self._provision()
        owner_email = provision.data['owner']['email']
        subscription = SubscriptionV2.objects.get(business_id=provision.data['business']['id'])
        subscription.status = SubscriptionV2.Status.PAST_DUE
        subscription.current_period_end = timezone.now() - timedelta(days=30)
        subscription.save(update_fields=['status', 'current_period_end'])

        with patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token') as mock_verify:
            mock_verify.return_value = _google_success(email=owner_email, sub='sub-expired-sub-001')
            resp = APIClient().post(PREAUTH_URL, {'credential': 'valid-token'})

        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionV2.Status.PAST_DUE)  # untouched
        self.assertEqual(subscription.provider, SubscriptionV2.Provider.MANUAL)


# ─────────────────────────────────────────────────────────────────────────────
# Rechazos seguros
# ─────────────────────────────────────────────────────────────────────────────

class GooglePreauthorizedRejectionTests(AdminClientes04CBaseTest):

    def test_01_unknown_email_rejected_no_new_user(self):
        users_before = User.objects.count()
        email = f'unknown-{uuid.uuid4().hex[:8]}@empresa.example'

        with patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token') as mock_verify:
            mock_verify.return_value = _google_success(email=email, sub='sub-unknown-001')
            resp = APIClient().post(PREAUTH_URL, {'credential': 'valid-token'})

        self._assert_rejected(resp)
        self.assertEqual(User.objects.count(), users_before)

    def test_02_ambiguous_email_rejected_never_500(self):
        email_a = f'AMBIGUOUS-{uuid.uuid4().hex[:8]}@empresa.example'
        email_b = email_a.lower()
        User.objects.create_user(username=f'user-a-{uuid.uuid4().hex[:6]}', email=email_a)
        User.objects.create_user(username=f'user-b-{uuid.uuid4().hex[:6]}', email=email_b)

        with patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token') as mock_verify:
            mock_verify.return_value = _google_success(email=email_b, sub='sub-ambiguous-001')
            resp = APIClient(raise_request_exception=False).post(PREAUTH_URL, {'credential': 'valid-token'})

        self._assert_rejected(resp)

    def test_03_inactive_user_rejected_sub_stays_unlinked(self):
        provision = self._provision()
        owner = User.objects.get(pk=provision.data['owner']['id'])
        owner.is_active = False
        owner.save(update_fields=['is_active'])
        profile = AccountProfile.objects.get(user=owner)

        with patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token') as mock_verify:
            mock_verify.return_value = _google_success(email=owner.email, sub='sub-inactive-001')
            resp = APIClient().post(PREAUTH_URL, {'credential': 'valid-token'})

        self._assert_rejected(resp)
        profile.refresh_from_db()
        self.assertIsNone(profile.google_sub)  # unlike /auth/google/, never linked before rejecting

    def test_04_missing_profile_rejected_not_autocreated(self):
        email = f'no-profile-{uuid.uuid4().hex[:8]}@empresa.example'
        user = User.objects.create_user(username=email, email=email)
        AccountProfile.objects.filter(user=user).delete()

        with patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token') as mock_verify:
            mock_verify.return_value = _google_success(email=email, sub='sub-no-profile-001')
            resp = APIClient().post(PREAUTH_URL, {'credential': 'valid-token'})

        self._assert_rejected(resp)
        self.assertFalse(AccountProfile.objects.filter(user=user).exists())

    def test_05_user_without_owner_membership_rejected_without_ensure_membership(self):
        email = f'no-membership-{uuid.uuid4().hex[:8]}@empresa.example'
        user = User.objects.create_user(username=email, email=email)

        with patch('apps.accounts.views._ensure_membership') as ensure_membership, \
                patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token') as mock_verify:
            mock_verify.return_value = _google_success(email=email, sub='sub-no-membership-001')
            resp = APIClient().post(PREAUTH_URL, {'credential': 'valid-token'})

        self._assert_rejected(resp)
        ensure_membership.assert_not_called()
        self.assertEqual(Membership.objects.filter(user=user).count(), 0)
        self.assertEqual(Business.objects.count(), 0)

    def test_06_inactive_owner_membership_rejected(self):
        provision = self._provision()
        owner = User.objects.get(pk=provision.data['owner']['id'])
        membership = Membership.objects.get(business_id=provision.data['business']['id'], user=owner)
        membership.status = Membership.Status.INACTIVE
        membership.save(update_fields=['status'])

        with patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token') as mock_verify:
            mock_verify.return_value = _google_success(email=owner.email, sub='sub-inactive-membership-001')
            resp = APIClient().post(PREAUTH_URL, {'credential': 'valid-token'})

        self._assert_rejected(resp)

    def test_07_profile_linked_to_different_sub_rejected_no_overwrite(self):
        provision = self._provision()
        owner = User.objects.get(pk=provision.data['owner']['id'])
        profile = AccountProfile.objects.get(user=owner)
        profile.google_sub = 'sub-original-001'
        profile.save(update_fields=['google_sub'])

        with patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token') as mock_verify:
            mock_verify.return_value = _google_success(email=owner.email, sub='sub-new-002')
            resp = APIClient().post(PREAUTH_URL, {'credential': 'valid-token'})

        self._assert_rejected(resp)
        profile.refresh_from_db()
        self.assertEqual(profile.google_sub, 'sub-original-001')

    def test_08_sub_owned_by_unrelated_ineligible_user_rejected(self):
        other_user = User.objects.create_user(
            username=f'other-{uuid.uuid4().hex[:6]}',
            email=f'other-{uuid.uuid4().hex[:8]}@otra-empresa.example',
        )
        other_profile = AccountProfile.objects.get(user=other_user)
        other_profile.google_sub = 'sub-belongs-to-ineligible-001'
        other_profile.save(update_fields=['google_sub'])

        provision = self._provision()
        owner = User.objects.get(pk=provision.data['owner']['id'])
        owner_profile = AccountProfile.objects.get(user=owner)

        with patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token') as mock_verify:
            mock_verify.return_value = _google_success(email=owner.email, sub='sub-belongs-to-ineligible-001')
            resp = APIClient().post(PREAUTH_URL, {'credential': 'valid-token'})

        self._assert_rejected(resp)  # other_user has no owner Membership -> ineligible
        owner_profile.refresh_from_db()
        self.assertIsNone(owner_profile.google_sub)
        other_profile.refresh_from_db()
        self.assertEqual(other_profile.google_sub, 'sub-belongs-to-ineligible-001')

    def test_09_sub_owned_by_eligible_other_owner_logs_in_as_that_owner_not_the_claim_email(self):
        other_provision = self._provision()
        other_owner = User.objects.get(pk=other_provision.data['owner']['id'])
        other_profile = AccountProfile.objects.get(user=other_owner)
        other_profile.google_sub = 'sub-belongs-to-eligible-001'
        other_profile.save(update_fields=['google_sub'])

        provision = self._provision()
        claim_owner_email = provision.data['owner']['email']

        with patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token') as mock_verify:
            mock_verify.return_value = _google_success(email=claim_owner_email, sub='sub-belongs-to-eligible-001')
            client = APIClient()
            resp = client.post(PREAUTH_URL, {'credential': 'valid-token'})

        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        me_resp = client.get(ME_URL)
        self.assertEqual(me_resp.data['user']['email'], other_owner.email)
        self.assertNotEqual(me_resp.data['user']['email'], claim_owner_email)

    @patch('apps.billing.mp_service.MercadoPagoService', side_effect=AssertionError('MP must not be called'))
    @patch('apps.accounts.tasks.send_verification_email_task.delay')
    def test_10_and_11_rejections_leave_zero_side_effects_and_no_external_calls(self, verification_task, mercado_pago):
        counts_before = (
            User.objects.count(), AccountProfile.objects.count(), Business.objects.count(),
            Membership.objects.count(), SubscriptionV2.objects.count(),
            Subscription.objects.count(), AccessAuditLog.objects.count(),
        )

        with patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token') as mock_verify:
            mock_verify.return_value = _google_success(
                email=f'unknown-{uuid.uuid4().hex[:8]}@empresa.example', sub='sub-side-effects-001',
            )
            resp = APIClient().post(PREAUTH_URL, {'credential': 'valid-token'})

        self._assert_rejected(resp)
        counts_after = (
            User.objects.count(), AccountProfile.objects.count(), Business.objects.count(),
            Membership.objects.count(), SubscriptionV2.objects.count(),
            Subscription.objects.count(), AccessAuditLog.objects.count(),
        )
        self.assertEqual(counts_before, counts_after)
        mercado_pago.assert_not_called()
        verification_task.assert_not_called()
        self.assertEqual(len(mail.outbox), 0)


# ─────────────────────────────────────────────────────────────────────────────
# Concurrencia
# ─────────────────────────────────────────────────────────────────────────────

class GooglePreauthorizedConcurrencyTests(AdminClientes04CBaseTest):

    def test_01_two_equivalent_first_linking_attempts_are_idempotent(self):
        provision = self._provision()
        owner_email = provision.data['owner']['email']
        owner = User.objects.get(pk=provision.data['owner']['id'])

        with patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token') as mock_verify:
            mock_verify.return_value = _google_success(email=owner_email, sub='sub-concurrent-001')
            resp1 = APIClient().post(PREAUTH_URL, {'credential': 'valid-token'})
        with patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token') as mock_verify2:
            mock_verify2.return_value = _google_success(email=owner_email, sub='sub-concurrent-001')
            resp2 = APIClient().post(PREAUTH_URL, {'credential': 'valid-token'})

        self.assertEqual(resp1.status_code, http_status.HTTP_200_OK)
        self.assertEqual(resp2.status_code, http_status.HTTP_200_OK)
        profile = AccountProfile.objects.get(user=owner)
        self.assertEqual(profile.google_sub, 'sub-concurrent-001')
        self.assertEqual(AccountProfile.objects.filter(google_sub='sub-concurrent-001').count(), 1)

    def test_02_sub_collision_with_other_user_rejects_without_500(self):
        """
        Simulates a concurrent request winning the race for this exact `sub`
        on a DIFFERENT profile, timed to land right after our own step-1
        lookup (by google_sub) finds nothing but before our own save — this
        reliably exercises the `except IntegrityError` recovery branch in
        `_resolve_preauthorized_user` (real unique-constraint violation, not
        a mocked one).

        NOTE on scope: because the whole resolution runs inside ONE
        `transaction.atomic()` that is rolled back in full on any rejection
        (by design — a rejected login must never leave partial writes), a
        single-connection test can't also assert that the "other" profile
        keeps its write once OUR transaction rolls back (that write is nested
        in the same connection/transaction and rolls back with it here,
        whereas in production it lives in a genuinely separate, already-
        committed transaction on another connection). Verifying that exact
        cross-connection durability would require `TransactionTestCase` with
        real threads/connections, which this repo's test DB cannot presently
        tear down (`treasury_expensetemplate`/`treasury_transactioncategory`
        TRUNCATE FK ordering fails — a pre-existing, unrelated infra issue,
        not fixed here). What IS verified and is the actual safety property:
        the collision is handled gracefully (401, not 500) and the LOSING
        request's own attempted write is fully rolled back.
        """
        provision = self._provision()
        owner_email = provision.data['owner']['email']
        owner = User.objects.get(pk=provision.data['owner']['id'])
        owner_profile = AccountProfile.objects.get(user=owner)

        other_provision = self._provision()
        other_owner = User.objects.get(pk=other_provision.data['owner']['id'])
        other_profile = AccountProfile.objects.get(user=other_owner)

        collision_sub = 'sub-collision-001'
        raced = {'done': False}
        original_filter = User.objects.filter

        def racy_filter(*args, **kwargs):
            qs = original_filter(*args, **kwargs)
            if not raced['done'] and kwargs.get('email__iexact') == owner_email:
                raced['done'] = True
                with db_transaction.atomic():
                    AccountProfile.objects.filter(pk=other_profile.pk).update(google_sub=collision_sub)
            return qs

        with patch.object(User.objects, 'filter', side_effect=racy_filter):
            with patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token') as mock_verify:
                mock_verify.return_value = _google_success(email=owner_email, sub=collision_sub)
                client = APIClient(raise_request_exception=False)
                resp = client.post(PREAUTH_URL, {'credential': 'valid-token'})

        self.assertTrue(raced['done'], 'racy_filter never fired')
        self.assertEqual(resp.status_code, http_status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(resp.data['code'], 'google_account_not_authorized')
        self.assertNotIn('access_token', resp.cookies)
        owner_profile.refresh_from_db()
        self.assertIsNone(owner_profile.google_sub)  # loser's write fully rolled back


# ─────────────────────────────────────────────────────────────────────────────
# Regresión — /auth/google/ (self-service) queda intacto
# ─────────────────────────────────────────────────────────────────────────────

class ExistingGoogleAuthUnaffectedTests(AdminClientes04CBaseTest):
    """Sanity check embedded in the 04C suite: the self-service endpoint's
    autocreation behavior is unaffected by the new preauthorized endpoint.
    The full test_pr2_google_oauth.py suite is also run separately as a
    regression, per the 04C validation requirements."""

    @patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token')
    def test_self_service_endpoint_still_autocreates_unknown_users(self, mock_verify):
        email = f'self-service-{uuid.uuid4().hex[:8]}@gmail.com'
        mock_verify.return_value = _google_success(email=email, sub='sub-self-service-001')

        resp = APIClient().post(GOOGLE_AUTH_URL, {'credential': 'valid-token'})

        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertTrue(resp.data['is_new_user'])
        self.assertEqual(User.objects.filter(email__iexact=email).count(), 1)
