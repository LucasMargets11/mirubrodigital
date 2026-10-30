"""S8H: authenticated admission; S8A-C remain the only metering/ledger writers."""
import hashlib
import logging

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.appointments.models import AppointmentAIUsageAuthorization
from apps.appointments.services.ai_usage import (
    AIUsageHardCapReached, AIUsageUnavailable, get_appointments_ai_usage, get_or_create_ai_usage_session,
)
from apps.billing.services.appointments_checkout import ManualContractRequired
from apps.business.models import Business
from apps.leads.models import AgentChannel, LeadAgentState

logger = logging.getLogger(__name__)


@transaction.atomic
def authorize_ai_interaction(*, agent_instance, conversation_id, interaction_id, occurred_at):
    if not getattr(settings, 'AI_USAGE_METERING_ENABLED', False):
        raise AIUsageUnavailable('AI metering is disabled.', reason='metering_disabled')
    now = timezone.now()
    if occurred_at > now:
        raise AIUsageUnavailable('Future interaction.', reason='invalid_request')
    # Several Lead episodes may share one conversation, but not several tenants/channels.
    contexts = set(LeadAgentState.objects.filter(
        agent_instance=agent_instance, channel__agent_instance=agent_instance,
        channel__is_active=True, external_conversation_id=conversation_id,
        lead__business_id=F('channel__business_id'),
    ).values_list('channel_id', 'channel__business_id'))
    if len(contexts) != 1:
        raise AIUsageUnavailable('Missing or ambiguous conversation.', reason='unsafe_conversation_context')
    channel_id, business_id = contexts.pop()
    business = Business.objects.select_for_update().get(pk=business_id)
    if not AgentChannel.objects.select_for_update().filter(
        pk=channel_id, business=business, agent_instance=agent_instance, is_active=True,
    ).exists():
        raise AIUsageUnavailable('Inactive channel.', reason='unsafe_conversation_context')
    try:
        # Re-check CURRENT lifecycle/tier, never let a historical timestamp bypass suspension.
        get_appointments_ai_usage(business, at=now)
        receipt = AppointmentAIUsageAuthorization.objects.filter(
            business=business, interaction_id=interaction_id,
        ).select_related('session').first()
        if receipt is not None and (
            receipt.occurred_at != occurred_at
            or receipt.session.external_conversation_id != conversation_id
        ):
            raise AIUsageUnavailable('Interaction identity conflict.', reason='interaction_conflict')
        if receipt is None:
            session, created = get_or_create_ai_usage_session(
                business=business, conversation_id=conversation_id,
                interaction_id=interaction_id, at=occurred_at,
            )
        else:
            session, created = receipt.session, False
        # A replay of an expired window is not permission to consume AI today.
        if session.expires_at <= now:
            raise AIUsageUnavailable('Expired interaction window.', reason='interaction_expired')
        if receipt is None:
            AppointmentAIUsageAuthorization.objects.create(
                business=business, interaction_id=interaction_id,
                session=session, occurred_at=occurred_at,
            )
        usage = get_appointments_ai_usage(business, at=now)
    except (AIUsageUnavailable, ManualContractRequired) as exc:
        reason = (
            'hard_cap_reached' if isinstance(exc, AIUsageHardCapReached)
            else 'manual_contract_required' if isinstance(exc, ManualContractRequired)
            else exc.reason
        )
        logger.warning(
            'ai_usage_authorize business=%s conversation=%s allowed=false reason=%s',
            business.pk, hashlib.sha256(conversation_id.encode()).hexdigest()[:16], reason,
        )
        raise
    return business, session, created, usage
