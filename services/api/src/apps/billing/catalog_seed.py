"""Shared seeding of internal, non-purchasable tier-priced Plan rows.

A tier-priced plan (Turnos IA, Recepcionista IA) has no fixed amount: its
prices live in the canonical usage tiers. Its Plan row exists only so platform
admins can grant it as complimentary access; it stays inactive, so no checkout
(all of them require plan_status='active') can sell it. An existing row keeps
its price; a new one is created with 0 instead of inventing one.
"""
from __future__ import annotations

from decimal import Decimal

from apps.billing.models import Plan


def upsert_internal_tier_plan(offer: dict, *, vertical: str, features: dict) -> Plan:
    defaults = {
        'name': offer['name'],
        'interval': 'monthly',
        'currency': 'ARS',
        'frequency': 1,
        'frequency_type': 'months',
        'plan_status': 'inactive',
        'features_json': {
            'vertical': vertical,
            'pricing_mode': 'usage_tier',
            'usage_tiers': list(offer['usage_tiers']),
            **features,
        },
    }
    plan, created = Plan.objects.get_or_create(
        code=offer['code'],
        defaults={**defaults, 'price': Decimal('0')},
    )
    if not created:
        for field, value in defaults.items():
            setattr(plan, field, value)
        plan.save(update_fields=list(defaults))
    return plan
