"""
accounts/tests/test_admin_clientes_02c_provisioning.py

ADMIN-CLIENTES 02C — Actor fresco y cierre de la taxonomía de errores.

Only covers the two contracts closed in this slice (does not repeat 02A/02B's
matrices, already covered by their own test modules):

  ActorFreshnessTest
    1. Active on the in-memory instance but deactivated directly in DB
       (instance never refreshed) -> rejected.
    2. Profile cached/loaded as 'superadmin' but updated directly in DB to
       'operations' -> rejected.
    3. User deleted after the instance was loaded -> rejected.
    4. Persisted, active superadmin with a valid profile -> accepted.
    5. The actor stored in AccessAuditLog/Membership corresponds to the
       DB-persisted user (by PK), regardless of which Python reference of
       that same row was passed in.
    6. All rejections above leave zero partial rows.

  ComplimentaryTaxonomyClosureTest
    1. Blank grant_reason -> InvalidComplimentaryGrantReasonError.
    2. Invalid service_type -> InvalidComplimentaryServiceTypeError.
    3. Both preserve the original billing exception as __cause__.
    4. Neither becomes ComplimentaryGrantFailedError.
    5. An unexpected *base* ComplimentaryAccessError instance still becomes
       ComplimentaryGrantFailedError (the only bucket it can fall into).
    6. Invalid period / plan not available / plan-service mismatch /
       active-subscription conflict keep their 02B-specific error types
       (regression).
    7. All of the above roll back Business/new owner/Membership/
       SubscriptionV2/audit logs completely.
    8. A pre-existing owner user is preserved (untouched) across rollback.
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
    ComplimentaryPlanNotAvailableError,
    ComplimentaryPlanServiceMismatchError,
    InvalidComplimentaryGrantReasonError,
    InvalidComplimentaryPeriodError,
    InvalidComplimentaryServiceTypeError,
    UnauthorizedProvisioningActorError,
    provision_admin_client,
)
from apps.accounts.models import AccessAuditLog, AccountProfile, Membership
from apps.billing.complimentary_access_service import (
    ActiveSubscriptionConflictError,
    ComplimentaryAccessError,
    InvalidGrantReasonError,
    InvalidPeriodError,
    InvalidServiceTypeError,
    PlanNotAvailableError,
    PlanServiceMismatchError,
)
from apps.billing.models import Plan, SubscriptionV2
from apps.business.models import Business

User = get_user_model()


def _make_admin(internal_role=AccountProfile.InternalRole.SUPERADMIN, is_platform_staff=True, email=None):
    email = email or f'admin-{uuid.uuid4()}@platform.com'
    user = User.objects.create_user(email=email, username=email, password='AdminPass123!')
    # Mutate the reverse-cached profile instance directly (not via a bulk
    # .update()) — see 02A/02B test helper comments for why.
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


# ── 1. Actor freshness ───────────────────────────────────────────────────────

class ActorFreshnessTest(ProvisioningTestBase):

    # ── 1: active on instance, deactivated directly in DB ───────────────────
    def test_01_rejects_actor_deactivated_in_db_without_refresh(self):
        admin = _make_admin()
        # Deactivate via a separate queryset write — `admin` (the Python
        # instance we still hold) is never refreshed, so admin.is_active
        # still reads True in memory.
        User.objects.filter(pk=admin.pk).update(is_active=False)
        self.assertTrue(admin.is_active)  # sanity: the stale instance lies

        with self.assertRaises(UnauthorizedProvisioningActorError):
            self._provision(granted_by=admin)
        self.assertEqual(Business.objects.count(), 0)

    # ── 2: profile cached/loaded as superadmin, DB says operations ──────────
    def test_02_rejects_actor_downgraded_to_operations_in_db(self):
        admin = _make_admin()  # loaded/cached as superadmin
        AccountProfile.objects.filter(user=admin).update(
            internal_role=AccountProfile.InternalRole.OPERATIONS,
        )
        self.assertEqual(admin.account_profile.internal_role, AccountProfile.InternalRole.SUPERADMIN)

        with self.assertRaises(UnauthorizedProvisioningActorError):
            self._provision(granted_by=admin)
        self.assertEqual(Business.objects.count(), 0)

    # ── 3: user deleted after the instance was loaded ───────────────────────
    def test_03_rejects_actor_deleted_after_load(self):
        admin = _make_admin()
        deleted_pk = admin.pk
        User.objects.filter(pk=deleted_pk).delete()

        with self.assertRaises(UnauthorizedProvisioningActorError):
            self._provision(granted_by=admin)
        self.assertEqual(Business.objects.count(), 0)

    # ── 4: persisted, active superadmin with a valid profile -> accepted ────
    def test_04_accepts_persisted_active_superadmin(self):
        result = self._provision()
        self.assertIsInstance(result.business, Business)

    # ── 5: audit/membership actor matches the DB-persisted user ─────────────
    def test_05_audit_actor_matches_persisted_admin(self):
        result = self._provision()
        for action in ('ADMIN_CLIENT_CREATED', 'ADMIN_OWNER_PREAUTHORIZED'):
            log = AccessAuditLog.objects.get(action=action, business=result.business)
            self.assertEqual(log.actor_id, self.admin.pk)
        self.assertEqual(result.membership.created_by_user_id, self.admin.pk)

    def test_05b_works_with_a_separately_fetched_instance_reference(self):
        # A different Python object for the exact same DB row must resolve
        # to the same canonical actor — the service keys off the PK, not
        # object identity.
        separate_reference = User.objects.get(pk=self.admin.pk)
        result = self._provision(granted_by=separate_reference)
        log = AccessAuditLog.objects.get(action='ADMIN_CLIENT_CREATED', business=result.business)
        self.assertEqual(log.actor_id, self.admin.pk)

    # ── 6: all rejections leave zero partial rows ───────────────────────────
    def test_06_all_actor_rejections_leave_zero_rows(self):
        deactivated = _make_admin()
        User.objects.filter(pk=deactivated.pk).update(is_active=False)

        downgraded = _make_admin()
        AccountProfile.objects.filter(user=downgraded).update(
            internal_role=AccountProfile.InternalRole.OPERATIONS,
        )

        deleted = _make_admin()
        User.objects.filter(pk=deleted.pk).delete()

        for granted_by in (deactivated, downgraded, deleted):
            with self.assertRaises(UnauthorizedProvisioningActorError):
                self._provision(granted_by=granted_by)

        self.assertEqual(Business.objects.count(), 0)
        self.assertEqual(Membership.objects.count(), 0)
        self.assertEqual(SubscriptionV2.objects.count(), 0)
        self.assertEqual(AccessAuditLog.objects.count(), 0)


# ── 2. Complimentary-access taxonomy closure ────────────────────────────────

class ComplimentaryTaxonomyClosureTest(ProvisioningTestBase):

    # ── 1: blank grant_reason -> specific error ─────────────────────────────
    def test_01_blank_grant_reason_specific_error(self):
        slug = f'blank-reason-{uuid.uuid4().hex[:8]}'
        email = f'blank-reason-{uuid.uuid4().hex[:8]}@cliente.com'
        with self.assertRaises(InvalidComplimentaryGrantReasonError) as ctx:
            self._provision(business_slug=slug, owner_email=email, grant_reason='   ')
        self.assertIsInstance(ctx.exception.__cause__, InvalidGrantReasonError)
        self._assert_zero_partial_rows(slug=slug, email=email)

    # ── 2: invalid service_type -> specific error ───────────────────────────
    def test_02_invalid_service_type_specific_error(self):
        slug = f'bad-svc-type-{uuid.uuid4().hex[:8]}'
        email = f'bad-svc-type-{uuid.uuid4().hex[:8]}@cliente.com'
        with self.assertRaises(InvalidComplimentaryServiceTypeError) as ctx:
            self._provision(business_slug=slug, owner_email=email, service_type='not_a_real_service')
        self.assertIsInstance(ctx.exception.__cause__, InvalidServiceTypeError)
        self._assert_zero_partial_rows(slug=slug, email=email)

    # ── 3 & 4: causes preserved, neither becomes the generic fallback ───────
    def test_03_and_04_causes_preserved_not_generic_fallback(self):
        with self.assertRaises(InvalidComplimentaryGrantReasonError) as ctx1:
            self._provision(grant_reason='')
        self.assertIsInstance(ctx1.exception.__cause__, InvalidGrantReasonError)
        self.assertNotIsInstance(ctx1.exception, ComplimentaryGrantFailedError)

        with self.assertRaises(InvalidComplimentaryServiceTypeError) as ctx2:
            self._provision(service_type='bogus')
        self.assertIsInstance(ctx2.exception.__cause__, InvalidServiceTypeError)
        self.assertNotIsInstance(ctx2.exception, ComplimentaryGrantFailedError)

    # ── 5: unexpected base ComplimentaryAccessError -> generic fallback ─────
    def test_05_unexpected_base_error_falls_back_to_generic(self):
        slug = f'unclassified-{uuid.uuid4().hex[:8]}'
        email = f'unclassified-{uuid.uuid4().hex[:8]}@cliente.com'

        with patch(
            'apps.accounts.admin_client_provisioning_service.grant_complimentary_access',
            side_effect=ComplimentaryAccessError('causa no clasificada'),
        ):
            with self.assertRaises(ComplimentaryGrantFailedError) as ctx:
                self._provision(business_slug=slug, owner_email=email)

        self.assertIsInstance(ctx.exception.__cause__, ComplimentaryAccessError)
        self._assert_zero_partial_rows(slug=slug, email=email)

    # ── 6: 02B taxonomy regressions kept intact ─────────────────────────────
    def test_06a_invalid_period_regression(self):
        with self.assertRaises(InvalidComplimentaryPeriodError):
            self._provision(complimentary_start=self.ends_at, complimentary_end=self.starts_at)

    def test_06b_plan_not_available_regression(self):
        with self.assertRaises(ComplimentaryPlanNotAvailableError):
            self._provision(plan_code=f'no-such-plan-{uuid.uuid4().hex[:8]}')

    def test_06c_plan_service_mismatch_regression(self):
        with self.assertRaises(ComplimentaryPlanServiceMismatchError):
            self._provision(service_type='menu_qr')  # gestion_pro plan is NOT menu_qr vertical

    def test_06d_active_subscription_conflict_regression(self):
        slug = f'conflict-{uuid.uuid4().hex[:8]}'
        email = f'conflict-{uuid.uuid4().hex[:8]}@cliente.com'
        with patch(
            'apps.accounts.admin_client_provisioning_service.grant_complimentary_access',
            side_effect=ActiveSubscriptionConflictError('conflicto real'),
        ):
            with self.assertRaises(ActiveComplimentarySubscriptionConflictError) as ctx:
                self._provision(business_slug=slug, owner_email=email)
        self.assertIsInstance(ctx.exception.__cause__, ActiveSubscriptionConflictError)

    # ── 7: every error above fully rolls back ───────────────────────────────
    def test_07_all_taxonomy_errors_roll_back_completely(self):
        scenarios = [
            dict(grant_reason=''),
            dict(service_type='bogus'),
            dict(complimentary_start=self.ends_at, complimentary_end=self.starts_at),
            dict(plan_code=f'no-such-plan-{uuid.uuid4().hex[:8]}'),
            dict(service_type='menu_qr'),
        ]
        for overrides in scenarios:
            slug = f'rollback-{uuid.uuid4().hex[:8]}'
            email = f'rollback-{uuid.uuid4().hex[:8]}@cliente.com'
            try:
                self._provision(business_slug=slug, owner_email=email, **overrides)
            except Exception:
                pass
            self._assert_zero_partial_rows(slug=slug, email=email)

    # ── 8: pre-existing owner preserved across rollback ─────────────────────
    def test_08_preexisting_owner_preserved_on_rollback(self):
        email = f'preexisting-taxonomy-{uuid.uuid4().hex[:8]}@cliente.com'
        existing = User.objects.create_user(
            email=email, username=email, password='OriginalPass123!',
        )
        original_password_hash = existing.password
        slug = f'rollback-preexisting-taxonomy-{uuid.uuid4().hex[:8]}'

        with self.assertRaises(InvalidComplimentaryGrantReasonError):
            self._provision(business_slug=slug, owner_email=email, grant_reason='  ')

        existing.refresh_from_db()
        self.assertTrue(User.objects.filter(pk=existing.pk).exists())
        self.assertEqual(existing.password, original_password_hash)
        self.assertEqual(Business.objects.filter(slug=slug).count(), 0)
        self.assertEqual(Membership.objects.filter(user=existing).count(), 0)
