"""
ADMIN-CLIENTES 04B — Integration: provisioned owner + existing Google OAuth.

Scope: integration/characterization only. No production code is touched by
this slice — `ExternalIdentity`, new migrations, parallel services and new
Google fields were explicitly reverted (04A) and are NOT recreated here.

The only external boundary mocked is `GoogleOAuthService.verify_token`
(exactly the same boundary `test_pr2_google_oauth.py` already mocks).
Everything downstream — `GoogleAuthView`, `AccountProfile.google_sub`,
`Membership`, JWT cookie issuance, `/auth/me` — runs unmocked, for real.

Owners are provisioned through the real HTTP endpoint added in 03A
(`POST /api/v1/platform-admin/clients/`), authenticated via
`force_authenticate` as a superadmin — this avoids exercising a second,
unrelated authentication flow just to reach the provisioning endpoint.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from django.core import mail
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
ME_URL = '/api/v1/auth/me/'

# Raise the auth_google throttle ceiling — same pattern as test_pr2_google_oauth.py.
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
    """Reuse the same canonical plan code as test_admin_clientes_03a_endpoint.py
    — it must exist in generated/pricing.json to pass plan/service compatibility
    (grant_complimentary_access), which an arbitrary made-up code does not."""
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
    """Build the exact canonical structure GoogleOAuthService.verify_token
    returns on success (GoogleVerifyResult wrapping a GoogleTokenPayload) —
    never a made-up payload shape."""
    return GoogleVerifyResult(valid=True, payload=_google_payload(**overrides))


@override_settings(GOOGLE_OAUTH_CLIENT_ID='test-client-id.apps.googleusercontent.com', REST_FRAMEWORK=_DRF_OVERRIDE)
class AdminClientes04BBaseTest(TestCase):
    """Shared provisioning fixtures for the 04B integration slice."""

    def setUp(self):
        self.superadmin = _make_superadmin()
        self.plan = _ensure_plan()
        self.starts_at = timezone.now().replace(microsecond=0)
        self.ends_at = self.starts_at + timedelta(days=180)

    def _provision(self, **overrides):
        payload = {
            'business_name': 'Comercio 04B',
            'business_slug': f'comercio-04b-{uuid.uuid4().hex[:10]}',
            'service_type': 'gestion',
            'country': 'AR',
            'currency': 'ARS',
            'owner_email': f'owner-04b-{uuid.uuid4().hex[:10]}@empresa.example',
            'plan_code': self.plan.code,
            'complimentary_start': self.starts_at.isoformat(),
            'complimentary_end': self.ends_at.isoformat(),
            'grant_reason': 'ADMIN-CLIENTES 04B — fixture de integración',
        }
        payload.update(overrides)
        client = APIClient()
        client.force_authenticate(user=self.superadmin)
        response = client.post(PROVISION_URL, payload, format='json')
        assert response.status_code == 201, response.data
        return response


# ─────────────────────────────────────────────────────────────────────────────
# Owner nuevo provisionado — happy path (sección 4 y 5)
# ─────────────────────────────────────────────────────────────────────────────

class GoogleNewOwnerLoginTests(AdminClientes04BBaseTest):
    """Owner nuevo provisionado inicia sesión con Google."""

    def setUp(self):
        super().setUp()
        provision = self._provision()
        self.business_id = provision.data['business']['id']
        self.owner_email = provision.data['owner']['email']
        self.owner = User.objects.get(pk=provision.data['owner']['id'])
        self.membership = Membership.objects.get(business_id=self.business_id, user=self.owner)
        self.subscription = SubscriptionV2.objects.get(business_id=self.business_id)
        self.profile = AccountProfile.objects.get(user=self.owner)

    def test_01_owner_state_before_google_login(self):
        self.assertEqual(Business.objects.filter(pk=self.business_id).count(), 1)
        self.assertEqual(self.membership.role, 'owner')
        self.assertEqual(self.membership.status, Membership.Status.ACTIVE)
        self.assertEqual(self.subscription.provider, SubscriptionV2.Provider.MANUAL)
        self.assertEqual(self.subscription.status, SubscriptionV2.Status.TRIALING)
        self.assertFalse(self.owner.has_usable_password())
        self.assertIsNone(self.profile.google_sub)
        self.assertFalse(self.profile.is_platform_staff)
        self.assertIsNone(self.profile.internal_role)

    @patch('apps.billing.mp_service.MercadoPagoService', side_effect=AssertionError('MP must not be called'))
    @patch('django.core.mail.send_mail')
    @patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token')
    def test_02_google_login_links_sub_and_reuses_same_user(self, mock_verify, send_mail, mercado_pago):
        mock_verify.return_value = _google_success(email=self.owner_email)
        client = APIClient()

        resp = client.post(GOOGLE_AUTH_URL, {'credential': 'valid-token'})

        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
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

        send_mail.assert_not_called()
        self.assertEqual(len(mail.outbox), 0)
        mercado_pago.assert_not_called()

    @patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token')
    def test_03_cookies_are_real_and_do_not_leak_sub(self, mock_verify):
        mock_verify.return_value = _google_success(email=self.owner_email)
        client = APIClient()

        resp = client.post(GOOGLE_AUTH_URL, {'credential': 'valid-token'})

        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertIn('access_token', resp.cookies)
        self.assertIn('refresh_token', resp.cookies)
        access_cookie = resp.cookies['access_token']
        refresh_cookie = resp.cookies['refresh_token']
        self.assertTrue(access_cookie['httponly'])
        self.assertTrue(refresh_cookie['httponly'])
        self.assertEqual(access_cookie['samesite'], django_settings.AUTH_COOKIE_SAMESITE)
        self.assertEqual(bool(access_cookie['secure']), django_settings.AUTH_COOKIE_SECURE)

        rendered_body = str(resp.data)
        self.assertNotIn(STABLE_SUB, rendered_body)
        self.assertNotIn('google_sub', rendered_body)
        self.assertEqual(set(resp.data), {'status', 'onboarding', 'is_new_user'})

    @patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token')
    def test_04_auth_me_identifies_the_same_owner_and_business(self, mock_verify):
        mock_verify.return_value = _google_success(email=self.owner_email)
        client = APIClient()
        login_resp = client.post(GOOGLE_AUTH_URL, {'credential': 'valid-token'})
        self.assertEqual(login_resp.status_code, http_status.HTTP_200_OK)

        me_resp = client.get(ME_URL)

        self.assertEqual(me_resp.status_code, http_status.HTTP_200_OK)
        self.assertEqual(me_resp.data['user']['email'], self.owner_email)
        self.assertNotEqual(me_resp.data['user']['email'], self.superadmin.email)
        self.assertEqual(User.objects.filter(email__iexact=self.owner_email).count(), 1)
        business_ids = {membership['business']['id'] for membership in me_resp.data['memberships']}
        self.assertEqual(business_ids, {self.business_id})
        self.assertEqual(me_resp.data['current']['business']['id'], self.business_id)


# ─────────────────────────────────────────────────────────────────────────────
# Owner preexistente reutilizado por provisioning (sección 6)
# ─────────────────────────────────────────────────────────────────────────────

class GoogleExistingOwnerReusedTests(AdminClientes04BBaseTest):
    """Provisioning reutiliza un usuario existente; luego ese usuario hace login con Google."""

    def setUp(self):
        super().setUp()
        self.existing_email = f'existing-owner-{uuid.uuid4().hex[:8]}@empresa.example'
        self.existing_user = User.objects.create_user(
            username=self.existing_email, email=self.existing_email, password='SecurePass123!',
        )
        provision = self._provision(owner_email=self.existing_email.upper())
        self.business_id = provision.data['business']['id']
        self.assertFalse(provision.data['owner']['created'])
        self.profile = AccountProfile.objects.get(user=self.existing_user)

    def test_01_provisioning_reused_the_existing_user_without_touching_its_password(self):
        self.assertEqual(User.objects.filter(email__iexact=self.existing_email).count(), 1)
        membership = Membership.objects.get(business_id=self.business_id, user=self.existing_user)
        self.assertEqual(membership.role, 'owner')
        self.assertEqual(membership.status, Membership.Status.ACTIVE)
        self.existing_user.refresh_from_db()
        self.assertTrue(self.existing_user.has_usable_password())
        self.assertIsNone(self.profile.google_sub)

    @patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token')
    def test_02_google_login_links_the_reused_profile_and_session_matches_it(self, mock_verify):
        mock_verify.return_value = _google_success(email=self.existing_email, sub='reused-owner-sub-001')
        client = APIClient()

        resp = client.post(GOOGLE_AUTH_URL, {'credential': 'valid-token'})

        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertFalse(resp.data['is_new_user'])
        self.assertEqual(User.objects.filter(email__iexact=self.existing_email).count(), 1)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.google_sub, 'reused-owner-sub-001')
        self.existing_user.refresh_from_db()
        self.assertTrue(self.existing_user.has_usable_password())

        me_resp = client.get(ME_URL)
        self.assertEqual(me_resp.data['user']['email'], self.existing_email)
        self.assertEqual(me_resp.data['current']['business']['id'], self.business_id)


# ─────────────────────────────────────────────────────────────────────────────
# Gmail, Google Workspace y matching case-insensitive (sección 7)
# ─────────────────────────────────────────────────────────────────────────────

class GoogleWorkspaceAndCaseInsensitiveTests(AdminClientes04BBaseTest):
    """El contrato actual de GoogleAuthView busca por `User.objects.get(email__iexact=...)`
    — no está limitado a @gmail.com y ya es case-insensitive por diseño."""

    def _provision_and_login(self, owner_email, claim_email, sub):
        self._provision(owner_email=owner_email)
        with patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token') as mock_verify:
            mock_verify.return_value = _google_success(email=claim_email, sub=sub)
            client = APIClient()
            resp = client.post(GOOGLE_AUTH_URL, {'credential': 'valid-token'})
        return resp

    def test_01_gmail_address_links_successfully(self):
        email = f'owner-gmail-{uuid.uuid4().hex[:8]}@gmail.com'
        resp = self._provision_and_login(email, email, 'sub-gmail-001')
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        profile = AccountProfile.objects.get(user__email__iexact=email)
        self.assertEqual(profile.google_sub, 'sub-gmail-001')

    def test_02_workspace_domain_email_links_successfully(self):
        email = f'owner-{uuid.uuid4().hex[:8]}@miempresa.com.ar'
        resp = self._provision_and_login(email, email, 'sub-workspace-001')
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        profile = AccountProfile.objects.get(user__email__iexact=email)
        self.assertEqual(profile.google_sub, 'sub-workspace-001')

    def test_03_uppercase_claim_email_matches_lowercase_stored_owner(self):
        email = f'owner-case-{uuid.uuid4().hex[:8]}@empresa.example'
        resp = self._provision_and_login(email, email.upper(), 'sub-case-001')
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertEqual(User.objects.filter(email__iexact=email).count(), 1)
        profile = AccountProfile.objects.get(user__email__iexact=email)
        self.assertEqual(profile.google_sub, 'sub-case-001')


# ─────────────────────────────────────────────────────────────────────────────
# Accesos posteriores por `sub` (sección 8)
# ─────────────────────────────────────────────────────────────────────────────

class GoogleSubIdempotencyTests(AdminClientes04BBaseTest):
    """Segundo login con el mismo `sub`, incluso si el email observado cambia."""

    def setUp(self):
        super().setUp()
        self.owner_email = f'idempotent-owner-{uuid.uuid4().hex[:8]}@empresa.example'
        provision = self._provision(owner_email=self.owner_email)
        self.business_id = provision.data['business']['id']
        self.owner = User.objects.get(pk=provision.data['owner']['id'])
        self.sub = 'sub-idempotent-001'

    def _login(self, **overrides):
        payload_kwargs = {'sub': self.sub, 'email': self.owner_email}
        payload_kwargs.update(overrides)
        with patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token') as mock_verify:
            mock_verify.return_value = _google_success(**payload_kwargs)
            client = APIClient()
            resp = client.post(GOOGLE_AUTH_URL, {'credential': 'valid-token'})
        return client, resp

    def test_01_second_login_by_sub_is_idempotent(self):
        _, resp1 = self._login()
        self.assertEqual(resp1.status_code, http_status.HTTP_200_OK)
        users_after_first = User.objects.count()
        memberships_after_first = Membership.objects.count()
        profiles_after_first = AccountProfile.objects.count()

        _, resp2 = self._login()

        self.assertEqual(resp2.status_code, http_status.HTTP_200_OK)
        self.assertIn('access_token', resp2.cookies)
        self.assertEqual(User.objects.count(), users_after_first)
        self.assertEqual(Membership.objects.count(), memberships_after_first)
        self.assertEqual(AccountProfile.objects.count(), profiles_after_first)

    def test_02_same_sub_different_observed_email_does_not_reassign_identity(self):
        self._login()  # first link
        other_email = f'different-claim-{uuid.uuid4().hex[:8]}@otra-empresa.example'

        client2, resp2 = self._login(email=other_email)

        self.assertEqual(resp2.status_code, http_status.HTTP_200_OK)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.email, self.owner_email)  # User.email never touched
        self.assertFalse(User.objects.filter(email__iexact=other_email).exists())
        self.assertEqual(User.objects.filter(email__iexact=self.owner_email).count(), 1)

        me_resp = client2.get(ME_URL)
        self.assertEqual(me_resp.data['user']['email'], self.owner_email)


# ─────────────────────────────────────────────────────────────────────────────
# Conflictos a caracterizar — sin corregir producción (sección 9)
# ─────────────────────────────────────────────────────────────────────────────

class GoogleConflictCharacterizationTests(AdminClientes04BBaseTest):
    """
    Characterization-only tests for pre-existing GoogleAuthView edge cases.
    These assert CURRENT behavior only — they do not legitimize it as safe,
    and no production code is touched even where a gap is found.

    "Usuario desconocido" is intentionally NOT re-tested here: it is already
    covered by test_pr2_google_oauth.GoogleAuthNewUserTests (auto-creates a
    new user, 0→1 users) — see the final report for that reference instead
    of duplicating it.
    """

    def test_01_ambiguous_case_insensitive_email_crashes_uncaught(self):
        """
        Two users share the same email case-insensitively (this repo's User
        model has no DB-level unique constraint on email). GoogleAuthView's
        email-lookup branch calls `User.objects.get(email__iexact=...)`,
        which raises `MultipleObjectsReturned` — not caught anywhere in the
        view. Gap: the endpoint 500s instead of rejecting deterministically.
        Not fixed in this slice.
        """
        email_a = f'AMBIGUOUS-{uuid.uuid4().hex[:8]}@empresa.example'
        email_b = email_a.lower()
        User.objects.create_user(username=f'user-a-{uuid.uuid4().hex[:6]}', email=email_a)
        User.objects.create_user(username=f'user-b-{uuid.uuid4().hex[:6]}', email=email_b)
        users_before = User.objects.count()

        with patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token') as mock_verify:
            mock_verify.return_value = _google_success(email=email_b, sub='sub-ambiguous-001')
            client = APIClient(raise_request_exception=False)
            resp = client.post(GOOGLE_AUTH_URL, {'credential': 'valid-token'})

        self.assertEqual(resp.status_code, http_status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(User.objects.count(), users_before)
        self.assertNotIn('access_token', resp.cookies)

    def test_02_inactive_preauthorized_owner_gets_linked_before_being_rejected(self):
        """
        A provisioned owner deactivated before ever logging in with Google:
        the email-lookup branch links `google_sub` BEFORE the `is_active`
        check runs further down, so the (still unusable-password) profile
        ends up linked to a `sub` even though the final response is 403 and
        no session/cookies are ever issued. Not reactivated, not fixed —
        documented as a minor side-effect gap.
        """
        provision = self._provision()
        owner = User.objects.get(pk=provision.data['owner']['id'])
        owner.is_active = False
        owner.save(update_fields=['is_active'])
        profile = AccountProfile.objects.get(user=owner)
        self.assertIsNone(profile.google_sub)

        with patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token') as mock_verify:
            mock_verify.return_value = _google_success(email=owner.email, sub='sub-inactive-001')
            client = APIClient()
            resp = client.post(GOOGLE_AUTH_URL, {'credential': 'valid-token'})

        self.assertEqual(resp.status_code, http_status.HTTP_403_FORBIDDEN)
        self.assertNotIn('access_token', resp.cookies)
        profile.refresh_from_db()
        self.assertEqual(profile.google_sub, 'sub-inactive-001')  # linked despite rejection
        owner.refresh_from_db()
        self.assertFalse(owner.is_active)  # never silently reactivated

    def test_03_owner_already_linked_to_a_different_sub_keeps_the_original_link(self):
        """
        Owner already has google_sub='sub-original-001'. A token arrives
        with a DIFFERENT sub for the same email. The view's `if not
        profile.google_sub:` guard means it never overwrites — it silently
        keeps the original link and logs the user in with the new claim's
        sub unused. No IntegrityError, no rejection, no replacement.
        """
        provision = self._provision()
        owner = User.objects.get(pk=provision.data['owner']['id'])
        profile = AccountProfile.objects.get(user=owner)
        profile.google_sub = 'sub-original-001'
        profile.save(update_fields=['google_sub'])

        with patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token') as mock_verify:
            mock_verify.return_value = _google_success(email=owner.email, sub='sub-new-002')
            client = APIClient()
            resp = client.post(GOOGLE_AUTH_URL, {'credential': 'valid-token'})

        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        profile.refresh_from_db()
        self.assertEqual(profile.google_sub, 'sub-original-001')  # unchanged
        self.assertFalse(AccountProfile.objects.filter(google_sub='sub-new-002').exists())

    def test_04_sub_owned_by_another_user_never_reassigns_to_the_email_match(self):
        """
        `sub` already belongs to a DIFFERENT, unrelated user. A token claims
        that same `sub` but with the provisioned owner's email. Step 1
        (lookup by sub) wins outright — the view logs in as the SUB'S
        original owner, the email claim is never consulted, and the
        provisioned owner's profile is left completely untouched. This is
        the safe invariant required by the spec (#18): identity (sub) beats
        email and is never reassigned by an email coincidence.
        """
        other_user = User.objects.create_user(
            username=f'other-sub-owner-{uuid.uuid4().hex[:6]}',
            email=f'other-{uuid.uuid4().hex[:8]}@otra-empresa.example',
        )
        other_profile = AccountProfile.objects.get(user=other_user)
        other_profile.google_sub = 'sub-belongs-to-other-001'
        other_profile.save(update_fields=['google_sub'])

        provision = self._provision()
        owner = User.objects.get(pk=provision.data['owner']['id'])
        owner_profile = AccountProfile.objects.get(user=owner)

        with patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token') as mock_verify:
            mock_verify.return_value = _google_success(email=owner.email, sub='sub-belongs-to-other-001')
            client = APIClient()
            resp = client.post(GOOGLE_AUTH_URL, {'credential': 'valid-token'})

        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        owner_profile.refresh_from_db()
        self.assertIsNone(owner_profile.google_sub)  # never touched/reassigned
        other_profile.refresh_from_db()
        self.assertEqual(other_profile.google_sub, 'sub-belongs-to-other-001')  # unchanged

        me_resp = client.get(ME_URL)
        self.assertEqual(me_resp.data['user']['email'], other_user.email)
        self.assertNotEqual(me_resp.data['user']['email'], owner.email)


# ─────────────────────────────────────────────────────────────────────────────
# Ausencia de efectos laterales (sección 11)
# ─────────────────────────────────────────────────────────────────────────────

class GoogleLoginNoSideEffectsTests(AdminClientes04BBaseTest):
    """El login Google del owner provisionado no crea filas nuevas de
    provisioning ni toca el período/provider bonificado."""

    def setUp(self):
        super().setUp()
        self.owner_email = f'no-side-effects-{uuid.uuid4().hex[:8]}@empresa.example'
        provision = self._provision(owner_email=self.owner_email)
        self.business_id = provision.data['business']['id']
        self.subscription = SubscriptionV2.objects.get(business_id=self.business_id)

    @patch('apps.billing.mp_service.MercadoPagoService', side_effect=AssertionError('MP must not be called'))
    @patch('apps.accounts.tasks.send_verification_email_task.delay')
    @patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token')
    def test_google_login_produces_no_extra_rows_or_side_effects(self, mock_verify, verification_task, mercado_pago):
        counts_before = (
            Business.objects.count(), Membership.objects.count(),
            SubscriptionV2.objects.count(), Subscription.objects.count(),
            AccessAuditLog.objects.count(),
        )
        period_before = (self.subscription.current_period_start, self.subscription.current_period_end)

        mock_verify.return_value = _google_success(email=self.owner_email, sub='sub-no-side-effects-001')
        client = APIClient()
        resp = client.post(GOOGLE_AUTH_URL, {'credential': 'valid-token'})

        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        counts_after = (
            Business.objects.count(), Membership.objects.count(),
            SubscriptionV2.objects.count(), Subscription.objects.count(),
            AccessAuditLog.objects.count(),
        )
        self.assertEqual(counts_before, counts_after)

        self.subscription.refresh_from_db()
        self.assertEqual(
            (self.subscription.current_period_start, self.subscription.current_period_end),
            period_before,
        )
        self.assertEqual(self.subscription.provider, SubscriptionV2.Provider.MANUAL)
        mercado_pago.assert_not_called()
        verification_task.assert_not_called()
        self.assertEqual(len(mail.outbox), 0)

        owner = User.objects.get(email__iexact=self.owner_email)
        self.assertFalse(owner.has_usable_password())
        profile = AccountProfile.objects.get(user=owner)
        self.assertFalse(profile.is_platform_staff)
        self.assertIsNone(profile.internal_role)
