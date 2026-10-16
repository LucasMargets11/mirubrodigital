"""Helpers compartidos de tests de apps.leads (AGENT 02A)."""
from __future__ import annotations

import uuid

from cryptography.fernet import Fernet
from django.utils import timezone

from apps.business.models import Business
from apps.leads.models import AgentChannel, AgentCredential, AgentInstance, Lead, LeadAgentState

TEST_KEY = Fernet.generate_key().decode()
SECRET = 'test-agent-secret-0123456789abcdef-XYZ'


def make_business(slug: str) -> Business:
    return Business.objects.create(
        name=f'Biz {slug}', slug=slug, default_service='appointments', status='active',
        timezone='America/Argentina/Buenos_Aires',
    )


def make_instance(external_id: str = 'dental-agent-test', **kwargs) -> AgentInstance:
    return AgentInstance.objects.create(external_id=external_id, name=kwargs.pop('name', external_id), **kwargs)


def make_credential(instance: AgentInstance, key_id: str = 'k1', secret: str = SECRET, **kwargs) -> AgentCredential:
    credential = AgentCredential(agent_instance=instance, key_id=key_id, **kwargs)
    credential.set_secret(secret)
    credential.save()
    return credential


def make_channel(instance: AgentInstance, business: Business, phone_number_id: str = '1234567890', **kwargs) -> AgentChannel:
    return AgentChannel.objects.create(
        agent_instance=instance, business=business, phone_number_id=phone_number_id, **kwargs,
    )


def make_state(lead: Lead, channel: AgentChannel, **overrides) -> LeadAgentState:
    now = timezone.now()
    data = dict(
        lead=lead, agent_instance=channel.agent_instance, channel=channel,
        external_lead_id=uuid.uuid4(), external_conversation_id='conv-' + uuid.uuid4().hex[:16],
        phone_e164='+5491112345678', opened_at=now, last_message_at=now,
        applied_version=1, payload_hash='a' * 64, last_event_id=uuid.uuid4(), last_synced_at=now,
    )
    data.update(overrides)
    return LeadAgentState.objects.create(**data)
