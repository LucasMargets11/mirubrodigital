"""
CRUD + validation tests for AppointmentSchedule (`apps.appointments`).
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, Subscription, BusinessPlan

from ..models import AppointmentProfessional, AppointmentSchedule

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


class AppointmentScheduleModelTests(TestCase):

    def test_start_before_end_constraint(self):
        biz = _create_business()
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                AppointmentSchedule.objects.create(
                    business=biz, weekday=0, start_time='13:00', end_time='09:00',
                )


class AppointmentScheduleAPITests(APITestCase):

    def setUp(self):
        self.biz = _create_business()
        self.owner = _auth_client(self.client, self.biz, role='owner')
        self.professional = AppointmentProfessional.objects.create(business=self.biz, name='Ana Pérez')

    def _create_schedule(self, **overrides):
        payload = {'weekday': 0, 'start_time': '09:00', 'end_time': '13:00'}
        payload.update(overrides)
        return self.client.post('/api/v1/appointments/schedules/', payload, format='json')

    def test_create_business_wide_schedule(self):
        resp = self._create_schedule()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertIsNone(resp.data['professional'])
        self.assertEqual(resp.data['weekday'], 0)

    def test_create_professional_schedule(self):
        resp = self._create_schedule(professional_id=str(self.professional.id))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['professional']['id'], str(self.professional.id))

    def test_multiple_blocks_same_day_allowed(self):
        self._create_schedule(start_time='09:00', end_time='13:00')
        resp = self._create_schedule(start_time='15:00', end_time='19:00')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_start_after_end_rejected(self):
        resp = self._create_schedule(start_time='13:00', end_time='09:00')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_start_equal_end_rejected(self):
        resp = self._create_schedule(start_time='09:00', end_time='09:00')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_overlapping_block_same_day_rejected(self):
        self._create_schedule(start_time='09:00', end_time='13:00')
        resp = self._create_schedule(start_time='12:00', end_time='15:00')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_overlap_check_is_scoped_per_professional(self):
        """A business-wide block and a professional-specific block on the same
        day/time do not conflict with each other."""
        self._create_schedule(start_time='09:00', end_time='13:00')
        resp = self._create_schedule(start_time='09:00', end_time='13:00', professional_id=str(self.professional.id))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_overlap_check_is_scoped_per_weekday(self):
        self._create_schedule(weekday=0, start_time='09:00', end_time='13:00')
        resp = self._create_schedule(weekday=1, start_time='09:00', end_time='13:00')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_professional_from_other_business_rejected(self):
        other_biz = _create_business(name='Other Biz', slug='other-biz-sched')
        other_professional = AppointmentProfessional.objects.create(business=other_biz, name='Bruno')
        resp = self._create_schedule(professional_id=str(other_professional.id))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('professional_id', resp.data)

    def test_update_schedule_block(self):
        create_resp = self._create_schedule()
        schedule_id = create_resp.data['id']
        resp = self.client.patch(
            f'/api/v1/appointments/schedules/{schedule_id}/',
            {'end_time': '14:00'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['end_time'], '14:00:00')

    def test_update_does_not_conflict_with_itself(self):
        create_resp = self._create_schedule()
        schedule_id = create_resp.data['id']
        resp = self.client.patch(
            f'/api/v1/appointments/schedules/{schedule_id}/',
            {'start_time': '10:00'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

    def test_delete_schedule_block(self):
        create_resp = self._create_schedule()
        schedule_id = create_resp.data['id']
        resp = self.client.delete(f'/api/v1/appointments/schedules/{schedule_id}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(AppointmentSchedule.objects.filter(pk=schedule_id).exists())

    def test_filter_by_professional(self):
        self._create_schedule()
        self._create_schedule(professional_id=str(self.professional.id))
        resp = self.client.get(f'/api/v1/appointments/schedules/?professional={self.professional.id}')
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['professional']['id'], str(self.professional.id))

    def test_filter_business_wide_only(self):
        self._create_schedule()
        self._create_schedule(professional_id=str(self.professional.id))
        resp = self.client.get('/api/v1/appointments/schedules/?professional=null')
        self.assertEqual(len(resp.data), 1)
        self.assertIsNone(resp.data[0]['professional'])

    def test_viewer_role_cannot_manage(self):
        viewer_biz = _create_business(name='Viewer Biz', slug='viewer-biz-sched')
        _auth_client(self.client, viewer_biz, role='viewer')
        resp = self.client.post('/api/v1/appointments/schedules/', {'weekday': 0, 'start_time': '09:00', 'end_time': '13:00'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_viewer_role_can_view(self):
        viewer_biz = _create_business(name='Viewer Biz 2', slug='viewer-biz-sched-2')
        _auth_client(self.client, viewer_biz, role='viewer')
        resp = self.client.get('/api/v1/appointments/schedules/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
