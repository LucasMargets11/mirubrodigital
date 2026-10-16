"""Helpers puros del Contract V1 (AGENT 02B): vectores congelados + payload_hash."""
from __future__ import annotations

import uuid

from django.test import SimpleTestCase

from apps.leads.contract import (
    body_sha256,
    canonical_string,
    compute_event_id,
    compute_payload_hash,
    compute_signature,
)
from apps.leads.serializers import LeadSyncSerializer

from .agent_client import T1, T2, handoff_requested, make_payload

VECTOR_PATH = '/api/v1/integrations/agent/leads/0c6a1f0e-8a7b-4f0e-9a51-3e2d9b1c7a44/'


class HmacContractVectorTests(SimpleTestCase):
    """Vector congelado de Contract V1: no recalcular ni cambiar la expectativa."""

    def test_frozen_vector(self):
        body = b'{"schema_version":1}'
        body_hash = body_sha256(body)
        self.assertEqual(body_hash, 'a9d5f6d002d956b8af5787a05e0ca000d45c03977ffa54ee8fbed719fed5fd23')
        canonical = canonical_string(
            method='PUT', path=VECTOR_PATH, timestamp='1791124330',
            request_id='3f1d2c4b-5a6e-4f70-8a91-b2c3d4e5f607', key_id='agent-key-2026-10', body_hash=body_hash,
        )
        self.assertEqual(
            compute_signature('test-secret-NOT-FOR-PRODUCTION', canonical),
            'v1=7ae8adabbfc3f6a16a8d41363774e78db822eefde5d200083c93c5fcde40e7c3',
        )

    def test_canonical_string_is_seven_lines_without_trailing_newline(self):
        canonical = canonical_string(
            method='PUT', path=VECTOR_PATH, timestamp='1', request_id='r', key_id='k', body_hash='h',
        )
        self.assertEqual(canonical.split('\n'), ['v1', 'PUT', VECTOR_PATH, '1', 'r', 'k', 'h'])
        self.assertFalse(canonical.endswith('\n'))


class EventIdContractVectorTests(SimpleTestCase):

    def test_frozen_vector(self):
        self.assertEqual(
            compute_event_id('dental-agent-prod', '0c6a1f0e-8a7b-4f0e-9a51-3e2d9b1c7a44', 4),
            uuid.UUID('41fb9406-3d01-5722-9d9f-103b83a3adfd'),
        )

    def test_uuid_object_and_uppercase_string_are_canonicalized(self):
        expected = uuid.UUID('41fb9406-3d01-5722-9d9f-103b83a3adfd')
        lead = '0c6a1f0e-8a7b-4f0e-9a51-3e2d9b1c7a44'
        self.assertEqual(compute_event_id('dental-agent-prod', uuid.UUID(lead), 4), expected)
        self.assertEqual(compute_event_id('dental-agent-prod', lead.upper(), 4), expected)


def _validated(payload):
    serializer = LeadSyncSerializer(data=payload)
    assert serializer.is_valid(), serializer.errors
    return serializer.validated_data


class PayloadHashTests(SimpleTestCase):
    def setUp(self):
        self.base = make_payload(
            agent_instance_id='dental-agent-prod', business_id=7, phone_number_id='1234567890',
            handoff={
                'requested': True, 'requested_at': T1,
                'reasons': [
                    {'code': 'urgency', 'first_at': T1, 'last_at': T2},
                    {'code': 'lead_ready', 'first_at': T2, 'last_at': T2},
                ],
            },
        )

    def test_hash_is_lowercase_sha256(self):
        digest = compute_payload_hash(_validated(self.base))
        self.assertRegex(digest, r'^[0-9a-f]{64}$')

    def test_same_semantics_same_hash(self):
        reference = compute_payload_hash(_validated(self.base))
        # Orden de claves distinto.
        reordered = dict(reversed(list(self.base.items())))
        self.assertEqual(compute_payload_hash(_validated(reordered)), reference)
        # Orden de reasons distinto.
        swapped = {**self.base, 'handoff': {**self.base['handoff'], 'reasons': list(reversed(self.base['handoff']['reasons']))}}
        self.assertEqual(compute_payload_hash(_validated(swapped)), reference)
        # Mismo instante con otro offset / sin microsegundos.
        offset = {**self.base, 'occurred_at': '2026-10-04T09:05:00-03:00', 'opened_at': '2026-10-04T12:00:00Z'}
        self.assertEqual(compute_payload_hash(_validated(offset)), reference)
        # UUID en mayúsculas.
        upper = {**self.base, 'external_lead_id': self.base['external_lead_id'].upper(), 'event_id': self.base['event_id'].upper()}
        self.assertEqual(compute_payload_hash(_validated(upper)), reference)

    def test_unknown_fields_never_reach_the_hash(self):
        """Política: campos desconocidos se IGNORAN (forward compat) y no cambian el hash."""
        reference = compute_payload_hash(_validated(self.base))
        extra = {**self.base, 'sent_at': '2026-10-04T13:00:00Z', 'transcript': 'hola', 'request_id': 'x'}
        validated = _validated(extra)
        self.assertNotIn('sent_at', validated)
        self.assertNotIn('transcript', validated)
        self.assertEqual(compute_payload_hash(validated), reference)

    def test_semantic_change_changes_hash(self):
        reference = compute_payload_hash(_validated(self.base))
        for field, value in [('summary', 'otro'), ('urgency', True), ('patient_name', None)]:
            with self.subTest(field=field):
                self.assertNotEqual(compute_payload_hash(_validated({**self.base, field: value})), reference)

    def test_handoff_helper_payload_is_valid(self):
        _validated({**self.base, 'handoff': handoff_requested('lead_ready')})
