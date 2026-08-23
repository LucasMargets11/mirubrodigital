from decimal import Decimal

from django.db import migrations


QR_REVIEWS_UPDATES = [
    ('qr_reviews_base', 'monthly', Decimal('15000.00'), 1, 'months', 'ARS'),
    ('qr_reviews_pro', 'monthly', Decimal('20000.00'), 1, 'months', 'ARS'),
]


def update_qr_reviews_prices(apps, schema_editor):
    Plan = apps.get_model('billing', 'Plan')
    for code, interval, price, frequency, frequency_type, currency in QR_REVIEWS_UPDATES:
        plans = Plan.objects.filter(code=code)
        for plan in plans:
            plan.price = price
            plan.interval = interval
            plan.frequency = frequency
            plan.frequency_type = frequency_type
            plan.currency = currency
            plan.save(update_fields=['price', 'interval', 'frequency', 'frequency_type', 'currency'])


def reverse_qr_reviews_prices(apps, schema_editor):
    Plan = apps.get_model('billing', 'Plan')
    for code, interval, price, frequency, frequency_type, currency in QR_REVIEWS_UPDATES:
        plans = Plan.objects.filter(code=code)
        for plan in plans:
            if code == 'qr_reviews_base':
                plan.price = Decimal('20000.00')
            elif code == 'qr_reviews_pro':
                plan.price = Decimal('28000.00')
            plan.interval = interval
            plan.frequency = frequency
            plan.frequency_type = frequency_type
            plan.currency = currency
            plan.save(update_fields=['price', 'interval', 'frequency', 'frequency_type', 'currency'])


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0018_subscriptionv2_manual_grant_reason_and_more'),
    ]

    operations = [
        migrations.RunPython(update_qr_reviews_prices, reverse_qr_reviews_prices),
    ]
