"""
CRUD + validation tests for AppointmentService (`apps.appointments`).
"""
from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, Subscription, BusinessPlan

from ..models import AppointmentCategory, AppointmentService

User = get_user_model()


def _create_business(name='Turnos Biz', slug='turnos-biz'):
    biz = Business.objects.create(name=name, default_service='appointments', slug=slug)
    Subscription.objects.create(business=biz, plan=BusinessPlan.APPOINTMENTS_BASE, service='appointments', status='active')
    return biz


def _auth_client(client, business, role='owner'):
    user = User.objects.create_user(username=f'u-{business.slug}', password='pass1234')
    Membership.objects.create(user=user, business=business, role=role)
    client.force_authenticate(user=user)
    return user


class AppointmentServiceModelTests(TestCase):

    def test_duration_check_constraint(self):
        biz = _create_business()
        with self.assertRaises(Exception):
            AppointmentService.objects.create(business=biz, name='Corte', duration_minutes=0, price=100)

    def test_price_check_constraint(self):
        biz = _create_business()
        with self.assertRaises(Exception):
            AppointmentService.objects.create(business=biz, name='Corte', duration_minutes=30, price=Decimal('-1'))


class AppointmentServiceAPITests(APITestCase):

    def setUp(self):
        self.biz = _create_business()
        self.owner = _auth_client(self.client, self.biz, role='owner')
        self.category = AppointmentCategory.objects.create(business=self.biz, name='Peluquería')

    def _create_service(self, **overrides):
        payload = {
            'name': 'Corte de pelo',
            'duration_minutes': 30,
            'price': '1000.00',
            'deposit_type': 'none',
            'deposit_value': '0',
        }
        payload.update(overrides)
        return self.client.post('/api/v1/appointments/services/', payload, format='json')

    def test_create_service_minimal(self):
        resp = self._create_service()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['name'], 'Corte de pelo')
        self.assertEqual(resp.data['deposit_value'], '0.00')

    def test_create_service_with_category(self):
        resp = self._create_service(category_id=str(self.category.id))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['category']['id'], str(self.category.id))

    def test_category_from_other_business_rejected(self):
        other_biz = _create_business(name='Other Biz', slug='other-biz')
        other_category = AppointmentCategory.objects.create(business=other_biz, name='Otra categoría')
        resp = self._create_service(category_id=str(other_category.id))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('category_id', resp.data)

    def test_duration_must_be_positive(self):
        resp = self._create_service(duration_minutes=0)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('duration_minutes', resp.data)

    def test_price_must_be_non_negative(self):
        resp = self._create_service(price='-10')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('price', resp.data)

    def test_deposit_none_forces_zero_value(self):
        resp = self._create_service(deposit_type='none', deposit_value='500')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['deposit_value'], '0.00')

    def test_deposit_fixed_valid(self):
        resp = self._create_service(deposit_type='fixed', deposit_value='300', price='1000')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['deposit_value'], '300.00')

    def test_deposit_fixed_cannot_exceed_price(self):
        resp = self._create_service(deposit_type='fixed', deposit_value='1500', price='1000')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('deposit_value', resp.data)

    def test_deposit_fixed_negative_rejected(self):
        resp = self._create_service(deposit_type='fixed', deposit_value='-1', price='1000')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('deposit_value', resp.data)

    def test_deposit_percentage_valid(self):
        resp = self._create_service(deposit_type='percentage', deposit_value='50')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['deposit_value'], '50.00')

    def test_deposit_percentage_zero_rejected(self):
        resp = self._create_service(deposit_type='percentage', deposit_value='0')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('deposit_value', resp.data)

    def test_deposit_percentage_over_100_rejected(self):
        resp = self._create_service(deposit_type='percentage', deposit_value='101')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('deposit_value', resp.data)

    def test_deposit_percentage_exactly_100_allowed(self):
        resp = self._create_service(deposit_type='percentage', deposit_value='100')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_update_service(self):
        create_resp = self._create_service()
        service_id = create_resp.data['id']
        resp = self.client.patch(f'/api/v1/appointments/services/{service_id}/', {'price': '1200.00'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['price'], '1200.00')

    def test_deactivate_service_is_soft_delete(self):
        create_resp = self._create_service()
        service_id = create_resp.data['id']
        resp = self.client.delete(f'/api/v1/appointments/services/{service_id}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        service = AppointmentService.objects.get(pk=service_id)
        self.assertFalse(service.is_active)

    def test_filter_by_category(self):
        self._create_service(name='Corte', category_id=str(self.category.id))
        self._create_service(name='Tinte')
        resp = self.client.get(f'/api/v1/appointments/services/?category={self.category.id}')
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['name'], 'Corte')

    def test_duplicate_service_name_rejected(self):
        self._create_service(name='Corte')
        resp = self._create_service(name='corte')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('name', resp.data)

    def test_viewer_role_cannot_manage(self):
        viewer_biz = _create_business(name='Viewer Biz', slug='viewer-biz')
        _auth_client(self.client, viewer_biz, role='viewer')
        resp = self.client.post('/api/v1/appointments/services/', {
            'name': 'Corte', 'duration_minutes': 30, 'price': '100',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
