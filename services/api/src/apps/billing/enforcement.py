"""
billing/enforcement.py — Global access enforcement decision layer.

Given a ResolvedSubscription (from billing.runtime), produces a deterministic
EnforcementDecision that is the single authoritative place for access gating
metadata with reason_code, grace details, and frontend hints.

Rules (§A):
  active           → access_allowed=True
  trialing         → access_allowed=True  (while within trial_ends_at)
  past_due         → access_allowed=True if within grace_until; else False
  checkout_pending → access_allowed=False
  suspended        → access_allowed=False
  canceled         → access_allowed=False
  none             → access_allowed=False

Design:
  - Does NOT re-query the database.
  - Derives decision purely from the ResolvedSubscription dataclass.
  - access_allowed mirrors resolved.access_granted (already computed in runtime).
  - Adds reason_code, grace metadata, and frontend hints on top.
  - All logging of access-denied events happens here.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from apps.billing.runtime import ResolvedSubscription

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Reason codes
# ──────────────────────────────────────────────────────────────────────────────

class ReasonCode:
    """
    Machine-readable reason codes for enforcement decisions.

    Frontend uses these to render appropriate UI:
      - access_granted        → normal access, no special UI needed
      - grace_period_active   → banner: "renew soon to avoid suspension"
      - grace_period_expired  → blocker: "renew to restore access"
      - trial_expired         → blocker: "trial ended, subscribe to continue"
      - suspended             → blocker: "account suspended, contact support"
      - canceled              → blocker: "subscription canceled"
      - checkout_pending      → info: "complete your payment to activate"
      - no_subscription       → blocker: "no active subscription found"
    """
    ACCESS_GRANTED       = 'access_granted'
    GRACE_PERIOD_ACTIVE  = 'grace_period_active'   # past_due, within grace
    GRACE_PERIOD_EXPIRED = 'grace_period_expired'  # past_due, grace elapsed
    TRIAL_EXPIRED        = 'trial_expired'          # trialing, trial ended
    SUSPENDED            = 'suspended'
    CANCELED             = 'canceled'
    CHECKOUT_PENDING     = 'checkout_pending'
    NO_SUBSCRIPTION      = 'no_subscription'


# ──────────────────────────────────────────────────────────────────────────────
# EnforcementDecision dataclass
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class EnforcementDecision:
    """
    Result of the global enforcement evaluation for a resolved subscription.

    Attributes:
        access_allowed:      True if the business may use plan features now.
        enforcement_status:  Effective status ('active', 'trialing', 'past_due',
                             'suspended', 'canceled', 'checkout_pending', 'none').
        reason_code:         Machine-readable string (see ReasonCode constants).
        in_grace_period:     True when PAST_DUE and still within grace window.
        grace_until:         End-of-grace datetime for PAST_DUE subs; None otherwise.
        access_until:        Best-effort datetime until access is guaranteed (may be None).
        show_renewal_prompt: True when the frontend should prompt for renewal.
        source:              Subscription source ('v2' | 'legacy' | 'none').
    """
    access_allowed: bool
    enforcement_status: str
    reason_code: str
    in_grace_period: bool
    grace_until: Optional[datetime]
    access_until: Optional[datetime]
    show_renewal_prompt: bool
    source: str


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def get_enforcement_decision(resolved: 'ResolvedSubscription') -> EnforcementDecision:
    """
    Compute the enforcement decision for an already-resolved subscription.

    This is the single authoritative place for access gating metadata.
    It does not query the database; it derives its decision entirely from the
    ResolvedSubscription returned by resolve_subscription().

    Args:
        resolved: Result of billing.runtime.resolve_subscription()

    Returns:
        EnforcementDecision with access_allowed, reason_code, grace info, and
        frontend hints.
    """
    access_allowed = resolved.access_granted
    status = resolved.status or 'none'
    source = resolved.source
    access_until = resolved.access_until

    grace_until: Optional[datetime] = None
    in_grace_period = False
    show_renewal_prompt = False

    sub_v2 = resolved.subscription_v2

    if access_allowed:
        if status == 'past_due' and sub_v2 is not None:
            # PAST_DUE within grace window — access granted, but show warning
            reason_code = ReasonCode.GRACE_PERIOD_ACTIVE
            in_grace_period = True
            grace_until = getattr(sub_v2, 'grace_until', None)
            show_renewal_prompt = True
            logger.info(
                "[enforcement] grace_period_active business=%s grace_until=%s",
                getattr(sub_v2, 'business_id', 'unknown'),
                grace_until,
            )
        else:
            reason_code = ReasonCode.ACCESS_GRANTED

    else:
        # Access denied — map status to reason code
        show_renewal_prompt = status in ('past_due', 'suspended', 'canceled')

        if status == 'past_due':
            reason_code = ReasonCode.GRACE_PERIOD_EXPIRED
            # grace_until may still be set (expired) — expose for debugging
            if sub_v2 is not None:
                grace_until = getattr(sub_v2, 'grace_until', None)

        elif status == 'trialing':
            # Trialing should not reach access_granted=False unless trial expired;
            # treat as trial expiry (no grace defined for trial status)
            reason_code = ReasonCode.TRIAL_EXPIRED

        elif status == 'suspended':
            reason_code = ReasonCode.SUSPENDED

        elif status == 'canceled':
            reason_code = ReasonCode.CANCELED

        elif status == 'checkout_pending':
            reason_code = ReasonCode.CHECKOUT_PENDING
            show_renewal_prompt = False

        else:
            # 'none', legacy-inactive, or any unknown status
            reason_code = ReasonCode.NO_SUBSCRIPTION
            show_renewal_prompt = False

        logger.info(
            "[enforcement] access_denied status=%s reason=%s source=%s",
            status, reason_code, source,
        )

    return EnforcementDecision(
        access_allowed=access_allowed,
        enforcement_status=status,
        reason_code=reason_code,
        in_grace_period=in_grace_period,
        grace_until=grace_until,
        access_until=access_until,
        show_renewal_prompt=show_renewal_prompt,
        source=source,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Human-readable messages (Spanish, for API responses / frontend display)
# ──────────────────────────────────────────────────────────────────────────────

_ENFORCEMENT_MESSAGES: dict[str, str] = {
    ReasonCode.ACCESS_GRANTED:       'Acceso permitido.',
    ReasonCode.GRACE_PERIOD_ACTIVE:  (
        'Tu pago está vencido. Tenés un período de gracia activo; '
        'regularizá tu suscripción para evitar la suspensión.'
    ),
    ReasonCode.GRACE_PERIOD_EXPIRED: (
        'Tu período de gracia venció. Regularizá tu suscripción para continuar.'
    ),
    ReasonCode.TRIAL_EXPIRED:        (
        'Tu período de prueba finalizó. Activá tu suscripción para continuar.'
    ),
    ReasonCode.SUSPENDED:            (
        'Tu suscripción está suspendida. Regularizá tu cuenta para continuar.'
    ),
    ReasonCode.CANCELED:             (
        'Tu suscripción fue cancelada. Contactá soporte o suscribite nuevamente.'
    ),
    ReasonCode.CHECKOUT_PENDING:     'Hay un pago pendiente de confirmación.',
    ReasonCode.NO_SUBSCRIPTION:      (
        'No hay suscripción activa asociada a este negocio.'
    ),
}


def enforcement_message(reason_code: str) -> str:
    """Return a human-readable enforcement message for the given reason_code."""
    return _ENFORCEMENT_MESSAGES.get(reason_code, 'Acceso restringido.')
