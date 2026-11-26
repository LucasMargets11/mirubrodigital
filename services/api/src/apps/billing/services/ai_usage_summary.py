"""PROD-02E3A — single read source of a Business's commercial AI consumption.

Built only from the metering engine's own helpers
(`ai_usage.read_ai_usage_admission`: same AI source resolution, lifecycle and
Business checks, usage period, allowance — fixed tier or Recepcionista Custom
policy — session count and admission economics), evaluated at the server's
current instant, WITHOUT locks or writes. What it reports as
`can_start_new_session` is exactly what the engine would decide for a new
conversation at that instant (barring the conversation-specific checks the
engine runs on its own: agent channel/context, replays, out-of-order windows).

Unit: the 24 h AI session (one per conversation and window), the engine's
billing unit. No OpenAI requests, tokens or operating costs.

Counting is the engine's: sessions of the Business whose usage period is
exactly the current one, whatever subscription they were attributed to
(see the PROD-02E2B report, limitation "conteo por Business y período").

Statuses (never an invented allowance; unknown values are null):
  available              – a new session would be admitted
  exhausted              – hard cap reached (not a suspension)
  policy_not_configured  – no usable allowance (manual_contract_required,
                           usage_policy_undefined, invalid_tier)
  suspended              – lifecycle / Business status does not allow AI now
  ambiguous_source       – Recepcionista and Turnos IA both eligible
  unavailable            – metering disabled or commercial data unresolved
`not_contracted` (no AI subscription at all) is returned to the view so it
can answer 403.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

CONTRACT_VERSION = 1
USAGE_UNIT = 'ai_session_24h'

AVAILABLE = 'available'
EXHAUSTED = 'exhausted'
POLICY_NOT_CONFIGURED = 'policy_not_configured'
SUSPENDED = 'suspended'
AMBIGUOUS = 'ambiguous_source'
UNAVAILABLE = 'unavailable'
NOT_CONTRACTED = 'not_contracted'

_POLICY_REASONS = {'manual_contract_required', 'usage_policy_undefined', 'invalid_tier'}
# Public, normalized reasons; anything else collapses to `usage_unavailable`.
_PUBLIC_REASONS = _POLICY_REASONS | {
    'hard_cap_reached', 'suspended', 'ambiguous_ai_source', 'metering_disabled', 'usage_unavailable',
}


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _source_block(subscription) -> Optional[dict]:
    if subscription is None:
        return None
    from apps.billing.services.ai_source import APPOINTMENTS_AI_SOURCE, RECEPTION_SOURCE

    reception = subscription.service_type == 'reception'
    return {
        'product': RECEPTION_SOURCE if reception else APPOINTMENTS_AI_SOURCE,
        'service_type': subscription.service_type,
        'plan_code': subscription.plan_code,
        'usage_tier': subscription.usage_tier,
        'policy_kind': 'custom' if subscription.usage_tier == 'reception_custom' else 'catalog',
    }


def _scheduled_change(subscription, now: datetime) -> Optional[dict]:
    """Next scheduled allowance of a Recepcionista Custom policy (public fields only)."""
    if subscription is None or subscription.usage_tier != 'reception_custom':
        return None
    from apps.billing.services.reception_ai_policy import _future_versions, is_reception_custom

    if not is_reception_custom(subscription):
        return None
    nxt = _future_versions(subscription, now).order_by('valid_from').first()
    if nxt is None:
        return None
    return {'included_sessions': nxt.included_sessions, 'effective_at': _iso(nxt.valid_from)}


def _blocked_subscription(business, now: datetime):
    """Subscription to identify when the engine refused (never for ambiguity)."""
    from apps.billing.services.ai_source import resolve_ai_source

    resolution = resolve_ai_source(business, at=now)
    if resolution.subscription is not None:
        return resolution.subscription
    if len(resolution.candidates) == 1:
        return resolution.candidates[0].subscription
    return None


def _empty(status: str, reason: str, now: datetime, subscription=None) -> dict:
    return {
        'contract_version': CONTRACT_VERSION,
        'evaluated_at': _iso(now),
        'status': status,
        'reason': reason if reason in _PUBLIC_REASONS else 'usage_unavailable',
        'can_start_new_session': False,
        'unit': USAGE_UNIT,
        'source': _source_block(subscription),
        'period': None,
        'sessions': None,
        'hard_cap': None,
        'overage': None,
        'scheduled_change': _scheduled_change(subscription, now),
    }


def get_ai_usage_summary(business) -> dict:
    """Read-only summary at the server's current instant (no caller-controlled time)."""
    from apps.appointments.services.ai_usage import (
        AIUsageHardCapReached, AIUsageUnavailable, read_ai_usage_admission,
    )
    from apps.billing.services.ai_source import AMBIGUOUS_AI_SOURCE, resolve_ai_source
    from apps.billing.services.appointments_checkout import ManualContractRequired

    now = timezone.now()
    resolution = resolve_ai_source(business, at=now)
    if resolution.reason == AMBIGUOUS_AI_SOURCE:
        return _empty(AMBIGUOUS, AMBIGUOUS_AI_SOURCE, now)
    if resolution.subscription is None and not resolution.candidates:
        return _empty(NOT_CONTRACTED, 'no_ai_entitlement', now)
    if not getattr(settings, 'AI_USAGE_METERING_ENABLED', False):
        # The agent endpoint refuses every authorization in this state.
        return _empty(UNAVAILABLE, 'metering_disabled', now, _blocked_subscription(business, now))

    try:
        usage, admission, subscription = read_ai_usage_admission(business, at=now)
    except AIUsageHardCapReached:
        return _empty(EXHAUSTED, 'hard_cap_reached', now, _blocked_subscription(business, now))
    except ManualContractRequired:
        return _empty(POLICY_NOT_CONFIGURED, 'manual_contract_required', now,
                      _blocked_subscription(business, now))
    except AIUsageUnavailable as exc:
        reason = exc.reason
        if reason == AMBIGUOUS_AI_SOURCE:
            return _empty(AMBIGUOUS, reason, now)
        if reason == 'no_ai_entitlement' and resolution.candidates:
            # AI subscriptions exist but none is eligible now (e.g. both out of lifecycle).
            reason = 'suspended'
        status = (
            POLICY_NOT_CONFIGURED if reason in _POLICY_REASONS
            else SUSPENDED if reason == 'suspended'
            else NOT_CONTRACTED if reason == 'no_ai_entitlement'
            else UNAVAILABLE
        )
        if reason not in _PUBLIC_REASONS:
            logger.info('ai_usage_summary unavailable business=%s reason=%s', business.pk, reason)
        return _empty(status, reason, now, _blocked_subscription(business, now))

    allowed = admission['can_start_new_session']
    reception = subscription.service_type == 'reception'
    used, included, max_total = admission['used_sessions'], admission['included_sessions'], admission['max_total_sessions']
    return {
        'contract_version': CONTRACT_VERSION,
        'evaluated_at': _iso(now),
        'status': AVAILABLE if allowed else EXHAUSTED,
        'reason': None if allowed else 'hard_cap_reached',
        'can_start_new_session': allowed,
        'unit': USAGE_UNIT,
        'source': _source_block(subscription),
        'period': {'start': _iso(usage['period_start']), 'end': _iso(usage['period_end'])},
        'sessions': {
            'included': included,
            'used': used,
            'available_included': max(0, included - used),
        },
        'hard_cap': {
            'max_sessions': max_total,
            'remaining_sessions': max(0, max_total - used),
        },
        'overage': {
            'enabled': admission['max_overage_sessions'] > 0,
            'unit_price': None if reception else admission['overage_unit_price'],
            'spend_limit': admission['hard_cap_amount'],
            'max_sessions': admission['max_overage_sessions'],
            'used_sessions': admission['overage_sessions'],
            'amount': admission['overage_amount'],
            'currency': 'ARS',
        },
        'scheduled_change': _scheduled_change(subscription, now),
    }
