from __future__ import annotations

import datetime as dt
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, transaction
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import Membership
from apps.billing.appointments_plans import EXTRA_PROFESSIONAL
from apps.billing.models import SubscriptionV2
from apps.billing.services.appointments import resolve_appointments_subscription_config
from apps.business.models import Business, SubscriptionAddon
from apps.customers.models import Customer

from ..models import (
    Appointment,
    AppointmentProfessional,
    AppointmentSchedule,
    AppointmentService,
)
from ..services.professional_quota import (
    ProfessionalQuotaExceeded,
    count_active_professionals,
    detect_over_limit,
)
from ..services.professionals import create_professional, set_professional_active, update_professional

User = get_user_model()


def _business(plan='appointments', *, usage_tier=None, slug=None):
    business = Business.objects.create(
        name='Professional quota',
        slug=slug or f'quota-{uuid.uuid4().hex[:8]}',
        default_service='appointments',
        status='active',
    )
    SubscriptionV2.objects.create(
        business=business,
        service_type='appointments',
        plan_code=plan,
        usage_tier=usage_tier,
        provider=SubscriptionV2.Provider.MANUAL,
        external_reference=f'SUB-{uuid.uuid4()}',
        status=SubscriptionV2.Status.ACTIVE,
    )
    return business


def _professional(business, name, *, active=True, membership=None):
    return AppointmentProfessional.objects.create(
        business=business,
        name=name,
        is_active=active,
        membership=membership,
    )


class ProfessionalQuotaModelTests(TestCase):
    def test_bulk_activation_and_creation_are_rejected(self):
        business = _business()
        inactive = _professional(business, 'Inactive', active=False)
        queryset = AppointmentProfessional.objects.filter(pk=inactive.pk)
        with self.assertRaises(ValidationError):
            queryset.update(is_active=True)
        inactive.is_active = True
        with self.assertRaises(ValidationError):
            queryset.bulk_update([inactive], ['is_active'])
        with self.assertRaises(ValidationError):
            AppointmentProfessional.objects.bulk_create([
                AppointmentProfessional(business=business, name='Bulk'),
            ])
        inactive.refresh_from_db()
        self.assertFalse(inactive.is_active)
        self.assertEqual(count_active_professionals(business), 0)

    def test_safe_bulk_changes_remain_available(self):
        business = _business()
        professional = _professional(business, 'Active')
        queryset = AppointmentProfessional.objects.filter(pk=professional.pk)
        queryset.update(is_active=False)
        professional.name = 'Renamed'
        queryset.bulk_update([professional], ['name'])
        professional.refresh_from_db()
        self.assertFalse(professional.is_active)
        self.assertEqual(professional.name, 'Renamed')

    def test_explicit_update_preserves_unrelated_changes_and_checks_quota(self):
        business = _business()
        inactive = create_professional(business=business, name='Inactive', is_active=False)
        update_professional(business=business, professional_id=inactive.pk, description='Updated')
        _professional(business, 'Ana')
        _professional(business, 'Bruno')
        with self.assertRaises(ProfessionalQuotaExceeded):
            set_professional_active(business=business, professional_id=inactive.pk, is_active=True)
        inactive.refresh_from_db()
        self.assertFalse(inactive.is_active)
        self.assertEqual(inactive.description, 'Updated')

    def test_partial_business_move_cannot_bypass_quota(self):
        business = _business()
        other = _business()
        professional = _professional(business, 'Moving')
        _professional(other, 'Ana')
        _professional(other, 'Bruno')
        professional.business = other
        professional.is_active = False
        with self.assertRaises(ProfessionalQuotaExceeded):
            professional.save(update_fields=['business'])
        professional.refresh_from_db()
        self.assertEqual(professional.business_id, business.pk)
        self.assertTrue(professional.is_active)

    def test_base_allows_two_and_rejects_third(self):
        business = _business()
        _professional(business, 'Ana')
        _professional(business, 'Bruno')
        with self.assertRaises(ProfessionalQuotaExceeded):
            _professional(business, 'Carla')

    def test_extra_professionals_extend_effective_quota(self):
        business = _business()
        subscription = SubscriptionV2.objects.get(business=business)
        SubscriptionAddon.objects.create(
            subscription_v2=subscription, code=EXTRA_PROFESSIONAL, quantity=1,
        )
        config = resolve_appointments_subscription_config(subscription)
        self.assertEqual(config.effective_professional_limit, 3)
        self.assertEqual(config.included_secondary_users, 2)
        for name in ('Ana', 'Bruno', 'Carla'):
            _professional(business, name)
        with self.assertRaises(ProfessionalQuotaExceeded):
            _professional(business, 'Diego')

    def test_pro_and_ai_allow_five_plus_extras(self):
        for plan, tier in (('appointments_pro', None), ('appointments_ai', 'ai_300')):
            with self.subTest(plan=plan):
                business = _business(plan, usage_tier=tier)
                for index in range(5):
                    _professional(business, f'Professional {index}')
                with self.assertRaises(ProfessionalQuotaExceeded):
                    _professional(business, 'Excess')

                subscription = SubscriptionV2.objects.get(business=business)
                SubscriptionAddon.objects.create(
                    subscription_v2=subscription, code=EXTRA_PROFESSIONAL, quantity=1,
                )
                _professional(business, 'Extra')
                with self.assertRaises(ProfessionalQuotaExceeded):
                    _professional(business, 'Second excess')

    def test_inactive_professionals_do_not_consume_quota(self):
        business = _business()
        _professional(business, 'Inactive', active=False)
        _professional(business, 'Ana')
        _professional(business, 'Bruno')
        with self.assertRaises(ProfessionalQuotaExceeded):
            _professional(business, 'Carla')
        self.assertEqual(count_active_professionals(business), 2)

    def test_reactivation_is_checked_against_quota(self):
        business = _business()
        inactive = _professional(business, 'Inactive', active=False)
        _professional(business, 'Ana')
        _professional(business, 'Bruno')
        inactive.is_active = True
        with self.assertRaises(ProfessionalQuotaExceeded):
            inactive.save(update_fields=['is_active', 'updated_at'])
        inactive.refresh_from_db()
        self.assertFalse(inactive.is_active)

    def test_downgrade_detector_reports_without_mutating(self):
        business = _business('appointments_pro')
        for index in range(3):
            _professional(business, f'Professional {index}')
        state = detect_over_limit(business, effective_limit=2)
        self.assertEqual(state.active_count, 3)
        self.assertEqual(state.effective_limit, 2)
        self.assertTrue(state.over_limit)
        self.assertEqual(count_active_professionals(business), 3)

    def test_membership_link_is_pro_only_and_unique_for_active_professionals(self):
        for plan, tier, should_allow in (
            ('appointments', None, False),
            ('appointments_pro', None, True),
            ('appointments_ai', 'ai_1500', True),
        ):
            with self.subTest(plan=plan):
                business = _business(plan, usage_tier=tier)
                user = User.objects.create_user(username=f'user-{uuid.uuid4().hex}', password='Pass12345')
                membership = Membership.objects.create(
                    user=user, business=business, role='professional',
                ) if should_allow else None
                if not should_allow:
                    base_user = User.objects.create_user(
                        username=f'user-{uuid.uuid4().hex}', password='Pass12345',
                    )
                    with self.assertRaises(ValidationError):
                        Membership.objects.create(
                            user=base_user, business=business, role='professional',
                        )
                    continue
                first = _professional(business, 'Linked', membership=membership)
                self.assertEqual(first.membership_id, membership.pk)
                with self.assertRaises(IntegrityError), transaction.atomic():
                    _professional(business, 'Duplicate', membership=membership)

    def test_owner_professional_is_counted_as_an_active_professional(self):
        business = _business('appointments_pro')
        owner = User.objects.create_user(username=f'owner-{uuid.uuid4().hex}', password='Pass12345')
        Membership.objects.create(user=owner, business=business, role='owner')
        _professional(business, 'Owner')
        self.assertEqual(count_active_professionals(business), 1)


@skipUnlessDBFeature('has_select_for_update')
class ProfessionalQuotaConcurrencyTests(TransactionTestCase):
    # Legacy unmanaged Treasury tables retain FKs; cascade the isolated test flush.
    available_apps = settings.INSTALLED_APPS
    reset_sequences = True

    def test_concurrent_activation_cannot_exceed_limit(self):
        business = _business()
        _professional(business, 'Existing')
        barrier = threading.Barrier(2)

        def create(name):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                create_professional(business=business, name=name)
                return 'created'
            except ProfessionalQuotaExceeded:
                return 'rejected'
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(create, ('Concurrent A', 'Concurrent B')))

        self.assertCountEqual(results, ['created', 'rejected'])
        self.assertEqual(count_active_professionals(business), 2)

    def test_concurrent_reactivation_cannot_exceed_limit(self):
        business = _business()
        _professional(business, 'Existing')
        inactive = [
            _professional(business, name, active=False)
            for name in ('Inactive A', 'Inactive B')
        ]
        barrier = threading.Barrier(2)

        def reactivate(professional):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                set_professional_active(
                    business=business, professional_id=professional.pk, is_active=True,
                )
                return 'activated'
            except ProfessionalQuotaExceeded:
                return 'rejected'
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(reactivate, inactive))
        self.assertCountEqual(results, ['activated', 'rejected'])
        self.assertEqual(count_active_professionals(business), 2)
        self.assertEqual(AppointmentProfessional.objects.filter(business=business, is_active=False).count(), 1)

    def test_concurrent_api_creates_and_reactivations_cannot_exceed_limit(self):
        for operation in ('create', 'reactivate'):
            with self.subTest(operation=operation):
                business = _business()
                owner = User.objects.create_user(username=f'owner-{uuid.uuid4().hex}')
                Membership.objects.create(user=owner, business=business, role='owner')
                _professional(business, 'Existing')
                inactive = [
                    _professional(business, name, active=False)
                    for name in ('Inactive A', 'Inactive B')
                ] if operation == 'reactivate' else []
                barrier = threading.Barrier(2)

                def mutate(index):
                    close_old_connections()
                    try:
                        client = APIClient()
                        client.force_authenticate(user=owner)
                        client.cookies['bid'] = str(business.pk)
                        barrier.wait(timeout=10)
                        if operation == 'create':
                            response = client.post(
                                '/api/v1/appointments/professionals/',
                                {'name': f'Concurrent {index}'}, format='json',
                            )
                        else:
                            response = client.patch(
                                f'/api/v1/appointments/professionals/{inactive[index].pk}/',
                                {'is_active': True}, format='json',
                            )
                        return response.status_code
                    finally:
                        close_old_connections()

                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(mutate, (0, 1)))
                success = status.HTTP_201_CREATED if operation == 'create' else status.HTTP_200_OK
                self.assertCountEqual(results, [success, status.HTTP_400_BAD_REQUEST])
                self.assertEqual(count_active_professionals(business), 2)


class ProfessionalScopeAPITests(APITestCase):
    def setUp(self):
        self.business = _business('appointments_pro')
        self.service = AppointmentService.objects.create(
            business=self.business,
            name='Consulta',
            duration_minutes=30,
            price=Decimal('1000'),
        )
        self.owner_professional = self._linked_professional('owner-professional')
        self.other_professional = self._linked_professional('other-professional')
        self.own_customer = Customer.objects.create(business=self.business, name='Own customer')
        self.other_customer = Customer.objects.create(business=self.business, name='Other customer')
        self.own_appointment = self._appointment(self.owner_professional, self.own_customer)
        self.other_appointment = self._appointment(self.other_professional, self.own_customer)
        self.own_schedule = AppointmentSchedule.objects.create(
            business=self.business,
            professional=self.owner_professional,
            weekday=0,
            start_time='09:00',
            end_time='10:00',
        )
        self.other_schedule = AppointmentSchedule.objects.create(
            business=self.business,
            professional=self.other_professional,
            weekday=0,
            start_time='10:00',
            end_time='11:00',
        )
        self.client.force_authenticate(user=self.owner_professional.membership.user)
        self.client.cookies['bid'] = str(self.business.pk)

    def _linked_professional(self, username):
        user = User.objects.create_user(username=f'{username}-{uuid.uuid4().hex}', password='Pass12345')
        membership = Membership.objects.create(
            user=user, business=self.business, role='professional',
        )
        return _professional(self.business, username, membership=membership)

    def _appointment(self, professional, customer):
        now = timezone.now()
        return Appointment.objects.create(
            business=self.business,
            service=self.service,
            professional=professional,
            customer=customer,
            customer_name=customer.name,
            customer_phone='1111111111',
            start_at=now,
            end_at=now + dt.timedelta(minutes=30),
            service_name=self.service.name,
            service_duration_minutes=self.service.duration_minutes,
            service_price=self.service.price,
            deposit_type=self.service.deposit_type,
            deposit_value=self.service.deposit_value,
        )

    def test_professional_sees_only_own_appointments_and_customers(self):
        response = self.client.get('/api/v1/appointments/appointments/')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual([row['id'] for row in response.data], [str(self.own_appointment.pk)])

        customers = self.client.get('/api/v1/customers/')
        self.assertEqual(customers.status_code, status.HTTP_200_OK, customers.data)
        self.assertEqual([row['id'] for row in customers.data['results']], [str(self.own_customer.pk)])
        detail = self.client.get(f'/api/v1/customers/{self.own_customer.pk}/')
        self.assertEqual(detail.status_code, status.HTTP_200_OK, detail.data)
        self.assertEqual(detail.data['appointments_summary']['total'], 1)

        unrelated = self.client.get(f'/api/v1/customers/{self.other_customer.pk}/')
        self.assertEqual(unrelated.status_code, status.HTTP_404_NOT_FOUND)

        history = self.client.get(f'/api/v1/customers/{self.own_customer.pk}/appointments/')
        self.assertEqual(history.status_code, status.HTTP_200_OK, history.data)
        self.assertEqual([row['id'] for row in history.data['results']], [str(self.own_appointment.pk)])

        other_history = self.client.get(f'/api/v1/customers/{self.other_customer.pk}/appointments/')
        self.assertEqual(other_history.status_code, status.HTTP_404_NOT_FOUND)

        timeline = self.client.get(
            f'/api/v1/customers/{self.own_customer.pk}/timeline/?types=appointment',
        )
        self.assertEqual(timeline.status_code, status.HTTP_200_OK, timeline.data)
        self.assertEqual(
            [row['id'] for row in timeline.data['results']],
            [f'appointment:{self.own_appointment.pk}'],
        )

    def test_professional_can_manage_only_own_appointment_and_schedule(self):
        own = self.client.patch(
            f'/api/v1/appointments/appointments/{self.own_appointment.pk}/',
            {'notes': 'Own note'},
            format='json',
        )
        self.assertEqual(own.status_code, status.HTTP_200_OK, own.data)

        other = self.client.patch(
            f'/api/v1/appointments/appointments/{self.other_appointment.pk}/',
            {'notes': 'Forbidden note'},
            format='json',
        )
        self.assertEqual(other.status_code, status.HTTP_404_NOT_FOUND)

        schedules = self.client.get('/api/v1/appointments/schedules/')
        self.assertEqual(schedules.status_code, status.HTTP_200_OK, schedules.data)
        self.assertEqual([row['id'] for row in schedules.data], [str(self.own_schedule.pk)])

        own_schedule_update = self.client.patch(
            f'/api/v1/appointments/schedules/{self.own_schedule.pk}/',
            {'start_time': '08:00'},
            format='json',
        )
        self.assertEqual(own_schedule_update.status_code, status.HTTP_200_OK, own_schedule_update.data)

        forbidden_update = self.client.patch(
            f'/api/v1/appointments/schedules/{self.other_schedule.pk}/',
            {'start_time': '11:00'},
            format='json',
        )
        self.assertEqual(forbidden_update.status_code, status.HTTP_404_NOT_FOUND)

    def test_global_owner_keeps_global_appointment_view(self):
        owner = User.objects.create_user(username=f'global-{uuid.uuid4().hex}', password='Pass12345')
        Membership.objects.create(user=owner, business=self.business, role='owner')
        self.client.force_authenticate(user=owner)
        response = self.client.get('/api/v1/appointments/appointments/')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertCountEqual(
            [row['id'] for row in response.data],
            [str(self.own_appointment.pk), str(self.other_appointment.pk)],
        )
