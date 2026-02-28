from __future__ import annotations

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('business', '0001_initial'),
        ('menu', '0005_menuitem_image'),
    ]

    operations = [
        # MenuEngagementSettings
        migrations.CreateModel(
            name='MenuEngagementSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tips_enabled', models.BooleanField(default=False)),
                (
                    'tips_mode',
                    models.CharField(
                        choices=[
                            ('mp_link', 'MP Link (Fase 1)'),
                            ('mp_qr_image', 'MP QR Image (Fase 1)'),
                            ('mp_oauth_checkout', 'MP OAuth Checkout (Fase 2)'),
                        ],
                        default='mp_link',
                        max_length=20,
                    ),
                ),
                ('mp_tip_url', models.URLField(blank=True, help_text='Link de Mercado Pago para propinas (Fase 1)', null=True)),
                (
                    'mp_qr_image',
                    models.ImageField(
                        blank=True,
                        help_text='Imagen QR de Mercado Pago (Fase 1)',
                        null=True,
                        upload_to='menu/tips/qr/',
                    ),
                ),
                ('reviews_enabled', models.BooleanField(default=False)),
                ('google_place_id', models.CharField(blank=True, max_length=255, null=True)),
                (
                    'google_review_url',
                    models.URLField(
                        blank=True,
                        help_text='URL directa de reseña de Google (fallback si no hay place_id)',
                        null=True,
                    ),
                ),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'business',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='menu_engagement_settings',
                        to='business.business',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Menu Engagement Settings',
                'verbose_name_plural': 'Menu Engagement Settings',
            },
        ),
        # MercadoPagoConnection (Fase 2)
        migrations.CreateModel(
            name='MercadoPagoConnection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('access_token', models.CharField(max_length=512)),
                ('refresh_token', models.CharField(blank=True, max_length=512)),
                ('token_expires_at', models.DateTimeField(blank=True, null=True)),
                ('mp_user_id', models.CharField(blank=True, max_length=128)),
                ('scope', models.CharField(blank=True, max_length=255)),
                (
                    'status',
                    models.CharField(
                        choices=[
                            ('connected', 'Connected'),
                            ('expired', 'Expired'),
                            ('revoked', 'Revoked'),
                            ('error', 'Error'),
                        ],
                        default='connected',
                        max_length=16,
                    ),
                ),
                ('last_error', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'business',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='mp_connection',
                        to='business.business',
                    ),
                ),
            ],
        ),
        # TipTransaction (Fase 2)
        migrations.CreateModel(
            name='TipTransaction',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('currency', models.CharField(default='ARS', max_length=8)),
                (
                    'status',
                    models.CharField(
                        choices=[
                            ('created', 'Created'),
                            ('pending', 'Pending'),
                            ('approved', 'Approved'),
                            ('rejected', 'Rejected'),
                            ('cancelled', 'Cancelled'),
                        ],
                        default='created',
                        max_length=16,
                    ),
                ),
                ('provider', models.CharField(default='mercadopago', max_length=32)),
                ('mp_preference_id', models.CharField(blank=True, max_length=128, null=True)),
                ('mp_payment_id', models.CharField(blank=True, max_length=128, null=True)),
                ('external_reference', models.CharField(max_length=64, unique=True)),
                ('menu_slug', models.CharField(blank=True, max_length=50)),
                ('table_ref', models.CharField(blank=True, max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'business',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='tip_transactions',
                        to='business.business',
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name='tiptransaction',
            index=models.Index(fields=['business', 'created_at'], name='menu_tiptra_busines_idx'),
        ),
        migrations.AddIndex(
            model_name='tiptransaction',
            index=models.Index(fields=['status'], name='menu_tiptra_status_idx'),
        ),
        migrations.AddIndex(
            model_name='tiptransaction',
            index=models.Index(fields=['external_reference'], name='menu_tiptra_ext_ref_idx'),
        ),
    ]
