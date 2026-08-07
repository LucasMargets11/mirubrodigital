"""
accounts/tests/test_admin_clientes_02a_provisioning.py

ADMIN-CLIENTES 02A — Provisioning transaccional de cliente (backend only).

Test matrix (mirrors the spec's numbered "Tests mínimos" list):
  ProvisioningSuccessTest
    1.  Full provisioning with a brand-new owner user.
    2.  New user gets an unusable password.
    3.  New user's email is NOT marked verified.
    4.  New user gets NO platform-staff permissions.
    5.  Case-insensitive reuse of an existing user.
    6.  Reuse does not modify password/flags/profile.
    7.  Same user can own two different businesses.
    8.  Membership is active with role=owner.
    9.  Owner does not consume a seat (canonical resolver regression).
    10. Root Business created with correct slug + service_type.
    11. SubscriptionV2 manual/bonified, tied to the business.
    12. Business ends in status='trialing'.
    13. Audit logs written with actor + expected details.

  ProvisioningRejectionTest
    14. Rejects a non-platform-staff actor.
    15. Rejects an 'operations' actor.
    16. Rejects an inactive existing owner user.
    17. Rejects an invalid email.
    18. Rejects when multiple users match the email case-insensitively.
    19. Rejects a duplicate slug — no second business created.
    20. Full rollback when grant_complimentary_access() fails.
    21. Full rollback on incompatible plan/service.
    22. Pre-existing owner user is preserved (untouched) across rollback.

  ProvisioningNoSideEffectsTest
    23. Never calls Mercado Pago.
    24. Never creates a legacy subscription (business.Subscription /
        billing.Subscription / SubscriptionIntent / PaymentAttempt).
    25. Never sends emails nor queues async tasks.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.accounts.admin_client_provisioning_service import (
    AdminClientProvisioningResult,
    ComplimentaryGrantFailedError,
    ComplimentaryPlanServiceMismatchError,
    DuplicateBusinessSlugError,
    InactiveOwnerAccountError,
    InvalidOwnerEmailError,
    MultipleOwnerAccountsError,
    UnauthorizedProvisioningActorError,
    provision_admin_client,
)
from apps.accounts.models import AccessAuditLog, AccountProfile, Membership
from apps.billing.complimentary_access_service import ComplimentaryAccessError
from apps.billing.models import (
    PaymentAttempt,
    Plan,
    Subscription as LegacyBillingSubscription,
    SubscriptionIntent,
    SubscriptionV2,
)
from apps.business.models import Business
from apps.business.models import Subscription as LegacyBusinessSubscription

User = get_user_model()


def _make_admin(internal_role=AccountProfile.InternalRole.SUPERADMIN, is_platform_staff=True, email=None):
    email = email or f'admin-{uuid.uuid4()}@platform.com'
    user = User.objects.create_user(email=email, username=email, password='AdminPass123!')
    # Mutate the reverse-cached AccountProfile instance directly (not via a
    # bulk .update()) — the post_save signal's get_or_create(user=instance)
    # sets Django's reverse-relation cache on `user`, so a separate queryset
    # .update() would silently leave that cached object (and therefore
    # `user.account_profile` as seen by the service) stale.
    profile = user.account_profile
    profile.is_platform_staff = is_platform_staff
    profile.internal_role = internal_role
    profile.save(update_fields=['is_platform_staff', 'internal_role'])
    return user


def _make_plan(code='gestion_pro', price=Decimal('50000.00'), plan_status='active'):
    plan, _ = Plan.objects.get_or_create(
        code=code,
        defaults={
            'name': code,
            'price': price,
            'interval': 'monthly',
            'currency': 'ARS',
            'frequency': 1,
            'frequency_type': 'months',
            'plan_status': plan_status,
        },
    )
    return plan


class ProvisioningTestBase(TestCase):
    def setUp(self):
        self.admin = _make_admin()
        self.plan = _make_plan()
        self.starts_at = timezone.now()
        self.ends_at = self.starts_at + timedelta(days=180)

    def _kwargs(self, **overrides):
        kwargs = dict(
            business_name='Nuevo Cliente SRL',
            business_slug=f'nuevo-cliente-{uuid.uuid4().hex[:8]}',
            service_type='gestion',
            country='AR',
            currency='ARS',
            owner_email=f'owner-{uuid.uuid4().hex[:8]}@cliente.com',
            plan_code=self.plan.code,
            complimentary_start=self.starts_at,
            complimentary_end=self.ends_at,
            granted_by=self.admin,
            grant_reason='Alta administrativa — cortesía comercial',
        )
        kwargs.update(overrides)
        return kwargs

    def _provision(self, **overrides) -> AdminClientProvisioningResult:
        return provision_admin_client(**self._kwargs(**overrides))


class ProvisioningSuccessTest(ProvisioningTestBase):

    # ── 1: full provisioning, new user ─────────────────────────────────────
    def test_01_full_provisioning_new_user(self):
        result = self._provision()
        self.assertTrue(result.owner_created)
        self.assertIsInstance(result.business, Business)
        self.assertIsInstance(result.membership, Membership)
        self.assertIsInstance(result.subscription, SubscriptionV2)

    # ── 2: unusable password ────────────────────────────────────────────────
    def test_02_new_user_unusable_password(self):
        result = self._provision()
        self.assertFalse(result.owner_user.has_usable_password())

    # ── 3: not verified ──────────────────────────────────────────────────────
    def test_03_new_user_email_not_verified(self):
        result = self._provision()
        profile = AccountProfile.objects.get(user=result.owner_user)
        self.assertFalse(profile.email_verified)

    # ── 4: no platform-staff grant ──────────────────────────────────────────
    def test_04_new_user_no_platform_staff(self):
        result = self._provision()
        profile = AccountProfile.objects.get(user=result.owner_user)
        self.assertFalse(profile.is_platform_staff)
        self.assertIsNone(profile.internal_role)

    # ── 5: case-insensitive reuse ────────────────────────────────────────────
    def test_05_reuse_case_insensitive(self):
        email = f'Owner.CI-{uuid.uuid4().hex[:8]}@Cliente.com'
        existing = User.objects.create_user(
            email=email.lower(), username=email.lower(), password='OwnerPass123!',
        )
        result = self._provision(
            owner_email=email.upper(),
            business_slug=f'ci-biz-{uuid.uuid4().hex[:8]}',
        )
        self.assertFalse(result.owner_created)
        self.assertEqual(result.owner_user.pk, existing.pk)

    # ── 6: reuse does not modify password/flags/profile ────────────────────
    def test_06_reuse_does_not_modify_password_flags_profile(self):
        email = f'reuse-{uuid.uuid4().hex[:8]}@cliente.com'
        existing = User.objects.create_user(
            email=email, username=email, password='OriginalPass123!',
            first_name='Original', last_name='Owner',
        )
        original_password_hash = existing.password
        AccountProfile.objects.filter(user=existing).update(
            email_verified=False, account_status=AccountProfile.AccountStatus.PENDING_EMAIL_VERIFICATION,
        )

        self._provision(owner_email=email, business_slug=f'reuse-biz-{uuid.uuid4().hex[:8]}')

        existing.refresh_from_db()
        profile = AccountProfile.objects.get(user=existing)
        self.assertEqual(existing.password, original_password_hash)
        self.assertEqual(existing.first_name, 'Original')
        self.assertEqual(existing.last_name, 'Owner')
        self.assertFalse(profile.email_verified)
        self.assertFalse(profile.is_platform_staff)

    # ── 7: same user, two businesses ────────────────────────────────────────
    def test_07_owner_of_two_businesses(self):
        email = f'multi-owner-{uuid.uuid4().hex[:8]}@cliente.com'
        result1 = self._provision(
            owner_email=email, business_slug=f'biz-one-{uuid.uuid4().hex[:8]}',
        )
        result2 = self._provision(
            owner_email=email, business_slug=f'biz-two-{uuid.uuid4().hex[:8]}',
        )
        self.assertEqual(result1.owner_user.pk, result2.owner_user.pk)
        self.assertNotEqual(result1.business.pk, result2.business.pk)
        self.assertEqual(
            Membership.objects.filter(user=result1.owner_user, role='owner').count(), 2,
        )

    # ── 8: membership active + owner ────────────────────────────────────────
    def test_08_membership_active_owner_role(self):
        result = self._provision()
        self.assertEqual(result.membership.role, 'owner')
        self.assertEqual(result.membership.status, Membership.Status.ACTIVE)
        self.assertEqual(result.membership.business_id, result.business.pk)
        self.assertEqual(result.membership.user_id, result.owner_user.pk)

    # ── 9: owner never consumes a seat (canonical resolver regression) ─────
    def test_09_owner_does_not_consume_seat(self):
        # The pre_save signal (accounts.models.check_seat_limit) exits early
        # for role='owner' *before* touching resolve_subscription at all —
        # so this must succeed even though no subscription exists yet at the
        # instant the Membership row is inserted (grant happens right after).
        with patch('apps.billing.runtime.resolve_subscription') as mock_resolve:
            result = self._provision()
            mock_resolve.assert_not_called()

        # And the seat-counting query (used elsewhere) still excludes it.
        non_owner_count = Membership.objects.filter(
            business=result.business,
        ).exclude(role='owner').count()
        self.assertEqual(non_owner_count, 0)

    # ── 10: root business, slug + service ───────────────────────────────────
    def test_10_business_root_slug_and_service(self):
        slug = f'root-biz-{uuid.uuid4().hex[:8]}'
        result = self._provision(business_slug=slug)
        self.assertIsNone(result.business.parent)
        self.assertEqual(result.business.slug, slug)
        self.assertEqual(result.business.service_type, 'gestion')
        self.assertEqual(result.business.country, 'AR')
        self.assertEqual(result.business.currency, 'ARS')

    # ── 11: SubscriptionV2 manual + bonified ────────────────────────────────
    def test_11_subscription_manual_bonified(self):
        result = self._provision()
        sub = result.subscription
        self.assertEqual(sub.business_id, result.business.pk)
        self.assertEqual(sub.provider, SubscriptionV2.Provider.MANUAL)
        self.assertEqual(sub.status, SubscriptionV2.Status.TRIALING)
        self.assertIsNone(sub.provider_sub_id)

    # ── 12: business final status trialing ──────────────────────────────────
    def test_12_business_final_status_trialing(self):
        result = self._provision()
        result.business.refresh_from_db()
        self.assertEqual(result.business.status, 'trialing')

    # ── 13: audit logs ───────────────────────────────────────────────────────
    def test_13_audit_logs_written(self):
        result = self._provision()

        created_log = AccessAuditLog.objects.get(
            action='ADMIN_CLIENT_CREATED', business=result.business,
        )
        self.assertEqual(created_log.actor_id, self.admin.pk)
        self.assertEqual(created_log.details['business_id'], result.business.pk)
        self.assertEqual(created_log.details['owner_user_id'], result.owner_user.pk)
        self.assertTrue(created_log.details['owner_created'])

        preauth_log = AccessAuditLog.objects.get(
            action='ADMIN_OWNER_PREAUTHORIZED', business=result.business,
        )
        self.assertEqual(preauth_log.actor_id, self.admin.pk)
        self.assertEqual(preauth_log.target_user_id, result.owner_user.pk)
        self.assertEqual(preauth_log.details['membership_id'], result.membership.pk)
        self.assertEqual(preauth_log.details['service_type'], 'gestion')
        self.assertEqual(preauth_log.details['plan_code'], self.plan.code)

        grant_log = AccessAuditLog.objects.get(
            action='ADMIN_COMPLIMENTARY_ACCESS_GRANTED', business=result.business,
        )
        self.assertEqual(grant_log.actor_id, self.admin.pk)


class ProvisioningRejectionTest(ProvisioningTestBase):

    # ── 14: non platform-staff actor ────────────────────────────────────────
    def test_14_rejects_non_platform_staff(self):
        plain_user = User.objects.create_user(
            email=f'plain-{uuid.uuid4().hex[:8]}@platform.com',
            username=f'plain-{uuid.uuid4().hex[:8]}',
            password='PlainPass123!',
        )
        with self.assertRaises(UnauthorizedProvisioningActorError):
            self._provision(granted_by=plain_user)
        self.assertEqual(Business.objects.count(), 0)

    # ── 15: 'operations' rejected ────────────────────────────────────────────
    def test_15_rejects_operations(self):
        ops = _make_admin(internal_role=AccountProfile.InternalRole.OPERATIONS)
        with self.assertRaises(UnauthorizedProvisioningActorError):
            self._provision(granted_by=ops)
        self.assertEqual(Business.objects.count(), 0)

    # ── 16: inactive existing owner ──────────────────────────────────────────
    def test_16_rejects_inactive_existing_owner(self):
        email = f'inactive-{uuid.uuid4().hex[:8]}@cliente.com'
        User.objects.create_user(
            email=email, username=email, password='Pass123!', is_active=False,
        )
        with self.assertRaises(InactiveOwnerAccountError):
            self._provision(owner_email=email)
        self.assertEqual(Business.objects.count(), 0)

    # ── 17: invalid email ─────────────────────────────────────────────────────
    def test_17_rejects_invalid_email(self):
        with self.assertRaises(InvalidOwnerEmailError):
            self._provision(owner_email='not-an-email')
        self.assertEqual(Business.objects.count(), 0)
        self.assertEqual(User.objects.filter(email='not-an-email').count(), 0)

    # ── 18: multiple case-insensitive matches ────────────────────────────────
    def test_18_rejects_multiple_case_insensitive_matches(self):
        base = f'dup-{uuid.uuid4().hex[:8]}@cliente.com'
        User.objects.create_user(email=base.lower(), username='dup_lower', password='Pass123!')
        User.objects.create_user(email=base.upper(), username='dup_upper', password='Pass123!')
        with self.assertRaises(MultipleOwnerAccountsError):
            self._provision(owner_email=base)
        self.assertEqual(Business.objects.count(), 0)

    # ── 19: duplicate slug, no second business ───────────────────────────────
    def test_19_rejects_duplicate_slug(self):
        slug = f'existing-biz-{uuid.uuid4().hex[:8]}'
        Business.objects.create(name='Existing Biz', slug=slug, status='active')
        self.assertEqual(Business.objects.filter(slug=slug).count(), 1)

        with self.assertRaises(DuplicateBusinessSlugError):
            self._provision(business_slug=slug)

        self.assertEqual(Business.objects.filter(slug=slug).count(), 1)
        self.assertEqual(Business.objects.count(), 1)

    # ── 20: rollback on grant_complimentary_access failure ──────────────────
    def test_20_rollback_on_grant_failure(self):
        slug = f'rollback-grant-{uuid.uuid4().hex[:8]}'
        email = f'rollback-grant-owner-{uuid.uuid4().hex[:8]}@cliente.com'

        # A cause with no specific taxonomy subclass falls back to
        # ComplimentaryGrantFailedError (ADMIN-CLIENTES 02B contract).
        with patch(
            'apps.accounts.admin_client_provisioning_service.grant_complimentary_access',
            side_effect=ComplimentaryAccessError('boom'),
        ):
            with self.assertRaises(ComplimentaryGrantFailedError):
                self._provision(business_slug=slug, owner_email=email)

        self.assertEqual(Business.objects.filter(slug=slug).count(), 0)
        self.assertEqual(User.objects.filter(email=email).count(), 0)
        self.assertEqual(Membership.objects.count(), 0)
        self.assertEqual(SubscriptionV2.objects.count(), 0)
        self.assertEqual(AccessAuditLog.objects.count(), 0)

    # ── 21: rollback on incompatible plan/service ───────────────────────────
    def test_21_rollback_on_incompatible_plan_service(self):
        slug = f'rollback-incompat-{uuid.uuid4().hex[:8]}'
        email = f'rollback-incompat-owner-{uuid.uuid4().hex[:8]}@cliente.com'

        # ADMIN-CLIENTES 02B: this cause now raises the specific subclass,
        # not the generic ComplimentaryGrantFailedError fallback.
        with self.assertRaises(ComplimentaryPlanServiceMismatchError):
            self._provision(
                business_slug=slug,
                owner_email=email,
                service_type='menu_qr',  # gestion_pro plan is NOT menu_qr vertical
            )

        self.assertEqual(Business.objects.filter(slug=slug).count(), 0)
        self.assertEqual(User.objects.filter(email=email).count(), 0)
        self.assertEqual(Membership.objects.count(), 0)
        self.assertEqual(SubscriptionV2.objects.count(), 0)
        self.assertEqual(AccessAuditLog.objects.count(), 0)

    # ── 22: pre-existing user preserved across rollback ─────────────────────
    def test_22_preexisting_user_preserved_on_rollback(self):
        email = f'preexisting-{uuid.uuid4().hex[:8]}@cliente.com'
        existing = User.objects.create_user(
            email=email, username=email, password='OriginalPass123!',
        )
        original_password_hash = existing.password
        slug = f'rollback-preexisting-{uuid.uuid4().hex[:8]}'

        with patch(
            'apps.accounts.admin_client_provisioning_service.grant_complimentary_access',
            side_effect=Exception('boom'),
        ):
            with self.assertRaises(Exception):
                self._provision(business_slug=slug, owner_email=email)

        existing.refresh_from_db()
        self.assertTrue(User.objects.filter(pk=existing.pk).exists())
        self.assertEqual(existing.password, original_password_hash)
        self.assertEqual(Business.objects.filter(slug=slug).count(), 0)
        self.assertEqual(Membership.objects.filter(user=existing).count(), 0)


class ProvisioningNoSideEffectsTest(ProvisioningTestBase):

    # ── 23: never calls Mercado Pago ────────────────────────────────────────
    def test_23_never_calls_mercadopago(self):
        with patch('apps.billing.mp_service.MercadoPagoService') as mock_mp_cls:
            self._provision()
            mock_mp_cls.assert_not_called()

    # ── 24: never creates a legacy subscription ─────────────────────────────
    def test_24_never_creates_legacy_subscriptions(self):
        self._provision()
        self.assertEqual(LegacyBusinessSubscription.objects.count(), 0)
        self.assertEqual(LegacyBillingSubscription.objects.count(), 0)
        self.assertEqual(SubscriptionIntent.objects.count(), 0)
        self.assertEqual(PaymentAttempt.objects.count(), 0)

    # ── 25: no emails, no async tasks ────────────────────────────────────────
    def test_25_no_emails_or_async_tasks(self):
        with patch('apps.notifications.services.queue_transactional_email') as mock_email:
            self._provision()
            mock_email.assert_not_called()
