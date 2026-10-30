"""SLICE 3A — `AppointmentProposal`: propuesta estructurada de turno desde recepción.

Modelo (constraints), servicio de dominio (validaciones, disponibilidad
reutilizada, snapshots, texto determinístico, reemplazo, idempotencia),
sincronización con el outbox `LeadStaffMessage`, expiración lazy y API (RBAC,
tenant, códigos HTTP). Transporte del agente siempre fake.
"""
from __future__ import annotations

import datetime as dt
import threading
import uuid
from decimal import Decimal
from unittest import mock

from django.apps import apps as django_apps
from django.db import IntegrityError, connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import Membership, RolePermissionOverride
from apps.appointments.models import (
    Appointment, AppointmentException, AppointmentPayment, AppointmentProfessional, AppointmentSchedule,
    AppointmentService,
)
from apps.appointments.services.availability import compute_availability
from apps.appointments.tests.test_customer_core_access import TurnosAgendaMixin, _login
from apps.leads.models import AppointmentProposal, ConversationControl, Lead, LeadStaffMessage, TakeoverCommand
from apps.leads.services import appointment_proposals as proposals
from apps.leads.services import human_messages as svc
from apps.leads.services.takeover import TakeoverUnavailable

from .test_crm_api import LeadApiMixin
from .test_human_messages import FakeSend, ok, retryable, terminal
from .test_takeover import TAKEOVER_SETTINGS, conv_id, later

PStatus = AppointmentProposal.Status
MsgStatus = LeadStaffMessage.Status
MONDAY = dt.date(2030, 3, 4)
assert MONDAY.weekday() == 0
START = '2030-03-04T10:00:00-03:00'


def _at(hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime.fromisoformat(f'{MONDAY.isoformat()}T{hour:02d}:{minute:02d}:00-03:00')


def _taken_control(biz, conversation_id, state=ConversationControl.State.TAKEN):
    return ConversationControl.objects.create(
        business=biz, external_conversation_id=conversation_id, state=state, command_version=1,
        last_event_id=uuid.uuid4(), last_command_action='takeover', taken_at=timezone.now(),
    )


class ProposalMixin(LeadApiMixin, TurnosAgendaMixin):

    def _setup(self, slug='proposal'):
        self.biz, self.channel = self._setup_tenant(slug)
        self.service, self.pro = self._agenda(self.biz)
        for professional in (None, self.pro):
            AppointmentSchedule.objects.create(
                business=self.biz, professional=professional, weekday=0, start_time='09:00', end_time='18:00',
            )
        self.lead, self.conv = self._taken_lead()
        self.user = self._member(self.biz, 'manager')

    def _taken_lead(self, biz=None, channel=None, **state):
        conversation_id = conv_id()
        lead = self._lead(
            biz or self.biz, channel or self.channel, external_conversation_id=conversation_id,
            patient_name=state.pop('patient_name', 'Ana Paciente'), **state,
        )
        _taken_control(biz or self.biz, conversation_id)
        return lead, conversation_id

    def _create(self, *, lead=None, service=None, professional='default', start_at=None, key=None, user=None):
        return proposals.create_and_send_appointment_proposal(
            lead=lead or self.lead,
            service_id=(service or self.service).pk,
            professional_id=self.pro.pk if professional == 'default' else (professional.pk if professional else None),
            start_at=start_at or _at(10),
            idempotency_key=key or uuid.uuid4(),
            user=user or self.user,
        )

    def _invalid(self, field, **kwargs):
        with self.assertRaises(proposals.ProposalInvalid) as ctx:
            self._create(**kwargs)
        self.assertEqual(ctx.exception.field, field)
        self.assert_nothing_created()
        return ctx.exception

    def _conflict(self, code, **kwargs):
        with self.assertRaises(proposals.ProposalConflict) as ctx:
            self._create(**kwargs)
        self.assertEqual(ctx.exception.code, code)
        return ctx.exception

    def assert_nothing_created(self):
        self.assertFalse(AppointmentProposal.objects.exists())
        self.assertFalse(LeadStaffMessage.objects.exists())
        self.assertFalse(Appointment.objects.exists())

    def _deliver(self, proposal, *responses, now=None):
        return svc.deliver_staff_message(proposal.staff_message_id, send=FakeSend(*responses), now=now)


# ── Modelo: constraints ─────────────────────────────────────────────────────

@override_settings(**TAKEOVER_SETTINGS)
class AppointmentProposalModelTests(ProposalMixin, TestCase):

    def setUp(self):
        self._setup('proposal-model')

    def _row(self, **overrides):
        data = dict(
            business=self.biz, lead=self.lead, service=self.service, professional=self.pro,
            proposed_start_at=_at(10), proposed_end_at=_at(10, 30), service_name='Corte', professional_name='Lu',
            service_duration_minutes=30, service_price=Decimal('1000'), currency='ARS', deposit_type='none',
            deposit_value=Decimal('0'), deposit_amount=Decimal('0'), idempotency_key=uuid.uuid4(),
        )
        data.update(overrides)
        return AppointmentProposal.objects.create(**data)

    def assert_rejected(self, **overrides):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._row(**overrides)

    def test_range_must_be_positive(self):
        self.assert_rejected(proposed_end_at=_at(10))
        self.assert_rejected(proposed_end_at=_at(9))

    def test_snapshots_must_be_valid(self):
        self.assert_rejected(service_duration_minutes=0)
        self.assert_rejected(service_price=Decimal('-1'))
        self.assert_rejected(deposit_value=Decimal('-1'))
        self.assert_rejected(deposit_amount=Decimal('-0.01'))
        self.assert_rejected(deposit_type='other')

    def test_status_must_be_known_and_queued_needs_expiry(self):
        self.assert_rejected(status='accepted')
        self.assert_rejected(status=PStatus.QUEUED, expires_at=None)
        self._row(status=PStatus.QUEUED, expires_at=later())

    def test_only_one_active_per_lead(self):
        self._row(status=PStatus.PENDING_DELIVERY)
        self.assert_rejected(status=PStatus.PENDING_DELIVERY)
        self.assert_rejected(status=PStatus.QUEUED, expires_at=later())
        for inactive in (PStatus.DELIVERY_FAILED, PStatus.EXPIRED, PStatus.SUPERSEDED):
            self._row(status=inactive)
        other_lead, _ = self._taken_lead()
        self._row(lead=other_lead)

    def test_idempotency_key_unique_per_business(self):
        key = uuid.uuid4()
        self._row(idempotency_key=key, status=PStatus.SUPERSEDED)
        self.assert_rejected(idempotency_key=key, status=PStatus.EXPIRED)
        other_biz, channel = self._setup_tenant('proposal-model-other')
        service, _ = self._agenda(other_biz)
        lead, _ = self._taken_lead(other_biz, channel)
        self._row(business=other_biz, lead=lead, service=service, professional=None, idempotency_key=key)

    def test_catalog_rows_are_protected(self):
        self._row()
        with self.assertRaises(Exception), transaction.atomic():
            self.service.delete()
        with self.assertRaises(Exception), transaction.atomic():
            self.pro.delete()


# ── Creación y validaciones ─────────────────────────────────────────────────

@override_settings(**TAKEOVER_SETTINGS)
class CreateProposalTests(ProposalMixin, TestCase):

    def setUp(self):
        self._setup('proposal-create')

    def test_creates_proposal_and_exactly_one_staff_message_without_appointment(self):
        before = compute_availability(
            business=self.biz, service_id=str(self.service.pk), target_date=MONDAY, professional_id=str(self.pro.pk),
        ).slots
        with self.captureOnCommitCallbacks() as callbacks:
            result = self._create()
        proposal = result.proposal
        self.assertTrue(result.created)
        self.assertEqual(proposal.status, PStatus.PENDING_DELIVERY)
        self.assertIsNone(proposal.expires_at)
        self.assertEqual(proposal.business, self.biz)
        self.assertEqual(proposal.created_by, self.user)
        self.assertEqual(proposal.proposed_end_at - proposal.proposed_start_at, dt.timedelta(minutes=30))
        self.assertIsNone(proposal.appointment_id)
        message = LeadStaffMessage.objects.get()
        self.assertEqual(proposal.staff_message, message)
        self.assertEqual(message.lead, self.lead)
        self.assertEqual(message.status, MsgStatus.PENDING)
        self.assertEqual(message.created_by, self.user)
        self.assertEqual(len(callbacks), 1, 'un solo kick del outbox, after-commit')
        self.assertFalse(Appointment.objects.exists())
        self.assertFalse(AppointmentPayment.objects.exists())
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.appointment_id)
        after = compute_availability(
            business=self.biz, service_id=str(self.service.pk), target_date=MONDAY, professional_id=str(self.pro.pk),
        ).slots
        self.assertEqual(after, before, 'la propuesta no ocupa el slot')

    def test_message_text_is_deterministic_spanish_in_business_timezone(self):
        proposal = self._create(start_at=dt.datetime(2030, 3, 4, 13, 0, tzinfo=dt.timezone.utc)).proposal
        self.assertEqual(
            proposal.staff_message.text,
            'Hola, Ana Paciente. Tenemos disponibilidad para Corte el 04/03/2030 a las 10:00 con Lu. '
            'Precio: ARS 1.000. El horario está sujeto a disponibilidad al confirmar. '
            '¿Querés que recepción lo confirme?',
        )

    def test_message_includes_deposit_and_omits_missing_name_and_free_price(self):
        self.service.deposit_type = AppointmentService.DepositType.PERCENTAGE
        self.service.deposit_value = Decimal('30')
        self.service.price = Decimal('1500.50')
        self.service.save()
        lead, _ = self._taken_lead(patient_name='', whatsapp_profile_name='')
        text = self._create(lead=lead).proposal.staff_message.text
        self.assertTrue(text.startswith('Hola. Tenemos disponibilidad para Corte'), text)
        self.assertIn('Precio: ARS 1.500,50. Seña: ARS 450,15.', text)

        free = AppointmentService.objects.create(business=self.biz, name='Control', duration_minutes=20, price=0)
        lead2, _ = self._taken_lead()
        text = self._create(lead=lead2, service=free, professional=None).proposal.staff_message.text
        self.assertNotIn('Precio', text)
        self.assertNotIn('Seña', text)

    def test_professional_nullable_when_service_has_no_professionals(self):
        solo = AppointmentService.objects.create(business=self.biz, name='Consulta', duration_minutes=45, price=500)
        proposal = self._create(service=solo, professional=None).proposal
        self.assertIsNone(proposal.professional_id)
        self.assertIsNone(proposal.professional_name)
        self.assertEqual(proposal.proposed_end_at, _at(10, 45))
        self.assertNotIn(' con ', proposal.staff_message.text)

    def test_professional_required_when_service_has_professionals(self):
        self._invalid('professional_id', professional=None)

    def test_service_and_professional_from_other_business(self):
        other_biz, _ = self._setup_tenant('proposal-foreign')
        service, pro = self._agenda(other_biz)
        self._invalid('service_id', service=service)
        self._invalid('professional_id', professional=pro)

    def test_professional_not_enabled_for_service(self):
        other = AppointmentProfessional.objects.create(business=self.biz, name='Sol')
        AppointmentSchedule.objects.create(
            business=self.biz, professional=other, weekday=0, start_time='09:00', end_time='18:00',
        )
        self._invalid('professional_id', professional=other)

    def test_inactive_service_or_professional(self):
        AppointmentService.objects.filter(pk=self.service.pk).update(is_active=False)
        self._invalid('service_id')
        AppointmentService.objects.filter(pk=self.service.pk).update(is_active=True)
        AppointmentProfessional.objects.filter(pk=self.pro.pk).update(is_active=False)
        self._invalid('professional_id')

    def test_closed_lead(self):
        Lead.objects.filter(pk=self.lead.pk).update(status=Lead.Status.CLOSED, outcome='not_interested')
        self._conflict('lead_closed')
        self.assert_nothing_created()

    def test_lead_with_appointment(self):
        appointment = self._appt(self.biz, self.service, None, _at(15), pro=self.pro)
        Lead.objects.filter(pk=self.lead.pk).update(appointment=appointment)
        self._conflict('lead_has_appointment')
        self.assertFalse(AppointmentProposal.objects.exists())
        self.assertFalse(LeadStaffMessage.objects.exists())

    def test_proposal_does_not_require_takeover(self):
        """Enviar una propuesta es una acción estructurada: no exige la conversación tomada."""
        for state in ('active', 'takeover_pending', 'taken', 'release_pending', 'error'):
            with self.subTest(state=state):
                AppointmentProposal.objects.all().delete()
                LeadStaffMessage.objects.all().delete()
                control = ConversationControl.objects.get(external_conversation_id=self.conv)
                control.state = state
                control.save(update_fields=['state'])
                result = self._create(key=uuid.uuid4())
                self.assertTrue(result.created)

    def test_proposal_does_not_change_conversation_control_or_pause_bot(self):
        ConversationControl.objects.filter(external_conversation_id=self.conv).update(state='active')
        before = ConversationControl.objects.get(external_conversation_id=self.conv)
        self._create()
        after = ConversationControl.objects.get(external_conversation_id=self.conv)
        # Ni estado, ni `taken_by`, ni `command_version` cambian: no hubo takeover.
        self.assertEqual(after.state, before.state)
        self.assertEqual(after.state, 'active')
        self.assertIsNone(after.taken_by_id)
        self.assertEqual(after.command_version, before.command_version)
        self.assertFalse(TakeoverCommand.objects.exists())

    def test_proposal_without_control_row_succeeds(self):
        conversation_id = conv_id()
        lead = self._lead(self.biz, self.channel, external_conversation_id=conversation_id)
        result = self._create(lead=lead)
        self.assertTrue(result.created)
        self.assertFalse(
            ConversationControl.objects.filter(business=self.biz, external_conversation_id=conversation_id).exists(),
        )

    def test_proposal_with_existing_takeover_also_works(self):
        """La conversación tomada (caso existente) sigue siendo un escenario válido."""
        ConversationControl.objects.filter(external_conversation_id=self.conv).update(
            state=ConversationControl.State.TAKEN,
        )
        result = self._create()
        self.assertTrue(result.created)
        self.assertEqual(AppointmentProposal.objects.count(), 1)
        self.assertEqual(LeadStaffMessage.objects.count(), 1)

    def test_lead_without_agent_conversation(self):
        lead = self._lead(self.biz, self.channel)  # external_conversation_id no es `wac1_…`
        with self.assertRaises(TakeoverUnavailable) as ctx:
            self._create(lead=lead)
        self.assertEqual(ctx.exception.code, 'conversation_unavailable')

    @override_settings(AGENT_TAKEOVER_ENABLED=False)
    def test_flag_disabled(self):
        with self.assertRaises(TakeoverUnavailable) as ctx:
            self._create()
        self.assertEqual(ctx.exception.code, 'takeover_disabled')
        self.assert_nothing_created()

    def test_start_in_the_past(self):
        self._invalid('start_at', start_at=timezone.now() - dt.timedelta(hours=1))


# ── Disponibilidad reutilizada ──────────────────────────────────────────────

@override_settings(**TAKEOVER_SETTINGS)
class ProposalAvailabilityTests(ProposalMixin, TestCase):

    def setUp(self):
        self._setup('proposal-availability')

    def test_valid_slot(self):
        self.assertTrue(self._create(start_at=_at(17, 30)).created)

    def test_slot_taken_by_confirmed_or_pending_payment(self):
        self._appt(self.biz, self.service, None, _at(10), pro=self.pro)
        self._appt(
            self.biz, self.service, None, _at(12), pro=self.pro, status_=Appointment.Status.PENDING_PAYMENT,
            expires_at=timezone.now() + dt.timedelta(minutes=10),
        )
        for start in (_at(10), _at(10, 15), _at(12)):
            with self.subTest(start=start):
                with self.assertRaises(proposals.ProposalInvalid) as ctx:
                    self._create(start_at=start)
                self.assertEqual(ctx.exception.field, 'start_at')
        self.assertFalse(AppointmentProposal.objects.exists())

    def test_outside_hours(self):
        self._invalid('start_at', start_at=_at(17, 45))
        self._invalid('start_at', start_at=_at(8, 30))
        self._invalid('start_at', start_at=dt.datetime.fromisoformat('2030-03-05T10:00:00-03:00'))

    def test_closed_exception(self):
        AppointmentException.objects.create(business=self.biz, date=MONDAY, is_closed=True)
        self._invalid('start_at')

    def test_professional_exception(self):
        AppointmentException.objects.create(business=self.biz, professional=self.pro, date=MONDAY, is_closed=True)
        self._invalid('start_at')

    def test_existing_proposal_does_not_block_slot(self):
        self._create()
        other_lead, _ = self._taken_lead()
        self.assertTrue(self._create(lead=other_lead).created)


# ── Snapshots ───────────────────────────────────────────────────────────────

@override_settings(**TAKEOVER_SETTINGS)
class ProposalSnapshotTests(ProposalMixin, TestCase):

    def setUp(self):
        self._setup('proposal-snapshot')

    def test_snapshots_and_later_catalog_changes(self):
        self.service.deposit_type = AppointmentService.DepositType.FIXED
        self.service.deposit_value = Decimal('250')
        self.service.save()
        self.biz.currency = 'USD'
        self.biz.save(update_fields=['currency'])
        proposal = self._create().proposal
        expected = dict(
            service_name='Corte', professional_name='Lu', service_duration_minutes=30,
            service_price=Decimal('1000.00'), currency='USD', deposit_type='fixed',
            deposit_value=Decimal('250.00'), deposit_amount=Decimal('250.00'),
            proposed_end_at=_at(10, 30),
        )

        AppointmentService.objects.filter(pk=self.service.pk).update(
            name='Corte Premium', duration_minutes=60, price=Decimal('9999'), deposit_type='percentage',
            deposit_value=Decimal('50'),
        )
        AppointmentProfessional.objects.filter(pk=self.pro.pk).update(name='Lucía')
        type(self.biz).objects.filter(pk=self.biz.pk).update(currency='ARS')

        proposal.refresh_from_db()
        for field, value in expected.items():
            self.assertEqual(getattr(proposal, field), value, field)


# ── Idempotencia ────────────────────────────────────────────────────────────

@override_settings(**TAKEOVER_SETTINGS)
class ProposalIdempotencyTests(ProposalMixin, TestCase):

    def setUp(self):
        self._setup('proposal-idem')

    def test_replay_same_payload_returns_existing_without_new_message(self):
        key = uuid.uuid4()
        first = self._create(key=key)
        with self.captureOnCommitCallbacks() as callbacks:
            second = self._create(key=key)
        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(second.proposal.pk, first.proposal.pk)
        self.assertEqual(callbacks, [])
        self.assertEqual(AppointmentProposal.objects.count(), 1)
        self.assertEqual(LeadStaffMessage.objects.count(), 1)

    def test_replay_survives_later_state_changes(self):
        key = uuid.uuid4()
        first = self._create(key=key).proposal
        ConversationControl.objects.filter(external_conversation_id=self.conv).update(state='active')
        self._appt(self.biz, self.service, None, _at(10), pro=self.pro)
        self.assertEqual(self._create(key=key).proposal.pk, first.pk)

    def test_same_key_different_payload_conflicts(self):
        key = uuid.uuid4()
        self._create(key=key)
        other_lead, _ = self._taken_lead()
        solo = AppointmentService.objects.create(business=self.biz, name='Consulta', duration_minutes=30, price=0)
        for kwargs in (
            {'start_at': _at(11)}, {'service': solo, 'professional': None}, {'lead': other_lead},
        ):
            with self.subTest(kwargs=list(kwargs)):
                self._conflict('idempotency_key_reused', key=key, **kwargs)
        self.assertEqual(AppointmentProposal.objects.count(), 1)
        self.assertEqual(LeadStaffMessage.objects.count(), 1)

    def test_same_key_in_other_business_is_independent(self):
        key = uuid.uuid4()
        self._create(key=key)
        other_biz, channel = self._setup_tenant('proposal-idem-other')
        service, pro = self._agenda(other_biz)
        AppointmentSchedule.objects.create(business=other_biz, weekday=0, start_time='09:00', end_time='18:00')
        AppointmentSchedule.objects.create(
            business=other_biz, professional=pro, weekday=0, start_time='09:00', end_time='18:00',
        )
        lead, _ = self._taken_lead(other_biz, channel)
        result = proposals.create_and_send_appointment_proposal(
            lead=lead, service_id=service.pk, professional_id=pro.pk, start_at=_at(10), idempotency_key=key,
            user=self._member(other_biz),
        )
        self.assertTrue(result.created)


# ── Reemplazo ───────────────────────────────────────────────────────────────

@override_settings(**TAKEOVER_SETTINGS)
class ProposalSupersedeTests(ProposalMixin, TestCase):

    def setUp(self):
        self._setup('proposal-supersede')

    def test_new_proposal_supersedes_active_one(self):
        a = self._create(start_at=_at(10)).proposal
        b = self._create(start_at=_at(11)).proposal
        a.refresh_from_db()
        self.assertEqual(a.status, PStatus.SUPERSEDED)
        self.assertEqual(b.status, PStatus.PENDING_DELIVERY)
        self.assertEqual(proposals.current_proposal(self.lead), b)
        self.assertEqual(LeadStaffMessage.objects.count(), 2)

    def test_queued_and_expired_proposal_becomes_expired_not_superseded(self):
        a = self._create(start_at=_at(10)).proposal
        self._deliver(a, ok())
        AppointmentProposal.objects.filter(pk=a.pk).update(expires_at=timezone.now() - dt.timedelta(seconds=1))
        self._create(start_at=_at(11))
        a.refresh_from_db()
        self.assertEqual(a.status, PStatus.EXPIRED)

    def test_superseded_proposal_is_not_revived_by_late_delivery(self):
        # El reemplazo ocurre mientras el HTTP está en vuelo (después del guard).
        a = self._create(start_at=_at(10)).proposal

        def accept_after_supersede(payload):
            self._create(start_at=_at(11))
            return ok()

        send = FakeSend(accept_after_supersede)
        self.assertEqual(svc.deliver_staff_message(a.staff_message_id, send=send), MsgStatus.DELIVERED)
        self.assertEqual(len(send.payloads), 1)
        a.refresh_from_db()
        self.assertEqual(a.status, PStatus.SUPERSEDED)
        self.assertIsNone(a.expires_at)


# ── Propuesta retirada antes del delivery ──────────────────────────────────

@override_settings(**TAKEOVER_SETTINGS)
class ProposalWithdrawnDeliveryTests(ProposalMixin, TestCase):

    def setUp(self):
        self._setup('proposal-withdrawn')

    def assert_withdrawn(self, proposal, status_, error):
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, status_)
        message = proposal.staff_message
        self.assertEqual(message.status, MsgStatus.FAILED)
        self.assertEqual(message.last_error, error)
        self.assertIsNone(message.lease_until)
        self.assertIsNone(message.next_attempt_at)
        self.assertIsNone(message.delivered_at)

    def test_superseded_pending_message_is_not_sent(self):
        a = self._create(start_at=_at(10)).proposal
        b = self._create(start_at=_at(11)).proposal
        send = FakeSend(ok())
        self.assertEqual(svc.deliver_staff_message(a.staff_message_id, send=send), MsgStatus.FAILED)
        self.assertEqual(len(send.payloads), 0)
        self.assert_withdrawn(a, PStatus.SUPERSEDED, 'proposal_superseded')
        self.assertEqual(proposals.current_proposal(self.lead), b)
        # Terminal: ni el Beat ni un kick tardío lo reintentan.
        self.assertIsNone(svc.deliver_staff_message(a.staff_message_id, send=send, now=later(3600)))
        counts = svc.retry_due_staff_messages(send=send, now=later(3600))
        self.assertEqual(len(send.payloads), 1)  # solo B
        self.assertEqual(counts['delivered'], 1)
        self.assertEqual(send.payloads[0].client_message_id, b.staff_message.client_message_id)
        b.refresh_from_db()
        self.assertEqual(b.status, PStatus.QUEUED)
        self.assertEqual(LeadStaffMessage.objects.count(), 2)

    def test_retry_after_supersede_is_not_sent(self):
        a = self._create(start_at=_at(10)).proposal
        send = FakeSend(retryable(), ok())
        self.assertEqual(svc.deliver_staff_message(a.staff_message_id, send=send), 'retry')
        self.assertEqual(len(send.payloads), 1)
        self._create(start_at=_at(11))
        self.assertEqual(svc.deliver_staff_message(a.staff_message_id, send=send, now=later(120)), MsgStatus.FAILED)
        self.assertEqual(len(send.payloads), 1)
        self.assert_withdrawn(a, PStatus.SUPERSEDED, 'proposal_superseded')

    def test_stuck_delivering_superseded_is_not_resent(self):
        a = self._create(start_at=_at(10)).proposal
        LeadStaffMessage.objects.filter(pk=a.staff_message_id).update(
            status=MsgStatus.DELIVERING, attempts=1, lease_until=timezone.now(), next_attempt_at=None,
        )
        self._create(start_at=_at(11))
        send = FakeSend(ok())
        self.assertEqual(svc.deliver_staff_message(a.staff_message_id, send=send, now=later(120)), MsgStatus.FAILED)
        self.assertEqual(len(send.payloads), 0)
        self.assert_withdrawn(a, PStatus.SUPERSEDED, 'proposal_superseded')

    def test_expired_before_delivery_is_not_sent(self):
        a = self._create(start_at=_at(10)).proposal
        AppointmentProposal.objects.filter(pk=a.pk).update(status=PStatus.EXPIRED)
        send = FakeSend(ok())
        self.assertEqual(svc.deliver_staff_message(a.staff_message_id, send=send), MsgStatus.FAILED)
        self.assertEqual(len(send.payloads), 0)
        self.assert_withdrawn(a, PStatus.EXPIRED, 'proposal_expired')

    def test_already_queued_is_not_unsent(self):
        a = self._create(start_at=_at(10)).proposal
        send = FakeSend(ok())
        self.assertEqual(svc.deliver_staff_message(a.staff_message_id, send=send), MsgStatus.DELIVERED)
        b = self._create(start_at=_at(11)).proposal
        a.refresh_from_db()
        self.assertEqual(a.status, PStatus.SUPERSEDED)
        self.assertEqual(a.staff_message.status, MsgStatus.DELIVERED)
        self.assertIsNone(svc.deliver_staff_message(a.staff_message_id, send=send, now=later(3600)))
        self.assertEqual(len(send.payloads), 1)
        self.assertEqual(proposals.current_proposal(self.lead), b)

    def test_active_pending_proposal_is_sent_normally(self):
        a = self._create(start_at=_at(10)).proposal
        send = FakeSend(ok())
        self.assertEqual(svc.deliver_staff_message(a.staff_message_id, send=send), MsgStatus.DELIVERED)
        self.assertEqual(len(send.payloads), 1)
        a.refresh_from_db()
        self.assertEqual(a.status, PStatus.QUEUED)

    def test_plain_staff_message_is_sent_normally(self):
        message = svc.send_staff_message(self.lead, 'Hola', user=self.user)
        send = FakeSend(ok())
        self.assertEqual(svc.deliver_staff_message(message.pk, send=send), MsgStatus.DELIVERED)
        self.assertEqual(len(send.payloads), 1)


# ── Outbox ↔ estado de la propuesta ─────────────────────────────────────────

@override_settings(**TAKEOVER_SETTINGS)
class ProposalOutboxTests(ProposalMixin, TestCase):

    def setUp(self):
        self._setup('proposal-outbox')

    def test_atomic_with_staff_message(self):
        with mock.patch.object(AppointmentProposal, 'save', side_effect=IntegrityError('boom')):
            with self.assertRaises(IntegrityError):
                self._create()
        self.assert_nothing_created()

    def test_message_failure_rolls_back_proposal(self):
        with mock.patch.object(proposals, 'enqueue_staff_message', side_effect=svc.MessageTextInvalid('too_long')):
            with self.assertRaises(svc.MessageTextInvalid):
                self._create()
        self.assert_nothing_created()

    def test_queued_when_agent_accepts(self):
        proposal = self._create().proposal
        now = timezone.now()
        self.assertEqual(self._deliver(proposal, ok(), now=now), MsgStatus.DELIVERED)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, PStatus.QUEUED)
        self.assertEqual(proposal.expires_at, now + dt.timedelta(hours=24))
        self.assertFalse(Appointment.objects.exists())

    def test_terminal_failure_marks_delivery_failed(self):
        proposal = self._create().proposal
        self.assertEqual(self._deliver(proposal, terminal('conversation_not_taken', 409)), MsgStatus.FAILED)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, PStatus.DELIVERY_FAILED)
        self.assertIsNone(proposal.expires_at)
        self.assertIsNone(proposals.current_proposal(self.lead))
        self.assertEqual(proposal.staff_message.last_error, 'conversation_not_taken')

    def test_retry_keeps_pending_then_queues_same_message(self):
        proposal = self._create().proposal
        self.assertEqual(self._deliver(proposal, retryable()), 'retry')
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, PStatus.PENDING_DELIVERY)
        send = FakeSend(ok())
        svc.deliver_staff_message(proposal.staff_message_id, send=send, now=later(120))
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, PStatus.QUEUED)
        self.assertEqual(LeadStaffMessage.objects.count(), 1)
        self.assertEqual(send.payloads[0].client_message_id, proposal.staff_message.client_message_id)

    @override_settings(AGENT_TAKEOVER_MAX_ATTEMPTS=1)
    def test_exhausted_retries_mark_delivery_failed(self):
        proposal = self._create().proposal
        self.assertEqual(self._deliver(proposal, retryable()), MsgStatus.FAILED)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, PStatus.DELIVERY_FAILED)

    def test_plain_staff_messages_unaffected(self):
        message = svc.send_staff_message(self.lead, 'Hola', user=self.user)
        self.assertEqual(svc.deliver_staff_message(message.pk, send=FakeSend(ok())), MsgStatus.DELIVERED)
        self.assertFalse(AppointmentProposal.objects.exists())


# ── Expiración lazy ─────────────────────────────────────────────────────────

@override_settings(**TAKEOVER_SETTINGS)
class ProposalExpirationTests(ProposalMixin, TestCase):

    def setUp(self):
        self._setup('proposal-expiry')

    def test_pending_delivery_never_expires(self):
        proposal = self._create().proposal
        self.assertEqual(proposals.current_proposal(self.lead, now=later(3 * 86400)), proposal)

    def test_current_expires_lazily(self):
        proposal = self._create().proposal
        self._deliver(proposal, ok())
        proposal.refresh_from_db()
        self.assertEqual(proposals.current_proposal(self.lead, now=proposal.expires_at - dt.timedelta(seconds=1)), proposal)
        self.assertIsNone(proposals.current_proposal(self.lead, now=proposal.expires_at))
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, PStatus.EXPIRED)

    def test_replay_of_expired_proposal_reports_expired(self):
        key = uuid.uuid4()
        proposal = self._create(key=key).proposal
        self._deliver(proposal, ok())
        AppointmentProposal.objects.filter(pk=proposal.pk).update(expires_at=timezone.now() - dt.timedelta(seconds=1))
        result = self._create(key=key)
        self.assertFalse(result.created)
        self.assertEqual(result.proposal.status, PStatus.EXPIRED)


# ── API ─────────────────────────────────────────────────────────────────────

@override_settings(**TAKEOVER_SETTINGS)
class ProposalApiTests(ProposalMixin, APITestCase):

    def setUp(self):
        self._setup('proposal-api')
        self.user = _login(self.client, self.biz, 'manager')
        self.payload = {
            'service_id': str(self.service.pk), 'professional_id': str(self.pro.pk), 'start_at': START,
            'idempotency_key': str(uuid.uuid4()),
        }

    def _url(self, lead=None):
        return f'/api/v1/leads/{(lead or self.lead).pk}/appointment-proposals/'

    def _current_url(self, lead=None):
        return f'{self._url(lead)}current/'

    def post(self, payload=None, lead=None, client=None):
        return (client or self.client).post(self._url(lead), self.payload if payload is None else payload, format='json')

    def test_create_returns_201_compact_payload(self):
        response = self.post()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        proposal = AppointmentProposal.objects.get()
        self.assertEqual(response.data, {
            'id': str(proposal.pk),
            'status': 'pending_delivery',
            'service': {'id': str(self.service.pk), 'name': 'Corte'},
            'professional': {'id': str(self.pro.pk), 'name': 'Lu'},
            'proposed_start_at': response.data['proposed_start_at'],
            'proposed_end_at': response.data['proposed_end_at'],
            'snapshots': {
                'service_name': 'Corte', 'professional_name': 'Lu', 'service_duration_minutes': 30,
                'service_price': '1000.00', 'currency': 'ARS', 'deposit_type': 'none', 'deposit_value': '0.00',
                'deposit_amount': '0.00',
            },
            'expires_at': None,
            'patient_confirmation': None,
            'staff_message_status': 'pending',
            'delivery_error': None,
            'created_at': response.data['created_at'],
        })
        self.assertEqual(
            dt.datetime.fromisoformat(response.data['proposed_end_at']) - dt.datetime.fromisoformat(START),
            dt.timedelta(minutes=30),
        )
        self.assertEqual(proposal.created_by, self.user)

    def test_replay_returns_200_and_conflict_409(self):
        self.assertEqual(self.post().status_code, status.HTTP_201_CREATED)
        replay = self.post()
        self.assertEqual(replay.status_code, status.HTTP_200_OK, replay.data)
        conflict = self.post({**self.payload, 'start_at': '2030-03-04T11:00:00-03:00'})
        self.assertEqual(conflict.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(conflict.data['code'], 'idempotency_key_reused')
        self.assertEqual(LeadStaffMessage.objects.count(), 1)

    def test_rejects_backend_owned_fields(self):
        for extra in ('end_at', 'price', 'deposit', 'deposit_amount', 'service_name', 'professional_name', 'text'):
            with self.subTest(extra=extra):
                response = self.post({**self.payload, extra: 'x', 'idempotency_key': str(uuid.uuid4())})
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(extra, response.data)
        self.assertFalse(AppointmentProposal.objects.exists())

    def test_requires_fields(self):
        for missing in ('service_id', 'start_at', 'idempotency_key'):
            with self.subTest(missing=missing):
                payload = {k: v for k, v in self.payload.items() if k != missing}
                self.assertEqual(self.post(payload).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.post({**self.payload, 'idempotency_key': 'not-a-uuid'}).status_code, 400)

    def test_error_mapping(self):
        slot = self.post({**self.payload, 'start_at': '2030-03-04T20:00:00-03:00'})
        self.assertEqual(slot.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('start_at', slot.data)
        # El bot activo (conversación no tomada) no bloquea el envío de la propuesta.
        ConversationControl.objects.filter(external_conversation_id=self.conv).update(state='active')
        not_taken = self.post()
        self.assertEqual(not_taken.status_code, status.HTTP_201_CREATED, not_taken.data)
        with override_settings(AGENT_TAKEOVER_ENABLED=False):
            disabled = self.post({**self.payload, 'idempotency_key': str(uuid.uuid4())})
        self.assertEqual(disabled.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(AppointmentProposal.objects.count(), 1)

    def test_foreign_and_missing_lead_404(self):
        other_biz, channel = self._setup_tenant('proposal-api-foreign')
        lead, _ = self._taken_lead(other_biz, channel)
        self.assertEqual(self.post(lead=lead).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.get(self._current_url(lead)).status_code, status.HTTP_404_NOT_FOUND)
        lead.pk = uuid.uuid4()
        self.assertEqual(self.post(lead=lead).status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(AppointmentProposal.objects.exists())

    def test_current_endpoint(self):
        self.assertEqual(self.client.get(self._current_url()).status_code, status.HTTP_404_NOT_FOUND)
        created = self.post().data
        response = self.client.get(self._current_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], created['id'])
        proposal = AppointmentProposal.objects.get()
        self._deliver(proposal, ok())
        response = self.client.get(self._current_url())
        self.assertEqual(response.data['status'], 'queued')
        self.assertEqual(response.data['staff_message_status'], 'delivered')
        self.assertIsNotNone(response.data['expires_at'])
        AppointmentProposal.objects.filter(pk=proposal.pk).update(expires_at=timezone.now() - dt.timedelta(seconds=1))
        self.assertEqual(self.client.get(self._current_url()).status_code, status.HTTP_404_NOT_FOUND)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, PStatus.EXPIRED)

    def test_owner_admin_manager_can_create(self):
        for role in ('owner', 'admin', 'manager'):
            with self.subTest(role=role):
                Membership.objects.filter(business=self.biz).delete()
                api = APIClient()
                _login(api, self.biz, role)
                lead, _ = self._taken_lead()
                response = self.post({**self.payload, 'idempotency_key': str(uuid.uuid4())}, lead=lead, client=api)
                self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
                self.assertEqual(api.get(self._current_url(lead)).status_code, status.HTTP_200_OK)

    def test_current_exposes_latest_delivery_failure_not_old_failures(self):
        created = self.post().data
        proposal = AppointmentProposal.objects.get(pk=created['id'])
        AppointmentProposal.objects.filter(pk=proposal.pk).update(status=PStatus.DELIVERY_FAILED)
        LeadStaffMessage.objects.filter(pk=proposal.staff_message_id).update(
            status=MsgStatus.FAILED, last_error='conversation_not_taken', failed_at=timezone.now(),
        )
        response = self.client.get(self._current_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'delivery_failed')
        self.assertEqual(response.data['delivery_error'], 'conversation_not_taken')
        replacement = self.post({**self.payload, 'idempotency_key': str(uuid.uuid4())}).data
        self.assertEqual(self.client.get(self._current_url()).data['id'], replacement['id'])
        for terminal_status in (PStatus.EXPIRED, PStatus.SUPERSEDED):
            AppointmentProposal.objects.filter(pk=replacement['id']).update(status=terminal_status)
            self.assertEqual(self.client.get(self._current_url()).status_code, status.HTTP_404_NOT_FOUND)

    def test_viewer_denied(self):
        Membership.objects.filter(business=self.biz).delete()
        _login(self.client, self.biz, 'viewer')
        self.assertEqual(self.post().status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get(self._current_url()).status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(AppointmentProposal.objects.exists())

    def test_unauthenticated(self):
        self.client.force_authenticate(user=None)
        self.assertIn(self.post().status_code, (401, 403))

    def test_overrides_revoking_either_permission_deny(self):
        for permission in ('manage_leads', 'manage_appointments'):
            with self.subTest(permission=permission):
                override = RolePermissionOverride.objects.create(
                    business=self.biz, role='manager', service='appointments', permission=permission, enabled=False,
                )
                response = self.post({**self.payload, 'idempotency_key': str(uuid.uuid4())})
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                override.delete()
        RolePermissionOverride.objects.create(
            business=self.biz, role='manager', service='appointments', permission='view_appointments', enabled=False,
        )
        self.assertEqual(self.client.get(self._current_url()).status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(AppointmentProposal.objects.exists())


# ── Concurrencia real (doble click) ─────────────────────────────────────────

@override_settings(**TAKEOVER_SETTINGS)
class ProposalConcurrencyTests(ProposalMixin, TransactionTestCase):
    # Mismo workaround que `test_public_booking_concurrency` (flush con CASCADE).
    available_apps = [cfg.name for cfg in django_apps.get_app_configs()]

    def setUp(self):
        self._setup('proposal-concurrency')

    def test_double_click_creates_single_proposal_and_message(self):
        key = uuid.uuid4()
        results, errors = [], []
        barrier = threading.Barrier(2)

        def attempt():
            try:
                barrier.wait()
                results.append(self._create(key=key))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                connections.close_all()

        with mock.patch.object(svc, '_kick'):
            threads = [threading.Thread(target=attempt) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(sorted(r.created for r in results), [False, True])
        self.assertEqual({r.proposal.pk for r in results}, {AppointmentProposal.objects.get().pk})
        self.assertEqual(LeadStaffMessage.objects.count(), 1)
