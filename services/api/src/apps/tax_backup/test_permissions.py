"""
Respaldo Impositivo — Permission tests for Fase B (Vista Read-Only Contador).

Verifies that the ``contador`` role can **read** all tax_backup endpoints
(GET → 200) but is **denied** mutation operations (POST/PUT/PATCH/DELETE → 403).

Also validates that the existing ``admin`` role retains full access.

Run with:
    python manage.py test apps.tax_backup.test_permissions
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, Subscription

from .models import (
    AllocationType,
    ExpenseFiscalProfile,
)

User = get_user_model()


class TaxBackupPermissionTestBase(APITestCase):
    """Shared setup for permission tests."""

    def setUp(self):
        self.business = Business.objects.create(name='Perm Biz', slug='perm-biz')
        sub = Subscription.objects.create(
            business=self.business,
            plan='business',
            status='active',
        )
        # Ensure enough seats for 3 users
        sub.max_seats = 10
        sub.save(update_fields=['max_seats'])

        # ── Users ────────────────────
        self.admin_user = User.objects.create_user(
            username='admin_perm', email='admin@test.com', password='pass1234',
        )
        Membership.objects.create(user=self.admin_user, business=self.business, role='admin')

        self.contador_user = User.objects.create_user(
            username='contador_perm', email='contador@test.com', password='pass1234',
        )
        Membership.objects.create(user=self.contador_user, business=self.business, role='contador')

        self.viewer_user = User.objects.create_user(
            username='viewer_perm', email='viewer@test.com', password='pass1234',
        )
        Membership.objects.create(user=self.viewer_user, business=self.business, role='viewer')

        # ── Seed data ────────────────
        from apps.treasury.models import Expense
        self.expense = Expense.objects.create(
            business=self.business, name='Luz', amount=Decimal('5000'),
            due_date=date(2025, 1, 15),
        )
        self.profile = ExpenseFiscalProfile.objects.create(
            business=self.business,
            expense=self.expense,
            allocation_type=AllocationType.BUSINESS,
        )

    def _auth(self, user):
        self.client.force_authenticate(user=user)
        self.client.cookies['bid'] = str(self.business.id)


# ─────────────────────────────────────────────────────────────────────────
# Contador — READ access
# ─────────────────────────────────────────────────────────────────────────
class ContadorReadTests(TaxBackupPermissionTestBase):
    """Contador role can GET all tax_backup endpoints."""

    def setUp(self):
        super().setUp()
        self._auth(self.contador_user)

    def test_list_profiles(self):
        resp = self.client.get('/api/v1/tax-backup/profiles/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_retrieve_profile(self):
        resp = self.client.get(f'/api/v1/tax-backup/profiles/{self.profile.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_profile_summary(self):
        resp = self.client.get('/api/v1/tax-backup/profiles/summary/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_list_duplicates(self):
        resp = self.client.get('/api/v1/tax-backup/duplicates/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_export_csv(self):
        resp = self.client.get('/api/v1/tax-backup/profiles/export-csv/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_checklist(self):
        resp = self.client.get('/api/v1/tax-backup/profiles/checklist/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────
# Contador — WRITE denied
# ─────────────────────────────────────────────────────────────────────────
class ContadorWriteDeniedTests(TaxBackupPermissionTestBase):
    """Contador role is denied all mutation operations (POST/PUT/PATCH/DELETE)."""

    def setUp(self):
        super().setUp()
        self._auth(self.contador_user)

    def test_create_profile_denied(self):
        resp = self.client.post('/api/v1/tax-backup/profiles/', {
            'expense': self.expense.pk,
            'allocation_type': 'business',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_profile_denied(self):
        resp = self.client.patch(
            f'/api/v1/tax-backup/profiles/{self.profile.pk}/',
            {'allocation_type': 'personal'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_profile_denied(self):
        resp = self.client.delete(f'/api/v1/tax-backup/profiles/{self.profile.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_re_evaluate_denied(self):
        resp = self.client.post(
            f'/api/v1/tax-backup/profiles/{self.profile.pk}/re-evaluate/',
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


# ─────────────────────────────────────────────────────────────────────────
# Viewer — NO finance access at all
# ─────────────────────────────────────────────────────────────────────────
class ViewerNoFinanceTests(TaxBackupPermissionTestBase):
    """Viewer role lacks view_finance — denied even GET on tax_backup."""

    def setUp(self):
        super().setUp()
        self._auth(self.viewer_user)

    def test_list_profiles_denied(self):
        resp = self.client.get('/api/v1/tax-backup/profiles/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


# ─────────────────────────────────────────────────────────────────────────
# Admin — FULL access
# ─────────────────────────────────────────────────────────────────────────
class AdminFullAccessTests(TaxBackupPermissionTestBase):
    """Admin role retains full read+write access."""

    def setUp(self):
        super().setUp()
        self._auth(self.admin_user)

    def test_list_profiles(self):
        resp = self.client.get('/api/v1/tax-backup/profiles/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_create_profile(self):
        from apps.treasury.models import Expense
        expense2 = Expense.objects.create(
            business=self.business, name='Gas', amount=Decimal('2000'),
            due_date=date(2025, 2, 15),
        )
        resp = self.client.post('/api/v1/tax-backup/profiles/', {
            'expense': expense2.pk,
            'allocation_type': 'business',
        }, format='json')
        self.assertIn(resp.status_code, [status.HTTP_201_CREATED, status.HTTP_200_OK])

    def test_update_profile(self):
        resp = self.client.patch(
            f'/api/v1/tax-backup/profiles/{self.profile.pk}/',
            {'allocation_type': 'personal'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
