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
from .canonical_pricing import get_usage_tier as _get_canonical_usage_tier
from .models import RECEPTION_CUSTOM_MAX_INCLUDED_SESSIONS, Plan, SubscriptionV2

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


class InvalidCustomAllowanceError(ComplimentaryAccessError):
    """
    PROD-02F3: ``custom_included_sessions`` missing/invalid for
    ``reception_custom``, sent for any other tier or product, or the bonified
    window no longer allows a valid custom policy.
    """


class InvalidUsageTierError(ComplimentaryAccessError):
    """
    ``usage_tier`` is missing for a tier-priced plan (Turnos IA), is not one of
    its provisionable tiers, or was sent for a plan that has no usage tiers.
    """


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


# ── Internal provisioning eligibility (PROD-02F2) ────────────────────────────
#
# Internal (platform-admin, complimentary) eligibility is an EXPLICIT policy,
# independent of public availability: public checkout stays gated by
# canonical_pricing.is_plan_product_active() and nothing here activates a
# product or plan. Only these inactive catalog plans may be granted, each with
# its own tier rule; every other inactive plan or internal tier stays out.
#
#   appointments (Turnos, seeded inactive by seed_appointments_catalog):
#       any plan of the vertical; tier-priced appointments_ai only with its
#       self-service tiers that have an allowance (ai_300/1500/3000). `custom`
#       never (no allowance, ManualContractRequired).
#   reception (Recepcionista IA, seeded inactive by seed_reception_catalog):
#       plan `reception` only, with exactly the fixed internal tiers below and
#       only while the catalog keeps them internal/manual, with a positive
#       allowance, overage disabled (no price, spend cap 0) and no public
#       price. `reception_custom` (PROD-02F3) only while the catalog keeps it
#       contact_sales/manual with NO global allowance, no price and no
#       overage: its allowance is always an individual ReceptionAIUsagePolicy
#       created in the same transaction (custom_included_sessions).
INTERNAL_PROVISIONING_POLICY = {
    'appointments': {'plans': None, 'tier_rule': 'self_service'},
    'reception': {
        'plans': frozenset({'reception'}),
        'tier_rule': 'internal_fixed',
        'tiers': frozenset({'reception_300', 'reception_1500', 'reception_3000'}),
        'custom_tiers': frozenset({'reception_custom'}),
    },
}
# Kept for readers of the old name: the verticals with internal eligibility.
_INTERNAL_PROVISIONING_VERTICALS = frozenset(INTERNAL_PROVISIONING_POLICY)


def _internal_policy(plan_code: str):
    canonical_plan = _get_canonical_plan(plan_code)
    if canonical_plan is None:
        return None, None
    policy = INTERNAL_PROVISIONING_POLICY.get(canonical_plan.get('vertical'))
    if policy is None or (policy['plans'] is not None and plan_code not in policy['plans']):
        return canonical_plan, None
    return canonical_plan, policy


def _is_provisionable_plan(plan: Plan) -> bool:
    if plan.plan_status == 'active':
        return True
    _, policy = _internal_policy(plan.code)
    return policy is not None


def _is_internal_fixed_tier(tier: dict) -> bool:
    """Recepcionista fixed tier with exactly the internal terms of the catalog."""
    included = tier.get('included_conversations')
    return (
        tier.get('purchase_mode') == 'internal'
        and tier.get('billing_mode') == 'manual'
        and type(included) is int and included > 0
        and tier.get('extra_conversation_price') is None
        and type(tier.get('default_extra_spend_limit')) is int
        and tier.get('default_extra_spend_limit') == 0
        and tier.get('monthly_price') is None
        and tier.get('annual_price') is None
    )


def _is_custom_policy_tier(tier: dict) -> bool:
    """Recepcionista Custom with exactly its catalog terms: allowance by policy only."""
    return (
        tier.get('purchase_mode') == 'contact_sales'
        and tier.get('billing_mode') == 'manual'
        and tier.get('included_conversations') is None
        and tier.get('extra_conversation_price') is None
        and tier.get('default_extra_spend_limit') in (None, 0)
        and tier.get('monthly_price') is None
        and tier.get('annual_price') is None
    )


def custom_policy_tiers(plan_code: str) -> frozenset:
    """Tiers of *plan_code* whose allowance is an individual policy (PROD-02F3)."""
    canonical_plan = _get_canonical_plan(plan_code)
    policy = INTERNAL_PROVISIONING_POLICY.get((canonical_plan or {}).get('vertical'))
    if policy is None or (policy['plans'] is not None and plan_code not in policy['plans']):
        return frozenset()
    return policy.get('custom_tiers', frozenset())


def _provisionable_usage_tiers(plan_code: str) -> list[dict]:
    """
    Usage tiers a complimentary grant may assign to *plan_code*, from the
    canonical catalog (generated/pricing.json). Empty for plans that are not
    tier-priced. Turnos IA: self-service tiers with a resolved conversation
    allowance (``custom`` fails closed). Recepcionista (PROD-02F2): only the
    allowlisted fixed tiers whose catalog terms are internal/manual, positive
    allowance, overage disabled and no public price.
    """
    canonical_plan = _get_canonical_plan(plan_code)
    if canonical_plan is None or canonical_plan.get('pricing_mode') != 'usage_tier':
        return []
    policy = INTERNAL_PROVISIONING_POLICY.get(canonical_plan.get('vertical'))
    if policy is not None and policy['plans'] is not None and plan_code not in policy['plans']:
        return []
    rule = policy['tier_rule'] if policy is not None else 'self_service'
    tiers = []
    for code in canonical_plan.get('usage_tiers', []):
        tier = _get_canonical_usage_tier(code)
        if tier is None or tier.get('plan_code') != plan_code:
            continue
        if rule == 'internal_fixed':
            if code in policy.get('custom_tiers', ()):
                if not _is_custom_policy_tier(tier):
                    continue
                tiers.append({
                    'code': tier['code'], 'name': tier['name'],
                    # The form must ask for the individual allowance (PROD-02F3).
                    'custom_allowance': {'min': 1, 'max': RECEPTION_CUSTOM_MAX_INCLUDED_SESSIONS},
                })
                continue
            if code not in policy['tiers'] or not _is_internal_fixed_tier(tier):
                continue
        elif (
            tier.get('purchase_mode') != 'self_service'
            or type(tier.get('included_conversations')) is not int
            or tier['included_conversations'] <= 0
        ):
            continue
        tiers.append({'code': tier['code'], 'name': tier['name']})
    return tiers


def _validate_usage_tier(plan_code: str, usage_tier) -> str | None:
    allowed = {tier['code'] for tier in _provisionable_usage_tiers(plan_code)}
    canonical_plan = _get_canonical_plan(plan_code) or {}
    if canonical_plan.get('pricing_mode') == 'usage_tier':
        if usage_tier not in allowed:
            raise InvalidUsageTierError(
                f"El plan '{plan_code}' requiere elegir un nivel de uso válido "
                f"({', '.join(sorted(allowed))})."
            )
        return usage_tier
    if usage_tier not in (None, ''):
        raise InvalidUsageTierError(
            f"El plan '{plan_code}' no admite nivel de uso."
        )
    return None


def list_provisioning_options() -> list[dict]:
    """
    Enumerate the (service_type, plan_code) combinations that
    ``grant_complimentary_access()`` currently accepts — read-only, no writes.

    For each provisionable ``Plan`` (``plan_status='active'``, or a seeded
    plan of an internal-provisioning vertical such as Turnos), derives its service_type
    from the same canonical vertical mapping (``_VERTICAL_TO_SERVICE_TYPE``)
    and re-validates the pair through the exact same
    ``_check_plan_service_compatibility()`` helper ``grant_complimentary_access()``
    calls — no separate compatibility matrix is created. A plan is included
    only if its derived service_type is also a real
    ``SubscriptionV2.ServiceType`` member, mirroring the service_type check
    ``grant_complimentary_access()`` performs before checking compatibility.

    Returns a list of ``{'value', 'label', 'plans': [{'code', 'name'}, ...]}``
    dicts, sorted deterministically by service_type then plan code. A
    tier-priced plan (Turnos IA) also carries ``usage_tiers: [{'code',
    'name'}, ...]``; it is omitted when none of its tiers is provisionable.
    """
    services: dict[str, dict] = {}
    for plan in Plan.objects.order_by('code'):
        if not _is_provisionable_plan(plan):
            continue
        canonical_plan = _get_canonical_plan(plan.code)
        if canonical_plan is None:
            continue

        service_type = _VERTICAL_TO_SERVICE_TYPE.get(canonical_plan['vertical'])
        if service_type is None or service_type not in SubscriptionV2.ServiceType.values:
            continue

        try:
            _check_plan_service_compatibility(plan.code, service_type)
        except PlanServiceMismatchError:
            continue

        bucket = services.setdefault(service_type, {
            'value': service_type,
            'label': SubscriptionV2.ServiceType(service_type).label,
            'plans': [],
        })
        option = {'code': plan.code, 'name': plan.name}
        if canonical_plan.get('pricing_mode') == 'usage_tier':
            tiers = _provisionable_usage_tiers(plan.code)
            if not tiers:
                continue
            option['usage_tiers'] = tiers
        bucket['plans'].append(option)

    return [services[key] for key in sorted(services)]


def grant_complimentary_access(
    *,
    business,
    plan_code: str,
    service_type: str,
    starts_at: datetime,
    ends_at: datetime,
    granted_by,
    reason: str,
    usage_tier: str | None = None,
    custom_included_sessions: int | None = None,
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
        usage_tier:   Required for a tier-priced plan (Turnos IA, e.g.
                      'ai_300'); must be None/blank for every other plan.

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
        InvalidUsageTierError: usage_tier missing/invalid for a tier-priced
            plan, or present for a plan without tiers.
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
    plan = Plan.objects.filter(code=plan_code).first()
    if plan is None or not _is_provisionable_plan(plan):
        raise PlanNotAvailableError(f"El plan '{plan_code}' no existe o no está activo.")

    # ── 3b. Validate plan_code's vertical matches the requested service ────
    _check_plan_service_compatibility(plan_code, service_type)

    # ── 3c. Usage tier: required by tier-priced plans, rejected otherwise ──
    usage_tier = _validate_usage_tier(plan_code, usage_tier)

    # ── 3d. Custom allowance (PROD-02F3): only and always for a custom-policy
    #        tier; strict int in [1, max]; never unlimited. One server instant.
    custom_tier = usage_tier in custom_policy_tiers(plan_code)
    if custom_tier:
        value = custom_included_sessions
        if type(value) is not int or not 1 <= value <= RECEPTION_CUSTOM_MAX_INCLUDED_SESSIONS:
            raise InvalidCustomAllowanceError(
                f'El cupo personalizado debe ser un entero entre 1 y {RECEPTION_CUSTOM_MAX_INCLUDED_SESSIONS}.'
            )
    elif custom_included_sessions is not None:
        raise InvalidCustomAllowanceError('El cupo personalizado solo aplica a Recepcionista Custom.')
    from django.utils import timezone as _tz

    now = _tz.now()
    policy_from = max(now, starts_at)
    if custom_tier and policy_from >= ends_at:
        raise InvalidCustomAllowanceError(
            'La ventana bonificada ya no permite una política personalizada vigente.'
        )

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
            usage_tier=usage_tier,
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

        # ── 5b. Recepcionista Custom: its individual policy, same transaction ─
        # Never retroactive (from max(now, start)) and inside the bonified
        # window; any failure rolls back the subscription too.
        if custom_tier:
            from .services.reception_ai_policy import CustomPolicyError, create_reception_custom_policy

            try:
                create_reception_custom_policy(
                    subscription=subscription, included_sessions=custom_included_sessions,
                    actor=granted_by, reason=reason, valid_from=policy_from, valid_until=ends_at, now=now,
                )
            except CustomPolicyError as exc:
                raise InvalidCustomAllowanceError(str(exc)) from exc

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
                'usage_tier': usage_tier,
                'custom_included_sessions': custom_included_sessions if custom_tier else None,
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
