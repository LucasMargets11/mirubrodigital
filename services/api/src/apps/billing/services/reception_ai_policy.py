"""PROD-02E2B — per-subscription AI usage policy for Recepcionista Custom.

`reception_custom` keeps no allowance in the catalog; its included
conversations come from `ReceptionAIUsagePolicy` (versioned, one effective
version per subscription and instant). This module is the only writer and the
only reader the metering engine uses.

Reading (`effective_reception_custom_policy`):
  * the subscription must be exactly reception/reception/reception_custom;
  * exactly one `active` version with valid_from <= at < valid_until;
  * none → `NoEffectiveCustomPolicy` (absent, future, expired, revoked:
    `manual_contract_required`, as before 02E2B);
  * several or an invalid allowance → `InvalidCustomPolicy`
    (`usage_policy_undefined`). Never unlimited.

Writing (internal service, reusable later by platform-admin; no endpoint):
  * every mutation locks Business → SubscriptionV2 (the metering engine's own
    order), so a consumption decision sees the policy either before or after
    a change, never in between;
  * increases apply immediately (current version closed at `now`, a new one
    opened, consumption of the period is NOT reset: counts come from the
    recorded sessions);
  * reductions are never immediate: they are scheduled at the end of the
    current usage period (the next period starts with the lower allowance);
  * revocation stops every current and scheduled version at once; a window
    already open stops authorizing too (the engine re-checks the policy at the
    current instant on every interaction);
  * history (sessions, charges, receipts, previous versions) is never deleted;
  * every mutation writes an append-only `ReceptionAIUsagePolicyChange` in the
    same transaction plus a best-effort `AccessAuditLog` platform entry.

No overage, prices, settlements or billing intents: Recepcionista Custom shares
the fixed tiers' policy (included only, spend cap 0).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.billing.models import (
    RECEPTION_CUSTOM_MAX_INCLUDED_SESSIONS, ReceptionAIUsagePolicy, ReceptionAIUsagePolicyChange,
    SubscriptionV2,
)

logger = logging.getLogger(__name__)

RECEPTION_CUSTOM_TIER = 'reception_custom'


class CustomPolicyError(ValueError):
    """Rejected policy mutation (never partially applied)."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


class NoEffectiveCustomPolicy(Exception):
    """No custom policy is effective at the instant (absent/future/expired/revoked)."""


class InvalidCustomPolicy(Exception):
    """Inconsistent policy data (overlap, wrong binding, invalid allowance)."""


def is_reception_custom(subscription: SubscriptionV2) -> bool:
    return (
        subscription.service_type == 'reception'
        and subscription.plan_code == 'reception'
        and subscription.usage_tier == RECEPTION_CUSTOM_TIER
    )


def _valid_allowance(value) -> bool:
    return type(value) is int and 0 < value <= RECEPTION_CUSTOM_MAX_INCLUDED_SESSIONS


def _effective_at(subscription_id, at: datetime):
    return ReceptionAIUsagePolicy.objects.filter(
        subscription_id=subscription_id, status=ReceptionAIUsagePolicy.Status.ACTIVE, valid_from__lte=at,
    ).filter(Q(valid_until__isnull=True) | Q(valid_until__gt=at))


def effective_reception_custom_policy(subscription: SubscriptionV2, *, at: datetime) -> ReceptionAIUsagePolicy:
    """The single policy version effective at `at`, or an exception (fail closed)."""
    if not isinstance(at, datetime) or timezone.is_naive(at):
        raise InvalidCustomPolicy('An explicit timezone-aware instant is required.')
    if not is_reception_custom(subscription):
        raise InvalidCustomPolicy('Not a Recepcionista Custom subscription.')
    rows = list(_effective_at(subscription.pk, at)[:2])
    if not rows:
        raise NoEffectiveCustomPolicy('No custom AI usage policy is effective.')
    if len(rows) > 1:
        logger.error('reception_custom_policy overlap subscription=%s at=%s', subscription.pk, at.isoformat())
        raise InvalidCustomPolicy('More than one custom policy is effective.')
    policy = rows[0]
    if policy.business_id != subscription.business_id or not _valid_allowance(policy.included_sessions):
        raise InvalidCustomPolicy('The custom policy is inconsistent.')
    return policy


# ── Mutations ─────────────────────────────────────────────────────────────────

def _now(now: Optional[datetime]) -> datetime:
    value = now or timezone.now()
    if not isinstance(value, datetime) or timezone.is_naive(value):
        raise CustomPolicyError('An explicit timezone-aware instant is required.', code='invalid_instant')
    return value


def _require(actor, reason) -> str:
    if actor is None or not getattr(actor, 'pk', None):
        raise CustomPolicyError('The responsible administrator is required.', code='actor_required')
    profile = getattr(actor, 'account_profile', None)
    if not getattr(profile, 'is_platform_staff', False) and not getattr(actor, 'is_superuser', False):
        raise CustomPolicyError('Only platform staff may change a custom AI policy.', code='actor_not_platform_staff')
    reason = (reason or '').strip()
    if not reason or len(reason) > 255:
        raise CustomPolicyError('A reason (1–255 characters) is required.', code='reason_required')
    return reason


def _require_allowance(value) -> int:
    if not _valid_allowance(value):
        raise CustomPolicyError(
            f'The allowance must be an integer between 1 and {RECEPTION_CUSTOM_MAX_INCLUDED_SESSIONS}.',
            code='invalid_allowance',
        )
    return value


def _lock(subscription: SubscriptionV2) -> SubscriptionV2:
    """Business → SubscriptionV2, the metering engine's lock order."""
    from apps.business.models import Business

    Business.objects.select_for_update().get(pk=subscription.business_id)
    locked = SubscriptionV2.objects.select_for_update().get(pk=subscription.pk)
    if not is_reception_custom(locked):
        raise CustomPolicyError(
            'Custom policies only apply to a Recepcionista subscription with tier reception_custom.',
            code='wrong_subscription',
        )
    if locked.status == SubscriptionV2.Status.CANCELED:
        raise CustomPolicyError('The subscription is canceled.', code='subscription_canceled')
    return locked


def _future_versions(subscription, now):
    return ReceptionAIUsagePolicy.objects.filter(
        subscription=subscription, status=ReceptionAIUsagePolicy.Status.ACTIVE, valid_from__gt=now,
    )


def _snapshot(policy: ReceptionAIUsagePolicy) -> dict:
    return {
        'policy_id': str(policy.pk),
        'included_sessions': policy.included_sessions,
        'status': policy.status,
        'valid_from': policy.valid_from.isoformat(),
        'valid_until': policy.valid_until.isoformat() if policy.valid_until else None,
    }


def _audit(*, subscription, policy, action, previous, new, effective_at, actor, reason, details):
    change = ReceptionAIUsagePolicyChange.objects.create(
        business_id=subscription.business_id, subscription=subscription, policy=policy, action=action,
        previous_included_sessions=previous, new_included_sessions=new, effective_at=effective_at,
        actor=actor, reason=reason, details=details,
    )
    # Reuse the platform audit trail (best effort, own savepoint): the
    # authoritative audit is the append-only change row above.
    from apps.accounts.platform_audit import log_platform_action

    with transaction.atomic():
        log_platform_action(
            action='PLATFORM_ADMIN_ACTION', actor=actor, entity_type='reception_ai_usage_policy',
            entity_id=str(policy.pk), business=subscription.business,
            details={
                'operation': f'reception_ai_policy_{action}', 'subscription_id': str(subscription.pk),
                'previous_included_sessions': previous, 'new_included_sessions': new,
                'effective_at': effective_at.isoformat(), 'reason': reason, 'change_id': str(change.pk),
            },
        )
    logger.info(
        'reception_custom_policy %s subscription=%s policy=%s previous=%s new=%s effective_at=%s actor=%s',
        action, subscription.pk, policy.pk, previous, new, effective_at.isoformat(), actor.pk,
    )
    return change


@transaction.atomic
def create_reception_custom_policy(
    *, subscription: SubscriptionV2, included_sessions: int, actor, reason: str,
    valid_from: Optional[datetime] = None, valid_until: Optional[datetime] = None,
    now: Optional[datetime] = None,
) -> ReceptionAIUsagePolicyChange:
    """First policy (or a new one after a revocation/expiry). Never backdated."""
    now = _now(now)
    reason = _require(actor, reason)
    included_sessions = _require_allowance(included_sessions)
    valid_from = valid_from or now
    if timezone.is_naive(valid_from) or valid_from < now:
        raise CustomPolicyError('A policy never starts in the past.', code='backdated')
    if valid_until is not None and (timezone.is_naive(valid_until) or valid_until <= valid_from):
        raise CustomPolicyError('The policy must end after it starts.', code='invalid_window')
    subscription = _lock(subscription)
    if _effective_at(subscription.pk, now).exists() or _future_versions(subscription, now).exists():
        raise CustomPolicyError(
            'The subscription already has a current or scheduled policy; change it instead.',
            code='policy_exists',
        )
    policy = ReceptionAIUsagePolicy.objects.create(
        business_id=subscription.business_id, subscription=subscription, included_sessions=included_sessions,
        valid_from=valid_from, valid_until=valid_until, created_by=actor,
    )
    return _audit(
        subscription=subscription, policy=policy, action=ReceptionAIUsagePolicyChange.Action.CREATED,
        previous=None, new=included_sessions, effective_at=valid_from, actor=actor, reason=reason,
        details={'after': _snapshot(policy)},
    )


def _next_usage_period_start(subscription: SubscriptionV2, now: datetime) -> datetime:
    from apps.appointments.services.ai_usage import AIUsageUnavailable, resolve_appointments_ai_usage_period

    try:
        _, period_end = resolve_appointments_ai_usage_period(subscription, at=now)
    except AIUsageUnavailable as exc:
        raise CustomPolicyError(
            'The current usage period is unresolved; a reduction cannot be scheduled safely.',
            code='usage_period_unresolved',
        ) from exc
    return period_end


@transaction.atomic
def change_reception_custom_allowance(
    *, subscription: SubscriptionV2, included_sessions: int, actor, reason: str,
    now: Optional[datetime] = None,
) -> ReceptionAIUsagePolicyChange:
    """Increase now, or schedule a reduction for the next usage period.

    Consumption already recorded in the period is never reset or reassigned.
    A pending scheduled change must be canceled first (no stacking).
    """
    now = _now(now)
    reason = _require(actor, reason)
    included_sessions = _require_allowance(included_sessions)
    subscription = _lock(subscription)
    current = list(_effective_at(subscription.pk, now).select_for_update()[:2])
    if len(current) != 1:
        raise CustomPolicyError('There is no single current policy to change.', code='no_current_policy')
    current = current[0]
    if _future_versions(subscription, now).exists():
        raise CustomPolicyError('A scheduled change is pending; cancel it first.', code='scheduled_change_pending')
    previous = current.included_sessions
    if included_sessions == previous:
        raise CustomPolicyError('The allowance is unchanged.', code='no_change')
    before = _snapshot(current)
    original_until = current.valid_until

    if included_sessions > previous:
        effective_at = now
        action = ReceptionAIUsagePolicyChange.Action.INCREASED
    else:
        # Never immediate: the lower allowance starts with the next usage period.
        effective_at = _next_usage_period_start(subscription, now)
        if original_until is not None and original_until <= effective_at:
            raise CustomPolicyError(
                'The current policy ends before the next usage period.', code='policy_ends_before_next_period',
            )
        action = ReceptionAIUsagePolicyChange.Action.REDUCTION_SCHEDULED

    if effective_at <= current.valid_from:
        raise CustomPolicyError('The change would not leave the current version a positive window.',
                                code='invalid_window')
    current.valid_until = effective_at
    current.save(update_fields=['valid_until', 'updated_at'])
    policy = ReceptionAIUsagePolicy.objects.create(
        business_id=subscription.business_id, subscription=subscription, included_sessions=included_sessions,
        valid_from=effective_at, valid_until=original_until, created_by=actor,
    )
    return _audit(
        subscription=subscription, policy=policy, action=action, previous=previous, new=included_sessions,
        effective_at=effective_at, actor=actor, reason=reason,
        details={'before': before, 'closed_version': _snapshot(current), 'after': _snapshot(policy)},
    )


@transaction.atomic
def cancel_scheduled_reception_custom_change(
    *, subscription: SubscriptionV2, actor, reason: str, now: Optional[datetime] = None,
) -> ReceptionAIUsagePolicyChange:
    """Cancel the pending scheduled version; the current one keeps its original window."""
    now = _now(now)
    reason = _require(actor, reason)
    subscription = _lock(subscription)
    scheduled = list(_future_versions(subscription, now).select_for_update().order_by('valid_from')[:2])
    if len(scheduled) != 1:
        raise CustomPolicyError('There is no single scheduled change.', code='no_scheduled_change')
    scheduled = scheduled[0]
    current = (
        ReceptionAIUsagePolicy.objects.select_for_update()
        .filter(subscription=subscription, status=ReceptionAIUsagePolicy.Status.ACTIVE,
                valid_until=scheduled.valid_from)
        .first()
    )
    scheduled.status = ReceptionAIUsagePolicy.Status.SUPERSEDED
    scheduled.save(update_fields=['status', 'updated_at'])
    if current is not None:
        current.valid_until = scheduled.valid_until
        current.save(update_fields=['valid_until', 'updated_at'])
    return _audit(
        subscription=subscription, policy=scheduled, action=ReceptionAIUsagePolicyChange.Action.SCHEDULE_CANCELED,
        previous=current.included_sessions if current else None, new=scheduled.included_sessions,
        effective_at=now, actor=actor, reason=reason,
        details={'canceled': _snapshot(scheduled), 'restored': _snapshot(current) if current else None},
    )


@transaction.atomic
def extend_reception_custom_policy(
    *, subscription: SubscriptionV2, previous_until: datetime, new_until: datetime, actor, reason: str,
    now: Optional[datetime] = None,
) -> Optional[ReceptionAIUsagePolicyChange]:
    """PROD-09D1: follow an extension of the bonified window.

    Only the active version that ends exactly at the previous commercial end
    (the current one, or a scheduled reduction) gets the new end: allowance,
    start and earlier versions are untouched, so the contracted allowance and
    any scheduled change are preserved. Revoked/superseded versions never come
    back; without an active version aligned to the previous end it fails closed.
    An open-ended version already covers the extension (nothing to write).
    """
    now = _now(now)
    reason = _require(actor, reason)
    for value in (previous_until, new_until):
        if not isinstance(value, datetime) or timezone.is_naive(value):
            raise CustomPolicyError('An explicit timezone-aware instant is required.', code='invalid_instant')
    if new_until <= previous_until:
        raise CustomPolicyError('The new end must be after the previous one.', code='invalid_window')
    subscription = _lock(subscription)
    versions = list(
        ReceptionAIUsagePolicy.objects.select_for_update()
        .filter(subscription=subscription, status=ReceptionAIUsagePolicy.Status.ACTIVE)
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now))
    )
    if any(version.valid_until is None for version in versions):
        return None
    tail = [version for version in versions if version.valid_until == previous_until]
    if len(tail) != 1 or any(version.valid_until > previous_until for version in versions):
        raise CustomPolicyError(
            'There is no single active policy aligned with the current end.', code='policy_not_extendable',
        )
    tail = tail[0]
    before = _snapshot(tail)
    tail.valid_until = new_until
    tail.save(update_fields=['valid_until', 'updated_at'])
    return _audit(
        subscription=subscription, policy=tail, action=ReceptionAIUsagePolicyChange.Action.EXTENDED,
        previous=tail.included_sessions, new=tail.included_sessions, effective_at=previous_until,
        actor=actor, reason=reason, details={'before': before, 'after': _snapshot(tail)},
    )


@transaction.atomic
def revoke_reception_custom_policy(
    *, subscription: SubscriptionV2, actor, reason: str, now: Optional[datetime] = None,
) -> ReceptionAIUsagePolicyChange:
    """Stop every current and scheduled version now. Revoked versions are never effective."""
    now = _now(now)
    reason = _require(actor, reason)
    from apps.business.models import Business

    # Revocation must stay possible even if the tier changed since: lock in the
    # same order but do not require reception_custom here.
    Business.objects.select_for_update().get(pk=subscription.business_id)
    subscription = SubscriptionV2.objects.select_for_update().get(pk=subscription.pk)
    versions = list(
        ReceptionAIUsagePolicy.objects.select_for_update()
        .filter(subscription=subscription, status=ReceptionAIUsagePolicy.Status.ACTIVE)
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now))
        .order_by('valid_from')
    )
    if not versions:
        raise CustomPolicyError('There is no current or scheduled policy to revoke.', code='no_policy')
    current = next((v for v in versions if v.valid_from <= now), None)
    for version in versions:
        version.status = ReceptionAIUsagePolicy.Status.REVOKED
        version.revoked_at = now
        version.revoked_by = actor
        version.save(update_fields=['status', 'revoked_at', 'revoked_by', 'updated_at'])
    anchor = current or versions[0]
    return _audit(
        subscription=subscription, policy=anchor, action=ReceptionAIUsagePolicyChange.Action.REVOKED,
        previous=current.included_sessions if current else None, new=None, effective_at=now,
        actor=actor, reason=reason, details={'revoked': [_snapshot(v) for v in versions]},
    )
