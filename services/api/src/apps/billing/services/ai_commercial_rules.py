"""
billing/services/ai_commercial_rules.py — PROD-02F5.1

The ONE commercial rule between the two AI sources of
``billing.services.ai_source.AI_SOURCES``:

    reception/reception  ⟂  appointments/appointments_ai

Every path that creates, activates or changes a subscription INTO an AI
source calls this module (complimentary grants, Turnos checkout start,
preapproval/payment webhooks, reconciliation through the activator, Turnos
plan changes). Turnos Base/Pro, Gestión and the other services are not AI
sources and are never affected.

Two checks:

* Exclusion: no other AI source may be non-canceled on the Business.
* Usage continuity: a NEW AI source may not start while AI usage is already
  counted in a usage period still running at its start. The engine counts
  per (Business, usage_period_start, usage_period_end); a new source would
  re-anchor the period and restart the count. Usage of the subscription
  itself is ignored, so renewals/recoveries of the same subscription are
  never blocked. The counting engine is untouched.

Callers MUST hold the Business row lock (``select_for_update``) in the
current transaction — the lock order is Business → SubscriptionV2 — so two
concurrent paths for one Business serialize on that row.
"""
from __future__ import annotations

from datetime import datetime

from django.db import connection
from django.db.models import Q

INCOMPATIBLE_AI_SERVICE = 'incompatible_ai_service'
AI_USAGE_PERIOD_OVERLAP = 'ai_usage_period_overlap'


class AICommercialConflict(ValueError):
    """Base: the requested AI source would break the commercial AI rule."""

    code = ''

    def __init__(self, message: str, *, conflicting_subscription_id=None):
        super().__init__(message)
        self.conflicting_subscription_id = conflicting_subscription_id


class IncompatibleAISourceConflict(AICommercialConflict):
    code = INCOMPATIBLE_AI_SERVICE


class AIUsagePeriodOverlapConflict(AICommercialConflict):
    code = AI_USAGE_PERIOD_OVERLAP


def is_ai_source(service_type, plan_code) -> bool:
    from apps.billing.services.ai_source import AI_SOURCES

    return (service_type, plan_code) in AI_SOURCES.values()


def find_ai_commercial_conflict(
    *,
    business_id: int,
    service_type: str,
    plan_code: str,
    starts_at: datetime,
    exclude_subscription_id=None,
    check_usage: bool = True,
    lock: bool = True,
) -> AICommercialConflict | None:
    """Return the conflict the rule finds (never raises), or None.

    ``lock=False`` is only for read-only reporting after the decision was
    already taken under the lock (e.g. writing a webhook note).
    """
    from apps.appointments.models import AppointmentAIUsageSession
    from apps.billing.models import SubscriptionV2
    from apps.billing.services.ai_source import AI_SOURCES

    requested = (service_type, plan_code)
    if requested not in AI_SOURCES.values():
        return None
    if lock and not connection.in_atomic_block:
        raise RuntimeError('The AI commercial rule must run inside the Business-locked transaction.')

    others = Q()
    for other_service, other_plan in AI_SOURCES.values():
        if (other_service, other_plan) != requested:
            others |= Q(service_type=other_service, plan_code=other_plan)
    rows = SubscriptionV2.objects.select_for_update() if lock else SubscriptionV2.objects
    conflicting = (
        rows.filter(others, business_id=business_id)
        .exclude(status=SubscriptionV2.Status.CANCELED)
        .exclude(pk=exclude_subscription_id)
        .order_by('created_at')
        .first()
    )
    if conflicting is not None:
        return IncompatibleAISourceConflict(
            f"El negocio ya tiene '{conflicting.service_type}/{conflicting.plan_code}' "
            f"(id={conflicting.pk}, status={conflicting.status}); Recepcionista IA y "
            f"Turnos IA no pueden convivir.",
            conflicting_subscription_id=conflicting.pk,
        )
    if requested == AI_SOURCES['reception']:
        # A Turnos IA purchase already in flight (open checkout the customer
        # may pay, or a Base/Pro → IA change awaiting payment/application) is
        # a Turnos IA source too: opening Recepcionista now would only turn
        # that future payment into a manual conflict.
        in_flight = _turnos_ai_in_flight(business_id, lock=lock)
        if in_flight is not None:
            return IncompatibleAISourceConflict(
                f'El negocio tiene una contratación de Turnos IA en curso ({in_flight}); '
                f'Recepcionista IA y Turnos IA no pueden convivir.'
            )
    if check_usage:
        sessions = AppointmentAIUsageSession.objects.filter(
            business_id=business_id, usage_period_end__gt=starts_at,
        )
        if exclude_subscription_id is not None:
            sessions = sessions.exclude(subscription_id=exclude_subscription_id)
        if sessions.exists():
            return AIUsagePeriodOverlapConflict(
                'El negocio ya tiene consumo de IA contado en un período que sigue vigente al '
                'inicio de la nueva fuente de IA. Debe empezar cuando ese período termine.'
            )
    return None


def _turnos_ai_in_flight(business_id: int, *, lock: bool) -> str | None:
    """An open Turnos IA checkout or pending change into Turnos IA, as a label."""
    from django.utils import timezone

    from apps.billing.models import AppointmentsCheckout, PendingSubscriptionChange

    checkouts = AppointmentsCheckout.objects.select_for_update() if lock else AppointmentsCheckout.objects
    checkout = (
        checkouts.filter(business_id=business_id, plan_code='appointments_ai')
        .filter(
            Q(status=AppointmentsCheckout.Status.LINKED)
            | Q(status=AppointmentsCheckout.Status.PENDING, expires_at__gt=timezone.now())
        )
        .first()
    )
    if checkout is not None:
        return f'checkout {checkout.pk}'
    changes = (
        PendingSubscriptionChange.objects.select_for_update(of=('self',)) if lock
        else PendingSubscriptionChange.objects
    )
    change = (
        changes.filter(
            subscription_v2__business_id=business_id,
            target_plan_code='appointments_ai',
            status__in=('pending_payment', 'processing', 'scheduled'),
        )
        .exclude(subscription_v2__plan_code='appointments_ai')
        .first()
    )
    if change is not None:
        return f'cambio de plan {change.pk}'
    return None


def assert_ai_source_allowed(**kwargs) -> None:
    """Raise the conflict found by ``find_ai_commercial_conflict`` (locked)."""
    conflict = find_ai_commercial_conflict(**kwargs)
    if conflict is not None:
        raise conflict
