from django.core.management.base import BaseCommand
from django.db import transaction

from apps.billing.canonical_pricing import get_appointments_catalog, price_to_decimal
from apps.billing.models import Bundle, Module, Plan


class Command(BaseCommand):
    help = 'Prepare only the unpublished Turnos catalog. No subscriptions or legacy changes.'

    @transaction.atomic
    def handle(self, *args, **options):
        catalog = get_appointments_catalog()
        addon = catalog['addons'][0]
        automations, _ = Module.objects.update_or_create(
            code=addon['code'],
            defaults={
                'name': addon['name'],
                'description': addon['description'],
                'category': 'operation',
                'vertical': 'appointments',
                'price_monthly': addon['price_monthly'],
                'price_yearly': addon['price_yearly'],
                'is_core': False,
                'is_active': False,
            },
        )
        for order, offer in enumerate(catalog['plans'], start=1):
            bundle, _ = Bundle.objects.update_or_create(
                code=offer['code'],
                defaults={
                    'name': offer['name'],
                    'vertical': 'appointments',
                    'pricing_mode': 'fixed_price',
                    'fixed_price_monthly': offer['price_monthly'],
                    'fixed_price_yearly': offer['price_yearly'],
                    'is_active': False,
                    'is_default_recommended': False,
                    'sort_order': order,
                },
            )
            bundle.modules.set(
                [automations] if addon['code'] in offer.get('included_addons', []) else []
            )
            # Plan.price is mandatory: a tier-priced IA plan cannot be represented
            # here without inventing a fixed checkout amount.
            if offer.get('pricing_mode') == 'usage_tier':
                Plan.objects.filter(code=offer['code']).update(plan_status='inactive')
                continue
            Plan.objects.update_or_create(
                code=offer['code'],
                defaults={
                    'name': offer['name'],
                    'price': price_to_decimal(offer['price_monthly']),
                    'interval': 'monthly',
                    'currency': 'ARS',
                    'frequency': 1,
                    'frequency_type': 'months',
                    'plan_status': 'inactive',
                    'features_json': {
                        'vertical': 'appointments',
                        'professionals_included': offer['professionals_included'],
                        'secondary_users_included': offer['secondary_users_included'],
                    },
                },
            )
        self.stdout.write(self.style.SUCCESS('Turnos catalog prepared (inactive, not for sale).'))
