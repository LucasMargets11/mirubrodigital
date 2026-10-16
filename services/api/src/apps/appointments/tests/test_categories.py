"""
CRUD + validation tests for AppointmentCategory (`apps.appointments`).
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, Subscription, BusinessPlan

from ..models import AppointmentCategory

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


class AppointmentCategoryModelTests(TestCase):

    def test_unique_name_per_business(self):
        biz = _create_business()
        AppointmentCategory.objects.create(business=biz, name='Corte de pelo')
        with self.assertRaises(Exception):
            AppointmentCategory.objects.create(business=biz, name='Corte de pelo')

    def test_same_name_allowed_across_businesses(self):
        biz1 = _create_business(name='Biz 1', slug='biz-1')
        biz2 = _create_business(name='Biz 2', slug='biz-2')
        AppointmentCategory.objects.create(business=biz1, name='Corte de pelo')
        AppointmentCategory.objects.create(business=biz2, name='Corte de pelo')
        self.assertEqual(AppointmentCategory.objects.count(), 2)


class AppointmentCategoryAPITests(APITestCase):

    def setUp(self):
        self.biz = _create_business()
        self.owner = _auth_client(self.client, self.biz, role='owner')

    def test_list_categories_empty(self):
        resp = self.client.get('/api/v1/appointments/categories/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data, [])

    def test_create_category(self):
        resp = self.client.post('/api/v1/appointments/categories/', {'name': 'Manicura'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['name'], 'Manicura')
        self.assertTrue(resp.data['is_active'])
        self.assertEqual(resp.data['services_count'], 0)

    def test_create_category_name_too_short(self):
        resp = self.client.post('/api/v1/appointments/categories/', {'name': 'A'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('name', resp.data)

    def test_create_duplicate_category_name_rejected(self):
        self.client.post('/api/v1/appointments/categories/', {'name': 'Manicura'}, format='json')
        resp = self.client.post('/api/v1/appointments/categories/', {'name': 'manicura'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('name', resp.data)

    def test_update_category(self):
        create_resp = self.client.post('/api/v1/appointments/categories/', {'name': 'Manicura'}, format='json')
        category_id = create_resp.data['id']
        resp = self.client.patch(f'/api/v1/appointments/categories/{category_id}/', {'name': 'Manicura y pedicura'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['name'], 'Manicura y pedicura')

    def test_deactivate_category_is_soft_delete(self):
        create_resp = self.client.post('/api/v1/appointments/categories/', {'name': 'Manicura'}, format='json')
        category_id = create_resp.data['id']
        resp = self.client.delete(f'/api/v1/appointments/categories/{category_id}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        category = AppointmentCategory.objects.get(pk=category_id)
        self.assertFalse(category.is_active)

    def test_inactive_categories_excluded_by_default(self):
        create_resp = self.client.post('/api/v1/appointments/categories/', {'name': 'Manicura'}, format='json')
        category_id = create_resp.data['id']
        self.client.delete(f'/api/v1/appointments/categories/{category_id}/')
        resp = self.client.get('/api/v1/appointments/categories/')
        self.assertEqual(resp.data, [])
        resp_all = self.client.get('/api/v1/appointments/categories/?include_inactive=true')
        self.assertEqual(len(resp_all.data), 1)

    def test_viewer_role_cannot_manage(self):
        viewer_biz = _create_business(name='Viewer Biz', slug='viewer-biz')
        _auth_client(self.client, viewer_biz, role='viewer')
        resp = self.client.post('/api/v1/appointments/categories/', {'name': 'Manicura'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_viewer_role_can_list(self):
        viewer_biz = _create_business(name='Viewer Biz 2', slug='viewer-biz-2')
        _auth_client(self.client, viewer_biz, role='viewer')
        resp = self.client.get('/api/v1/appointments/categories/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_unauthenticated_blocked(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get('/api/v1/appointments/categories/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_business_without_appointments_service_blocked(self):
        gestion_biz = Business.objects.create(name='Gestion Biz', default_service='gestion', slug='gestion-biz')
        Subscription.objects.create(business=gestion_biz, plan=BusinessPlan.START, service='gestion', status='active')
        user = User.objects.create_user(username='gestion-user', password='pass1234')
        Membership.objects.create(user=user, business=gestion_biz, role='owner')
        self.client.force_authenticate(user=user)
        resp = self.client.get('/api/v1/appointments/categories/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
