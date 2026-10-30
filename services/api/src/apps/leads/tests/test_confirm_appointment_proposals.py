"""Slice 3C.1: conversión manual, replay y carreras sobre PostgreSQL."""
from __future__ import annotations

import datetime as dt
import threading
import uuid
from decimal import Decimal
from unittest import mock

from django.apps import apps as django_apps
from django.db import connections, transaction
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import Membership, RolePermissionOverride
from apps.appointments.models import Appointment, AppointmentException, AppointmentSchedule, AppointmentService
from apps.appointments.serializers import AppointmentSerializer
from apps.appointments.services import booking
from apps.appointments.tests.test_customer_core_access import _login
from apps.customers.models import Customer
from apps.business.models import Business
from apps.leads.models import AppointmentProposal, ConversationControl, Lead, LeadActivity, LeadStaffMessage
from apps.leads.services import appointment_proposals as proposals
from apps.leads.services import human_messages

from .test_appointment_proposals import MONDAY, ProposalMixin, _at
from .test_takeover import TAKEOVER_SETTINGS


@override_settings(**TAKEOVER_SETTINGS)
class ConfirmProposalTests(ProposalMixin, APITestCase):
    def setUp(self):
        self._setup('proposal-confirm')
        self.user = _login(self.client, self.biz, 'manager')
        self.proposal = self._create().proposal

    def url(self, *, lead=None, proposal_id=None):
        return (
            f'/api/v1/leads/{(lead or self.lead).pk}/appointment-proposals/'
            f'{proposal_id or self.proposal.pk}/confirm/'
        )

    def confirm(self, **kwargs):
        return self.client.post(self.url(**kwargs), {}, format='json')

    def assert_rejected(self, code):
        response = self.confirm()
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data['code'], code)
        self.proposal.refresh_from_db()
        self.lead.refresh_from_db()
        self.assertIsNone(self.proposal.appointment_id)
        self.assertNotEqual(self.proposal.status, AppointmentProposal.Status.CONVERTED)
        return response

    def test_confirm_links_real_appointment_customer_and_activity_without_message(self):
        before = Lead.objects.filter(pk=self.lead.pk).values('status', 'outcome', 'acknowledged_at').get()
        messages = LeadStaffMessage.objects.count()
        response = self.confirm()
        self.assertEqual(response.status_code, 200, response.data)
        appointment = Appointment.objects.get()
        self.lead.refresh_from_db()
        self.proposal.refresh_from_db()
        self.assertEqual(response.data['id'], str(appointment.pk))
        self.assertEqual(self.lead.appointment_id, appointment.pk)
        self.assertEqual(self.proposal.appointment_id, appointment.pk)
        self.assertEqual(self.proposal.status, AppointmentProposal.Status.CONVERTED)
        self.assertEqual(appointment.status, Appointment.Status.CONFIRMED)
        self.assertEqual(appointment.source, Appointment.Source.MANUAL)
        self.assertEqual(appointment.start_at, self.proposal.proposed_start_at)
        self.assertEqual(appointment.end_at, self.proposal.proposed_end_at)
        self.assertEqual(appointment.service_id, self.proposal.service_id)
        self.assertEqual(appointment.professional_id, self.proposal.professional_id)
        self.assertEqual(appointment.customer_name, 'Ana Paciente')
        self.assertEqual(self.lead.customer_id, appointment.customer_id)
        self.assertIsNotNone(appointment.customer_id)
        self.assertEqual(LeadStaffMessage.objects.count(), messages)
        self.assertEqual(Lead.objects.filter(pk=self.lead.pk).values(*before).get(), before)
        self.assertEqual(set(self.lead.activities.values_list('kind', flat=True)), {
            LeadActivity.Kind.APPOINTMENT_LINKED, LeadActivity.Kind.CUSTOMER_LINKED,
        })
        self.assertIsNone(proposals.current_proposal(self.lead))
        self.assertEqual(self.client.get(
            f'/api/v1/leads/{self.lead.pk}/appointment-proposals/current/',
        ).status_code, 404)

    def test_queued_also_confirmable_without_takeover_or_enabled_integration(self):
        AppointmentProposal.objects.filter(pk=self.proposal.pk).update(
            status='queued', expires_at=timezone.now() + dt.timedelta(hours=1),
        )
        ConversationControl.objects.filter(business=self.biz).delete()
        with override_settings(AGENT_TAKEOVER_ENABLED=False):
            self.assertEqual(self.confirm().status_code, 200)
        self.assertEqual(Appointment.objects.count(), 1)

    def test_replay_returns_original_even_if_lead_closed_or_unlinked_and_slot_now_occupied(self):
        first = self.confirm()
        Lead.objects.filter(pk=self.lead.pk).update(status='closed', outcome='booked', appointment=None)
        AppointmentProposal.objects.filter(pk=self.proposal.pk).update(expires_at=timezone.now() - dt.timedelta(days=1))
        second = self.confirm()
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(first.data['id'], second.data['id'])
        self.assertEqual(Appointment.objects.count(), 1)
        self.assertEqual(self.lead.activities.filter(kind=LeadActivity.Kind.APPOINTMENT_LINKED).count(), 1)

    def test_terminal_states_rejected(self):
        for state, code in (
            ('expired', 'proposal_expired'), ('superseded', 'proposal_superseded'),
            ('delivery_failed', 'proposal_delivery_failed'),
        ):
            with self.subTest(state=state):
                AppointmentProposal.objects.filter(pk=self.proposal.pk).update(status=state)
                self.assert_rejected(code)
        self.assertFalse(Appointment.objects.exists())
        self.assertFalse(Customer.objects.exists())

    def test_lazy_expiry_rejected_without_current_get(self):
        AppointmentProposal.objects.filter(pk=self.proposal.pk).update(
            status='queued', expires_at=timezone.now() - dt.timedelta(seconds=1),
        )
        self.assert_rejected('proposal_expired')
        self.assertFalse(Appointment.objects.exists())

    def test_closed_lead_rejected(self):
        Lead.objects.filter(pk=self.lead.pk).update(status='closed', outcome='not_interested')
        self.assert_rejected('proposal_not_confirmable')

    def test_existing_lead_appointment_rejected(self):
        appointment = self._appt(self.biz, self.service, None, _at(12), pro=self.pro)
        Lead.objects.filter(pk=self.lead.pk).update(appointment=appointment)
        self.assert_rejected('lead_already_has_appointment')
        self.assertEqual(self.lead.appointment_id, appointment.pk)
        self.assertEqual(Appointment.objects.count(), 1)

    def test_occupied_slot_does_not_convert_or_create_customer(self):
        self._appt(self.biz, self.service, None, _at(10), pro=self.pro)
        self.assert_rejected('slot_unavailable')
        self.assertEqual(self.proposal.status, AppointmentProposal.Status.PENDING_DELIVERY)
        self.assertEqual(Appointment.objects.count(), 1)
        self.assertFalse(Customer.objects.exists())

    def test_revalidates_schedules_exceptions_and_past_start(self):
        schedules = AppointmentSchedule.objects.filter(business=self.biz, professional=self.pro)
        schedules.update(end_time='09:30')
        self.assert_rejected('slot_unavailable')
        schedules.update(end_time='18:00')
        exception = AppointmentException.objects.create(business=self.biz, professional=self.pro, date=MONDAY, is_closed=True)
        self.assert_rejected('slot_unavailable')
        exception.delete()
        with mock.patch.object(proposals.timezone, 'now', return_value=_at(11)):
            self.assert_rejected('slot_unavailable')
        self.assertFalse(Appointment.objects.exists())

    def test_service_and_professional_must_still_be_active_and_eligible(self):
        AppointmentService.objects.filter(pk=self.service.pk).update(is_active=False)
        self.assert_rejected('proposal_not_confirmable')
        AppointmentService.objects.filter(pk=self.service.pk).update(is_active=True)
        self.pro.is_active = False
        self.pro.save(update_fields=['is_active'])
        self.assert_rejected('proposal_not_confirmable')
        self.pro.is_active = True
        self.pro.save(update_fields=['is_active'])
        self.pro.services.clear()
        self.assert_rejected('proposal_not_confirmable')
        self.assertFalse(Appointment.objects.exists())

    def test_historical_snapshots_price_percentage_deposit_and_duration_preserved(self):
        AppointmentProposal.objects.filter(pk=self.proposal.pk).update(
            deposit_type='percentage', deposit_value=Decimal('20'), deposit_amount=Decimal('200'),
        )
        AppointmentService.objects.filter(pk=self.service.pk).update(
            name='Nuevo corte', duration_minutes=60, price=Decimal('9000'),
            deposit_type='fixed', deposit_value=Decimal('500'),
        )
        self.assertEqual(self.confirm().status_code, 200)
        appointment = Appointment.objects.get()
        self.assertEqual(appointment.service_name, 'Corte')
        self.assertEqual(appointment.service_duration_minutes, 30)
        self.assertEqual(appointment.service_price, Decimal('1000'))
        self.assertEqual(appointment.deposit_type, 'percentage')
        self.assertEqual(appointment.deposit_value, Decimal('20'))
        self.assertEqual(appointment.deposit_amount, Decimal('200'))
        self.assertEqual(appointment.end_at, _at(10, 30))

    def test_historical_fixed_deposit_preserved(self):
        AppointmentProposal.objects.filter(pk=self.proposal.pk).update(
            deposit_type='fixed', deposit_value=Decimal('150'), deposit_amount=Decimal('150'),
        )
        AppointmentService.objects.filter(pk=self.service.pk).update(price=Decimal('5000'))
        self.assertEqual(self.confirm().status_code, 200)
        appointment = Appointment.objects.get()
        self.assertEqual(appointment.deposit_type, 'fixed')
        self.assertEqual(appointment.deposit_value, Decimal('150'))
        self.assertEqual(appointment.deposit_amount, Decimal('150'))

    def test_revalidates_whole_historical_interval_not_shorter_current_duration(self):
        AppointmentService.objects.filter(pk=self.service.pk).update(duration_minutes=15)
        self._appt(self.biz, self.service, None, _at(10, 20), pro=self.pro)
        self.assert_rejected('slot_unavailable')

    def test_changed_currency_or_inconsistent_snapshots_rejected_explicitly(self):
        for changes in (
            {'currency': 'USD'}, {'proposed_end_at': _at(10, 15)}, {'deposit_amount': Decimal('1')},
        ):
            with self.subTest(changes=changes):
                AppointmentProposal.objects.filter(pk=self.proposal.pk).update(**changes)
                self.assert_rejected('proposal_not_confirmable')
                AppointmentProposal.objects.filter(pk=self.proposal.pk).update(
                    currency='ARS', proposed_end_at=_at(10, 30), deposit_amount=Decimal('0'),
                )

    def test_currency_is_refreshed_after_taking_booking_lock(self):
        lock = booking.lock_professionals

        def changed_before_lock(business, professionals):
            Business.objects.filter(pk=business.pk).update(currency='USD')
            lock(business, professionals)

        with mock.patch.object(booking, 'lock_professionals', side_effect=changed_before_lock):
            response = self.assert_rejected('proposal_not_confirmable')
        self.assertIn('moneda', response.data['detail'])
        self.assertFalse(Appointment.objects.exists())
        self.assertFalse(Customer.objects.exists())

    def test_explicit_lead_customer_reused_without_mutation(self):
        customer = Customer.objects.create(business=self.biz, name='Familiar', phone='1155550000')
        Lead.objects.filter(pk=self.lead.pk).update(customer=customer)
        self.assertEqual(self.confirm().status_code, 200)
        appointment = Appointment.objects.get()
        self.assertEqual(appointment.customer_id, customer.pk)
        self.assertEqual(appointment.customer_name, 'Ana Paciente')
        customer.refresh_from_db()
        self.assertEqual(customer.name, 'Familiar')
        self.assertEqual(Customer.objects.count(), 1)

    def test_link_failure_rolls_back_everything(self):
        with mock.patch(
            'apps.leads.services.lead_appointments.record_update_activity', side_effect=RuntimeError('link failure'),
        ), self.assertRaisesMessage(RuntimeError, 'link failure'):
            self.confirm()
        self.proposal.refresh_from_db()
        self.lead.refresh_from_db()
        self.assertIsNone(self.proposal.appointment_id)
        self.assertIsNone(self.lead.appointment_id)
        self.assertFalse(Appointment.objects.exists())
        self.assertFalse(Customer.objects.exists())

    def test_tenant_and_url_lead_isolation_including_replay(self):
        other_biz, channel = self._setup_tenant('confirm-other')
        foreign, _ = self._taken_lead(other_biz, channel)
        other, _ = self._taken_lead()
        for lead, proposal_id in ((foreign, None), (other, None), (None, uuid.uuid4())):
            self.assertEqual(self.confirm(lead=lead, proposal_id=proposal_id).status_code, 404)
        self.assertEqual(self.confirm().status_code, 200)
        _login(self.client, other_biz, 'owner')
        self.assertEqual(self.confirm().status_code, 404)

    def test_requires_both_permissions(self):
        for permission in ('manage_leads', 'manage_appointments'):
            with self.subTest(permission=permission):
                override = RolePermissionOverride.objects.create(
                    business=self.biz, role='manager', service='appointments', permission=permission, enabled=False,
                )
                self.assertEqual(self.confirm().status_code, 403)
                override.delete()
        self.assertFalse(Appointment.objects.exists())

    def test_requires_auth_and_active_membership(self):
        self.client.force_authenticate(user=None)
        self.assertIn(self.confirm().status_code, (401, 403))
        self.client.force_authenticate(user=self.user)
        Membership.objects.filter(user=self.user, business=self.biz).update(status=Membership.Status.INACTIVE)
        self.assertEqual(self.confirm().status_code, 403)
        self.assertFalse(Appointment.objects.exists())
        Membership.objects.filter(user=self.user, business=self.biz).delete()
        self.assertEqual(self.confirm().status_code, 403)

    def test_late_delivery_results_do_not_undo_conversion(self):
        self.assertEqual(self.confirm().status_code, 200)
        message = self.proposal.staff_message
        for delivery_status in ('delivered', 'failed'):
            with self.subTest(delivery_status=delivery_status):
                message.status = delivery_status
                human_messages._sync_proposal(message, timezone.now())
                self.proposal.refresh_from_db()
                self.assertEqual(self.proposal.status, AppointmentProposal.Status.CONVERTED)
                self.assertIsNotNone(self.proposal.appointment_id)

    def test_requires_current_entitlement(self):
        from apps.business import entitlements

        with mock.patch.dict(entitlements.PLAN_ENTITLEMENTS, {'appointments_base': {'appointments.customers'}}):
            response = self.confirm()
        self.assertEqual(response.status_code, 403, response.data)
        self.assertEqual(response.data['code'], 'plan_entitlement_required')
        self.assertFalse(Appointment.objects.exists())


@override_settings(**TAKEOVER_SETTINGS)
class ConfirmProposalConcurrencyTests(ProposalMixin, TransactionTestCase):
    available_apps = [cfg.name for cfg in django_apps.get_app_configs()]

    def setUp(self):
        self._setup('confirm-concurrency')
        with mock.patch.object(human_messages, '_kick'):
            self.proposal = self._create().proposal

    def _confirm(self, lead=None, proposal=None):
        try:
            appointment = proposals.confirm_appointment_proposal(
                lead=lead or self.lead, proposal_id=(proposal or self.proposal).pk, user=self.user,
            )
            return ('ok', appointment.pk)
        except proposals.ProposalConflict as exc:
            return ('conflict', exc.code)

    def race(self, *actions):
        barrier = threading.Barrier(len(actions))
        results, errors = [], []

        def run(action):
            try:
                barrier.wait(timeout=10)
                results.append(action())
            except Exception as exc:
                errors.append(exc)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=run, args=(action,), daemon=True) for action in actions]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
        self.assertFalse(any(thread.is_alive() for thread in threads), 'La carrera no terminó (posible deadlock).')
        self.assertEqual(errors, [])
        return results

    def test_two_receptionists_double_confirm_create_one_appointment(self):
        results = self.race(self._confirm, self._confirm)
        appointment = Appointment.objects.get()
        self.assertEqual(results, [('ok', appointment.pk), ('ok', appointment.pk)])
        self.proposal.refresh_from_db()
        self.lead.refresh_from_db()
        self.assertEqual(self.proposal.appointment_id, appointment.pk)
        self.assertEqual(self.lead.appointment_id, appointment.pk)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(self.lead.activities.filter(kind=LeadActivity.Kind.APPOINTMENT_LINKED).count(), 1)

    def test_two_leads_cannot_convert_same_slot(self):
        lead, _ = self._taken_lead()
        with mock.patch.object(human_messages, '_kick'):
            proposal = self._create(lead=lead).proposal
        results = self.race(self._confirm, lambda: self._confirm(lead, proposal))
        self.assertEqual(sorted(result[0] for result in results), ['conflict', 'ok'])
        self.assertIn(('conflict', 'slot_unavailable'), results)
        self.assertEqual(Appointment.objects.count(), 1)
        self.assertEqual(AppointmentProposal.objects.filter(status='converted').count(), 1)
        self.assertEqual(Lead.objects.filter(appointment__isnull=False).count(), 1)

    def test_booking_competes_using_same_professional_and_business_locks(self):
        def book():
            serializer = AppointmentSerializer(data={
                'service_id': str(self.service.pk), 'professional_id': str(self.pro.pk), 'start_at': _at(10),
                'customer_name': 'Otra persona', 'customer_phone': '1155559999',
            }, context={'business': self.biz})
            serializer.is_valid(raise_exception=True)
            from rest_framework.exceptions import ValidationError
            try:
                return ('ok', serializer.save(business=self.biz).pk)
            except ValidationError:
                return ('conflict', 'slot_unavailable')

        results = self.race(self._confirm, book)
        self.assertEqual(sorted(result[0] for result in results), ['conflict', 'ok'])
        self.assertIn(('conflict', 'slot_unavailable'), results)
        self.assertEqual(Appointment.objects.count(), 1)

    def test_manual_lead_creation_competes_without_duplicate_appointment(self):
        def create():
            client = APIClient()
            client.force_authenticate(user=self.user)
            client.cookies['bid'] = str(self.biz.pk)
            response = client.post(f'/api/v1/leads/{self.lead.pk}/appointment/', {
                'service_id': str(self.service.pk), 'professional_id': str(self.pro.pk), 'start_at': _at(11).isoformat(),
            }, format='json')
            return ('create', response.status_code)

        results = self.race(self._confirm, create)
        self.assertEqual(Appointment.objects.count(), 1)
        self.lead.refresh_from_db()
        self.proposal.refresh_from_db()
        if self.proposal.appointment_id is not None:
            self.assertIn(('create', 400), results)
            self.assertEqual(self.lead.appointment_id, self.proposal.appointment_id)
        else:
            self.assertIn(('create', 201), results)
            self.assertIn(('conflict', 'lead_already_has_appointment'), results)

    def test_concurrent_existing_link_is_seen_after_waiting_for_lead_lock(self):
        appointment = self._appt(self.biz, self.service, None, _at(12), pro=self.pro)
        started = threading.Event()
        results, errors = [], []

        def confirm():
            started.set()
            try:
                results.append(self._confirm())
            except Exception as exc:
                errors.append(exc)
            finally:
                connections.close_all()

        with transaction.atomic():
            lead = Lead.objects.select_for_update().get(pk=self.lead.pk)
            thread = threading.Thread(target=confirm, daemon=True)
            thread.start()
            self.assertTrue(started.wait(timeout=10))
            lead.appointment = appointment
            lead.save(update_fields=['appointment'])
        thread.join(timeout=20)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(results, [('conflict', 'lead_already_has_appointment')])
        self.assertEqual(Appointment.objects.count(), 1)
