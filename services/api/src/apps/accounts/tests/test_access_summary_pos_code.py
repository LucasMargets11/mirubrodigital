"""
Tests for pos_access_code field in GET /api/v1/owner/access/summary/
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import Membership
from apps.business.models import Business, Subscription

User = get_user_model()

_URL = '/api/v1/owner/access/summary/'


class PosAccessCodeSummaryTestCase(TestCase):
    """Verify that pos_access_code is exposed correctly per role."""

    def setUp(self):
        self.business = Business.objects.create(
            name='Kiosko Test',
            default_service='gestion',
        )
        # Business.save() auto-generates slug from name, e.g. "kiosko-test".
        self.business.refresh_from_db()

        self.subscription = Subscription.objects.create(
            business=self.business,
            plan='starter',
            status='active',
        )

        def _make_user(username, role):
            user = User.objects.create_user(
                username=username,
                email=username,
                password='testpass123',
            )
            Membership.objects.create(user=user, business=self.business, role=role)
            return user

        self.owner = _make_user('owner@test.com', 'owner')
        self.admin = _make_user('admin@test.com', 'admin')
        self.manager = _make_user('manager@test.com', 'manager')
        self.cashier = _make_user('cashier@test.com', 'cashier')
        self.staff = _make_user('staff@test.com', 'staff')
        self.viewer = _make_user('viewer@test.com', 'viewer')

        self.client = APIClient()

    # ------------------------------------------------------------------
    # Owner — must receive pos_access_code equal to Business.slug
    # ------------------------------------------------------------------

    def test_owner_receives_pos_access_code(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('pos_access_code', response.data)
        self.assertEqual(response.data['pos_access_code'], self.business.slug)
        self.assertIsNotNone(response.data['pos_access_code'])

    def test_owner_pos_access_code_matches_slug(self):
        """pos_access_code must equal Business.slug exactly (no truncation, no transform)."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(_URL)

        self.assertEqual(response.data['pos_access_code'], self.business.slug)

    # ------------------------------------------------------------------
    # Admin — must receive pos_access_code
    # ------------------------------------------------------------------

    def test_admin_receives_pos_access_code(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('pos_access_code', response.data)
        self.assertEqual(response.data['pos_access_code'], self.business.slug)

    # ------------------------------------------------------------------
    # Manager — must NOT receive pos_access_code
    # ------------------------------------------------------------------

    def test_manager_does_not_receive_pos_access_code(self):
        self.client.force_authenticate(user=self.manager)
        response = self.client.get(_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn('pos_access_code', response.data)

    # ------------------------------------------------------------------
    # Cashier / staff / viewer — must NOT receive pos_access_code
    # ------------------------------------------------------------------

    def test_cashier_does_not_receive_pos_access_code(self):
        self.client.force_authenticate(user=self.cashier)
        response = self.client.get(_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn('pos_access_code', response.data)

    def test_staff_does_not_receive_pos_access_code(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn('pos_access_code', response.data)

    def test_viewer_does_not_receive_pos_access_code(self):
        self.client.force_authenticate(user=self.viewer)
        response = self.client.get(_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn('pos_access_code', response.data)

    # ------------------------------------------------------------------
    # Cache-Control header
    # ------------------------------------------------------------------

    def test_response_has_no_store_cache_header(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(_URL)

        self.assertEqual(response['Cache-Control'], 'no-store')

    # ------------------------------------------------------------------
    # Unauthenticated
    # ------------------------------------------------------------------

    def test_unauthenticated_is_rejected(self):
        response = self.client.get(_URL)
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
