from django.core.management.base import BaseCommand
from django.db import transaction

from apps.billing.canonical_pricing import get_reception_catalog
from apps.billing.catalog_seed import upsert_internal_tier_plan


class Command(BaseCommand):
    help = 'Prepare only the unpublished Recepcionista IA catalog. No subscriptions, no sale.'

    @transaction.atomic
    def handle(self, *args, **options):
        catalog = get_reception_catalog()
        for offer in catalog['plans']:
            # Inactive, price 0: not sellable and, while its tiers stay
            # contact_sales without allowances, not provisionable either.
            upsert_internal_tier_plan(offer, vertical='reception', features={
                'secondary_users_included': offer['secondary_users_included'],
            })
        self.stdout.write(self.style.SUCCESS('Recepcionista IA catalog prepared (inactive, not for sale).'))
