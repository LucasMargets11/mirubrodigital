"""
CRUD + validation tests for AppointmentProfessional (`apps.appointments`).
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, Subscription, BusinessPlan

from ..models import AppointmentProfessional, AppointmentService

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


class AppointmentProfessionalModelTests(TestCase):

    def test_unique_name_per_business(self):
        biz = _create_business()
        AppointmentProfessional.objects.create(business=biz, name='Ana')
        with self.assertRaises(Exception):
            AppointmentProfessional.objects.create(business=biz, name='Ana')

    def test_same_name_allowed_in_different_business(self):
        biz_a = _create_business('A', 'a')
        biz_b = _create_business('B', 'b')
        AppointmentProfessional.objects.create(business=biz_a, name='Ana')
        # Should not raise.
        AppointmentProfessional.objects.create(business=biz_b, name='Ana')


class AppointmentProfessionalAPITests(APITestCase):

    def setUp(self):
        self.biz = _create_business()
        self.owner = _auth_client(self.client, self.biz, role='owner')
        self.service = AppointmentService.objects.create(
            business=self.biz, name='Corte de pelo', duration_minutes=30, price=1000,
        )

    def _create_professional(self, **overrides):
        payload = {'name': 'Ana Pérez'}
        payload.update(overrides)
        return self.client.post('/api/v1/appointments/professionals/', payload, format='json')

    def test_create_professional_minimal(self):
        resp = self._create_professional()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['name'], 'Ana Pérez')
        self.assertEqual(resp.data['services'], [])
        self.assertTrue(resp.data['is_active'])

    def test_create_professional_with_services(self):
        resp = self._create_professional(service_ids=[str(self.service.id)])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(len(resp.data['services']), 1)
        self.assertEqual(resp.data['services'][0]['id'], str(self.service.id))

    def test_create_professional_with_contact_info(self):
        resp = self._create_professional(description='Estilista senior', phone='11-5555-5555', email='ana@example.com')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['phone'], '11-5555-5555')
        self.assertEqual(resp.data['email'], 'ana@example.com')

    def test_service_from_other_business_rejected(self):
        other_biz = _create_business(name='Other Biz', slug='other-biz')
        other_service = AppointmentService.objects.create(
            business=other_biz, name='Otro servicio', duration_minutes=30, price=100,
        )
        resp = self._create_professional(service_ids=[str(other_service.id)])
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('service_ids', resp.data)

    def test_duplicate_professional_name_rejected(self):
        self._create_professional(name='Ana')
        resp = self._create_professional(name='ana')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('name', resp.data)

    def test_update_professional_services(self):
        create_resp = self._create_professional()
        professional_id = create_resp.data['id']
        resp = self.client.patch(
            f'/api/v1/appointments/professionals/{professional_id}/',
            {'service_ids': [str(self.service.id)]},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(len(resp.data['services']), 1)

    def test_update_professional_can_clear_services(self):
        create_resp = self._create_professional(service_ids=[str(self.service.id)])
        professional_id = create_resp.data['id']
        resp = self.client.patch(
            f'/api/v1/appointments/professionals/{professional_id}/',
            {'service_ids': []},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['services'], [])

    def test_deactivate_professional_is_soft_delete(self):
        create_resp = self._create_professional()
        professional_id = create_resp.data['id']
        resp = self.client.delete(f'/api/v1/appointments/professionals/{professional_id}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        professional = AppointmentProfessional.objects.get(pk=professional_id)
        self.assertFalse(professional.is_active)

    def test_list_excludes_inactive_by_default(self):
        create_resp = self._create_professional()
        professional_id = create_resp.data['id']
        self.client.delete(f'/api/v1/appointments/professionals/{professional_id}/')
        resp = self.client.get('/api/v1/appointments/professionals/')
        ids = [item['id'] for item in resp.data]
        self.assertNotIn(professional_id, ids)

    def test_list_includes_inactive_when_requested(self):
        create_resp = self._create_professional()
        professional_id = create_resp.data['id']
        self.client.delete(f'/api/v1/appointments/professionals/{professional_id}/')
        resp = self.client.get('/api/v1/appointments/professionals/?include_inactive=true')
        ids = [item['id'] for item in resp.data]
        self.assertIn(professional_id, ids)

    def test_search_by_name(self):
        self._create_professional(name='Ana')
        self._create_professional(name='Bruno')
        resp = self.client.get('/api/v1/appointments/professionals/?search=ana')
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['name'], 'Ana')

    def test_zero_professionals_is_a_valid_state(self):
        resp = self.client.get('/api/v1/appointments/professionals/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data, [])

    def test_viewer_role_cannot_manage(self):
        viewer_biz = _create_business(name='Viewer Biz', slug='viewer-biz')
        _auth_client(self.client, viewer_biz, role='viewer')
        resp = self.client.post('/api/v1/appointments/professionals/', {'name': 'Ana'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_viewer_role_can_view(self):
        viewer_biz = _create_business(name='Viewer Biz 2', slug='viewer-biz-2')
        _auth_client(self.client, viewer_biz, role='viewer')
        resp = self.client.get('/api/v1/appointments/professionals/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
