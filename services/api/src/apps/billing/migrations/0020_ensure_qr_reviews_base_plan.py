"""
0020_ensure_qr_reviews_base_plan
=================================
Data migration: ensure the qr_reviews_base Plan record exists.

This guarantees that a fresh database has the canonical Base plan after
`manage.py migrate`, without requiring a manual `seed_billing` run.
"""

from decimal import Decimal

from django.db import migrations


def ensure_qr_reviews_base_plan(apps, schema_editor):
    Plan = apps.get_model('billing', 'Plan')
    Plan.objects.update_or_create(
        code='qr_reviews_base',
        defaults={
            'name': 'Reseñas Base',
            'price': Decimal('15000.00'),
            'interval': 'monthly',
            'currency': 'ARS',
            'frequency': 1,
            'frequency_type': 'months',
            'plan_status': 'active',
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0019_update_qr_reviews_prices'),
    ]

    operations = [
        migrations.RunPython(ensure_qr_reviews_base_plan, migrations.RunPython.noop),
    ]
