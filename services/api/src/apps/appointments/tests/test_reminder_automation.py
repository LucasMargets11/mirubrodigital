"""Recordatorios internos automáticos desde Turnos (CUSTOMER 07B).

Configuración por Business (`/api/v1/appointments/reminder-automation/`) y
reconciliación en el ciclo de vida real del turno: alta interna, reserva
pública, confirmación por webhook de pago, reprogramación, cancelación,
vencimiento y no-show. Nada se envía al cliente: solo `CustomerReminder`.
"""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone as dj_timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.accounts.rbac import permissions_for_service
from apps.customers.models import Customer, CustomerReminder, CustomerReminderAutomationSettings

from ..models import Appointment, AppointmentPayment, AppointmentProfessional, AppointmentSchedule
from ..services import reminder_automation
from ..services.booking import create_public_appointment
from ..services.reminder_automation import reconcile_appointment_reminders
from .test_appointment_checkout import TOKEN_A, TOKEN_B, create_business, create_service
from .test_appointment_payment_webhook import WEBHOOK_SETTINGS, FakePaymentsSDK, mp_payment
from .test_customer_core_access import _gestion_business, _login, _turnos_business

User = get_user_model()
A = Appointment.Status
R = CustomerReminder.Status
S = CustomerReminder.Source
ART = dt.timezone(dt.timedelta(hours=-3))
MONDAY = dt.date(2030, 3, 4)
SETTINGS_URL = '/api/v1/appointments/reminder-automation/'
APPTS_URL = '/api/v1/appointments/appointments/'


def at(hour, minute=0, day=MONDAY):
    return dt.datetime(day.year, day.month, day.day, hour, minute, tzinfo=ART)


def _automation(biz, **fields):
    obj, _ = CustomerReminderAutomationSettings.objects.update_or_create(business=biz, defaults=fields)
    return obj


# ── Configuración ────────────────────────────────────────────────────────────


class ReminderAutomationSettingsTests(APITestCase):

    def setUp(self):
        self.biz = _turnos_business(slug='auto-settings')

    def test_defaults_off_without_creating_row(self):
        _login(self.client, self.biz, 'owner')
        resp = self.client.get(SETTINGS_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(
            {k: v for k, v in resp.data.items() if k != 'updated_at'},
            {
                'appointment_reminder_enabled': False,
                'appointment_reminder_hours_before': 24,
                'no_show_followup_enabled': False,
                'no_show_followup_delay_hours': 24,
            },
        )
        self.assertFalse(CustomerReminderAutomationSettings.objects.exists())

    def test_owner_and_admin_can_configure(self):
        for role, hours in (('owner', 48), ('admin', 12)):
            with self.subTest(role=role):
                _login(self.client, self.biz, role)
                resp = self.client.patch(
                    SETTINGS_URL, {'appointment_reminder_enabled': True, 'appointment_reminder_hours_before': hours}, format='json',
                )
                self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
                row = CustomerReminderAutomationSettings.objects.get(business=self.biz)
                self.assertTrue(row.appointment_reminder_enabled)
                self.assertEqual(row.appointment_reminder_hours_before, hours)
                self.assertFalse(row.no_show_followup_enabled)

    def test_manager_reads_but_cannot_modify(self):
        _automation(self.biz, no_show_followup_enabled=True)
        _login(self.client, self.biz, 'manager')
        resp = self.client.get(SETTINGS_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data['no_show_followup_enabled'])
        resp = self.client.patch(SETTINGS_URL, {'no_show_followup_enabled': False}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(CustomerReminderAutomationSettings.objects.get(business=self.biz).no_show_followup_enabled)

    def test_viewer_cannot_read_or_modify(self):
        _login(self.client, self.biz, 'viewer')
        self.assertEqual(self.client.get(SETTINGS_URL).status_code, status.HTTP_403_FORBIDDEN)
        resp = self.client.patch(SETTINGS_URL, {'appointment_reminder_enabled': True}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(CustomerReminderAutomationSettings.objects.exists())

    def test_gestion_only_business_has_no_access(self):
        """`manage_settings` de Gestión no alcanza: hace falta Turnos (`view_appointments`)."""
        biz = _gestion_business('pro', 'auto-gestion')
        _login(self.client, biz, 'owner')
        self.assertEqual(self.client.get(SETTINGS_URL).status_code, status.HTTP_403_FORBIDDEN)

    def test_hour_limits(self):
        _login(self.client, self.biz, 'owner')
        bad = [
            {'appointment_reminder_hours_before': 0},
            {'appointment_reminder_hours_before': -1},
            {'appointment_reminder_hours_before': 169},
            {'no_show_followup_delay_hours': 0},
            {'no_show_followup_delay_hours': 721},
            {'appointment_reminder_hours_before': 'x'},
        ]
        for payload in bad:
            with self.subTest(payload=payload):
                resp = self.client.patch(SETTINGS_URL, payload, format='json')
                self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(next(iter(payload)), resp.data)
        ok = {'appointment_reminder_hours_before': 168, 'no_show_followup_delay_hours': 720}
        self.assertEqual(self.client.patch(SETTINGS_URL, ok, format='json').status_code, status.HTTP_200_OK)
        ok = {'appointment_reminder_hours_before': 1, 'no_show_followup_delay_hours': 1}
        self.assertEqual(self.client.patch(SETTINGS_URL, ok, format='json').status_code, status.HTTP_200_OK)

    def test_put_not_allowed(self):
        _login(self.client, self.biz, 'owner')
        self.assertEqual(self.client.put(SETTINGS_URL, {}, format='json').status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_settings_isolated_per_business(self):
        other = _turnos_business(slug='auto-settings-b')
        _automation(other, appointment_reminder_enabled=True, appointment_reminder_hours_before=72)
        _login(self.client, self.biz, 'owner')
        resp = self.client.get(SETTINGS_URL)
        self.assertFalse(resp.data['appointment_reminder_enabled'])
        self.assertEqual(resp.data['appointment_reminder_hours_before'], 24)
        self.client.patch(SETTINGS_URL, {'no_show_followup_enabled': True}, format='json')
        other_row = CustomerReminderAutomationSettings.objects.get(business=other)
        self.assertFalse(other_row.no_show_followup_enabled)
        self.assertEqual(other_row.appointment_reminder_hours_before, 72)

    def test_permission_matrix(self):
        expected = {'owner': True, 'admin': True, 'manager': False, 'viewer': False}
        for role, allowed in expected.items():
            with self.subTest(role=role):
                self.assertEqual(permissions_for_service('appointments', role)['manage_reminder_automations'], allowed)
        for role in ('owner', 'admin', 'manager', 'cashier', 'staff', 'viewer'):
            self.assertFalse(permissions_for_service('gestion', role)['manage_reminder_automations'])


# ── Ciclo de vida del turno ──────────────────────────────────────────────────


@override_settings(**WEBHOOK_SETTINGS)
class AppointmentReminderAutomationTests(APITestCase):

    def setUp(self):
        cache.clear()
        self.biz = create_business(name='Auto Biz', slug='auto-biz', token=TOKEN_A)
        self.service = create_service(self.biz, deposit_type='none', deposit_value=Decimal('0'))
        self.deposit_service = create_service(self.biz, deposit_value=Decimal('40'))
        self.deposit_service.name = 'Color'
        self.deposit_service.save(update_fields=['name'])
        self.pro = AppointmentProfessional.objects.create(business=self.biz, name='Lu')
        self.pro.services.add(self.service, self.deposit_service)
        for day in (MONDAY, MONDAY + dt.timedelta(days=1)):
            for prof in (None, self.pro):
                AppointmentSchedule.objects.create(
                    business=self.biz, professional=prof, weekday=day.weekday(), start_time='09:00', end_time='19:00',
                )
        self.customer = Customer.objects.create(business=self.biz, name='Ana', phone='1155550101')
        user = User.objects.create_user(username='auto-owner', password='x')
        Membership.objects.create(user=user, business=self.biz, role='owner')
        self.client.force_authenticate(user=user)
        self.client.cookies['bid'] = str(self.biz.id)
        self.mp = FakePaymentsSDK()
        patcher = patch('mercadopago.SDK', new=self.mp)
        patcher.start()
        self.addCleanup(patcher.stop)

    # helpers ---------------------------------------------------------------

    def _on(self, **fields):
        defaults = {'appointment_reminder_enabled': True, 'no_show_followup_enabled': True}
        defaults.update(fields)
        return _automation(self.biz, **defaults)

    def _create_via_api(self, start=None, **overrides):
        payload = {
            'service_id': str(self.service.pk), 'professional_id': str(self.pro.pk),
            'start_at': (start or at(16)).isoformat(), 'customer_name': 'Ana', 'customer_phone': '1155550101',
        }
        payload.update(overrides)
        resp = self.client.post(APPTS_URL, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        return Appointment.objects.get(pk=resp.json()['id'])

    def _appt(self, *, status_=A.CONFIRMED, start=None, customer='default', service=None, expires_at=None):
        start = start or at(16)
        service = service or self.service
        return Appointment.objects.create(
            business=self.biz, service=service, professional=self.pro,
            customer=self.customer if customer == 'default' else customer,
            customer_name='Ana', customer_phone='1155550101',
            start_at=start, end_at=start + dt.timedelta(minutes=30), status=status_, expires_at=expires_at,
            source=Appointment.Source.PUBLIC, service_name=service.name, service_duration_minutes=30,
            service_price=service.price, deposit_type=service.deposit_type, deposit_value=service.deposit_value,
        )

    def _patch(self, appt, payload, expected=status.HTTP_200_OK):
        resp = self.client.patch(f'{APPTS_URL}{appt.pk}/', payload, format='json')
        self.assertEqual(resp.status_code, expected, resp.content)
        return resp

    def _auto(self, appt, source=S.APPOINTMENT_UPCOMING):
        return CustomerReminder.objects.filter(appointment=appt, source=source)

    def _payment(self, appt):
        pid = uuid.uuid4()
        return AppointmentPayment.objects.create(
            id=pid, business=self.biz, appointment=appt,
            external_reference=AppointmentPayment.build_external_reference(pid),
            amount=appt.deposit_amount, status=AppointmentPayment.Status.PENDING, provider_preference_id='PREF-1',
        )

    def _confirm_via_webhook(self, payment, event='pay-1'):
        from apps.billing.payment_webhook import process_payment_event
        self.mp.responses[TOKEN_A] = mp_payment(payment)
        process_payment_event(event, flow='appointment', ref=payment.external_reference)

    # 6–8 alta ---------------------------------------------------------------

    def test_confirmed_with_automation_on_creates_reminder(self):
        self._on(appointment_reminder_hours_before=24)
        appt = self._create_via_api(start=at(16))
        [reminder] = self._auto(appt)
        self.assertEqual(reminder.status, R.PENDING)
        self.assertEqual(reminder.remind_at, at(16, day=MONDAY - dt.timedelta(days=1)))
        self.assertEqual(reminder.customer_id, appt.customer_id)
        self.assertEqual(reminder.business_id, self.biz.pk)
        self.assertEqual(reminder.title, 'Confirmar turno de Ana')
        self.assertEqual(reminder.automation_key, reminder_automation.upcoming_key(appt))
        self.assertIsNone(reminder.created_by_id)
        self.assertIn('04/03/2030 16:00', reminder.description)

    def test_hours_before_is_configurable(self):
        self._on(appointment_reminder_hours_before=3)
        appt = self._create_via_api(start=at(16))
        self.assertEqual(self._auto(appt).get().remind_at, at(13))

    def test_automation_off_creates_nothing(self):
        _automation(self.biz, appointment_reminder_enabled=False, no_show_followup_enabled=True)
        self._create_via_api()
        self.assertFalse(CustomerReminder.objects.exists())

    def test_no_settings_row_creates_nothing(self):
        self._create_via_api()
        self.assertFalse(CustomerReminder.objects.exists())

    def test_customer_null_or_inactive_creates_nothing(self):
        self._on()
        reconcile_appointment_reminders(self._appt(customer=None))
        inactive = Customer.objects.create(business=self.biz, name='Baja', phone='1155550199', is_active=False)
        reconcile_appointment_reminders(self._appt(customer=inactive, start=at(10)))
        self.assertFalse(CustomerReminder.objects.exists())

    # 9–10 seña / webhook ----------------------------------------------------

    def test_public_booking_without_deposit_creates_reminder(self):
        self._on()
        appt = create_public_appointment(
            business=self.biz, service_id=str(self.service.pk), professional_id=str(self.pro.pk),
            start_at=at(11), customer_name='Ana', customer_phone='1155550101',
        )
        self.assertEqual(appt.status, A.CONFIRMED)
        self.assertEqual(self._auto(appt).count(), 1)

    def test_pending_payment_creates_nothing_until_webhook_confirms(self):
        self._on()
        appt = create_public_appointment(
            business=self.biz, service_id=str(self.deposit_service.pk), professional_id=str(self.pro.pk),
            start_at=at(11), customer_name='Ana', customer_phone='1155550101',
        )
        self.assertEqual(appt.status, A.PENDING_PAYMENT)
        self.assertFalse(CustomerReminder.objects.exists())

        payment = self._payment(appt)
        self._confirm_via_webhook(payment, event='pay-1')
        appt.refresh_from_db()
        self.assertEqual(appt.status, A.CONFIRMED)
        self.assertEqual(self._auto(appt).count(), 1)

        # 14. webhook repetido / reproceso → sigue habiendo 1.
        self._confirm_via_webhook(payment, event='pay-1')
        reconcile_appointment_reminders(appt)
        self.assertEqual(self._auto(appt).count(), 1)
        self.assertEqual(CustomerReminder.objects.count(), 1)

    # 11–13 estados / anticipación -------------------------------------------

    def test_cancelled_expired_completed_no_show_create_nothing(self):
        self._on(no_show_followup_enabled=False)
        for index, state in enumerate((A.CANCELLED, A.EXPIRED, A.COMPLETED, A.NO_SHOW, A.PENDING_PAYMENT)):
            with self.subTest(state=state):
                expires = dj_timezone.now() + dt.timedelta(minutes=5) if state == A.PENDING_PAYMENT else None
                reconcile_appointment_reminders(self._appt(status_=state, start=at(9 + index), expires_at=expires))
        self.assertFalse(CustomerReminder.objects.exists())

    def test_inside_lead_time_never_creates_past_reminder(self):
        self._on(appointment_reminder_hours_before=24)
        soon = dj_timezone.now() + dt.timedelta(hours=2)
        reconcile_appointment_reminders(self._appt(start=soon))
        self.assertFalse(CustomerReminder.objects.exists())

    def test_past_appointment_creates_nothing(self):
        self._on(appointment_reminder_hours_before=1)
        reconcile_appointment_reminders(self._appt(start=dj_timezone.now() - dt.timedelta(hours=3)))
        self.assertFalse(CustomerReminder.objects.exists())

    # 14 idempotencia ---------------------------------------------------------

    def test_reprocessing_and_unrelated_edits_do_not_duplicate(self):
        self._on()
        appt = self._create_via_api()
        reminder = self._auto(appt).get()
        for _ in range(3):
            reconcile_appointment_reminders(appt)
        self._patch(appt, {'notes': 'Trae su propio producto'})
        self._patch(appt, {'customer_name': 'Ana María'})
        self.assertEqual(self._auto(appt).count(), 1)
        reminder.refresh_from_db()
        self.assertEqual((reminder.status, reminder.remind_at), (R.PENDING, at(16, day=MONDAY - dt.timedelta(days=1))))

    def test_unique_key_enforced_by_database(self):
        from django.db import IntegrityError, transaction
        self._on()
        appt = self._create_via_api()
        with self.assertRaises(IntegrityError), transaction.atomic():
            CustomerReminder.objects.create(
                customer=self.customer, appointment=appt, title='x', remind_at=at(9),
                source=S.APPOINTMENT_UPCOMING, automation_key=reminder_automation.upcoming_key(appt),
            )

    # 15 reprogramación ---------------------------------------------------------

    def test_reschedule_moves_pending_reminder(self):
        self._on(appointment_reminder_hours_before=24)
        appt = self._create_via_api(start=at(16))
        original = self._auto(appt).get()
        tuesday = MONDAY + dt.timedelta(days=1)
        self._patch(appt, {'start_at': at(18, day=tuesday).isoformat()})
        [moved] = self._auto(appt)
        self.assertEqual(moved.pk, original.pk)
        self.assertEqual(moved.status, R.PENDING)
        self.assertEqual(moved.remind_at, at(18))  # lunes 18:00 = martes 18:00 - 24 h
        self.assertIn('05/03/2030 18:00', moved.description)
        self.assertNotIn('04/03/2030 16:00', moved.description)
        appt.refresh_from_db()
        self.assertEqual(moved.automation_key, reminder_automation.upcoming_key(appt))

    def test_reschedule_after_completed_creates_new_one_and_keeps_old(self):
        self._on()
        appt = self._create_via_api(start=at(16))
        done = self._auto(appt).get()
        CustomerReminder.objects.filter(pk=done.pk).update(status=R.COMPLETED, completed_at=dj_timezone.now())
        self._patch(appt, {'start_at': at(17).isoformat()})
        reminders = list(self._auto(appt).order_by('created_at'))
        self.assertEqual([r.status for r in reminders], [R.COMPLETED, R.PENDING])
        self.assertEqual(reminders[1].remind_at, at(17, day=MONDAY - dt.timedelta(days=1)))

    def test_reschedule_back_to_closed_slot_does_not_revive(self):
        self._on()
        appt = self._create_via_api(start=at(16))
        first = self._auto(appt).get()
        CustomerReminder.objects.filter(pk=first.pk).update(status=R.CANCELLED)
        self._patch(appt, {'start_at': at(17).isoformat()})   # crea uno nuevo (key 17:00)
        self._patch(appt, {'start_at': at(16).isoformat()})   # vuelve al horario cuyo previo se cerró
        statuses = sorted(self._auto(appt).values_list('status', flat=True))
        self.assertEqual(statuses, [R.CANCELLED, R.CANCELLED])

    def test_reschedule_into_lead_time_cancels_pending(self):
        self._on(appointment_reminder_hours_before=24)
        appt = self._appt(start=dj_timezone.now() + dt.timedelta(days=5))
        reconcile_appointment_reminders(appt)
        self.assertEqual(self._auto(appt).get().status, R.PENDING)
        appt.start_at = dj_timezone.now() + dt.timedelta(hours=3)
        appt.save(update_fields=['start_at'])
        reconcile_appointment_reminders(appt)
        self.assertEqual(self._auto(appt).get().status, R.CANCELLED)

    def test_reschedule_moves_even_if_rule_was_turned_off(self):
        """Los switches gobiernan la creación; lo ya creado sigue al turno."""
        self._on()
        appt = self._create_via_api(start=at(16))
        _automation(self.biz, appointment_reminder_enabled=False)
        self._patch(appt, {'start_at': at(17).isoformat()})
        self.assertEqual(self._auto(appt).get().remind_at, at(17, day=MONDAY - dt.timedelta(days=1)))

    def test_customer_change_moves_pending_reminder(self):
        self._on()
        appt = self._create_via_api()
        beto = Customer.objects.create(business=self.biz, name='Beto', phone='1155550102')
        self._patch(appt, {'customer_id': str(beto.pk)})
        reminder = self._auto(appt).get()
        self.assertEqual((reminder.customer_id, reminder.title, reminder.status), (beto.pk, 'Confirmar turno de Beto', R.PENDING))

    # 16–18 cancelación / vencimiento ---------------------------------------------

    def test_cancel_appointment_cancels_automatic_but_not_manual(self):
        self._on()
        appt = self._create_via_api()
        manual = CustomerReminder.objects.create(
            customer=appt.customer, appointment=appt, title='Pedir seña', remind_at=at(9),
        )
        resp = self.client.delete(f'{APPTS_URL}{appt.pk}/')
        self.assertIn(resp.status_code, (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT), resp.content)
        appt.refresh_from_db()
        self.assertEqual(appt.status, A.CANCELLED)
        self.assertEqual(self._auto(appt).get().status, R.CANCELLED)
        manual.refresh_from_db()
        self.assertEqual(manual.status, R.PENDING)
        self.assertTrue(CustomerReminder.objects.filter(pk=manual.pk).exists())

    def test_status_patch_to_cancelled_and_completed_cancels_pending(self):
        self._on()
        for target in (A.CANCELLED, A.COMPLETED):
            with self.subTest(target=target):
                appt = self._create_via_api(start=at(10 if target == A.CANCELLED else 12))
                self._patch(appt, {'status': target})
                self.assertEqual(self._auto(appt).get().status, R.CANCELLED)

    def test_expired_appointment_cancels_automatic(self):
        self._on()
        appt = self._create_via_api()
        Appointment.objects.filter(pk=appt.pk).update(status=A.EXPIRED)
        appt.refresh_from_db()
        reconcile_appointment_reminders(appt)
        self.assertEqual(self._auto(appt).get().status, R.CANCELLED)

    def test_reconfirm_after_cancel_creates_new_reminder_only_if_on(self):
        self._on()
        appt = self._create_via_api()
        self._patch(appt, {'status': A.CANCELLED})
        self._patch(appt, {'status': A.CONFIRMED})
        # Mismo horario = misma key, ya cerrada → no se revive ni se duplica.
        self.assertEqual(list(self._auto(appt).values_list('status', flat=True)), [R.CANCELLED])

    # 19 tenant ---------------------------------------------------------------

    def test_other_tenant_not_affected(self):
        other = create_business(name='Otro', slug='auto-biz-b', token=TOKEN_B)
        _automation(other, appointment_reminder_enabled=True)
        other_customer = Customer.objects.create(business=other, name='Zoe', phone='1155550777')
        foreign = CustomerReminder.objects.create(customer=other_customer, title='Ajeno', remind_at=at(9))
        _automation(self.biz, appointment_reminder_enabled=False)
        appt = self._create_via_api()
        self._patch(appt, {'status': A.CANCELLED})
        self.assertEqual(CustomerReminder.objects.filter(business=self.biz).count(), 0)
        foreign.refresh_from_db()
        self.assertEqual(foreign.status, R.PENDING)
        self.assertEqual(CustomerReminder.objects.filter(business=other).count(), 1)

    # Robustez ----------------------------------------------------------------

    def test_reconcile_failure_never_breaks_appointment_mutation(self):
        self._on()
        appt = self._create_via_api()
        with patch.object(reminder_automation, '_reconcile_upcoming', side_effect=RuntimeError('boom')):
            self._patch(appt, {'start_at': at(17).isoformat()})
        appt.refresh_from_db()
        self.assertEqual(appt.start_at, at(17))

    # 20–26 no-show -------------------------------------------------------------

    def test_no_show_creates_followup(self):
        self._on(no_show_followup_delay_hours=24)
        appt = self._create_via_api()
        before = dj_timezone.now()
        self._patch(appt, {'status': A.NO_SHOW})
        after = dj_timezone.now()
        [followup] = self._auto(appt, S.NO_SHOW_FOLLOWUP)
        self.assertEqual(followup.status, R.PENDING)
        self.assertEqual(followup.title, 'Contactar por inasistencia')
        self.assertEqual(followup.customer_id, self.customer.pk)
        self.assertEqual(followup.appointment_id, appt.pk)
        self.assertEqual(followup.business_id, self.biz.pk)
        self.assertGreaterEqual(followup.remind_at, before + dt.timedelta(hours=24))
        self.assertLessEqual(followup.remind_at, after + dt.timedelta(hours=24))
        # El previo pendiente ya no aplica.
        self.assertEqual(self._auto(appt).get().status, R.CANCELLED)

    def test_no_show_delay_is_configurable(self):
        self._on(no_show_followup_delay_hours=72)
        appt = self._create_via_api()
        before = dj_timezone.now()
        self._patch(appt, {'status': A.NO_SHOW})
        followup = self._auto(appt, S.NO_SHOW_FOLLOWUP).get()
        self.assertGreaterEqual(followup.remind_at, before + dt.timedelta(hours=72))
        self.assertLess(followup.remind_at, before + dt.timedelta(hours=73))

    def test_no_show_off_creates_nothing(self):
        self._on(no_show_followup_enabled=False)
        appt = self._create_via_api()
        self._patch(appt, {'status': A.NO_SHOW})
        self.assertFalse(self._auto(appt, S.NO_SHOW_FOLLOWUP).exists())

    def test_no_show_retries_do_not_duplicate(self):
        self._on()
        appt = self._create_via_api()
        self._patch(appt, {'status': A.NO_SHOW})
        self._patch(appt, {'status': A.NO_SHOW})
        reconcile_appointment_reminders(appt, previous_status=A.CONFIRMED)  # reintento del proceso
        # Ida y vuelta: sigue siendo la primera transición la que cuenta.
        self._patch(appt, {'status': A.CONFIRMED})
        self._patch(appt, {'status': A.NO_SHOW})
        self.assertEqual(self._auto(appt, S.NO_SHOW_FOLLOWUP).count(), 1)

    def test_no_show_without_customer_creates_nothing(self):
        self._on()
        appt = self._appt(customer=None, start=at(10))
        self._patch(appt, {'status': A.NO_SHOW})
        self.assertFalse(CustomerReminder.objects.exists())

    def test_seeded_no_show_without_transition_is_not_backfilled(self):
        self._on()
        appt = self._appt(status_=A.NO_SHOW)
        reconcile_appointment_reminders(appt)
        self.assertFalse(CustomerReminder.objects.exists())

    # Edición de automáticos (backend) ------------------------------------------

    def test_automatic_reminder_can_be_completed_but_not_edited(self):
        self._on()
        appt = self._create_via_api()
        reminder = self._auto(appt).get()
        url = f'/api/v1/customers/{reminder.customer_id}/reminders/{reminder.pk}/'
        listed = self.client.get(f'/api/v1/customers/{reminder.customer_id}/reminders/')
        row = listed.data['results'][0]
        self.assertEqual((row['source'], row['is_automatic'], row['source_display']), ('appointment_upcoming', True, 'Antes del turno'))
        for payload in ({'title': 'Otro'}, {'remind_at': '2030-03-01T10:00'}, {'description': 'x'}, {'appointment_id': None}):
            with self.subTest(payload=payload):
                resp = self.client.patch(url, payload, format='json')
                self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)
        resp = self.client.patch(url, {'status': 'completed'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        reminder.refresh_from_db()
        self.assertEqual((reminder.status, reminder.title), (R.COMPLETED, 'Confirmar turno de Ana'))

    def test_manual_reminders_created_via_api_are_manual(self):
        resp = self.client.post(
            f'/api/v1/customers/{self.customer.pk}/reminders/',
            {'title': 'Llamar', 'remind_at': '2030-03-01T10:00', 'source': 'no_show_followup', 'automation_key': 'x'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual((resp.data['source'], resp.data['is_automatic']), ('manual', False))
        self.assertIsNone(CustomerReminder.objects.get(pk=resp.data['id']).automation_key)
