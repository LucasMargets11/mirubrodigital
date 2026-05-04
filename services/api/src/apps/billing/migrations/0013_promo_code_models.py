# Generated migration: Promotional Codes system
# Adds PromoCode and PromoCodeRedemption models.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0012_update_help_text_pesos'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PromoCode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=64, unique=True)),
                ('name', models.CharField(max_length=128)),
                ('description', models.TextField(blank=True)),
                ('discount_type', models.CharField(
                    max_length=16,
                    choices=[('percent', 'Porcentaje'), ('fixed_amount', 'Monto fijo')],
                )),
                ('discount_value', models.DecimalField(
                    max_digits=10, decimal_places=2,
                    help_text='Percentage (0–100) or fixed ARS amount to subtract.',
                )),
                ('duration_cycles', models.PositiveSmallIntegerField(
                    default=1,
                    help_text='Number of billing cycles the discount applies. Minimum 1.',
                )),
                ('starts_at', models.DateTimeField(null=True, blank=True)),
                ('ends_at', models.DateTimeField(null=True, blank=True)),
                ('max_redemptions', models.PositiveIntegerField(
                    null=True, blank=True,
                    help_text='Global redemption cap. Null = unlimited.',
                )),
                ('max_redemptions_per_business', models.PositiveSmallIntegerField(
                    default=1,
                    help_text='Max times a single business can use this code. Default 1.',
                )),
                ('active', models.BooleanField(default=True)),
                ('applies_to_plan_codes', models.JSONField(
                    default=list,
                    help_text='List of Plan.code values. Must contain at least one entry.',
                )),
                ('applies_to_service', models.CharField(
                    max_length=32, blank=True,
                    help_text="Service slug restriction ('gestion', 'restaurante', …). Empty = any.",
                )),
                ('applies_to_billing_periods', models.JSONField(
                    default=list,
                    help_text="List of billing periods ('monthly', 'yearly'). Empty = any.",
                )),
                ('created_by', models.ForeignKey(
                    to=settings.AUTH_USER_MODEL,
                    on_delete=django.db.models.deletion.SET_NULL,
                    null=True, blank=True,
                    related_name='created_promo_codes',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='PromoCodeRedemption',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('promo_code', models.ForeignKey(
                    to='billing.PromoCode',
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='redemptions',
                )),
                ('business', models.ForeignKey(
                    to='business.Business',
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='promo_redemptions',
                )),
                ('user', models.ForeignKey(
                    to=settings.AUTH_USER_MODEL,
                    on_delete=django.db.models.deletion.SET_NULL,
                    null=True, blank=True,
                    related_name='promo_redemptions',
                )),
                ('subscription', models.ForeignKey(
                    to='billing.SubscriptionV2',
                    on_delete=django.db.models.deletion.SET_NULL,
                    null=True, blank=True,
                    related_name='promo_redemptions',
                )),
                ('checkout_session', models.ForeignKey(
                    to='billing.MpCheckoutSession',
                    on_delete=django.db.models.deletion.SET_NULL,
                    null=True, blank=True,
                    related_name='promo_redemptions',
                )),
                ('original_amount', models.DecimalField(max_digits=12, decimal_places=2)),
                ('discounted_amount', models.DecimalField(max_digits=12, decimal_places=2)),
                ('cycles_total', models.PositiveSmallIntegerField()),
                ('cycles_used', models.PositiveSmallIntegerField(default=0)),
                ('status', models.CharField(
                    max_length=16,
                    choices=[
                        ('pending',   'Pendiente'),
                        ('active',    'Activo'),
                        ('completed', 'Completado'),
                        ('cancelled', 'Cancelado'),
                        ('expired',   'Expirado'),
                    ],
                    default='pending',
                )),
                ('price_restored', models.BooleanField(default=False)),
                ('price_restored_at', models.DateTimeField(null=True, blank=True)),
                ('last_applied_payment_id', models.CharField(max_length=128, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddIndex(
            model_name='promocoderedemption',
            index=models.Index(
                fields=['subscription', 'status'],
                name='pr_sub_status_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='promocoderedemption',
            index=models.Index(
                fields=['business', 'promo_code'],
                name='pr_biz_code_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='promocoderedemption',
            index=models.Index(
                fields=['checkout_session'],
                name='promo_redemption_session_idx',
            ),
        ),
        migrations.AddConstraint(
            model_name='promocoderedemption',
            constraint=models.UniqueConstraint(
                fields=['promo_code', 'business'],
                condition=models.Q(status__in=['pending', 'active']),
                name='uq_pr_active_biz_code',
            ),
        ),
    ]
