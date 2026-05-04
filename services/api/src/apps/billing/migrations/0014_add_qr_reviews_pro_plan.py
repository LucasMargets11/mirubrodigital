"""
0014_add_qr_reviews_pro_plan
============================
Data migration: upsert the qr_reviews_pro Plan record.

The plan already exists in generated/pricing.json (price_monthly=40000).
This migration ensures it is present in the billing_plan table on any
existing database without requiring a manual `manage.py seed_billing` run.
"""
from decimal import Decimal

from django.db import migrations


def add_qr_reviews_pro_plan(apps, schema_editor):
    Plan = apps.get_model('billing', 'Plan')
    Plan.objects.update_or_create(
        code='qr_reviews_pro',
        defaults={
            'name': 'Reseñas Pro',
            'price': Decimal('40000.00'),
            'interval': 'monthly',
            'currency': 'ARS',
            'frequency': 1,
            'frequency_type': 'months',
            'plan_status': 'active',
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0013_promo_code_models'),
    ]

    operations = [
        migrations.RunPython(add_qr_reviews_pro_plan, migrations.RunPython.noop),
    ]
