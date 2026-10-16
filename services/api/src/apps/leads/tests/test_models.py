"""Modelos y constraints de apps.leads (AGENT 02A)."""
from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import DataError, IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.customers.models import Customer
from apps.leads.models import AgentChannel, AgentCredential, AgentInstance, Lead, LeadAgentState, LeadNote

from .factories import SECRET, TEST_KEY, make_business, make_channel, make_credential, make_instance, make_state

User = get_user_model()


class DbAssertMixin:
    def assertDbRejects(self, fn):
        # IntegrityError: constraints/NOT NULL/unique. DataError: varchar overflow.
        with self.assertRaises((IntegrityError, DataError)):
            with transaction.atomic():
                fn()


class AgentInstanceTests(DbAssertMixin, TestCase):
    def test_valid_external_id(self):
        instance = make_instance('dental-agent-prod')
        instance.full_clean()
        self.assertTrue(instance.is_enabled)
        self.assertIsNone(instance.disabled_at)
        self.assertIsInstance(instance.pk, uuid.UUID)
        self.assertNotEqual(str(instance.pk), instance.external_id)

    def test_invalid_external_id_rejected_by_validation(self):
        for bad in ['ab', 'Dental-Agent', 'dental_agent', 'dental agent', 'x' * 65, '']:
            with self.subTest(bad=bad):
                with self.assertRaises(ValidationError):
                    AgentInstance(external_id=bad, name='n').full_clean()

    def test_invalid_external_id_rejected_by_db(self):
        self.assertDbRejects(lambda: AgentInstance.objects.create(external_id='Bad_ID', name='n'))

    def test_external_id_unique(self):
        make_instance('dental-agent-prod')
        self.assertDbRejects(lambda: make_instance('dental-agent-prod'))

    def test_external_id_immutable(self):
        instance = make_instance('dental-agent-prod')
        instance.external_id = 'dental-agent-other'
        with self.assertRaises(ValueError):
            instance.save()
        instance.refresh_from_db()
        instance.name = 'renamed'
        instance.save()  # otros campos sí se pueden editar


@override_settings(AGENT_SECRET_ENCRYPTION_KEY=TEST_KEY)
class AgentCredentialTests(DbAssertMixin, TestCase):
    def setUp(self):
        self.instance = make_instance()

    def test_secret_stored_encrypted_and_roundtrips(self):
        credential = make_credential(self.instance)
        credential.refresh_from_db()
        self.assertNotEqual(credential.encrypted_secret, SECRET)
        self.assertNotIn(SECRET, credential.encrypted_secret)
        self.assertEqual(credential.get_secret(), SECRET)
        self.assertEqual(credential.status, AgentCredential.Status.ACTIVE)

    def test_str_and_repr_never_include_secret(self):
        credential = make_credential(self.instance)
        for text in (str(credential), repr(credential)):
            self.assertNotIn(SECRET, text)
            self.assertNotIn(credential.encrypted_secret, text)

    def test_plaintext_secret_rejected_by_db(self):
        self.assertDbRejects(lambda: AgentCredential.objects.create(
            agent_instance=self.instance, key_id='raw', encrypted_secret=SECRET,
        ))

    def test_missing_key_fails_closed(self):
        from apps.leads.crypto import AgentSecretEncryptionError
        with override_settings(AGENT_SECRET_ENCRYPTION_KEY=''):
            with self.assertRaises(AgentSecretEncryptionError):
                make_credential(self.instance, key_id='nokey')
        self.assertFalse(AgentCredential.objects.filter(key_id='nokey').exists())

    def test_key_id_unique(self):
        make_credential(self.instance, key_id='k1')
        other = make_instance('other-agent')
        self.assertDbRejects(lambda: make_credential(other, key_id='k1'))

    def test_key_id_format(self):
        for bad in ['', 'has space', 'k/1', 'x' * 65]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValidationError):
                    AgentCredential(agent_instance=self.instance, key_id=bad, encrypted_secret='gAAAAAx').full_clean()
        self.assertDbRejects(lambda: make_credential(self.instance, key_id='k/1'))
        make_credential(self.instance, key_id='K_1.prod-2026')

    def test_status_states(self):
        retiring = make_credential(self.instance, key_id='k-ret', status=AgentCredential.Status.RETIRING)
        self.assertEqual(retiring.status, 'retiring')
        revoked = make_credential(
            self.instance, key_id='k-rev', status=AgentCredential.Status.REVOKED, revoked_at=timezone.now(),
        )
        self.assertEqual(revoked.status, 'revoked')

    def test_invalid_status_rejected_by_db(self):
        self.assertDbRejects(lambda: make_credential(self.instance, key_id='k-bad', status='disabled'))

    def test_revoked_requires_revoked_at(self):
        self.assertDbRejects(lambda: make_credential(self.instance, key_id='k-a', status=AgentCredential.Status.REVOKED))
        self.assertDbRejects(lambda: make_credential(self.instance, key_id='k-b', revoked_at=timezone.now()))

    def test_multiple_credentials_per_instance(self):
        make_credential(self.instance, key_id='k1')
        make_credential(self.instance, key_id='k2')
        self.assertEqual(self.instance.credentials.count(), 2)


class AgentChannelTests(DbAssertMixin, TestCase):
    def setUp(self):
        self.instance = make_instance()
        self.biz_a = make_business('agent-ch-a')
        self.biz_b = make_business('agent-ch-b')

    def test_active_channel_valid(self):
        channel = make_channel(self.instance, self.biz_a)
        channel.full_clean()
        self.assertTrue(channel.is_active)
        self.assertEqual(channel.provider, AgentChannel.Provider.WHATSAPP_CLOUD)

    def test_same_phone_number_active_twice_rejected(self):
        make_channel(self.instance, self.biz_a, '111')
        self.assertDbRejects(lambda: make_channel(self.instance, self.biz_a, '111'))

    def test_same_phone_number_active_in_other_business_rejected(self):
        make_channel(self.instance, self.biz_a, '111')
        self.assertDbRejects(lambda: make_channel(self.instance, self.biz_b, '111'))
        other_instance = make_instance('other-agent')
        self.assertDbRejects(lambda: make_channel(other_instance, self.biz_b, '111'))

    def test_reassignment_after_deactivation_allowed(self):
        old = make_channel(self.instance, self.biz_a, '111')
        old.is_active = False
        old.deactivated_at = timezone.now()
        old.save()
        new = make_channel(self.instance, self.biz_b, '111')
        self.assertTrue(new.is_active)
        # Puede haber varios históricos inactivos para el mismo número.
        new.is_active = False
        new.save()
        make_channel(self.instance, self.biz_a, '111')

    def test_two_phone_numbers_same_business_allowed(self):
        make_channel(self.instance, self.biz_a, '111')
        make_channel(self.instance, self.biz_a, '222')
        self.assertEqual(self.biz_a.agent_channels.filter(is_active=True).count(), 2)

    def test_instance_with_several_channels_allowed(self):
        make_channel(self.instance, self.biz_a, '111')
        make_channel(self.instance, self.biz_b, '222')
        self.assertEqual(self.instance.channels.count(), 2)

    def test_phone_number_id_format(self):
        for bad in ['', '+5491112345678', '12a4', '1' * 33]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValidationError):
                    AgentChannel(agent_instance=self.instance, business=self.biz_a, phone_number_id=bad).full_clean()
        self.assertDbRejects(lambda: make_channel(self.instance, self.biz_a, '12a4'))
        make_channel(self.instance, self.biz_a, '1' * 32)

    def test_invalid_provider_rejected_by_db(self):
        self.assertDbRejects(lambda: make_channel(self.instance, self.biz_a, '111', provider='telegram'))

    def test_active_channel_cannot_have_deactivated_at(self):
        self.assertDbRejects(lambda: make_channel(self.instance, self.biz_a, '111', deactivated_at=timezone.now()))


class LeadTests(DbAssertMixin, TestCase):
    def setUp(self):
        self.business = make_business('lead-a')

    def test_defaults(self):
        lead = Lead.objects.create(business=self.business)
        self.assertEqual(lead.source, Lead.Source.WHATSAPP_AGENT)
        self.assertEqual(lead.status, Lead.Status.NEW)
        for field in ('outcome', 'assigned_to', 'customer', 'appointment', 'needs_attention_at', 'closed_at', 'closed_by'):
            self.assertIsNone(getattr(lead, field), field)
        self.assertIsNotNone(lead.created_at)
        self.assertIsNotNone(lead.updated_at)

    def test_business_required(self):
        self.assertDbRejects(lambda: Lead.objects.create())

    def test_customer_link_nullable_and_set_null(self):
        customer = Customer.objects.create(business=self.business, name='Ana')
        lead = Lead.objects.create(business=self.business, customer=customer)
        customer.delete()
        lead.refresh_from_db()
        self.assertIsNone(lead.customer_id)

    def test_customer_from_other_business_rejected(self):
        other = make_business('lead-b')
        customer = Customer.objects.create(business=other, name='Otro')
        with self.assertRaises(ValueError):
            Lead.objects.create(business=self.business, customer=customer)

    def test_outcome_required_when_closed(self):
        self.assertDbRejects(lambda: Lead.objects.create(business=self.business, status=Lead.Status.CLOSED))
        lead = Lead.objects.create(
            business=self.business, status=Lead.Status.CLOSED, outcome=Lead.Outcome.SPAM, closed_at=timezone.now(),
        )
        self.assertEqual(lead.outcome, 'spam')

    def test_outcome_null_while_open(self):
        for status in (Lead.Status.NEW, Lead.Status.IN_PROGRESS):
            with self.subTest(status=status):
                self.assertDbRejects(lambda: Lead.objects.create(
                    business=self.business, status=status, outcome=Lead.Outcome.BOOKED,
                ))

    def test_invalid_enums_rejected_by_db(self):
        self.assertDbRejects(lambda: Lead.objects.create(business=self.business, status='pending'))
        self.assertDbRejects(lambda: Lead.objects.create(business=self.business, source='web'))
        self.assertDbRejects(lambda: Lead.objects.create(
            business=self.business, status=Lead.Status.CLOSED, outcome='converted',
        ))


class LeadAgentStateTests(DbAssertMixin, TestCase):
    def setUp(self):
        self.business = make_business('state-a')
        self.instance = make_instance()
        self.channel = make_channel(self.instance, self.business)
        self.lead = Lead.objects.create(business=self.business)

    def test_create_and_defaults(self):
        state = make_state(self.lead, self.channel)
        state.full_clean()
        self.assertEqual(self.lead.agent_state, state)
        self.assertEqual(state.agent_status, LeadAgentState.AgentStatus.ACTIVE)
        self.assertFalse(state.urgency)
        self.assertFalse(state.handoff_requested)
        self.assertEqual(state.handoff_reasons, [])
        self.assertNotIn('+5491112345678', str(state))

    def test_one_to_one(self):
        make_state(self.lead, self.channel)
        self.assertDbRejects(lambda: make_state(self.lead, self.channel))

    def test_external_identity_unique_per_instance(self):
        external_lead_id = uuid.uuid4()
        make_state(self.lead, self.channel, external_lead_id=external_lead_id)
        other_lead = Lead.objects.create(business=self.business)
        self.assertDbRejects(lambda: make_state(other_lead, self.channel, external_lead_id=external_lead_id))

    def test_same_external_id_in_other_instance_allowed(self):
        external_lead_id = uuid.uuid4()
        make_state(self.lead, self.channel, external_lead_id=external_lead_id)
        other_instance = make_instance('other-agent')
        other_channel = make_channel(other_instance, self.business, '999')
        other_lead = Lead.objects.create(business=self.business)
        make_state(other_lead, other_channel, external_lead_id=external_lead_id)

    def test_version_must_be_positive(self):
        self.assertDbRejects(lambda: make_state(self.lead, self.channel, applied_version=0))

    def test_payload_hash_format(self):
        self.assertDbRejects(lambda: make_state(self.lead, self.channel, payload_hash='abc'))
        self.assertDbRejects(lambda: make_state(self.lead, self.channel, payload_hash='A' * 64))
        make_state(self.lead, self.channel, payload_hash='')

    def test_phone_e164_format(self):
        self.assertDbRejects(lambda: make_state(self.lead, self.channel, phone_e164='1112345678'))
        self.assertDbRejects(lambda: make_state(self.lead, self.channel, phone_e164='+0111'))

    def test_enums(self):
        self.assertDbRejects(lambda: make_state(self.lead, self.channel, agent_status='paused'))
        self.assertDbRejects(lambda: make_state(self.lead, self.channel, close_reason='timeout'))
        state = make_state(
            self.lead, self.channel, agent_status=LeadAgentState.AgentStatus.CLOSED,
            close_reason=LeadAgentState.CloseReason.RECEPTION, closed_at=timezone.now(),
        )
        self.assertEqual(state.close_reason, 'reception')

    def test_reasons_require_handoff(self):
        self.assertDbRejects(lambda: make_state(self.lead, self.channel, handoff_reasons=['wants_human']))
        state = make_state(
            self.lead, self.channel, handoff_requested=True, handoff_requested_at=timezone.now(),
            handoff_reasons=['wants_human'],
        )
        self.assertEqual(state.handoff_reasons, ['wants_human'])

    def test_text_lengths(self):
        cases = {
            'patient_name': LeadAgentState.PATIENT_NAME_MAX_LENGTH,
            'whatsapp_profile_name': LeadAgentState.PATIENT_NAME_MAX_LENGTH,
            'reason': LeadAgentState.REASON_MAX_LENGTH,
            'preferred_time': LeadAgentState.REASON_MAX_LENGTH,
            'summary': LeadAgentState.SUMMARY_MAX_LENGTH,
            'external_conversation_id': 64,
        }
        for field, limit in cases.items():
            with self.subTest(field=field):
                self.assertEqual(LeadAgentState._meta.get_field(field).max_length, limit)
                self.assertDbRejects(lambda: make_state(self.lead, self.channel, **{field: 'x' * (limit + 1)}))
        make_state(self.lead, self.channel, patient_name='x' * 150, reason='y' * 500, summary='z' * 2000)

    def test_channel_must_belong_to_lead_business(self):
        other = make_business('state-b')
        other_lead = Lead.objects.create(business=other)
        with self.assertRaises(ValueError):
            make_state(other_lead, self.channel)

    def test_channel_must_belong_to_agent_instance(self):
        other_instance = make_instance('other-agent')
        with self.assertRaises(ValueError):
            make_state(self.lead, self.channel, agent_instance=other_instance)

    def test_business_delete_cascades_through_channel(self):
        make_state(self.lead, self.channel)
        self.business.delete()
        self.assertFalse(LeadAgentState.objects.exists())
        self.assertFalse(AgentChannel.objects.exists())
        self.assertTrue(AgentInstance.objects.filter(pk=self.instance.pk).exists())


class LeadNoteTests(DbAssertMixin, TestCase):
    def setUp(self):
        self.business = make_business('note-a')
        self.lead = Lead.objects.create(business=self.business)
        self.user = User.objects.create_user(username='note-author', email='note-author@example.test', password='x')

    def test_create_note(self):
        note = LeadNote.objects.create(lead=self.lead, author=self.user, body='Llamar mañana')
        self.assertEqual(note.business_id, self.business.pk)
        self.assertEqual(note.author, self.user)
        self.assertEqual(list(self.lead.notes.all()), [note])

    def test_empty_body_rejected(self):
        self.assertDbRejects(lambda: LeadNote.objects.create(lead=self.lead, author=self.user, body=''))

    def test_business_must_match_lead(self):
        other = make_business('note-b')
        with self.assertRaises(ValueError):
            LeadNote.objects.create(lead=self.lead, business=other, body='x')

    def test_author_deleted_keeps_note(self):
        note = LeadNote.objects.create(lead=self.lead, author=self.user, body='x')
        self.user.delete()
        note.refresh_from_db()
        self.assertIsNone(note.author_id)
