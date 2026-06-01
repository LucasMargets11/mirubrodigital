"""
billing/service_activation.py
==============================
Service-specific activation hooks invoked after the canonical activator
(``activate_subscription_from_invoice``) has marked SubscriptionV2 / Business
as active.

Why this exists
---------------
``activate_subscription_from_invoice`` only writes V2 + Business.status.  Some
services (notably ``qr_reviews``) still gate runtime access through legacy
artifacts that are not yet migrated:

  • ``business.Subscription`` (OneToOne legacy plan/service/status row)
  • ``reviews.ReviewConfig`` (enabled flag + Google place defaults)

This module keeps SubscriptionV2 and those legacy artifacts in sync so the
gate at ``GET /api/v1/reviews/qr/`` (which reads legacy) responds 200 after
an automatic Mercado Pago activation — same end state as the manual shell
fix that operations used to apply.

Design rules
------------
* IDEMPOTENT — safe to call from the webhook handler, the reconcile path, or a
  retry/operator action.  No call ever creates duplicates or destroys
  user-edited configuration.
* DEFENSIVE — never raises out of the activation transaction.  All failures
  are logged with full context; the canonical activation is the source of
  truth and must not be reverted by a sync failure in a sibling service.
* NARROW SCOPE — only writes the legacy/companion artifacts a service needs
  to function.  Does NOT touch billing primitives (SubscriptionV2 status,
  invoice events, etc.) — those are owned by ``subscription_activator``.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def ensure_service_activation(
    *,
    business,
    owner=None,
    plan_code: str,
    service_type: str,
    subscription_v2=None,
    source: str = 'unknown',
    external_reference: str = '',
    provider: str = 'mercadopago',
) -> None:
    """
    Dispatch service-specific activation work after the canonical activator
    has run.

    Parameters
    ----------
    business : business.Business
        The tenant being activated.  Must be non-null.
    owner : accounts.User | None
        The user who initiated the checkout.  Optional — used to ensure an
        owner Membership exists.
    plan_code : str
        Canonical plan code from SubscriptionV2 (e.g. 'qr_reviews_pro',
        'qr_reviews_base', 'qr_reviews', 'gestion_pro', ...).
    service_type : str
        Canonical service type from SubscriptionV2.service_type.  Drives
        per-service dispatch.
    subscription_v2 : billing.SubscriptionV2 | None
        The activated V2 row.  Optional — used to read period_end and other
        denormalized data for the legacy sync.
    source : str
        Free-form caller tag for logs: 'webhook' | 'reconcile' | 'manual' | ...
    external_reference : str
        MP external_reference for traceability.
    provider : str
        Payment provider tag.  Currently informational only.

    Returns
    -------
    None.  Failures are logged but never raised — the canonical activation
    must stand even if a companion artifact write fails.
    """
    if business is None:
        logger.warning('[service-activation] business is None — nothing to do')
        return

    if not plan_code:
        logger.warning(
            '[service-activation] business=%s missing plan_code — skipping',
            business.pk,
        )
        return

    svc = (service_type or '').lower()

    try:
        if svc == 'qr_reviews':
            activate_qr_reviews(
                business=business,
                owner=owner,
                plan_code=plan_code,
                subscription_v2=subscription_v2,
                source=source,
                external_reference=external_reference,
                provider=provider,
            )
        else:
            # Other services do not need legacy/companion sync today.
            # Logging at debug so we still have a trace if needed.
            logger.debug(
                '[service-activation] no hook for service=%s business=%s plan=%s source=%s',
                svc, business.pk, plan_code, source,
            )
    except Exception as exc:  # noqa: BLE001 — must never propagate
        logger.exception(
            '[service-activation] hook failed service=%s business=%s plan=%s '
            'source=%s ext_ref=%s: %s',
            svc, business.pk, plan_code, source, external_reference, exc,
        )


# ─────────────────────────────────────────────────────────────────────────────
# QR de Reseñas
# ─────────────────────────────────────────────────────────────────────────────

# Canonical plan codes accepted by the qr_reviews hook.
_QR_REVIEWS_PLAN_CODES = frozenset({'qr_reviews', 'qr_reviews_base', 'qr_reviews_pro'})
_QR_REVIEWS_PRO_CODES = frozenset({'qr_reviews_pro'})


def activate_qr_reviews(
    *,
    business,
    owner=None,
    plan_code: str,
    subscription_v2=None,
    source: str,
    external_reference: str = '',
    provider: str = 'mercadopago',
) -> None:
    """
    Idempotent activation of the QR de Reseñas service.

    Performs four small, independently-idempotent writes:

      A) Business — ensure ``status='active'``, ``default_service='qr_reviews'``
         (and ``service_type='qr_reviews'`` if the canonical Phase-2A column is
         present), and ``activated_at`` set.
      B) Membership — ensure an active owner Membership exists for *owner*.
      C) business.Subscription (legacy) — upsert OneToOne row with
         ``plan=plan_code``, ``service='qr_reviews'``, ``status='active'``,
         ``renews_at`` from V2 or now+30d.
      D) ReviewConfig — ensure exists with ``enabled=True``,
         ``redirect_threshold=4``, ``mode=smart_filter`` for Pro, without
         overwriting user-edited fields.
    """
    if plan_code not in _QR_REVIEWS_PLAN_CODES:
        logger.warning(
            '[service-activation/qr_reviews] business=%s unknown plan_code=%s — skipping',
            business.pk, plan_code,
        )
        return

    with transaction.atomic():
        _qr_reviews_business_fields(business)
        _qr_reviews_membership(business, owner)
        legacy_id = _qr_reviews_legacy_subscription(
            business=business,
            plan_code=plan_code,
            subscription_v2=subscription_v2,
        )
        config_id = _qr_reviews_review_config(business=business, plan_code=plan_code)
        _qr_reviews_sync_v2(
            subscription_v2=subscription_v2,
            plan_code=plan_code,
            external_reference=external_reference,
        )

    logger.info(
        '[service-activation] service=qr_reviews business=%s plan=%s source=%s '
        'legacy=%s review_config=%s ext_ref=%s provider=%s',
        business.pk, plan_code, source, legacy_id, config_id,
        external_reference, provider,
    )


# ─────────────────────────────────────────────────────────────────────────────
# QR de Reseñas — internal steps
# ─────────────────────────────────────────────────────────────────────────────

def _qr_reviews_business_fields(business) -> None:
    """Ensure Business has status=active, default_service=qr_reviews, activated_at."""
    update_fields: list[str] = []
    now = timezone.now()

    if business.status != 'active':
        business.status = 'active'
        update_fields.append('status')

    if getattr(business, 'default_service', None) != 'qr_reviews':
        business.default_service = 'qr_reviews'
        update_fields.append('default_service')

    # Phase-2A canonical column may or may not exist depending on the
    # migration state of the deployment.  Only touch it when present.
    if hasattr(business, 'service_type') and business.service_type != 'qr_reviews':
        business.service_type = 'qr_reviews'
        update_fields.append('service_type')

    if getattr(business, 'activated_at', None) is None:
        business.activated_at = now
        update_fields.append('activated_at')

    if update_fields:
        business.save(update_fields=update_fields)


def _qr_reviews_membership(business, owner) -> None:
    """Ensure *owner* has an active owner Membership for *business*."""
    if owner is None:
        return

    from apps.accounts.models import Membership

    membership, created = Membership.objects.get_or_create(
        user=owner,
        business=business,
        defaults={'role': 'owner', 'status': Membership.Status.ACTIVE},
    )
    if created:
        return

    # Existing membership: only force back to ACTIVE if it was inactive/suspended;
    # never demote the role (operator may have promoted/demoted intentionally).
    if hasattr(membership, 'status') and membership.status != Membership.Status.ACTIVE:
        membership.status = Membership.Status.ACTIVE
        membership.save(update_fields=['status'])


def _qr_reviews_legacy_subscription(
    *,
    business,
    plan_code: str,
    subscription_v2,
) -> Optional[int]:
    """Upsert the OneToOne legacy ``business.Subscription`` row."""
    from apps.business.models import Subscription as BusinessSubscription

    period_end = _resolve_period_end(subscription_v2)

    defaults = {
        'plan': plan_code,
        'service': 'qr_reviews',
        'status': 'active',
        'renews_at': period_end,
    }

    legacy, created = BusinessSubscription.objects.update_or_create(
        business=business,
        defaults=defaults,
    )

    # max_branches / max_seats: only set on create — never overwrite operator
    # adjustments (e.g. a manually-granted extra seat).
    if created:
        legacy.max_branches = 1
        legacy.max_seats = 2
        legacy.save(update_fields=['max_branches', 'max_seats'])

    return legacy.pk


def _qr_reviews_review_config(*, business, plan_code: str) -> Optional[int]:
    """Ensure ReviewConfig exists and is enabled, without overwriting edits."""
    from apps.reviews.models import ReviewConfig, ReviewMode

    config, created = ReviewConfig.objects.get_or_create(business=business)

    update_fields: list[str] = []

    if not config.enabled:
        config.enabled = True
        update_fields.append('enabled')

    # redirect_threshold defaults to 4 on the model; only reset to 4 on create
    # to avoid overwriting a value the user picked.
    if created and config.redirect_threshold != 4:
        config.redirect_threshold = 4
        update_fields.append('redirect_threshold')

    # Mode: Pro gets smart_filter by default; Base/legacy stays in direct mode.
    # Only set on create to avoid stepping on operator/user choices.
    if created:
        target_mode = (
            ReviewMode.SMART_FILTER
            if plan_code in _QR_REVIEWS_PRO_CODES
            else ReviewMode.DIRECT
        )
        if config.mode != target_mode:
            config.mode = target_mode
            update_fields.append('mode')

    if update_fields:
        config.save(update_fields=update_fields)

    return config.pk


def _qr_reviews_sync_v2(
    *,
    subscription_v2,
    plan_code: str,
    external_reference: str,
) -> None:
    """Best-effort consistency tweaks on the V2 row (service_type, plan_code, ext_ref)."""
    if subscription_v2 is None:
        return

    update_fields: list[str] = []

    if getattr(subscription_v2, 'service_type', None) != 'qr_reviews':
        subscription_v2.service_type = 'qr_reviews'
        update_fields.append('service_type')

    if getattr(subscription_v2, 'plan_code', None) != plan_code:
        subscription_v2.plan_code = plan_code
        update_fields.append('plan_code')

    # external_reference is required + unique.  Never overwrite an existing
    # one — only fill if missing.
    if (
        external_reference
        and not getattr(subscription_v2, 'external_reference', None)
    ):
        subscription_v2.external_reference = external_reference
        update_fields.append('external_reference')

    if update_fields:
        try:
            subscription_v2.save(update_fields=update_fields)
        except Exception as exc:  # noqa: BLE001
            # Unique-constraint collision (e.g. duplicate external_reference)
            # is non-fatal; the canonical activator already committed V2 in a
            # usable state.
            logger.warning(
                '[service-activation/qr_reviews] V2 sync skipped sub=%s fields=%s: %s',
                subscription_v2.pk, update_fields, exc,
            )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_period_end(subscription_v2):
    """Pick a sensible renews_at: V2.current_period_end, else now+30d."""
    if subscription_v2 is not None:
        end = getattr(subscription_v2, 'current_period_end', None)
        if end is not None:
            return end
    return timezone.now() + timedelta(days=30)
