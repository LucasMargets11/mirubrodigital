from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, BusinessPlan, Subscription

from ..models import AppointmentProfessional, AppointmentSchedule, AppointmentService

User = get_user_model()


class AppointmentOnboardingStatusAPITests(APITestCase):
    def setUp(self):
        self.business = Business.objects.create(
            name='Turnos Onboarding',
            default_service='appointments',
            slug='turnos-onboarding',
        )
        Subscription.objects.create(
            business=self.business,
            plan=BusinessPlan.APPOINTMENTS_BASE,
            service='appointments',
            status='active',
        )
        user = User.objects.create_user(username='turnos-onboarding-owner', password='pass1234')
        Membership.objects.create(user=user, business=self.business, role='owner')
        self.client.force_authenticate(user=user)
        self.url = '/api/v1/appointments/onboarding-status/'

    def create_service(self, **overrides):
        payload = {
            'business': self.business,
            'name': 'Consulta',
            'duration_minutes': 30,
            'price': 100,
        }
        payload.update(overrides)
        return AppointmentService.objects.create(**payload)

    def create_schedule(self, *, professional=None, start_time='09:00', end_time='10:00'):
        return AppointmentSchedule.objects.create(
            business=self.business,
            professional=professional,
            weekday=0,
            start_time=start_time,
            end_time=end_time,
        )

    def test_no_service_or_schedule_is_not_ready(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['active_services_count'], 0)
        self.assertFalse(response.data['has_valid_availability'])
        self.assertFalse(response.data['ready_to_receive_bookings'])

    def test_inactive_service_does_not_complete_service_step(self):
        self.create_service(is_active=False)

        response = self.client.get(self.url)

        self.assertEqual(response.data['active_services_count'], 0)
        self.assertFalse(response.data['has_active_services'])
        self.assertFalse(response.data['has_reservable_service'])
        self.assertFalse(response.data['ready_to_receive_bookings'])

    def test_invalid_legacy_deposit_does_not_make_service_reservable(self):
        self.create_service(
            deposit_type='fixed',
            deposit_value=0,
        )
        self.create_schedule()

        response = self.client.get(self.url)

        self.assertEqual(response.data['active_services_count'], 1)
        self.assertTrue(response.data['has_active_services'])
        self.assertFalse(response.data['has_reservable_service'])
        self.assertFalse(response.data['has_valid_availability'])
        self.assertFalse(response.data['ready_to_receive_bookings'])

    def test_business_schedule_is_sufficient_without_professionals(self):
        self.create_service()
        self.create_schedule()

        with patch(
            'apps.appointments.public_page.public_booking_snapshot',
            return_value={'available': True},
        ):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['has_active_services'])
        self.assertTrue(response.data['has_valid_availability'])
        self.assertEqual(response.data['active_professionals_count'], 0)
        self.assertTrue(response.data['ready_to_receive_bookings'])

    def test_missing_public_booking_page_keeps_agenda_not_ready(self):
        self.create_service()
        self.create_schedule()

        with patch(
            'apps.appointments.public_page.public_booking_snapshot',
            return_value={'available': False},
        ):
            response = self.client.get(self.url)

        self.assertTrue(response.data['has_active_services'])
        self.assertTrue(response.data['has_valid_availability'])
        self.assertFalse(response.data['public_booking_available'])
        self.assertFalse(response.data['ready_to_receive_bookings'])

    def test_professional_service_needs_overlapping_business_and_professional_hours(self):
        service = self.create_service()
        professional = AppointmentProfessional.objects.create(
            business=self.business,
            name='Ana',
        )
        professional.services.add(service)
        self.create_schedule()

        response = self.client.get(self.url)
        self.assertFalse(response.data['has_valid_availability'])

        self.create_schedule(professional=professional, start_time='09:15', end_time='10:00')
        response = self.client.get(self.url)
        self.assertTrue(response.data['has_valid_availability'])
        self.assertEqual(response.data['active_professionals_count'], 1)

    def test_too_short_schedule_does_not_count_as_bookable_availability(self):
        self.create_service(duration_minutes=30)
        self.create_schedule(start_time='09:00', end_time='09:29')

        response = self.client.get(self.url)

        self.assertFalse(response.data['has_valid_availability'])
