"""
Tests for Phase 3 backfill_terminals and backfill_cashsessions commands.
"""
from __future__ import annotations

from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.management import call_command
from django.test import TestCase

from apps.accounts.models import EmployeeProfile, Membership
from apps.business.models import Business, Subscription
from apps.cash.models import CashRegister, CashSession, Terminal

User = get_user_model()


def _make_hq(name="HQ"):
    biz = Business.objects.create(name=name, default_service="gestion")
    Subscription.objects.create(business=biz, plan="starter", status="active")
    return biz


def _call(cmd, *args, **kwargs):
    out = StringIO()
    call_command(cmd, *args, stdout=out, stderr=out, **kwargs)
    return out.getvalue()


# =============================================================================
#  backfill_terminals
# =============================================================================

class BackfillTerminalsTest(TestCase):

    def setUp(self):
        self.biz = _make_hq("Shop HQ")
        self.reg = CashRegister.objects.create(
            business=self.biz, name="Caja Principal", is_active=True,
        )

    # ── happy path ──────────────────────────────────────────────────────────

    def test_creates_terminal_for_register(self):
        _call("backfill_terminals")

        t = Terminal.objects.filter(cash_register=self.reg).first()
        self.assertIsNotNone(t)
        self.assertEqual(t.business,   self.biz)
        self.assertEqual(t.name,       "Caja Principal")
        self.assertEqual(t.terminal_type, Terminal.TerminalType.CASHIER)
        self.assertTrue(t.is_active)
        self.assertIsNone(t.branch)

    def test_inactive_register_produces_inactive_terminal(self):
        self.reg.is_active = False
        self.reg.save(update_fields=["is_active"])

        _call("backfill_terminals")

        t = Terminal.objects.get(cash_register=self.reg)
        self.assertFalse(t.is_active)

    # ── branch handling ──────────────────────────────────────────────────────

    def test_branch_register_sets_branch_on_terminal(self):
        branch = Business.objects.create(name="Branch B", parent=self.biz)
        branch_reg = CashRegister.objects.create(
            business=branch, name="Caja Sucursal",
        )

        _call("backfill_terminals")

        t = Terminal.objects.get(cash_register=branch_reg)
        self.assertEqual(t.business, self.biz)    # always HQ
        self.assertEqual(t.branch,   branch)

    # ── idempotency ──────────────────────────────────────────────────────────

    def test_idempotent(self):
        _call("backfill_terminals")
        _call("backfill_terminals")
        self.assertEqual(Terminal.objects.filter(cash_register=self.reg).count(), 1)

    def test_dry_run_writes_nothing(self):
        _call("backfill_terminals", dry_run=True)
        self.assertEqual(Terminal.objects.count(), 0)

    # ── code uniqueness when two registers have clashing UUIDs ───────────────

    def test_multiple_registers_get_unique_codes(self):
        reg2 = CashRegister.objects.create(
            business=self.biz, name="Caja 2",
        )
        _call("backfill_terminals")

        codes = list(Terminal.objects.values_list("code", flat=True))
        self.assertEqual(len(codes), len(set(codes)),
                         "Terminal codes must be unique within a business")

    # ── business-id filter ───────────────────────────────────────────────────

    def test_business_id_filter_leaves_other_businesses_untouched(self):
        other_biz = _make_hq("Other HQ")
        other_reg = CashRegister.objects.create(
            business=other_biz, name="Caja Other",
        )

        _call("backfill_terminals", business_id=self.biz.id)

        self.assertFalse(Terminal.objects.filter(cash_register=other_reg).exists())


# =============================================================================
#  backfill_cashsessions
# =============================================================================

class BackfillCashSessionsTest(TestCase):

    def setUp(self):
        self.biz  = _make_hq("CashBiz HQ")
        self.user = User.objects.create_user(
            username="emp1", email="emp1@t.com", password="pass",
            first_name="Emp", last_name="One",
        )
        Membership.objects.create(
            user=self.user, business=self.biz, role="cashier",
            status=Membership.Status.ACTIVE,
        )

        # Create CashRegister → Terminal pair (prerequisite for cashsessions backfill)
        self.register = CashRegister.objects.create(
            business=self.biz, name="Caja 1",
        )
        self.terminal = Terminal.objects.create(
            business=self.biz,
            cash_register=self.register,
            code="CR-00000001",
            name="Caja 1",
            terminal_type=Terminal.TerminalType.CASHIER,
        )

        # Create EmployeeProfile linked to the user (prereq for employee FK resolution)
        self.ep = EmployeeProfile.objects.create(
            business=self.biz,
            linked_user=self.user,
            first_name="Emp",
            last_name="One",
            employee_code="EMP-0001",
            role_type=EmployeeProfile.RoleType.CASHIER,
            login_code_hash=make_password(None),
            must_change_pin=True,
        )

        # Create a CashSession using the legacy register + user fields
        self.session = CashSession.objects.create(
            business=self.biz,
            register=self.register,
            opened_by=self.user,
            opening_cash_amount=Decimal("100.00"),
        )

    # ── happy path ──────────────────────────────────────────────────────────

    def test_terminal_fk_populated(self):
        _call("backfill_cashsessions")

        self.session.refresh_from_db()
        self.assertEqual(self.session.terminal, self.terminal)

    def test_opened_by_employee_populated(self):
        _call("backfill_cashsessions")

        self.session.refresh_from_db()
        self.assertEqual(self.session.opened_by_employee, self.ep)

    def test_closed_by_employee_populated_when_session_closed(self):
        close_user = User.objects.create_user(
            username="closer", email="closer@t.com", password="pass",
        )
        ep_close = EmployeeProfile.objects.create(
            business=self.biz,
            linked_user=close_user,
            first_name="Closer",
            last_name="User",
            employee_code="EMP-0002",
            role_type=EmployeeProfile.RoleType.CASHIER,
            login_code_hash=make_password(None),
        )
        self.session.closed_by = close_user
        self.session.status    = CashSession.Status.CLOSED
        self.session.save(update_fields=["closed_by", "status"])

        _call("backfill_cashsessions")

        self.session.refresh_from_db()
        self.assertEqual(self.session.closed_by_employee, ep_close)

    def test_branch_set_from_terminal_branch(self):
        branch = Business.objects.create(name="Branch X", parent=self.biz)
        self.terminal.branch = branch
        self.terminal.save(update_fields=["branch"])

        _call("backfill_cashsessions")

        self.session.refresh_from_db()
        self.assertEqual(self.session.branch, branch)

    # ── dry run ──────────────────────────────────────────────────────────────

    def test_dry_run_makes_no_changes(self):
        _call("backfill_cashsessions", dry_run=True)

        self.session.refresh_from_db()
        self.assertIsNone(self.session.terminal)
        self.assertIsNone(self.session.opened_by_employee)

    # ── idempotency ──────────────────────────────────────────────────────────

    def test_idempotent(self):
        _call("backfill_cashsessions")
        _call("backfill_cashsessions")   # second run
        # Terminal count unchanged
        self.assertEqual(Terminal.objects.count(), 1)
        self.session.refresh_from_db()
        self.assertEqual(self.session.terminal, self.terminal)

    # ── session with no register ─────────────────────────────────────────────

    def test_skip_session_without_register(self):
        self.session.register = None
        self.session.save(update_fields=["register"])

        output = _call("backfill_cashsessions")

        self.assertIn("no register FK", output.lower())

    # ── session where terminal doesn't exist yet ─────────────────────────────

    def test_warns_when_terminal_missing_for_register(self):
        unreferenced_reg = CashRegister.objects.create(
            business=self.biz, name="Orphan Caja",
        )
        orphan_session = CashSession.objects.create(
            business=self.biz,
            register=unreferenced_reg,
            opened_by=self.user,
            opening_cash_amount=Decimal("0"),
        )

        output = _call("backfill_cashsessions")

        self.assertIn("no terminal yet", output.lower())
        orphan_session.refresh_from_db()
        self.assertIsNone(orphan_session.terminal)
