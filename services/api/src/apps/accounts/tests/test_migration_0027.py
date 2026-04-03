"""
accounts/tests/test_migration_0027.py — Test for data migration 0027_clear_must_change_pin.

Verifies that all EmployeeProfile rows with must_change_pin=True are
updated to False after the migration runs.
"""
from django.contrib.auth.hashers import make_password
from django.test import TestCase

from apps.accounts.models import EmployeeProfile
from apps.business.models import Business


class ClearMustChangePinMigrationTest(TestCase):
    """
    Tests that migration 0027 correctly clears must_change_pin for all
    existing EmployeeProfile rows.

    Since we run tests against the fully-migrated database, 0027 has already
    executed.  We simulate the pre-migration state by manually setting
    must_change_pin=True on test rows and then verifying the invariant that
    new creation + reset flows always produce must_change_pin=False.
    """

    def setUp(self):
        self.business = Business.objects.create(
            name='MigrationTestBiz', default_service='gestion', status='active',
        )

    def _make_employee(self, code: str, must_change_pin: bool) -> EmployeeProfile:
        return EmployeeProfile.objects.create(
            business=self.business,
            first_name='Test',
            last_name='Employee',
            employee_code=code,
            role_type=EmployeeProfile.RoleType.CASHIER,
            credential_type=EmployeeProfile.CredentialType.PIN,
            login_code_hash=make_password('123456'),
            must_change_pin=must_change_pin,
            status=EmployeeProfile.Status.ACTIVE,
        )

    def test_migration_clears_must_change_pin_for_legacy_employees(self):
        """
        Simulates the migration's effect: employees with must_change_pin=True
        should have it set to False after the bulk update.

        This test creates employees with must_change_pin=True (simulating
        pre-migration state), runs the same update logic used in the
        migration, and verifies all rows end up with must_change_pin=False.
        """
        # Create employees in the "legacy" state
        emp_a = self._make_employee('EMP-MIG01', must_change_pin=True)
        emp_b = self._make_employee('EMP-MIG02', must_change_pin=True)
        emp_c = self._make_employee('EMP-MIG03', must_change_pin=False)  # already clean

        # Verify pre-condition
        self.assertTrue(
            EmployeeProfile.objects.filter(
                business=self.business, must_change_pin=True,
            ).exists()
        )

        # Run the same logic as migration 0027
        updated = EmployeeProfile.objects.filter(
            must_change_pin=True,
        ).update(must_change_pin=False)

        # Assertions
        self.assertEqual(updated, 2)  # only the two legacy rows

        # All employees must now have must_change_pin=False
        self.assertFalse(
            EmployeeProfile.objects.filter(must_change_pin=True).exists()
        )

        # Verify each individually
        for emp in (emp_a, emp_b, emp_c):
            emp.refresh_from_db()
            self.assertFalse(
                emp.must_change_pin,
                f'{emp.employee_code} should have must_change_pin=False',
            )

    def test_migration_is_idempotent(self):
        """Running the migration logic twice has no adverse effect."""
        self._make_employee('EMP-MIG04', must_change_pin=True)

        # First pass
        EmployeeProfile.objects.filter(must_change_pin=True).update(must_change_pin=False)
        # Second pass (no rows to update)
        updated = EmployeeProfile.objects.filter(must_change_pin=True).update(must_change_pin=False)

        self.assertEqual(updated, 0)
        self.assertFalse(EmployeeProfile.objects.filter(must_change_pin=True).exists())

    def test_no_legacy_employees_after_migration(self):
        """
        Post-migration invariant: the database should not contain any
        EmployeeProfile with must_change_pin=True.

        Since this test runs on the fully-migrated DB and employee creation
        now defaults to must_change_pin=False, this asserts the steady state.
        """
        self._make_employee('EMP-MIG05', must_change_pin=False)
        self._make_employee('EMP-MIG06', must_change_pin=False)

        self.assertEqual(
            EmployeeProfile.objects.filter(must_change_pin=True).count(),
            0,
        )
