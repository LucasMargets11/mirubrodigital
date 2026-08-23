from django.db import migrations


def align_qr_reviews_bundle_monthly_prices(apps, schema_editor):
    Bundle = apps.get_model('billing', 'Bundle')
    
    Bundle.objects.update_or_create(
        code='qr_reviews_base',
        defaults={
            'name': 'Reseñas Base',
            'description': 'Generá reseñas en Google de forma simple.',
            'vertical': 'qr_reviews',
            'pricing_mode': 'fixed_price',
            'fixed_price_monthly': 15000,
            'fixed_price_yearly': 192000,
            'is_default_recommended': False,
            'is_active': True,
            'badge': '',
            'sort_order': 1,
            'cta_label': 'Activar Reseñas Base',
        },
    )
    
    Bundle.objects.update_or_create(
        code='qr_reviews_pro',
        defaults={
            'name': 'Reseñas Pro',
            'description': 'Elegí qué llega a Google y qué queda como feedback privado.',
            'vertical': 'qr_reviews',
            'pricing_mode': 'fixed_price',
            'fixed_price_monthly': 20000,
            'fixed_price_yearly': 268800,
            'is_default_recommended': True,
            'is_active': True,
            'badge': 'Recomendado',
            'sort_order': 2,
            'cta_label': 'Activar Reseñas Pro',
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0020_ensure_qr_reviews_base_plan'),
    ]

    operations = [
        migrations.RunPython(align_qr_reviews_bundle_monthly_prices, migrations.RunPython.noop),
    ]
