# Generated manually on 2026-02-27 — QR Menu Lite/Pro/Premium plans + pro_included_module

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('business', '0013_alter_business_default_service_and_more'),
    ]

    operations = [
        # ── 1. Expand plan choices to include new QR plans ──────────────────
        migrations.AlterField(
            model_name='subscription',
            name='plan',
            field=models.CharField(
                choices=[
                    ('start', 'Start'),
                    ('pro', 'Pro'),
                    ('business', 'Business'),
                    ('enterprise', 'Enterprise'),
                    ('menu_qr', 'Menú QR'),
                    ('menu_qr_visual', 'Menú QR Visual'),
                    ('menu_qr_marca', 'Menú QR Marca'),
                    # New plans
                    ('menu_qr_lite', 'Menú QR Lite'),
                    ('menu_qr_pro', 'Menú QR Pro'),
                    ('menu_qr_premium', 'Menú QR Premium'),
                    # Legacy
                    ('starter', 'Starter (Legacy)'),
                    ('plus', 'Plus (Legacy)'),
                ],
                default='start',
                max_length=32,
            ),
        ),

        # ── 2. Add pro_included_module to Subscription ───────────────────────
        migrations.AddField(
            model_name='subscription',
            name='pro_included_module',
            field=models.CharField(
                blank=True,
                choices=[
                    ('reviews', 'Reseñas de Google'),
                    ('tips', 'Propina (Mercado Pago)'),
                ],
                help_text='Solo para plan menu_qr_pro: módulo incluido en el precio base (reviews|tips)',
                max_length=16,
                null=True,
            ),
        ),

        # ── 3. Expand SubscriptionAddon code choices ─────────────────────────
        migrations.AlterField(
            model_name='subscriptionaddon',
            name='code',
            field=models.CharField(
                choices=[
                    ('extra_branch', 'Sucursal Extra'),
                    ('extra_seat', 'Usuario Extra'),
                    ('invoices_module', 'Módulo de Facturación'),
                    ('menu_qr_addon_reviews', 'Módulo Reseñas (Menú QR)'),
                    ('menu_qr_addon_tips', 'Módulo Propina (Menú QR)'),
                ],
                max_length=64,
            ),
        ),
    ]
