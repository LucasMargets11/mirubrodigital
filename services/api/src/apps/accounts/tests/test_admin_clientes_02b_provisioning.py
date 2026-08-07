"""
accounts/tests/test_admin_clientes_02b_provisioning.py

ADMIN-CLIENTES 02B — Cierre de validaciones y errores de dominio.

Only covers the three contracts closed in this slice (does not repeat 02A's
matrix, which is already covered by test_admin_clientes_02a_provisioning.py):

  ComplimentaryTaxonomyTest
    1. Invalid period -> InvalidComplimentaryPeriodError (specific).
    2. Plan/service incompatible -> ComplimentaryPlanServiceMismatchError (specific).
    3. Existing incompatible subscription -> ActiveComplimentarySubscriptionConflictError (specific).
    4. Generic failure -> ComplimentaryGrantFailedError (fallback only).
    5. Original cause preserved as __cause__ for all of the above.

  BusinessBasicsValidationTest
    6.  Blank/whitespace-only name rejected.
    7.  Valid name persisted with no leading/trailing whitespace.
    8.  Invalid country rejected (exceeds Business.country's real max_length).
    9.  Invalid currency rejected (exceeds Business.currency's real max_length).
    10. service_type and default_service stay in sync.

  ActorValidationTest
    11. Inactive actor rejected.
    12. Non-persisted (in-memory/unsaved) actor rejected.
    13. Actor without AccountProfile rejected.
    14. 'operations' still rejected.
    15. All rejections above leave zero partial rows.
    16. Pre-existing owner user preserved across rollback (actor-side rejections
        never even start the transaction, so nothing to roll back — this is
        checked directly).
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
    ActiveComplimentarySubscriptionConflictError,
    ComplimentaryGrantFailedError,
    ComplimentaryPlanServiceMismatchError,
    InvalidBusinessCountryError,
    InvalidBusinessCurrencyError,
    InvalidBusinessNameError,
    InvalidComplimentaryPeriodError,
    UnauthorizedProvisioningActorError,
    provision_admin_client,
)
from apps.accounts.models import AccessAuditLog, AccountProfile, Membership
from apps.billing.complimentary_access_service import (
    ActiveSubscriptionConflictError,
    ComplimentaryAccessError,
    InvalidPeriodError,
    PlanServiceMismatchError,
    grant_complimentary_access,
)
from apps.billing.models import Plan, SubscriptionV2
from apps.business.models import Business

User = get_user_model()


def _make_admin(internal_role=AccountProfile.InternalRole.SUPERADMIN, is_platform_staff=True, email=None):
    email = email or f'admin-{uuid.uuid4()}@platform.com'
    user = User.objects.create_user(email=email, username=email, password='AdminPass123!')
    # See 02A test helper comment: mutate the reverse-cached profile
    # directly instead of a bulk .update(), which would leave it stale.
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

    def _provision(self, **overrides):
        return provision_admin_client(**self._kwargs(**overrides))

    def _assert_zero_partial_rows(self, slug=None, email=None):
        if slug is not None:
            self.assertEqual(Business.objects.filter(slug=slug).count(), 0)
        if email is not None:
            self.assertEqual(User.objects.filter(email=email).count(), 0)
        self.assertEqual(Membership.objects.count(), 0)
        self.assertEqual(SubscriptionV2.objects.count(), 0)
        self.assertEqual(AccessAuditLog.objects.count(), 0)


# ── 1. Complimentary-access specific taxonomy ──────────────────────────────

class ComplimentaryTaxonomyTest(ProvisioningTestBase):

    # ── Unit-level: complimentary_access_service raises the right subclass ──
    def test_00a_grant_complimentary_access_raises_specific_period_error(self):
        with self.assertRaises(InvalidPeriodError):
            grant_complimentary_access(
                business=Business.objects.create(name='Direct Biz', status='onboarding'),
                plan_code=self.plan.code,
                service_type='gestion',
                starts_at=self.ends_at,
                ends_at=self.starts_at,  # inverted -> invalid period
                granted_by=self.admin,
                reason='test',
            )

    # ── 1: invalid period -> specific provisioning error ────────────────────
    def test_01_invalid_period_specific_error(self):
        slug = f'bad-period-{uuid.uuid4().hex[:8]}'
        email = f'bad-period-{uuid.uuid4().hex[:8]}@cliente.com'
        with self.assertRaises(InvalidComplimentaryPeriodError) as ctx:
            self._provision(
                business_slug=slug, owner_email=email,
                complimentary_start=self.ends_at, complimentary_end=self.starts_at,
            )
        self.assertIsInstance(ctx.exception.__cause__, InvalidPeriodError)
        self._assert_zero_partial_rows(slug=slug, email=email)

    # ── 2: plan/service incompatible -> specific provisioning error ────────
    def test_02_plan_service_incompatible_specific_error(self):
        slug = f'bad-service-{uuid.uuid4().hex[:8]}'
        email = f'bad-service-{uuid.uuid4().hex[:8]}@cliente.com'
        with self.assertRaises(ComplimentaryPlanServiceMismatchError) as ctx:
            self._provision(business_slug=slug, owner_email=email, service_type='menu_qr')
        self.assertIsInstance(ctx.exception.__cause__, PlanServiceMismatchError)
        self._assert_zero_partial_rows(slug=slug, email=email)

    # ── 3: existing incompatible subscription -> specific provisioning error ─
    def test_03_active_subscription_conflict_specific_error(self):
        # Unit-level proof: grant_complimentary_access itself raises the
        # specific billing-level exception for a real conflicting row.
        first = self._provision()
        with self.assertRaises(ActiveSubscriptionConflictError):
            grant_complimentary_access(
                business=first.business,
                plan_code=self.plan.code,
                service_type='gestion',
                starts_at=self.starts_at,
                ends_at=self.ends_at,
                granted_by=self.admin,
                reason='segundo intento',
            )

    def test_03b_active_subscription_conflict_wrapped_by_provisioning(self):
        # Contract-level proof: provision_admin_client() maps that exact
        # billing exception type to its own specific subclass and preserves
        # the cause. A fresh Business can never itself already hold a
        # conflicting subscription (provisioning always creates a brand-new
        # Business right before granting), so the only way to exercise the
        # wrapper's mapping for this branch is via the real exception class
        # raised through the same seam used for the generic-fallback test.
        slug = f'conflict-wrap-{uuid.uuid4().hex[:8]}'
        email = f'conflict-wrap-{uuid.uuid4().hex[:8]}@cliente.com'

        with patch(
            'apps.accounts.admin_client_provisioning_service.grant_complimentary_access',
            side_effect=ActiveSubscriptionConflictError('conflicto real'),
        ):
            with self.assertRaises(ActiveComplimentarySubscriptionConflictError) as ctx:
                self._provision(business_slug=slug, owner_email=email)

        self.assertIsInstance(ctx.exception.__cause__, ActiveSubscriptionConflictError)
        self._assert_zero_partial_rows(slug=slug, email=email)

    # ── 4: generic/unclassified failure -> fallback error only ──────────────
    def test_04_generic_failure_falls_back_to_grant_failed_error(self):
        slug = f'generic-fail-{uuid.uuid4().hex[:8]}'
        email = f'generic-fail-{uuid.uuid4().hex[:8]}@cliente.com'

        with patch(
            'apps.accounts.admin_client_provisioning_service.grant_complimentary_access',
            side_effect=ComplimentaryAccessError('motivo no clasificado'),
        ):
            with self.assertRaises(ComplimentaryGrantFailedError) as ctx:
                self._provision(business_slug=slug, owner_email=email)

        self.assertIsInstance(ctx.exception.__cause__, ComplimentaryAccessError)
        # And NOT one of the specific subclasses.
        self.assertNotIsInstance(ctx.exception, InvalidComplimentaryPeriodError)
        self.assertNotIsInstance(ctx.exception, ComplimentaryPlanServiceMismatchError)
        self.assertNotIsInstance(ctx.exception, ActiveComplimentarySubscriptionConflictError)
        self._assert_zero_partial_rows(slug=slug, email=email)


# ── 2. Business basic-data validation ──────────────────────────────────────

class BusinessBasicsValidationTest(ProvisioningTestBase):

    # ── 6: blank/whitespace-only name rejected ──────────────────────────────
    def test_06_rejects_blank_name(self):
        with self.assertRaises(InvalidBusinessNameError):
            self._provision(business_name='   ')
        self.assertEqual(Business.objects.count(), 0)

    # ── 7: valid name persisted stripped ────────────────────────────────────
    def test_07_valid_name_persisted_stripped(self):
        result = self._provision(business_name='   Cliente Prolijo SRL   ')
        self.assertEqual(result.business.name, 'Cliente Prolijo SRL')

    # ── 8: invalid country rejected (exceeds real model max_length) ────────
    def test_08_rejects_country_exceeding_max_length(self):
        max_len = Business._meta.get_field('country').max_length
        too_long_country = 'X' * (max_len + 1)
        slug = f'bad-country-{uuid.uuid4().hex[:8]}'
        with self.assertRaises(InvalidBusinessCountryError):
            self._provision(business_slug=slug, country=too_long_country)
        self.assertEqual(Business.objects.filter(slug=slug).count(), 0)

    def test_08b_rejects_blank_country(self):
        slug = f'blank-country-{uuid.uuid4().hex[:8]}'
        with self.assertRaises(InvalidBusinessCountryError):
            self._provision(business_slug=slug, country='   ')
        self.assertEqual(Business.objects.filter(slug=slug).count(), 0)

    # ── 9: invalid currency rejected (exceeds real model max_length) ───────
    def test_09_rejects_currency_exceeding_max_length(self):
        max_len = Business._meta.get_field('currency').max_length
        too_long_currency = 'X' * (max_len + 1)
        slug = f'bad-currency-{uuid.uuid4().hex[:8]}'
        with self.assertRaises(InvalidBusinessCurrencyError):
            self._provision(business_slug=slug, currency=too_long_currency)
        self.assertEqual(Business.objects.filter(slug=slug).count(), 0)

    def test_09b_rejects_blank_currency(self):
        slug = f'blank-currency-{uuid.uuid4().hex[:8]}'
        with self.assertRaises(InvalidBusinessCurrencyError):
            self._provision(business_slug=slug, currency='')
        self.assertEqual(Business.objects.filter(slug=slug).count(), 0)

    # ── 10: service_type / default_service stay in sync ─────────────────────
    def test_10_service_type_and_default_service_synced(self):
        result = self._provision(service_type='gestion')
        self.assertEqual(result.business.service_type, 'gestion')
        self.assertEqual(result.business.default_service, 'gestion')


# ── 3. Actor validation ─────────────────────────────────────────────────────

class ActorValidationTest(ProvisioningTestBase):

    # ── 11: inactive actor rejected ─────────────────────────────────────────
    def test_11_rejects_inactive_actor(self):
        admin = _make_admin()
        admin.is_active = False
        admin.save(update_fields=['is_active'])

        with self.assertRaises(UnauthorizedProvisioningActorError):
            self._provision(granted_by=admin)
        self.assertEqual(Business.objects.count(), 0)

    # ── 12: non-persisted (in-memory) actor rejected ────────────────────────
    def test_12_rejects_non_persisted_actor(self):
        unsaved = User(username='ghost', email='ghost@platform.com', pk=999999)
        with self.assertRaises(UnauthorizedProvisioningActorError):
            self._provision(granted_by=unsaved)
        self.assertEqual(Business.objects.count(), 0)

    def test_12b_rejects_none_actor(self):
        with self.assertRaises(UnauthorizedProvisioningActorError):
            self._provision(granted_by=None)
        self.assertEqual(Business.objects.count(), 0)

    # ── 13: actor without AccountProfile rejected ───────────────────────────
    def test_13_rejects_actor_without_account_profile(self):
        bare_user = User.objects.create_user(
            email=f'bare-{uuid.uuid4().hex[:8]}@platform.com',
            username=f'bare-{uuid.uuid4().hex[:8]}',
            password='Pass123!',
        )
        AccountProfile.objects.filter(user=bare_user).delete()

        with self.assertRaises(UnauthorizedProvisioningActorError):
            self._provision(granted_by=bare_user)
        self.assertEqual(Business.objects.count(), 0)

    # ── 14: 'operations' still rejected ─────────────────────────────────────
    def test_14_rejects_operations(self):
        ops = _make_admin(internal_role=AccountProfile.InternalRole.OPERATIONS)
        with self.assertRaises(UnauthorizedProvisioningActorError):
            self._provision(granted_by=ops)
        self.assertEqual(Business.objects.count(), 0)

    # ── 15: all rejections above leave zero partial rows ────────────────────
    def test_15_all_actor_rejections_leave_zero_rows(self):
        admin = _make_admin()
        admin.is_active = False
        admin.save(update_fields=['is_active'])

        for granted_by in (admin, None, User(username='ghost2', pk=888888)):
            try:
                self._provision(granted_by=granted_by)
            except UnauthorizedProvisioningActorError:
                pass
        self.assertEqual(Business.objects.count(), 0)
        self.assertEqual(Membership.objects.count(), 0)
        self.assertEqual(SubscriptionV2.objects.count(), 0)
        self.assertEqual(AccessAuditLog.objects.count(), 0)

    # ── 16: pre-existing owner preserved when actor is rejected ─────────────
    def test_16_preexisting_owner_preserved_when_actor_rejected(self):
        email = f'preexisting-actor-reject-{uuid.uuid4().hex[:8]}@cliente.com'
        existing = User.objects.create_user(
            email=email, username=email, password='OriginalPass123!',
        )
        original_password_hash = existing.password

        ops = _make_admin(internal_role=AccountProfile.InternalRole.OPERATIONS)
        with self.assertRaises(UnauthorizedProvisioningActorError):
            self._provision(granted_by=ops, owner_email=email)

        existing.refresh_from_db()
        self.assertEqual(existing.password, original_password_hash)
        self.assertEqual(Membership.objects.filter(user=existing).count(), 0)
