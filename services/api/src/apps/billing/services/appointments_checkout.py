"""Canonical Turnos quote, checkout, and authoritative payment application."""
from __future__ import annotations

import calendar
import logging
import uuid
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.billing import canonical_pricing
from apps.billing.appointments_plans import (
    AUTOMATIONS,
    EXTRA_PROFESSIONAL,
    get_appointments_plan_config,
)

logger = logging.getLogger(__name__)
QUOTE_VERSION = 1


class ManualContractRequired(ValueError):
    """The selected Turnos tier requires a manually negotiated contract."""


def quote_appointments(
    *,
    plan_code: str,
    billing_cycle: str,
    usage_tier: str | None = None,
    automations: bool | None = None,
    automations_quantity: int | None = None,
    extra_professionals: int = 0,
) -> dict:
    if billing_cycle not in ('monthly', 'yearly'):
        raise ValidationError({'billing_cycle': 'Use monthly or yearly.'})
    if type(extra_professionals) is not int or extra_professionals < 0:
        raise ValidationError({'extra_professionals': 'Must be a nonnegative integer.'})
    if automations is not None and type(automations) is not bool:
        raise ValidationError({'automations': 'Must be a boolean.'})
    if automations_quantity is not None:
        if type(automations_quantity) is not int or automations_quantity not in (0, 1):
            raise ValidationError({'automations_quantity': 'Quantity must be 0 or 1.'})
        if automations is not None and automations != bool(automations_quantity):
            raise ValidationError({'automations': 'Conflicts with automations_quantity.'})
        automations = bool(automations_quantity)
    automations = bool(automations)

    get_appointments_plan_config(plan_code, usage_tier)
    tier = canonical_pricing.get_usage_tier(usage_tier) if usage_tier else None
    if tier and tier.get('purchase_mode') == 'contact_sales':
        raise ManualContractRequired('contact_sales / manual_contract_required')

    if plan_code == 'appointments_ai':
        base_amount = canonical_pricing.usage_tier_price(usage_tier, billing_cycle)
        automations_state = 'included'
        addon_amount = 0
    else:
        base_amount = canonical_pricing.plan_price(plan_code, billing_cycle)
        automations_state = 'enabled' if automations else 'disabled'
        addon_amount = (
            canonical_pricing.addon_price(AUTOMATIONS, billing_cycle)
            if automations else 0
        )

    extra_unit_price = canonical_pricing.extra_price(EXTRA_PROFESSIONAL, billing_cycle)
    extras_amount = extra_unit_price * extra_professionals
    items = [{
        'code': usage_tier if plan_code == 'appointments_ai' else plan_code,
        'description': (
            f"{canonical_pricing.get_usage_tier(usage_tier)['name']}"
            if plan_code == 'appointments_ai'
            else canonical_pricing.get_plan(plan_code)['name']
        ),
        'quantity': 1,
        'unit_price': base_amount,
        'total': base_amount,
    }]
    if plan_code != 'appointments_ai' and automations:
        items.append({
            'code': AUTOMATIONS,
            'description': canonical_pricing.get_addon(AUTOMATIONS)['name'],
            'quantity': 1,
            'unit_price': addon_amount,
            'total': addon_amount,
        })
    elif plan_code == 'appointments_ai':
        items.append({
            'code': AUTOMATIONS,
            'description': canonical_pricing.get_addon(AUTOMATIONS)['name'],
            'quantity': 1,
            'unit_price': 0,
            'total': 0,
            'included': True,
        })
    if extra_professionals:
        items.append({
            'code': EXTRA_PROFESSIONAL,
            'description': canonical_pricing.get_extra(EXTRA_PROFESSIONAL)['name'],
            'quantity': extra_professionals,
            'unit_price': extra_unit_price,
            'total': extras_amount,
        })

    subtotal = sum(item['total'] for item in items)
    discount_amount = 0
    total = subtotal - discount_amount
    created_at = timezone.now().isoformat()
    return {
        'service_type': 'appointments',
        'plan_code': plan_code,
        'usage_tier': usage_tier,
        'billing_cycle': billing_cycle,
        'automations': automations_state,
        'extra_professionals': extra_professionals,
        'base_amount': base_amount,
        'addons_amount': addon_amount,
        'extras_amount': extras_amount,
        'discount_amount': discount_amount,
        'total_amount': total,
        'subtotal': subtotal,
        'currency': 'ARS',
        'line_items': items,
        'unit_prices': {
            'base': base_amount,
            AUTOMATIONS: addon_amount if plan_code != 'appointments_ai' else 0,
            EXTRA_PROFESSIONAL: extra_unit_price,
        },
        'quantities': {
            'base': 1,
            AUTOMATIONS: 1 if plan_code == 'appointments_ai' or automations else 0,
            EXTRA_PROFESSIONAL: extra_professionals,
        },
        'catalog_version': canonical_pricing._DATA['version'],
        'quote_version': QUOTE_VERSION,
        'created_at': created_at,
    }


def create_appointments_checkout(
    *,
    user,
    business,
    internal_provisioning: bool = False,
    frontend_url: str | None = None,
    **quote_request,
) -> dict:
    from apps.billing.models import AppointmentsCheckout, SubscriptionV2

    if internal_provisioning is not True and not canonical_pricing.is_plan_product_active(
        quote_request.get('plan_code', ''),
    ):
        raise ValueError('Product is not available for public purchase.')

    quote = quote_appointments(**quote_request)
    metadata = {
        'service_type': 'appointments',
        'plan_code': quote['plan_code'],
        'usage_tier': quote['usage_tier'],
        'billing_cycle': quote['billing_cycle'],
        'automations': quote['automations'],
        'extra_professionals': quote['extra_professionals'],
        'business_id': str(business.pk),
        'quote_version': quote['quote_version'],
        'catalog_version': quote['catalog_version'],
    }
    ref = f"APPT-{uuid.uuid4()}"
    with transaction.atomic():
        locked_business = type(business).objects.select_for_update().get(pk=business.pk)
        existing = (
            AppointmentsCheckout.objects.select_for_update()
            .filter(business=locked_business, status__in=('pending', 'linked'))
            .first()
        )
        if existing:
            if _request_matches_checkout(existing, metadata):
                return _checkout_response(existing, reused=True)
            raise ValueError('Another Turnos checkout is already in progress.')

        current = SubscriptionV2.objects.select_for_update().filter(
            business=locked_business,
            service_type=SubscriptionV2.ServiceType.APPOINTMENTS,
        ).exclude(status=SubscriptionV2.Status.CANCELED).first()
        if current:
            raise ValueError('An existing Turnos subscription must use the lifecycle change flow.')

        checkout = AppointmentsCheckout.objects.create(
            business=locked_business,
            user=user,
            external_reference=ref,
            plan_code=quote['plan_code'],
            usage_tier=quote['usage_tier'],
            billing_cycle=quote['billing_cycle'],
            automations=quote['automations'],
            extra_professional_quantity=quote['extra_professionals'],
            quote_snapshot=quote,
            metadata_json=metadata,
        )
        base = (frontend_url or getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')).rstrip('/')
        back_url = f'{base}/subscribe/return?appointments_checkout_id={checkout.pk}'
        from apps.billing.mp_service import MercadoPagoService

        frequency = 12 if quote['billing_cycle'] == 'yearly' else 1
        response = MercadoPagoService().create_preapproval_plan(
            reason=f"MiRubro Turnos - {quote['line_items'][0]['description']}",
            auto_recurring={
                'frequency': frequency,
                'frequency_type': 'months',
                'transaction_amount': quote['total_amount'],
                'currency_id': quote['currency'],
            },
            back_url=back_url,
            external_reference=ref,
            metadata=metadata,
        )
        plan_id = response.get('id')
        checkout_url = response.get('sandbox_init_point') or response.get('init_point')
        if not plan_id or not checkout_url:
            raise ValueError('Mercado Pago response is missing plan id or checkout URL.')
        checkout.provider_preapproval_plan_id = str(plan_id)
        checkout.provider_checkout_url = checkout_url
        checkout.save(update_fields=[
            'provider_preapproval_plan_id', 'provider_checkout_url', 'updated_at',
        ])
    return _checkout_response(checkout, reused=False)


def _checkout_response(checkout, *, reused: bool) -> dict:
    return {
        'checkout_id': str(checkout.pk),
        'external_reference': checkout.external_reference,
        'init_point': checkout.provider_checkout_url,
        'status': checkout.status,
        'reused': reused,
        'quote': checkout.quote_snapshot,
    }


def _request_matches_checkout(checkout, metadata: dict) -> bool:
    keys = (
        'service_type', 'plan_code', 'usage_tier', 'billing_cycle',
        'automations', 'extra_professionals', 'business_id',
    )
    return all(checkout.metadata_json.get(key) == metadata.get(key) for key in keys)


def validate_appointments_checkout_snapshot(checkout) -> dict:
    snapshot = checkout.quote_snapshot
    metadata = checkout.metadata_json
    for key, expected in (
        ('service_type', 'appointments'),
        ('plan_code', checkout.plan_code),
        ('usage_tier', checkout.usage_tier),
        ('billing_cycle', checkout.billing_cycle),
        ('automations', checkout.automations),
        ('extra_professionals', checkout.extra_professional_quantity),
    ):
        if metadata.get(key) != expected or snapshot.get(key) != expected:
            raise ValueError(f'Appointments checkout snapshot mismatch for {key}.')
    if metadata.get('business_id') != str(checkout.business_id):
        raise ValueError('Appointments checkout snapshot business mismatch.')
    if (
        not isinstance(snapshot.get('line_items'), list)
        or type(snapshot.get('subtotal')) is not int
        or type(snapshot.get('discount_amount')) is not int
        or type(snapshot.get('total_amount')) is not int
        or snapshot.get('currency') != 'ARS'
        or snapshot.get('quote_version') != QUOTE_VERSION
        or snapshot.get('catalog_version') != metadata.get('catalog_version')
        or metadata.get('quote_version') != QUOTE_VERSION
    ):
        raise ValueError('Appointments checkout snapshot is invalid.')
    for item in snapshot['line_items']:
        if (
            not isinstance(item, dict)
            or type(item.get('quantity')) is not int
            or item['quantity'] < 0
            or type(item.get('unit_price')) is not int
            or item['unit_price'] < 0
            or type(item.get('total')) is not int
            or item['total'] != item['quantity'] * item['unit_price']
        ):
            raise ValueError('Appointments checkout line item is invalid.')
    if sum(item['total'] for item in snapshot['line_items']) != snapshot['subtotal']:
        raise ValueError('Appointments checkout line items do not match subtotal.')
    if snapshot['subtotal'] - snapshot['discount_amount'] != snapshot['total_amount']:
        raise ValueError('Appointments checkout total does not match snapshot.')
    if (
        type(snapshot.get('base_amount')) is not int
        or type(snapshot.get('addons_amount')) is not int
        or type(snapshot.get('extras_amount')) is not int
        or snapshot['base_amount'] + snapshot['addons_amount'] + snapshot['extras_amount']
        != snapshot['subtotal']
    ):
        raise ValueError('Appointments checkout components do not match subtotal.')
    return snapshot


def apply_appointments_preapproval(*, preapproval_id: str, plan_id: str, preapproval: dict) -> bool:
    from apps.billing.models import AppointmentsCheckout, SubscriptionV2
    from apps.billing.webhook_lifecycle import WebhookPermanentError

    checkout = AppointmentsCheckout.objects.filter(
        provider_preapproval_plan_id=plan_id,
    ).select_related('business').first()
    if checkout is None:
        return False
    try:
        snapshot = validate_appointments_checkout_snapshot(checkout)
    except ValueError as exc:
        raise WebhookPermanentError('appointments_quote_invalid', str(exc)) from exc
    if preapproval.get('external_reference') != checkout.external_reference:
        raise WebhookPermanentError('appointments_ref_mismatch', 'Preapproval reference mismatch.')
    auto_recurring = preapproval.get('auto_recurring') or {}
    from apps.billing.mp_service import normalize_mp_subscription_status
    canceled = normalize_mp_subscription_status(preapproval.get('status')) == 'canceled'
    if not canceled:
        _validate_provider_amount(
            auto_recurring.get('transaction_amount'),
            auto_recurring.get('currency_id'),
            snapshot,
        )

    with transaction.atomic():
        business = type(checkout.business).objects.select_for_update().get(pk=checkout.business_id)
        checkout = AppointmentsCheckout.objects.select_for_update().get(pk=checkout.pk)
        subscription = SubscriptionV2.objects.select_for_update().filter(
            provider_sub_id=preapproval_id,
        ).first()
        if canceled:
            if subscription and subscription.status == SubscriptionV2.Status.CHECKOUT_PENDING:
                subscription.status = SubscriptionV2.Status.CANCELED
                subscription.canceled_at = timezone.now()
                subscription.save(update_fields=['status', 'canceled_at', 'updated_at'])
            if checkout.status != AppointmentsCheckout.Status.ACTIVE:
                checkout.status = AppointmentsCheckout.Status.FAILED
                checkout.save(update_fields=['status', 'updated_at'])
            return True
        if subscription is None:
            current = SubscriptionV2.objects.select_for_update().filter(
                business=business,
                service_type=SubscriptionV2.ServiceType.APPOINTMENTS,
            ).exclude(status=SubscriptionV2.Status.CANCELED).first()
            if current:
                raise WebhookPermanentError(
                    'appointments_subscription_conflict',
                    'A non-canceled Turnos subscription already exists for this business.',
                )
            subscription = SubscriptionV2.objects.create(
                business=business,
                service_type=SubscriptionV2.ServiceType.APPOINTMENTS,
                plan_code=checkout.plan_code,
                usage_tier=checkout.usage_tier,
                billing_cycle=checkout.billing_cycle,
                provider=SubscriptionV2.Provider.MERCADOPAGO,
                provider_sub_id=preapproval_id,
                provider_preapproval_plan_id=plan_id,
                external_reference=f'SUB-{uuid.uuid4()}',
                status=SubscriptionV2.Status.CHECKOUT_PENDING,
                price_snapshot=snapshot,
                raw_snapshot_json=preapproval,
            )
        elif (
            subscription.business_id != business.pk
            or subscription.service_type != SubscriptionV2.ServiceType.APPOINTMENTS
            or subscription.plan_code != checkout.plan_code
            or subscription.usage_tier != checkout.usage_tier
            or subscription.billing_cycle != checkout.billing_cycle
            or subscription.provider_preapproval_plan_id != plan_id
        ):
            raise WebhookPermanentError(
                'appointments_subscription_mismatch',
                'Existing SubscriptionV2 does not match this checkout.',
            )
        if checkout.status == AppointmentsCheckout.Status.ACTIVE:
            if checkout.subscription_v2_id != subscription.pk:
                raise WebhookPermanentError(
                    'appointments_subscription_mismatch',
                    'Active checkout references a different subscription.',
                )
        else:
            checkout.subscription_v2 = subscription
            checkout.provider_preapproval_id = preapproval_id
            checkout.status = AppointmentsCheckout.Status.LINKED
            checkout.save(update_fields=[
                'subscription_v2', 'provider_preapproval_id', 'status', 'updated_at',
            ])
    return True


def validate_appointments_authorized_payment(*, subscription, payment_data: dict) -> bool:
    from apps.billing.models import AppointmentsCheckout

    checkout = AppointmentsCheckout.objects.filter(subscription_v2=subscription).first()
    if checkout is None:
        return False
    try:
        snapshot = validate_appointments_checkout_snapshot(checkout)
    except ValueError as exc:
        from apps.billing.webhook_lifecycle import WebhookPermanentError

        raise WebhookPermanentError('appointments_quote_invalid', str(exc)) from exc
    _validate_provider_amount(
        payment_data.get('transaction_amount') or payment_data.get('total_paid_amount'),
        payment_data.get('currency_id'),
        snapshot,
    )
    return True


def apply_appointments_authorized_payment(*, subscription, invoice_event, payment_data: dict) -> bool:
    from apps.billing.models import AppointmentsCheckout
    from apps.business.models import SubscriptionAddon
    from apps.billing.webhook_lifecycle import WebhookPermanentError

    if not validate_appointments_authorized_payment(
        subscription=subscription, payment_data=payment_data,
    ):
        return False
    checkout = AppointmentsCheckout.objects.get(subscription_v2=subscription)
    payment_id = str(invoice_event.provider_payment_id or invoice_event.provider_authorized_payment_id)

    with transaction.atomic():
        checkout = AppointmentsCheckout.objects.select_for_update().get(pk=checkout.pk)
        if checkout.status == AppointmentsCheckout.Status.ACTIVE:
            return False
        subscription = type(subscription).objects.select_for_update().get(pk=subscription.pk)
        if (
            subscription.plan_code != checkout.plan_code
            or subscription.usage_tier != checkout.usage_tier
            or subscription.billing_cycle != checkout.billing_cycle
            or subscription.status != type(subscription).Status.ACTIVE
        ):
            raise WebhookPermanentError(
                'appointments_subscription_mismatch',
                'Activated subscription does not match the persisted checkout.',
            )
        SubscriptionAddon.objects.update_or_create(
            subscription_v2=subscription,
            code=EXTRA_PROFESSIONAL,
            defaults={
                'quantity': checkout.extra_professional_quantity,
                'is_active': True,
                'deactivated_at': None,
            },
        )
        if subscription.plan_code == 'appointments_ai' and subscription.usage_tier:
            subscription.usage_tier_effective_from = (
                subscription.usage_tier_effective_from
                or subscription.current_period_start
                or invoice_event.paid_at
                or timezone.now()
            )
            subscription.save(update_fields=['usage_tier_effective_from', 'updated_at'])
        if checkout.automations == 'enabled':
            SubscriptionAddon.objects.update_or_create(
                subscription_v2=subscription,
                code=AUTOMATIONS,
                defaults={'quantity': 1, 'is_active': True, 'deactivated_at': None},
            )
        checkout.provider_payment_id = payment_id
        checkout.status = AppointmentsCheckout.Status.ACTIVE
        checkout.activated_at = invoice_event.paid_at or timezone.now()
        checkout.save(update_fields=[
            'provider_payment_id', 'status', 'activated_at', 'updated_at',
        ])
    return True


def _validate_provider_amount(amount, currency, snapshot: dict) -> None:
    from apps.billing.webhook_lifecycle import WebhookPermanentError

    try:
        actual = Decimal(str(amount))
        expected = Decimal(snapshot['total_amount'])
    except (InvalidOperation, TypeError, KeyError, ValueError) as exc:
        raise WebhookPermanentError(
            'appointments_amount_invalid', 'Provider amount is missing or invalid.',
        ) from exc
    if actual != expected or currency != snapshot['currency']:
        raise WebhookPermanentError(
            'appointments_amount_mismatch',
            'Provider amount/currency does not match the persisted Turnos quote.',
        )


def appointments_period_end(period_start, billing_cycle: str):
    months = 12 if billing_cycle == 'yearly' else 1
    month_index = period_start.month - 1 + months
    year = period_start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(period_start.day, calendar.monthrange(year, month)[1])
    return period_start.replace(year=year, month=month, day=day)
