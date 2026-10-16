"""
CRUD + validation tests for AppointmentException (`apps.appointments`).
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, Subscription, BusinessPlan

from ..models import AppointmentException, AppointmentProfessional

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


class AppointmentExceptionModelTests(TestCase):

    def test_closed_with_hours_rejected_at_db_level(self):
        biz = _create_business()
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                AppointmentException.objects.create(
                    business=biz, date='2026-12-25', is_closed=True,
                    start_time='09:00', end_time='13:00',
                )

    def test_open_without_hours_rejected_at_db_level(self):
        biz = _create_business()
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                AppointmentException.objects.create(
                    business=biz, date='2026-12-24', is_closed=False,
                )


class AppointmentExceptionAPITests(APITestCase):

    def setUp(self):
        self.biz = _create_business()
        self.owner = _auth_client(self.client, self.biz, role='owner')
        self.professional = AppointmentProfessional.objects.create(business=self.biz, name='Lucas')

    def _create_exception(self, **overrides):
        payload = {'date': '2026-12-25', 'is_closed': True}
        payload.update(overrides)
        return self.client.post('/api/v1/appointments/exceptions/', payload, format='json')

    def test_create_closed_exception(self):
        resp = self._create_exception()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertTrue(resp.data['is_closed'])
        self.assertIsNone(resp.data['start_time'])
        self.assertIsNone(resp.data['end_time'])

    def test_create_special_hours_exception(self):
        resp = self._create_exception(date='2026-12-24', is_closed=False, start_time='09:00', end_time='13:00')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertFalse(resp.data['is_closed'])
        self.assertEqual(resp.data['start_time'], '09:00:00')

    def test_open_exception_requires_hours(self):
        resp = self._create_exception(date='2026-12-24', is_closed=False)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_open_exception_start_after_end_rejected(self):
        resp = self._create_exception(date='2026-12-24', is_closed=False, start_time='13:00', end_time='09:00')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_closed_exception_ignores_provided_hours(self):
        resp = self._create_exception(is_closed=True, start_time='09:00', end_time='13:00')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertIsNone(resp.data['start_time'])
        self.assertIsNone(resp.data['end_time'])

    def test_create_professional_exception(self):
        resp = self._create_exception(professional_id=str(self.professional.id))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['professional']['id'], str(self.professional.id))

    def test_professional_from_other_business_rejected(self):
        other_biz = _create_business(name='Other Biz', slug='other-biz-exc')
        other_professional = AppointmentProfessional.objects.create(business=other_biz, name='Bruno')
        resp = self._create_exception(professional_id=str(other_professional.id))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('professional_id', resp.data)

    def test_duplicate_exception_same_date_rejected(self):
        self._create_exception(date='2026-12-25')
        resp = self._create_exception(date='2026-12-25')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_same_date_allowed_for_business_and_professional(self):
        """A business-wide exception and a professional-specific one on the same
        date do not conflict with each other."""
        self._create_exception(date='2026-12-25')
        resp = self._create_exception(date='2026-12-25', professional_id=str(self.professional.id))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_update_exception_note(self):
        create_resp = self._create_exception()
        exception_id = create_resp.data['id']
        resp = self.client.patch(
            f'/api/v1/appointments/exceptions/{exception_id}/',
            {'note': 'Feriado nacional'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['note'], 'Feriado nacional')

    def test_update_does_not_conflict_with_itself(self):
        create_resp = self._create_exception()
        exception_id = create_resp.data['id']
        resp = self.client.patch(
            f'/api/v1/appointments/exceptions/{exception_id}/',
            {'note': 'Actualizado'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

    def test_delete_exception(self):
        create_resp = self._create_exception()
        exception_id = create_resp.data['id']
        resp = self.client.delete(f'/api/v1/appointments/exceptions/{exception_id}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(AppointmentException.objects.filter(pk=exception_id).exists())

    def test_filter_by_professional(self):
        self._create_exception(date='2026-12-25')
        self._create_exception(date='2026-12-26', professional_id=str(self.professional.id))
        resp = self.client.get(f'/api/v1/appointments/exceptions/?professional={self.professional.id}')
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['professional']['id'], str(self.professional.id))

    def test_viewer_role_cannot_manage(self):
        viewer_biz = _create_business(name='Viewer Biz', slug='viewer-biz-exc')
        _auth_client(self.client, viewer_biz, role='viewer')
        resp = self.client.post('/api/v1/appointments/exceptions/', {'date': '2026-12-25', 'is_closed': True}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_viewer_role_can_view(self):
        viewer_biz = _create_business(name='Viewer Biz 2', slug='viewer-biz-exc-2')
        _auth_client(self.client, viewer_biz, role='viewer')
        resp = self.client.get('/api/v1/appointments/exceptions/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
