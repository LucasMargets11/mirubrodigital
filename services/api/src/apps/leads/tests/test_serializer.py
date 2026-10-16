"""Schema `lead.sync` v1 (AGENT 02B): claves, tipos, enums, límites y coherencia."""
from __future__ import annotations

import datetime as dt

from django.test import SimpleTestCase

from apps.leads.errors import flatten_serializer_errors
from apps.leads.serializers import LeadSyncSerializer

from .agent_client import PII_SENTINEL, T0, T1, T2, T3, bump, handoff_requested, make_payload

REQUIRED_KEYS = (
    'schema_version', 'event_id', 'event_type', 'occurred_at', 'business_id', 'agent_instance_id',
    'phone_number_id', 'external_conversation_id', 'external_lead_id', 'previous_external_lead_id', 'version',
    'channel', 'phone_e164', 'patient_name', 'whatsapp_profile_name', 'reason', 'preferred_time', 'urgency',
    'agent_status', 'handoff', 'summary', 'opened_at', 'closed_at', 'close_reason', 'last_message_at',
)


def base(**overrides):
    defaults = dict(agent_instance_id='dental-agent-test', business_id=1, phone_number_id='1234567890')
    return make_payload(**{**defaults, **overrides})


class LeadSyncSerializerTests(SimpleTestCase):

    def assertValid(self, payload):
        serializer = LeadSyncSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        return serializer.validated_data

    def assertInvalid(self, payload, field, code=None):
        serializer = LeadSyncSerializer(data=payload)
        self.assertFalse(serializer.is_valid())
        flat = flatten_serializer_errors(serializer.errors)
        fields = {item['field'] for item in flat}
        self.assertIn(field, fields, flat)
        if code is not None:
            self.assertIn({'field': field, 'code': code}, flat)
        return flat

    # ── válidos ──────────────────────────────────────────────────────────

    def test_minimal_payload_valid(self):
        data = self.assertValid(base(patient_name=None, whatsapp_profile_name=None, reason=None,
                                     preferred_time=None, summary=None))
        self.assertIsNone(data['patient_name'])

    def test_full_payload_valid_closed_with_handoff(self):
        payload = base(
            agent_status='closed', closed_at=T3, close_reason='reception', last_message_at=T2,
            urgency=True, handoff=handoff_requested('patient_asked_human', 'urgency', first_at=T1, last_at=T2),
            previous_external_lead_id='0c6a1f0e-8a7b-4f0e-9a51-3e2d9b1c7a44',
        )
        data = self.assertValid(payload)
        self.assertTrue(data['handoff']['requested'])
        self.assertEqual(len(data['handoff']['reasons']), 2)

    def test_every_handoff_code_and_close_reason_accepted(self):
        for code in ('lead_ready', 'urgency', 'patient_asked_human', 'agent_handoff_required',
                     'medication_question', 'agent_error', 'unsupported_message', 'recovery_dropped'):
            with self.subTest(code=code):
                self.assertValid(base(handoff=handoff_requested(code)))
        for reason in ('idle', 'reception'):
            with self.subTest(reason=reason):
                self.assertValid(base(agent_status='closed', closed_at=T2, close_reason=reason))

    # ── claves obligatorias ───────────────────────────────────────────────

    def test_every_key_required_even_nullable(self):
        for key in REQUIRED_KEYS:
            payload = base()
            payload.pop(key)
            with self.subTest(key=key):
                self.assertInvalid(payload, key, 'required')

    def test_nested_handoff_keys_required(self):
        for key in ('requested', 'requested_at', 'reasons'):
            payload = base()
            payload['handoff'].pop(key)
            with self.subTest(key=key):
                self.assertInvalid(payload, f'handoff.{key}', 'required')
        payload = base(handoff=handoff_requested('lead_ready'))
        payload['handoff']['reasons'][0].pop('last_at')
        self.assertInvalid(payload, 'handoff.reasons[0].last_at', 'required')

    # ── constantes ────────────────────────────────────────────────────────

    def test_schema_version_must_be_1(self):
        for value in (2, 0, '1', True, 1.0):
            with self.subTest(value=value):
                self.assertInvalid(base(schema_version=value), 'schema_version')

    def test_event_type_and_channel(self):
        self.assertInvalid(base(event_type='lead.created'), 'event_type')
        self.assertInvalid(base(channel='instagram'), 'channel')

    # ── enums ─────────────────────────────────────────────────────────────

    def test_unknown_enums_rejected(self):
        self.assertInvalid(base(agent_status='paused'), 'agent_status', 'invalid_choice')
        self.assertInvalid(base(agent_status='closed', closed_at=T2, close_reason='spam'), 'close_reason', 'invalid_choice')
        self.assertInvalid(base(handoff=handoff_requested('vip')), 'handoff.reasons[0].code', 'invalid_choice')

    def test_urgency_is_boolean_not_enum(self):
        for value in ('high', 'true', 1, None):
            with self.subTest(value=value):
                self.assertInvalid(base(urgency=value), 'urgency')

    # ── formatos y límites ────────────────────────────────────────────────

    def test_phone_e164(self):
        for bad in ('5491112345678', '+0123456789', '+12345', '+1234567890123456', '+54 9 11', ''):
            with self.subTest(bad=bad):
                self.assertInvalid(base(phone_e164=bad), 'phone_e164')
        self.assertValid(base(phone_e164='+1234567'))
        self.assertValid(base(phone_e164='+123456789012345'))

    def test_phone_number_id(self):
        for bad in ('', 'abc', '12 3', '1' * 33, 123):
            with self.subTest(bad=bad):
                self.assertInvalid(base(phone_number_id=bad), 'phone_number_id')
        self.assertValid(base(phone_number_id='1' * 32))

    def test_agent_instance_id_format(self):
        for bad in ('ab', 'Dental', 'dental_agent', 'x' * 65):
            with self.subTest(bad=bad):
                self.assertInvalid(base(agent_instance_id=bad), 'agent_instance_id')

    def test_lengths(self):
        cases = {
            'external_conversation_id': 64, 'patient_name': 150, 'whatsapp_profile_name': 150,
            'reason': 500, 'preferred_time': 500, 'summary': 2000,
        }
        for field, limit in cases.items():
            with self.subTest(field=field):
                self.assertValid(base(**{field: 'a' * limit}))
                self.assertInvalid(base(**{field: 'a' * (limit + 1)}), field, 'max_length')

    def test_positive_integers(self):
        for field in ('version', 'business_id'):
            for bad in (0, -1, '3', 1.5, True):
                with self.subTest(field=field, bad=bad):
                    payload = base()
                    payload[field] = bad
                    self.assertInvalid(payload, field)

    def test_strict_text_types(self):
        self.assertInvalid(base(patient_name=123), 'patient_name', 'invalid')
        self.assertInvalid(base(external_lead_id='not-a-uuid'), 'external_lead_id')

    # ── fechas ────────────────────────────────────────────────────────────

    def test_utc_and_offsets_normalized(self):
        data = self.assertValid(base(occurred_at='2026-10-04T09:05:00-03:00', opened_at='2026-10-04T12:00:00Z'))
        self.assertEqual(data['occurred_at'], dt.datetime(2026, 10, 4, 12, 5, tzinfo=dt.timezone.utc))
        self.assertEqual(data['occurred_at'].utcoffset(), dt.timedelta(0))

    def test_naive_or_invalid_dates_rejected(self):
        self.assertInvalid(base(occurred_at='2026-10-04T12:00:00'), 'occurred_at', 'naive')
        self.assertInvalid(base(opened_at='ayer'), 'opened_at', 'invalid')
        self.assertInvalid(base(last_message_at=1791124330), 'last_message_at', 'invalid')

    # ── coherencia ────────────────────────────────────────────────────────

    def test_handoff_false_requires_empty_reasons_and_null_requested_at(self):
        self.assertInvalid(
            base(handoff={'requested': False, 'requested_at': None,
                          'reasons': [{'code': 'urgency', 'first_at': T1, 'last_at': T1}]}),
            'handoff.reasons', 'must_be_empty',
        )
        self.assertInvalid(base(handoff={'requested': False, 'requested_at': T1, 'reasons': []}),
                           'handoff.requested_at', 'must_be_null')

    def test_handoff_true_requires_reasons_and_requested_at(self):
        self.assertInvalid(base(handoff={'requested': True, 'requested_at': T1, 'reasons': []}),
                           'handoff.reasons', 'required_when_requested')
        payload = base(handoff=handoff_requested('urgency'))
        payload['handoff']['requested_at'] = None
        self.assertInvalid(payload, 'handoff.requested_at', 'required_when_requested')

    def test_requested_at_must_equal_min_first_at(self):
        handoff = {
            'requested': True, 'requested_at': T2,
            'reasons': [{'code': 'lead_ready', 'first_at': T2, 'last_at': T2},
                        {'code': 'urgency', 'first_at': T1, 'last_at': T2}],
        }
        self.assertInvalid(base(handoff=handoff), 'handoff.requested_at', 'mismatch_first_at')
        handoff['requested_at'] = T1
        self.assertValid(base(handoff=handoff))

    def test_duplicate_reason_code(self):
        handoff = {
            'requested': True, 'requested_at': T1,
            'reasons': [{'code': 'urgency', 'first_at': T1, 'last_at': T1},
                        {'code': 'urgency', 'first_at': T1, 'last_at': T2}],
        }
        self.assertInvalid(base(handoff=handoff), 'handoff.reasons', 'duplicate_code')

    def test_reason_first_at_after_last_at(self):
        self.assertInvalid(base(handoff=handoff_requested('urgency', first_at=T2, last_at=T1)),
                           'handoff.reasons[0].last_at', 'before_first_at')

    def test_agent_status_closed_fields(self):
        self.assertInvalid(base(closed_at=T2), 'closed_at', 'must_be_null')
        self.assertInvalid(base(close_reason='idle'), 'close_reason', 'must_be_null')
        self.assertInvalid(base(agent_status='closed', close_reason='idle'), 'closed_at', 'required_when_closed')
        self.assertInvalid(base(agent_status='closed', closed_at=T2), 'close_reason', 'required_when_closed')

    def test_opened_at_before_last_message_at(self):
        self.assertInvalid(base(opened_at=T2, last_message_at=T0), 'last_message_at', 'before_opened_at')

    def test_event_id_mismatch(self):
        payload = base(version=4)
        payload['event_id'] = str(bump(payload, 5)['event_id'])
        self.assertInvalid(payload, 'event_id', 'mismatch')

    # ── sin eco de valores ────────────────────────────────────────────────

    def test_errors_never_echo_values(self):
        payload = base(agent_status=PII_SENTINEL, patient_name=PII_SENTINEL * 20, phone_e164=PII_SENTINEL,
                       handoff=handoff_requested(PII_SENTINEL))
        flat = self.assertInvalid(payload, 'agent_status')
        self.assertNotIn(PII_SENTINEL, repr(flat))
