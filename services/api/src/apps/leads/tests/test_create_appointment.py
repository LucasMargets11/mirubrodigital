"""Slice 1: reserva manual canónica y vínculo con Lead en una transacción."""
from __future__ import annotations

import datetime as dt
import uuid
from unittest import mock

from django.db import connection
from rest_framework.test import APITestCase

from apps.accounts import permissions
from apps.accounts.models import Membership
from apps.appointments.models import Appointment, AppointmentSchedule
from apps.appointments.serializers import AppointmentSerializer
from apps.appointments.tests.test_customer_core_access import TurnosAgendaMixin, _login
from apps.customers.models import Customer
from apps.leads.models import Lead, LeadActivity

from .test_crm_api import LeadApiMixin


class LeadCreateAppointmentTests(LeadApiMixin, TurnosAgendaMixin, APITestCase):
    def setUp(self):
        self.biz, self.channel = self._setup_tenant('create-appointment')
        self.user = _login(self.client, self.biz, 'manager')
        self.lead = self._lead(self.biz, self.channel, patient_name='Ana Paciente')
        self.service, self.pro = self._agenda(self.biz)
        for professional in (None, self.pro):
            AppointmentSchedule.objects.create(
                business=self.biz, professional=professional, weekday=0,
                start_time='09:00', end_time='18:00',
            )
        self.payload = {
            'service_id': str(self.service.pk),
            'professional_id': str(self.pro.pk),
            'start_at': '2026-11-02T10:00:00-03:00',
        }

    def post(self, payload=None, lead=None):
        return self.client.post(
            f'/api/v1/leads/{(lead or self.lead).pk}/appointment/',
            self.payload if payload is None else payload, format='json',
        )

    def assert_unchanged(self, appointments=0, customers=0):
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.appointment_id)
        self.assertIsNone(self.lead.customer_id)
        self.assertEqual(Appointment.objects.count(), appointments)
        self.assertEqual(Customer.objects.count(), customers)
        self.assertFalse(LeadActivity.objects.exists())

    def test_creates_links_and_records_activity_without_closing_lead(self):
        before = Lead.objects.filter(pk=self.lead.pk).values(
            'status', 'outcome', 'closed_at', 'closed_by', 'needs_attention_at', 'acknowledged_at',
        ).get()
        response = self.post({**self.payload, 'end_at': '2026-11-03T22:00:00Z'})
        self.assertEqual(response.status_code, 201, response.data)
        self.lead.refresh_from_db()
        appointment = self.lead.appointment
        self.assertEqual(appointment.business_id, self.biz.pk)
        self.assertEqual(appointment.end_at - appointment.start_at, dt.timedelta(minutes=30))
        self.assertEqual(appointment.customer_name, 'Ana Paciente')
        self.assertEqual(appointment.customer_phone, self.lead.agent_state.phone_e164)
        self.assertEqual(appointment.source, Appointment.Source.MANUAL)
        self.assertEqual(appointment.status, Appointment.Status.CONFIRMED)
        self.assertEqual(self.lead.customer_id, appointment.customer_id)
        self.assertIsNotNone(self.lead.customer_id)
        self.assertEqual(Lead.objects.filter(pk=self.lead.pk).values(*before).get(), before)
        self.assertEqual(set(self.lead.activities.values_list('kind', flat=True)), {
            LeadActivity.Kind.APPOINTMENT_LINKED, LeadActivity.Kind.CUSTOMER_LINKED,
        })
        self.assertEqual(response.data['appointment']['professional_name'], 'Lu')
        self.assertEqual(response.data['appointment']['customer']['id'], str(appointment.customer_id))

    def test_owner_admin_manager_can_create(self):
        for index, role in enumerate(('owner', 'admin', 'manager')):
            with self.subTest(role=role):
                Membership.objects.filter(business=self.biz).delete()
                _login(self.client, self.biz, role)
                lead = self._lead(self.biz, self.channel, patient_name='Ana Paciente')
                payload = {**self.payload, 'start_at': f'2026-11-02T{11 + index}:00:00-03:00'}
                response = self.post(payload, lead)
                self.assertEqual(response.status_code, 201, response.data)

    def test_viewer_cannot_create(self):
        Membership.objects.filter(business=self.biz).delete()
        _login(self.client, self.biz, 'viewer')
        self.assertEqual(self.post().status_code, 403)
        self.assert_unchanged()

    def test_requires_both_permissions(self):
        real = permissions.permissions_for_service
        for denied in ('manage_leads', 'manage_appointments'):
            with self.subTest(denied=denied):
                def restricted(*args, **kwargs):
                    return {**real(*args, **kwargs), denied: False}
                with mock.patch.object(permissions, 'permissions_for_service', side_effect=restricted):
                    self.assertEqual(self.post().status_code, 403)
                self.assert_unchanged()

    def test_unauthenticated(self):
        self.client.force_authenticate(user=None)
        self.assertIn(self.post().status_code, (401, 403))
        self.assert_unchanged()

    def test_foreign_lead_and_missing_lead_are_not_found(self):
        foreign_biz, channel = self._setup_tenant('foreign-lead')
        lead = self._lead(foreign_biz, channel)
        self.assertEqual(self.post(lead=lead).status_code, 404)
        lead.pk = uuid.uuid4()
        self.assertEqual(self.post(lead=lead).status_code, 404)
        self.assert_unchanged()

    def test_foreign_relations_are_rejected(self):
        foreign_biz, _ = self._setup_tenant('foreign-relations')
        service, pro = self._agenda(foreign_biz)
        customer = Customer.objects.create(business=foreign_biz, name='Otra', phone='1155550001')
        for field, value in (
            ('service_id', service.pk), ('professional_id', pro.pk), ('customer_id', customer.pk),
        ):
            with self.subTest(field=field):
                response = self.post({**self.payload, field: str(value)})
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn(field, response.data)
                self.assert_unchanged(customers=1)

    def test_existing_link_rejects_repeat_without_second_appointment(self):
        self.assertEqual(self.post().status_code, 201)
        response = self.post()
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('non_field_errors', response.data)
        self.assertEqual(Appointment.objects.count(), 1)
        self.assertEqual(self.lead.activities.filter(kind=LeadActivity.Kind.APPOINTMENT_LINKED).count(), 1)

    def test_canonical_serializer_runs_inside_transaction_with_lead_locked(self):
        original_create = AppointmentSerializer.create

        def create(serializer, validated_data):
            self.assertTrue(connection.in_atomic_block)
            self.assertEqual(validated_data['business'], self.biz)
            return original_create(serializer, validated_data)

        with mock.patch.object(AppointmentSerializer, 'create', create):
            with mock.patch('apps.leads.crm_views.LeadCreateAppointmentView.get_lead',
                            wraps=None) as get_lead:
                def locked(*, for_update=False):
                    self.assertTrue(for_update)
                    return Lead.objects.select_for_update().get(pk=self.lead.pk)
                get_lead.side_effect = locked
                self.assertEqual(self.post().status_code, 201)

    def test_creation_failure_rolls_back_customer_and_appointment(self):
        with mock.patch(
            'apps.appointments.serializers.reminder_automation.reconcile_appointment_reminders',
            side_effect=RuntimeError('creation failure'),
        ):
            with self.assertRaisesMessage(RuntimeError, 'creation failure'):
                self.post()
        self.assert_unchanged()

    def test_link_activity_failure_rolls_back_everything(self):
        with mock.patch('apps.leads.services.lead_appointments.record_update_activity', side_effect=RuntimeError('link failure')):
            with self.assertRaisesMessage(RuntimeError, 'link failure'):
                self.post()
        self.assert_unchanged()

    def test_invalid_availability_rolls_back(self):
        response = self.post({**self.payload, 'start_at': '2026-11-02T23:00:00-03:00'})
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('start_at', response.data)
        self.assert_unchanged()

    def test_slot_occupied_after_availability_is_rejected(self):
        availability = self.client.get('/api/v1/appointments/availability/', {
            'service': self.service.pk, 'professional': self.pro.pk, 'date': '2026-11-02',
        })
        self.assertEqual(availability.status_code, 200, availability.data)
        self.assertTrue(availability.data['slots'])
        other_lead = self._lead(self.biz, self.channel, patient_name='Otro Paciente')
        self.assertEqual(self.post(lead=other_lead).status_code, 201)
        response = self.post()
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('start_at', response.data)
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.appointment_id)
        self.assertEqual(Appointment.objects.count(), 1)

    def test_explicit_lead_customer_wins_over_phone_matching(self):
        customer = Customer.objects.create(business=self.biz, name='Ficha', phone='1155550202')
        lead = self.lead
        lead.customer = customer
        lead.save()
        response = self.post()
        self.assertEqual(response.status_code, 201, response.data)
        lead.refresh_from_db()
        self.assertEqual(lead.appointment.customer_id, customer.pk)
        self.assertEqual(Customer.objects.count(), 1)

    def test_cannot_replace_lead_customer_in_booking_payload(self):
        customer = Customer.objects.create(business=self.biz, name='Ficha', phone='1155550202')
        self.lead.customer = customer
        self.lead.save()
        other = Customer.objects.create(business=self.biz, name='Otra', phone='1155550203')
        response = self.post({**self.payload, 'customer_id': str(other.pk)})
        self.assertEqual(response.status_code, 400)
        self.assertIn('customer_id', response.data)
        self.assertFalse(Appointment.objects.exists())

    def test_unique_phone_customer_is_reused_and_linked(self):
        customer = Customer.objects.create(
            business=self.biz, name='Existente', phone=self.lead.agent_state.phone_e164,
        )
        self.assertEqual(self.post().status_code, 201)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.customer_id, customer.pk)
        self.assertEqual(self.lead.appointment.customer_id, customer.pk)
        self.assertEqual(Customer.objects.count(), 1)

    def test_duplicate_phone_does_not_choose_arbitrarily(self):
        for name in ('Ana Uno', 'Ana Dos'):
            Customer.objects.create(business=self.biz, name=name, phone=self.lead.agent_state.phone_e164)
        response = self.post()
        self.assertEqual(response.status_code, 201, response.data)
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.customer_id)
        self.assertIsNone(self.lead.appointment.customer_id)
        self.assertEqual(Customer.objects.count(), 2)

    def test_customer_in_payload_is_linked_when_lead_has_none(self):
        customer = Customer.objects.create(business=self.biz, name='Elegido', phone='1155550202')
        self.assertEqual(self.post({**self.payload, 'customer_id': str(customer.pk)}).status_code, 201)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.customer_id, customer.pk)

    def test_without_agent_state_can_complete_patient_data(self):
        lead = Lead.objects.create(business=self.biz)
        response = self.post({
            **self.payload, 'customer_name': 'Paciente Manual', 'customer_phone': '1155550202',
        }, lead)
        self.assertEqual(response.status_code, 201, response.data)
        lead.refresh_from_db()
        self.assertEqual(lead.appointment.customer_name, 'Paciente Manual')
