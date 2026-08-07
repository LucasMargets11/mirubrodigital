"""
billing/complimentary_access_service.py — ADMIN-CLIENTES 01A

Domain service for platform-admin-granted complimentary ("bonificado") access.

A complimentary access is a regular ``SubscriptionV2`` row with
``provider='manual'`` and ``status='trialing'``.  It never talks to
Mercado Pago and never creates a ``SubscriptionIntent``/``PaymentAttempt`` or
any provider identifier.

This module owns exactly one transactional entry point:
``grant_complimentary_access()``.  Cancellation of a manual subscription is
handled by the existing ``cancellation_service.cancel_subscription_immediately``
(it already skips all Mercado Pago calls when ``provider != mercadopago``).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime

from django.db import transaction

from .canonical_pricing import PRODUCTS as _CANONICAL_PRODUCTS
from .canonical_pricing import get_plan as _get_canonical_plan
from .models import Plan, SubscriptionV2

logger = logging.getLogger(__name__)


class ComplimentaryAccessError(Exception):
    """
    Base domain error for an invalid complimentary access grant.

    Kept as the base class for backward compatibility and for failures that
    don't map to one of the specific causes below (missing business/actor,
    blank reason, or a malformed service_type). Callers that need to tell
    causes apart (ADMIN-CLIENTES 02B) should catch the specific subclasses
    first — never inspect ``str(exc)``.
    """
    pass


class InvalidPeriodError(ComplimentaryAccessError):
    """``ends_at`` is missing or not strictly after ``starts_at``."""


class PlanNotAvailableError(ComplimentaryAccessError):
    """``plan_code`` does not exist or is not ``plan_status='active'``."""


class PlanServiceMismatchError(ComplimentaryAccessError):
    """
    ``plan_code``'s canonical vertical does not map to ``service_type`` —
    including plans with no canonical pricing entry at all (fails closed,
    e.g. legacy 'restaurante' vertical plans).
    """


class ActiveSubscriptionConflictError(ComplimentaryAccessError):
    """``business`` already has a non-canceled SubscriptionV2 for ``service_type``."""


class InvalidGrantReasonError(ComplimentaryAccessError):
    """``reason`` is blank/whitespace-only."""


class InvalidServiceTypeError(ComplimentaryAccessError):
    """``service_type`` is not a member of ``SubscriptionV2.ServiceType.values``."""


# Derived (not hardcoded) from generated/pricing.json's canonical "products"
# list — the single source of truth already used by canonical_pricing.py /
# commercial_plans.py.  e.g. {'commercial': 'gestion', 'menu_qr': 'menu_qr',
# 'qr_reviews': 'qr_reviews'}.
_VERTICAL_TO_SERVICE_TYPE: dict = {
    product['vertical']: product['code'] for product in _CANONICAL_PRODUCTS
}


def _check_plan_service_compatibility(plan_code: str, service_type: str) -> None:
    """
    Reject a plan_code/service_type pair unless the plan's canonical vertical
    (generated/pricing.json) maps to the requested service_type.

    Fails closed: a plan_code with no canonical pricing entry (e.g. the
    legacy 'restaurante' vertical plans, which predate the canonical pricing
    catalog — see seed_billing.py PLAN_SEEDS) is rejected rather than
    guessed, since there is no unambiguous source to validate it against.
    """
    canonical_plan = _get_canonical_plan(plan_code)
    if canonical_plan is None:
        raise PlanServiceMismatchError(
            f"El plan '{plan_code}' no tiene información canónica de vertical "
            f"(generated/pricing.json). No se puede verificar su compatibilidad "
            f"con el servicio '{service_type}' de forma segura."
        )

    expected_service_type = _VERTICAL_TO_SERVICE_TYPE.get(canonical_plan['vertical'])
    if expected_service_type != service_type:
        raise PlanServiceMismatchError(
            f"El plan '{plan_code}' pertenece a la vertical '{canonical_plan['vertical']}' "
            f"(servicio '{expected_service_type}'), incompatible con el servicio "
            f"solicitado '{service_type}'."
        )


def grant_complimentary_access(
    *,
    business,
    plan_code: str,
    service_type: str,
    starts_at: datetime,
    ends_at: datetime,
    granted_by,
    reason: str,
) -> SubscriptionV2:
    """
    Grant a complimentary (bonified) access period to *business*.

    Creates a single ``SubscriptionV2`` with ``provider=manual``,
    ``status=trialing``, ``is_active=True`` and ``provider_sub_id=None``.
    Advances ``Business.status`` to ``trialing`` and writes an
    ``ADMIN_COMPLIMENTARY_ACCESS_GRANTED`` entry to ``AccessAuditLog``.

    Never calls Mercado Pago. Never writes to the legacy ``billing.Subscription``
    model. The whole operation is atomic — any failure rolls back all writes.

    Args:
        business:     business.Business instance to grant access to.
        plan_code:    Plan.code of an active catalog plan (e.g. 'gestion_pro').
        service_type: One of SubscriptionV2.ServiceType values (e.g. 'gestion').
        starts_at:    Start of the bonified period (current_period_start).
        ends_at:      End of the bonified period (current_period_end).
        granted_by:   The platform admin (User) granting the access.
        reason:       Non-empty internal reason for the grant.

    Returns:
        The newly created SubscriptionV2.

    Raises:
        InvalidPeriodError: ends_at missing or not strictly after starts_at.
        PlanNotAvailableError: plan_code does not exist or is not active.
        PlanServiceMismatchError: plan_code's vertical does not match service_type
            (including plans with no canonical pricing entry at all).
        ActiveSubscriptionConflictError: business already has a non-canceled
            subscription for the same service_type.
        InvalidGrantReasonError: reason is blank/whitespace-only.
        InvalidServiceTypeError: service_type is not a SubscriptionV2.ServiceType member.
        ComplimentaryAccessError: any other validation failure (missing
            business or missing actor) — these represent a caller building
            the request incorrectly (an internal invariant violation for a
            correctly-constructed provisioning caller), so they are kept on
            the base class rather than given their own public subclass.
    """
    # ── 1. Basic field validation ───────────────────────────────────────────
    if not ends_at or not starts_at or ends_at <= starts_at:
        raise InvalidPeriodError(
            'La fecha de finalización debe ser posterior a la fecha de inicio.'
        )

    reason = (reason or '').strip()
    if not reason:
        raise InvalidGrantReasonError('Debe indicar un motivo para el acceso bonificado.')

    # ── 2. Validate service_type against the existing canonical enum ───────
    if service_type not in SubscriptionV2.ServiceType.values:
        raise InvalidServiceTypeError(f"service_type '{service_type}' no es válido.")

    # ── 3. Validate plan_code against the existing Plan catalog ────────────
    if not Plan.objects.filter(code=plan_code, plan_status='active').exists():
        raise PlanNotAvailableError(f"El plan '{plan_code}' no existe o no está activo.")

    # ── 3b. Validate plan_code's vertical matches the requested service ────
    _check_plan_service_compatibility(plan_code, service_type)

    if business is None:
        raise ComplimentaryAccessError('Debe indicar un negocio válido.')

    if granted_by is None:
        raise ComplimentaryAccessError('Debe indicar el administrador que otorga el acceso.')

    with transaction.atomic():
        # ── 4. Reject if the business already has a vigent, incompatible sub ──
        existing = (
            SubscriptionV2.objects
            .select_for_update()
            .filter(business=business, service_type=service_type)
            .exclude(status=SubscriptionV2.Status.CANCELED)
            .first()
        )
        if existing is not None:
            raise ActiveSubscriptionConflictError(
                f"El negocio ya tiene una suscripción vigente para '{service_type}' "
                f"(id={existing.pk}, status={existing.status}). No se reemplaza automáticamente."
            )

        # ── 5. Create the manual, bonified SubscriptionV2 ──────────────────
        subscription = SubscriptionV2.objects.create(
            business=business,
            service_type=service_type,
            plan_code=plan_code,
            provider=SubscriptionV2.Provider.MANUAL,
            provider_sub_id=None,
            external_reference=f"SUB-{uuid.uuid4()}",
            status=SubscriptionV2.Status.TRIALING,
            is_active=True,
            current_period_start=starts_at,
            current_period_end=ends_at,
            manual_granted_by=granted_by,
            manual_grant_reason=reason,
        )

        # ── 6. Advance Business.status to 'trialing' (canonical mapping) ───
        _advance_business_to_trialing(business)

        # ── 7. Audit log — inside the same transaction (rolls back on error) ─
        from apps.accounts.platform_audit import log_platform_action
        log_platform_action(
            action='ADMIN_COMPLIMENTARY_ACCESS_GRANTED',
            actor=granted_by,
            entity_type='subscription_v2',
            entity_id=str(subscription.id),
            business=business,
            details={
                'subscription_id': str(subscription.id),
                'business_id': business.pk,
                'plan_code': plan_code,
                'service_type': service_type,
                'current_period_start': starts_at.isoformat(),
                'current_period_end': ends_at.isoformat(),
                'reason': reason,
            },
        )

    logger.info(
        "[complimentary_access] Granted sub=%s business=%s plan=%s service=%s "
        "admin=%s start=%s end=%s",
        subscription.pk, business.pk, plan_code, service_type,
        granted_by.pk, starts_at, ends_at,
    )

    return subscription


def _advance_business_to_trialing(business) -> None:
    """
    Set Business.status='trialing', mirroring the canonical mapping used by
    subscription_activator._activate_tenant() for SubscriptionV2.TRIALING.
    No-op if the business is already 'trialing'.
    """
    if business.status == 'trialing':
        return
    business.status = 'trialing'
    business.save(update_fields=['status'])
