"""PROD-02E3B — Platform Admin read model of a Business's commercial AI usage.

Three read-only views, no locks, no writes, server time only:

* `admin_ai_usage_overview` — the PROD-02E3A merchant summary (same function,
  same instant) plus the source subscription's commercial identity/validity
  and an internal diagnosis (why AI is or is not commercially authorized).
  It is NEVER the operational state of the bot, WhatsApp or Meta: nothing
  here knows about connections, and nothing is inferred about them.
* `admin_ai_usage_history` — past and current usage periods rebuilt from the
  recorded sessions and charges, attributed per subscription, with the
  historical snapshots only (`included_sessions_snapshot` of the charges);
  what cannot be rebuilt reliably is null.
* `admin_reception_policies` — Recepcionista Custom policy versions and the
  append-only change history of the Business.

Attribution vs. engine count: the engine admits new sessions counting every
session of the Business whose usage period is exactly the current one,
whatever subscription it was attributed to (PROD-02E2A/B). The history keeps
both numbers per period: `engine_counted_sessions` (that criterion) and the
per-subscription `attributions` (sessions/charges recorded against each one).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from django.db.models import Count, Max, Min, Q, Sum
from django.utils import timezone

logger = logging.getLogger(__name__)

HISTORY_DEFAULT_LIMIT = 12
HISTORY_MAX_LIMIT = 36
CHANGES_DEFAULT_LIMIT = 50
CHANGES_MAX_LIMIT = 200

# Diagnosis codes (internal; commercial authorization only).
DIAG_OK = 'ok'
DIAG_NO_SUBSCRIPTION = 'no_ai_subscription'
DIAG_CANCELED = 'subscription_canceled'
DIAG_SUSPENDED = 'subscription_suspended'
DIAG_PAST_DUE_EXPIRED = 'past_due_grace_expired'
DIAG_PENDING = 'subscription_not_active'
DIAG_BENEFIT_FUTURE = 'benefit_not_started'
DIAG_BENEFIT_EXPIRED = 'benefit_expired'
DIAG_PERIOD_ENDED = 'canceled_at_period_end'
DIAG_BUSINESS_INACTIVE = 'business_not_active'
DIAG_INVALID_TIER = 'invalid_tier'
DIAG_CUSTOM_MISSING = 'custom_policy_missing'
DIAG_CUSTOM_REVOKED = 'custom_policy_revoked'
DIAG_CUSTOM_FUTURE = 'custom_policy_not_started'
DIAG_CUSTOM_EXPIRED = 'custom_policy_expired'
DIAG_POLICY_UNDEFINED = 'usage_policy_undefined'
DIAG_EXHAUSTED = 'quota_exhausted'
DIAG_AMBIGUOUS = 'ambiguous_ai_source'
DIAG_KILL_SWITCH = 'reception_kill_switch_disabled'
DIAG_METERING_DISABLED = 'metering_disabled'
DIAG_RESOLUTION_ERROR = 'resolution_error'
DIAG_UNAVAILABLE = 'usage_unavailable'


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def clamp(raw, default: int, maximum: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(1, min(value, maximum))


def offset_of(raw) -> int:
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


def _ai_subscriptions(business):
    from apps.billing.models import SubscriptionV2
    from apps.billing.services.ai_source import AI_SOURCES

    pairs = Q()
    for service_type, plan_code in AI_SOURCES.values():
        pairs |= Q(service_type=service_type, plan_code=plan_code)
    return SubscriptionV2.objects.filter(business=business).filter(pairs)


def _product(subscription) -> Optional[str]:
    from apps.billing.services.ai_source import AI_SOURCES

    for source, pair in AI_SOURCES.items():
        if (subscription.service_type, subscription.plan_code) == pair:
            return source
    return None


def _subscription_block(subscription) -> Optional[dict]:
    """Commercial identity and validity (no provider ids, raw snapshots or admin identities)."""
    if subscription is None:
        return None
    from apps.billing.services.appointments_lifecycle import is_complimentary_grant

    return {
        'id': str(subscription.pk),
        'product': _product(subscription),
        'service_type': subscription.service_type,
        'plan_code': subscription.plan_code,
        'usage_tier': subscription.usage_tier,
        'status': subscription.status,
        'provider': subscription.provider,
        'billing_cycle': subscription.billing_cycle or None,
        'complimentary': is_complimentary_grant(subscription),
        'current_period_start': _iso(subscription.current_period_start),
        'current_period_end': _iso(subscription.current_period_end),
        'grace_until': _iso(subscription.grace_until),
        'cancel_at_period_end': subscription.cancel_at_period_end,
        'canceled_at': _iso(subscription.canceled_at),
    }


def _lifecycle_code(business, subscription, now) -> str:
    from apps.billing.models import SubscriptionV2
    from apps.billing.services.ai_source import _business_may_consume
    from apps.billing.services.appointments_lifecycle import is_complimentary_grant

    if is_complimentary_grant(subscription):
        start, end = subscription.current_period_start, subscription.current_period_end
        if start is not None and now < start:
            return DIAG_BENEFIT_FUTURE
        if end is not None and now >= end:
            return DIAG_BENEFIT_EXPIRED
    if subscription.cancel_at_period_end and (
        subscription.current_period_end is None or subscription.current_period_end <= now
    ):
        return DIAG_PERIOD_ENDED
    status = subscription.status
    if status == SubscriptionV2.Status.SUSPENDED:
        return DIAG_SUSPENDED
    if status == SubscriptionV2.Status.PAST_DUE:
        return DIAG_PAST_DUE_EXPIRED
    if status in (SubscriptionV2.Status.CHECKOUT_PENDING, SubscriptionV2.Status.TRIALING):
        return DIAG_PENDING
    if not _business_may_consume(business, subscription, at=now):
        return DIAG_BUSINESS_INACTIVE
    return DIAG_SUSPENDED


def _custom_policy_code(subscription, now) -> str:
    from apps.billing.models import ReceptionAIUsagePolicy

    versions = ReceptionAIUsagePolicy.objects.filter(subscription=subscription)
    active = versions.filter(status=ReceptionAIUsagePolicy.Status.ACTIVE)
    if active.filter(valid_from__gt=now).exists():
        return DIAG_CUSTOM_FUTURE
    latest = versions.exclude(status=ReceptionAIUsagePolicy.Status.SUPERSEDED).order_by('-valid_from', '-created_at').first()
    if latest is None:
        return DIAG_CUSTOM_MISSING
    if latest.status == ReceptionAIUsagePolicy.Status.REVOKED:
        return DIAG_CUSTOM_REVOKED
    if latest.valid_until is not None and latest.valid_until <= now:
        return DIAG_CUSTOM_EXPIRED
    return DIAG_POLICY_UNDEFINED


def _candidates(business, now):
    """Per-source candidates with the resolver's own rules; raises on resolution errors."""
    from apps.billing.services.ai_source import AI_SOURCES, _candidate

    return [c for c in (_candidate(business, source, at=now) for source in AI_SOURCES) if c is not None]


def _diagnosis(business, summary, now) -> dict:
    from apps.appointments.services import ai_usage

    try:
        candidates = _candidates(business, now)
    except Exception:  # noqa: BLE001 — diagnosis must never fail open or crash the page
        logger.exception('admin_ai_usage diagnosis resolution failed business=%s', business.pk)
        return {'code': DIAG_RESOLUTION_ERROR, 'subscription_id': None, 'candidates': []}

    listed = [{
        'product': c.source, 'subscription_id': str(c.subscription.pk), 'status': c.subscription.status,
        'eligible': c.eligible, 'ineligible_reason': c.reason,
        'policy_configured': c.policy_configured, 'policy_reason': c.policy_reason,
    } for c in candidates]

    def result(code, subscription=None):
        return {'code': code, 'subscription_id': str(subscription.pk) if subscription else None, 'candidates': listed}

    status, reason = summary['status'], summary['reason']
    if status == 'ambiguous_source':
        return result(DIAG_AMBIGUOUS)
    if not candidates:
        latest = _ai_subscriptions(business).order_by('-created_at').first()
        if latest is None:
            return result(DIAG_NO_SUBSCRIPTION)
        return result({
            'canceled': DIAG_CANCELED, 'suspended': DIAG_SUSPENDED, 'past_due': DIAG_PAST_DUE_EXPIRED,
        }.get(latest.status, DIAG_PENDING), latest)
    eligible = [c for c in candidates if c.eligible]
    current = eligible[0] if len(eligible) == 1 else (candidates[0] if len(candidates) == 1 else None)
    subscription = current.subscription if current else None
    if status == 'available':
        return result(DIAG_OK, subscription)
    if status == 'exhausted':
        return result(DIAG_EXHAUSTED, subscription)
    if reason == 'metering_disabled':
        return result(DIAG_METERING_DISABLED, subscription)
    if current is not None and not current.eligible:
        if current.reason == 'invalid_tier':
            return result(DIAG_INVALID_TIER, subscription)
        return result(_lifecycle_code(business, subscription, now), subscription)
    if status == 'policy_not_configured' and subscription is not None:
        if reason == 'invalid_tier':
            return result(DIAG_INVALID_TIER, subscription)
        reception = subscription.service_type == 'reception'
        if reception and reason == 'usage_policy_undefined' and not ai_usage.RECEPTION_AI_CONSUMPTION_ENABLED:
            return result(DIAG_KILL_SWITCH, subscription)
        if reception and subscription.usage_tier == 'reception_custom' and reason == 'manual_contract_required':
            return result(_custom_policy_code(subscription, now), subscription)
        return result(DIAG_POLICY_UNDEFINED if reason == 'usage_policy_undefined' else reason, subscription)
    if status == 'suspended' and subscription is not None:
        return result(_lifecycle_code(business, subscription, now), subscription)
    return result(DIAG_UNAVAILABLE, subscription)


def admin_ai_usage_overview(business) -> dict:
    from apps.billing.services.ai_usage_summary import summary_at

    now = timezone.now()
    try:
        summary = summary_at(business, now)
    except Exception:  # noqa: BLE001 — never a 500 with internals on the admin page
        logger.exception('admin_ai_usage summary failed business=%s', business.pk)
        return {
            'business_id': business.pk, 'evaluated_at': _iso(now), 'summary': None,
            'source_subscription': None,
            'diagnosis': {'code': DIAG_RESOLUTION_ERROR, 'subscription_id': None, 'candidates': []},
            'scope': 'commercial_authorization_only',
        }
    diagnosis = _diagnosis(business, summary, now)
    source = None
    if diagnosis['subscription_id']:
        source = _ai_subscriptions(business).filter(pk=diagnosis['subscription_id']).first()
    return {
        'business_id': business.pk,
        'evaluated_at': summary['evaluated_at'],
        'summary': summary,
        'source_subscription': _subscription_block(source),
        'diagnosis': diagnosis,
        # Commercial authorization only: says nothing about the bot, WhatsApp or Meta.
        'scope': 'commercial_authorization_only',
    }


# ── History ───────────────────────────────────────────────────────────────────

def admin_ai_usage_history(business, *, limit: int, offset: int) -> dict:
    from apps.appointments.models import (
        AppointmentAIUsageCharge, AppointmentAIUsageSession, AppointmentAIUsageSettlement,
    )
    from apps.billing.models import SubscriptionV2

    sessions = AppointmentAIUsageSession.objects.filter(business=business)
    periods = (
        sessions.values('usage_period_start', 'usage_period_end')
        .annotate(engine_counted_sessions=Count('id'))
        .order_by('-usage_period_start', '-usage_period_end')
    )
    total = periods.count()
    page = list(periods[offset:offset + limit])
    if not page:
        return {'count': total, 'limit': limit, 'offset': offset, 'results': []}

    window = Q()
    for p in page:
        window |= Q(usage_period_start=p['usage_period_start'], usage_period_end=p['usage_period_end'])
    attributed = list(
        sessions.filter(window)
        .values('usage_period_start', 'usage_period_end', 'subscription_id', 'usage_tier')
        .annotate(sessions=Count('id'))
    )
    charges = {
        (c['usage_period_start'], c['usage_period_end'], c['subscription_id'], c['usage_tier']): c
        for c in AppointmentAIUsageCharge.objects.filter(business=business).filter(window)
        .values('usage_period_start', 'usage_period_end', 'subscription_id', 'usage_tier')
        .annotate(
            charges=Count('id'),
            included=Count('id', filter=Q(classification='included')),
            overage=Count('id', filter=Q(classification='overage')),
            overage_amount=Sum('amount', filter=Q(classification='overage')),
            snapshot_min=Min('included_sessions_snapshot'),
            snapshot_max=Max('included_sessions_snapshot'),
        )
    }
    subs = {
        s.pk: s for s in SubscriptionV2.objects.filter(
            business=business, pk__in={a['subscription_id'] for a in attributed},
        )
    }
    settlements = {}
    for st in AppointmentAIUsageSettlement.objects.filter(business=business).filter(window):
        settlements.setdefault((st.usage_period_start, st.usage_period_end), []).append({
            'subscription_id': str(st.subscription_id), 'status': st.status, 'total_sessions': st.total_sessions,
            'overage_sessions': st.overage_sessions, 'overage_amount': st.overage_amount, 'currency': st.currency,
        })

    results = []
    for p in page:
        key = (p['usage_period_start'], p['usage_period_end'])
        rows = []
        for a in sorted((a for a in attributed if (a['usage_period_start'], a['usage_period_end']) == key),
                        key=lambda a: (str(a['subscription_id']), a['usage_tier'])):
            sub = subs.get(a['subscription_id'])
            c = charges.get((*key, a['subscription_id'], a['usage_tier']))
            charged = c['charges'] if c else 0
            reliable = c is not None and charged == a['sessions']
            rows.append({
                'subscription_id': str(a['subscription_id']),
                'product': _product(sub) if sub else None,
                'service_type': sub.service_type if sub else None,
                'plan_code': sub.plan_code if sub else None,
                'subscription_status_now': sub.status if sub else None,
                'usage_tier': a['usage_tier'],  # tier recorded on the sessions
                'sessions': a['sessions'],
                'sessions_without_charge': a['sessions'] - charged,
                'charges': {
                    'included': c['included'] if c else 0,
                    'overage': c['overage'] if c else 0,
                    'overage_amount': (c['overage_amount'] or 0) if c else 0,
                    'currency': 'ARS',
                } if c else None,
                # Allowance as recorded on each charge at its creation (never today's policy).
                # Null when any session lacks economic evidence.
                'included_sessions_snapshot': (
                    {'min': c['snapshot_min'], 'max': c['snapshot_max']} if reliable else None
                ),
            })
        results.append({
            'period': {'start': _iso(key[0]), 'end': _iso(key[1])},
            'engine_counted_sessions': p['engine_counted_sessions'],
            'attributions': rows,
            'settlements': settlements.get(key, []),
        })
    return {'count': total, 'limit': limit, 'offset': offset, 'results': results}


# ── Policies ──────────────────────────────────────────────────────────────────

def _actor(user) -> Optional[dict]:
    if user is None:
        return None
    return {'id': user.pk, 'username': user.get_username(), 'email': user.email or None}


def _version_state(policy, now) -> str:
    from apps.billing.models import ReceptionAIUsagePolicy

    if policy.status != ReceptionAIUsagePolicy.Status.ACTIVE:
        return policy.status  # revoked | superseded
    if policy.valid_from > now:
        return 'scheduled'
    if policy.valid_until is not None and policy.valid_until <= now:
        return 'past'
    return 'current'


def admin_reception_policies(business, *, limit: int, offset: int) -> dict:
    from apps.billing.models import ReceptionAIUsagePolicy, ReceptionAIUsagePolicyChange

    now = timezone.now()
    versions = list(
        ReceptionAIUsagePolicy.objects.filter(business=business, subscription__business=business)
        .select_related('created_by', 'revoked_by').order_by('-valid_from', '-created_at')
    )
    changes = (
        ReceptionAIUsagePolicyChange.objects.filter(business=business, subscription__business=business)
        .select_related('actor').order_by('-created_at')
    )
    total = changes.count()
    serialized = [{
        'id': str(v.pk),
        'subscription_id': str(v.subscription_id),
        'included_sessions': v.included_sessions,
        'state': _version_state(v, now),
        'status': v.status,
        'valid_from': _iso(v.valid_from),
        'valid_until': _iso(v.valid_until),
        'created_at': _iso(v.created_at),
        'created_by': _actor(v.created_by),
        'revoked_at': _iso(v.revoked_at),
        'revoked_by': _actor(v.revoked_by),
    } for v in versions]
    return {
        'evaluated_at': _iso(now),
        'current': [v for v in serialized if v['state'] == 'current'],
        'scheduled': [v for v in serialized if v['state'] == 'scheduled'],
        'versions': serialized,
        'changes': {
            'count': total, 'limit': limit, 'offset': offset,
            'results': [{
                'id': str(ch.pk),
                'subscription_id': str(ch.subscription_id),
                'policy_id': str(ch.policy_id),
                'action': ch.action,
                'previous_included_sessions': ch.previous_included_sessions,
                'new_included_sessions': ch.new_included_sessions,
                'effective_at': _iso(ch.effective_at),
                'recorded_at': _iso(ch.created_at),
                'actor': _actor(ch.actor),
                'reason': ch.reason,
            } for ch in changes[offset:offset + limit]],
        },
    }
