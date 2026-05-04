"""
0016 — Seed / fix menu_qr and qr_reviews bundles (May 2026 copy refresh).

Idempotent: safe to run multiple times via update_or_create.

Changes applied:
  menu_qr:
    - menu_qr_online  → is_active=False (legacy)
    - menu_qr_basico  → name='Lite', desc, sort_order=1, cta='Empezar con Lite'
    - menu_qr_visual  → name='Pro',  desc, sort_order=2, badge='Recomendado', cta='Elegir Pro'
    - menu_qr_marca   → name='Premium', desc, sort_order=3, cta='Ir a Premium'
    - menu_qr_empresarial → name='Empresarial', sort_order=4, badge='Contactar',
                            is_custom (price=None), cta='Hablar con MiRubro'

  qr_reviews:
    - qr_reviews      → is_active=False (legacy, code='qr_reviews')
    - qr_reviews_base → name='Reseñas Base', sort_order=1, cta='Activar Reseñas Base'
    - qr_reviews_pro  → name='Reseñas Pro', sort_order=2, badge='Recomendado', cta='Activar Reseñas Pro'
    - qr_reviews_empresarial → sort_order=3, badge='Contactar', cta='Hablar con MiRubro'
"""
from django.db import migrations


MENU_QR_BUNDLES = [
    {
        'code': 'menu_qr_online',
        'defaults': {
            'is_active': False,
            'sort_order': 99,
        },
    },
    {
        'code': 'menu_qr_basico',
        'defaults': {
            'name': 'Lite',
            'description': 'Carta digital básica con branding. Ideal para empezar.',
            'vertical': 'menu_qr',
            'pricing_mode': 'fixed_price',
            'fixed_price_monthly': 18000,
            'fixed_price_yearly': 172800,
            'badge': '',
            'is_default_recommended': False,
            'is_active': True,
            'sort_order': 1,
            'cta_label': 'Empezar con Lite',
        },
    },
    {
        'code': 'menu_qr_visual',
        'defaults': {
            'name': 'Pro',
            'description': 'Imágenes, analítica avanzada y 1 módulo de engagement a elección.',
            'vertical': 'menu_qr',
            'pricing_mode': 'fixed_price',
            'fixed_price_monthly': 30000,
            'fixed_price_yearly': 288000,
            'badge': 'Recomendado',
            'is_default_recommended': True,
            'is_active': True,
            'sort_order': 2,
            'cta_label': 'Elegir Pro',
        },
    },
    {
        'code': 'menu_qr_marca',
        'defaults': {
            'name': 'Premium',
            'description': 'Todo incluido: reseñas, propinas, imágenes, dominio y multi-sucursal.',
            'vertical': 'menu_qr',
            'pricing_mode': 'fixed_price',
            'fixed_price_monthly': 55000,
            'fixed_price_yearly': 528000,
            'badge': '',
            'is_default_recommended': False,
            'is_active': True,
            'sort_order': 3,
            'cta_label': 'Ir a Premium',
        },
    },
    {
        'code': 'menu_qr_empresarial',
        'defaults': {
            'name': 'Empresarial',
            'description': 'Una experiencia digital adaptada a tu marca y operación.',
            'vertical': 'menu_qr',
            'pricing_mode': 'fixed_price',
            'fixed_price_monthly': None,
            'fixed_price_yearly': None,
            'badge': 'Contactar',
            'is_default_recommended': False,
            'is_active': True,
            'sort_order': 4,
            'cta_label': 'Hablar con MiRubro',
        },
    },
]

QR_REVIEWS_BUNDLES = [
    {
        'code': 'qr_reviews',
        'defaults': {
            'is_active': False,
            'sort_order': 99,
        },
    },
    {
        'code': 'qr_reviews_base',
        'defaults': {
            'name': 'Reseñas Base',
            'description': 'Generá reseñas en Google de forma simple.',
            'vertical': 'qr_reviews',
            'pricing_mode': 'fixed_price',
            'fixed_price_monthly': 25000,
            'fixed_price_yearly': 240000,
            'badge': '',
            'is_default_recommended': False,
            'is_active': True,
            'sort_order': 1,
            'cta_label': 'Activar Reseñas Base',
        },
    },
    {
        'code': 'qr_reviews_pro',
        'defaults': {
            'name': 'Reseñas Pro',
            'description': 'Elegí qué llega a Google y qué queda como feedback privado.',
            'vertical': 'qr_reviews',
            'pricing_mode': 'fixed_price',
            'fixed_price_monthly': 40000,
            'fixed_price_yearly': 384000,
            'badge': 'Recomendado',
            'is_default_recommended': True,
            'is_active': True,
            'sort_order': 2,
            'cta_label': 'Activar Reseñas Pro',
        },
    },
    {
        'code': 'qr_reviews_empresarial',
        'defaults': {
            'name': 'Empresarial',
            'description': 'Una propuesta personalizada para escalar tu reputación digital.',
            'vertical': 'qr_reviews',
            'pricing_mode': 'fixed_price',
            'fixed_price_monthly': None,
            'fixed_price_yearly': None,
            'badge': 'Contactar',
            'is_default_recommended': False,
            'is_active': True,
            'sort_order': 3,
            'cta_label': 'Hablar con MiRubro',
        },
    },
]


def seed_bundles(apps, schema_editor):
    Bundle = apps.get_model('billing', 'Bundle')

    for entry in MENU_QR_BUNDLES + QR_REVIEWS_BUNDLES:
        # Only update existing records — don't create bundles that don't exist yet
        # (seed_billing.py is responsible for initial creation).
        # For the data migration we use update_or_create so it is safe on fresh DBs too.
        Bundle.objects.update_or_create(
            code=entry['code'],
            defaults=entry['defaults'],
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0015_bundle_sort_order_cta_label'),
    ]

    operations = [
        migrations.RunPython(seed_bundles, reverse_code=noop),
    ]
