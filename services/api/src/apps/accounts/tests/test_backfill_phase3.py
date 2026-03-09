"""
Tests for Phase 3 backfill_memberships and backfill_employees management commands.
"""
from __future__ import annotations

from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import is_password_usable
from django.core.management import call_command
from django.test import TestCase

from apps.accounts.models import EmployeeProfile, Membership
from apps.business.models import Business, Subscription

User = get_user_model()


def _make_business(name="HQ", service="gestion"):
    biz = Business.objects.create(name=name, default_service=service)
    Subscription.objects.create(business=biz, plan="starter", status="active")
    return biz


def _make_user(username, first="", last=""):
    return User.objects.create_user(
        username=username,
        email=f"{username}@test.com",
        password="pass1234",
        first_name=first,
        last_name=last,
    )


def _call(cmd, *args, **kwargs):
    out = StringIO()
    call_command(cmd, *args, stdout=out, stderr=out, **kwargs)
    return out.getvalue()


# =============================================================================
#  backfill_memberships
# =============================================================================

class BackfillMembershipsTest(TestCase):

    def setUp(self):
        self.biz    = _make_business()
        self.owner  = _make_user("owner1")
        self.m_own  = Membership.objects.create(
            user=self.owner, business=self.biz, role="owner",
            status=Membership.Status.ACTIVE,
        )

    # ── basic runs ──────────────────────────────────────────────────────────

    def test_dry_run_produces_no_writes(self):
        # Force a dirty state first
        self.m_own.status = ""
        self.m_own.save(update_fields=["status"])

        _call("backfill_memberships", dry_run=True)

        self.m_own.refresh_from_db()
        self.assertEqual(self.m_own.status, "")  # unchanged

    def test_normalises_empty_status_to_active(self):
        self.m_own.status = ""
        self.m_own.save(update_fields=["status"])

        _call("backfill_memberships")

        self.m_own.refresh_from_db()
        self.assertEqual(self.m_own.status, Membership.Status.ACTIVE)

    def test_clears_branch_scope_from_owner(self):
        branch = Business.objects.create(name="Branch A", parent=self.biz)
        self.m_own.branch_scope = branch
        self.m_own.save(update_fields=["branch_scope"])

        _call("backfill_memberships")

        self.m_own.refresh_from_db()
        self.assertIsNone(self.m_own.branch_scope_id)

    def test_warns_when_no_active_owner(self):
        self.m_own.status = Membership.Status.INACTIVE
        self.m_own.save(update_fields=["status"])

        output = _call("backfill_memberships")

        self.assertIn("no active OWNER", output.lower())

    def test_idempotent(self):
        _call("backfill_memberships")
        output = _call("backfill_memberships")  # second run
        self.assertIn("No changes needed", output)

    def test_business_id_filter(self):
        other_biz  = _make_business(name="Other HQ")
        other_user = _make_user("owner2")
        other_m    = Membership.objects.create(
            user=other_user, business=other_biz, role="owner",
        )
        other_m.status = ""
        other_m.save(update_fields=["status"])

        _call("backfill_memberships", business_id=self.biz.id)

        other_m.refresh_from_db()
        self.assertEqual(other_m.status, "")  # NOT touched

    def test_keeps_suspended_status_unchanged(self):
        self.m_own.status = Membership.Status.SUSPENDED
        self.m_own.save(update_fields=["status"])

        _call("backfill_memberships")

        self.m_own.refresh_from_db()
        self.assertEqual(self.m_own.status, Membership.Status.SUSPENDED)


# =============================================================================
#  backfill_employees
# =============================================================================

class BackfillEmployeesTest(TestCase):

    def setUp(self):
        self.biz     = _make_business(name="RestHQ", service="restaurante")
        self.owner   = _make_user("owner2")
        Membership.objects.create(
            user=self.owner, business=self.biz, role="owner",
            status=Membership.Status.ACTIVE,
        )
        self.cashier = _make_user("cashier1", first="Ana", last="Lopez")
        self.m_cash  = Membership.objects.create(
            user=self.cashier, business=self.biz, role="cashier",
            status=Membership.Status.ACTIVE,
        )

    # ── happy path ──────────────────────────────────────────────────────────

    def test_creates_employee_for_cashier_role(self):
        _call("backfill_employees")

        ep = EmployeeProfile.objects.filter(
            business=self.biz, linked_user=self.cashier
        ).first()
        self.assertIsNotNone(ep)
        self.assertEqual(ep.role_type, EmployeeProfile.RoleType.CASHIER)
        self.assertEqual(ep.first_name, "Ana")
        self.assertEqual(ep.last_name,  "Lopez")
        self.assertTrue(ep.must_change_pin)
        self.assertFalse(is_password_usable(ep.login_code_hash))

    def test_owner_does_not_create_employee(self):
        _call("backfill_employees")

        exists = EmployeeProfile.objects.filter(
            business=self.biz, linked_user=self.owner
        ).exists()
        self.assertFalse(exists)

    def test_salon_role_maps_to_server(self):
        salon_user = _make_user("salon1")
        Membership.objects.create(
            user=salon_user, business=self.biz, role="salon",
            status=Membership.Status.ACTIVE,
        )

        _call("backfill_employees")

        ep = EmployeeProfile.objects.get(business=self.biz, linked_user=salon_user)
        self.assertEqual(ep.role_type, EmployeeProfile.RoleType.SERVER)

    def test_kitchen_role_maps_to_kitchen(self):
        kitchen_user = _make_user("kitchen1")
        Membership.objects.create(
            user=kitchen_user, business=self.biz, role="kitchen",
            status=Membership.Status.ACTIVE,
        )
        _call("backfill_employees")

        ep = EmployeeProfile.objects.get(business=self.biz, linked_user=kitchen_user)
        self.assertEqual(ep.role_type, EmployeeProfile.RoleType.KITCHEN)

    def test_staff_role_falls_back_to_cashier(self):
        staff_user = _make_user("staff1")
        Membership.objects.create(
            user=staff_user, business=self.biz, role="staff",
            status=Membership.Status.ACTIVE,
        )
        _call("backfill_employees")

        ep = EmployeeProfile.objects.get(business=self.biz, linked_user=staff_user)
        self.assertEqual(ep.role_type, EmployeeProfile.RoleType.CASHIER)

    # ── idempotency ──────────────────────────────────────────────────────────

    def test_idempotent(self):
        _call("backfill_employees")
        count_1 = EmployeeProfile.objects.filter(business=self.biz).count()

        _call("backfill_employees")
        count_2 = EmployeeProfile.objects.filter(business=self.biz).count()

        self.assertEqual(count_1, count_2)

    def test_dry_run_creates_no_db_rows(self):
        _call("backfill_employees", dry_run=True)
        self.assertEqual(
            EmployeeProfile.objects.filter(business=self.biz).count(), 0
        )

    # ── employee_code uniqueness ─────────────────────────────────────────────

    def test_employee_codes_unique_per_business(self):
        kitchen_user = _make_user("kitchen2")
        staff_user   = _make_user("staff2")
        Membership.objects.create(
            user=kitchen_user, business=self.biz, role="kitchen",
        )
        Membership.objects.create(
            user=staff_user, business=self.biz, role="staff",
        )

        _call("backfill_employees")

        codes = list(
            EmployeeProfile.objects.filter(business=self.biz)
            .values_list('employee_code', flat=True)
        )
        self.assertEqual(len(codes), len(set(codes)),
                         "employee_code values must be unique within a business")

    # ── branch scope ─────────────────────────────────────────────────────────

    def test_branch_scope_propagated_to_employee(self):
        branch = Business.objects.create(name="Suc Centro", parent=self.biz)
        self.m_cash.branch_scope = branch
        self.m_cash.save(update_fields=["branch_scope"])

        _call("backfill_employees")

        ep = EmployeeProfile.objects.get(business=self.biz, linked_user=self.cashier)
        self.assertEqual(ep.branch, branch)

    # ── provenance ───────────────────────────────────────────────────────────

    def test_permission_overrides_contains_provenance(self):
        _call("backfill_employees")

        ep = EmployeeProfile.objects.get(business=self.biz, linked_user=self.cashier)
        self.assertIn("_migrated_from",        ep.permission_overrides)
        self.assertEqual(ep.permission_overrides["_migrated_from"], "membership")
        self.assertEqual(ep.permission_overrides["_legacy_membership_id"], self.m_cash.id)
