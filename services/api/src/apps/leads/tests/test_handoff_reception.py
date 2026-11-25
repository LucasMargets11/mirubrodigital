"""Derivación a recepción (primer cliente): `handoff_paused_at` aditivo en
lead.sync y el estado "pendiente de recepción · bot pausado" del panel."""
from __future__ import annotations

import datetime as dt

from django.utils import timezone

from apps.leads.crm_serializers import handoff_pending
from apps.leads.models import ConversationControl

from .agent_client import handoff_requested
from .test_receiver_api import ReceiverTestBase

HANDOFF_AT = '2026-10-04T14:30:00.000Z'


class HandoffPausedAtReceiverTests(ReceiverTestBase):

    def test_absent_field_keeps_null_and_duplicate_hash(self):
        payload = self.payload()
        self.assertResult(self.put(payload), 201, 'created', received=1, applied=1)
        self.assertIsNone(self.state(payload).handoff_paused_at)
        # Same revision again: same hash (the optional field is not in it)
        self.assertResult(self.put(payload), 200, 'duplicate', received=1, applied=1)

    def test_handoff_revision_stores_the_timestamp(self):
        first = self.payload()
        self.assertResult(self.put(first), 201, 'created', received=1, applied=1)
        second = self.payload(
            external_lead_id=first['external_lead_id'], version=2,
            handoff=handoff_requested('lead_ready'), handoff_paused_at=HANDOFF_AT,
        )
        self.assertResult(self.put(second), 200, 'applied', received=2, applied=2)
        state = self.state(second)
        self.assertEqual(state.handoff_paused_at, dt.datetime(2026, 10, 4, 14, 30, tzinfo=dt.timezone.utc))
        self.assertTrue(state.lead.attention_pending)
        self.assertTrue(handoff_pending(state, None))

    def test_invalid_timestamp_is_a_validation_error(self):
        payload = self.payload(handoff_paused_at='2026-10-04')
        response = self.put(payload)
        self.assertEqual(response.status_code, 400, response.content)


class HandoffPendingRuleTests(ReceiverTestBase):

    def _state(self, paused_at):
        payload = self.payload(**({'handoff_paused_at': paused_at} if paused_at else {}))
        self.put(payload)
        return self.state(payload)

    def _control(self, lead_state, **fields):
        return ConversationControl.objects.create(
            business=self.business, external_conversation_id=lead_state.external_conversation_id, **fields,
        )

    def test_never_handed_off(self):
        self.assertFalse(handoff_pending(self._state(None), None))

    def test_taken_or_in_flight_is_not_pending(self):
        state = self._state(HANDOFF_AT)
        for value in (ConversationControl.State.TAKEN, ConversationControl.State.TAKEOVER_PENDING,
                      ConversationControl.State.RELEASE_PENDING, ConversationControl.State.ERROR):
            control = ConversationControl(state=value)
            self.assertFalse(handoff_pending(state, control), value)

    def test_release_after_the_handoff_reactivates_the_bot(self):
        state = self._state(HANDOFF_AT)
        control = self._control(state, state=ConversationControl.State.ACTIVE, released_at=timezone.now())
        self.assertFalse(handoff_pending(state, control))

    def test_handoff_after_an_older_release_is_pending_again(self):
        state = self._state(HANDOFF_AT)
        control = self._control(
            state, state=ConversationControl.State.ACTIVE,
            released_at=dt.datetime(2026, 10, 4, 14, 0, tzinfo=dt.timezone.utc),
        )
        self.assertTrue(handoff_pending(state, control))
