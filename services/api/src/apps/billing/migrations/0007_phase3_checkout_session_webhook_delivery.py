"""
Migration 0007 – Phase 3: Robust subscription flow

New models:
  - MpCheckoutSession   : idempotent checkout/session tracker
  - WebhookDelivery     : immutable webhook audit log
  - BillingInvoiceEvent : authorized-payment events from MP

New fields on existing models:
  - Plan                : currency, frequency, frequency_type, plan_status
  - SubscriptionV2      : checkout_session FK, provider_preapproval_plan_id,
                          is_active, raw_snapshot_json
"""
from __future__ import annotations

import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0006_subscriptionintent_add_v2_fk'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('business', '__first__'),
    ]

    operations = [
        # ── Plan: add V2 catalog fields ────────────────────────────────────────
        migrations.AddField(
            model_name='plan',
            name='currency',
            field=models.CharField(default='ARS', max_length=3),
        ),
        migrations.AddField(
            model_name='plan',
            name='frequency',
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='plan',
            name='frequency_type',
            field=models.CharField(default='months', max_length=16),
        ),
        migrations.AddField(
            model_name='plan',
            name='plan_status',
            field=models.CharField(
                choices=[('active', 'Active'), ('inactive', 'Inactive')],
                default='active',
                max_length=16,
            ),
        ),

        # ── MpCheckoutSession ─────────────────────────────────────────────────
        migrations.CreateModel(
            name='MpCheckoutSession',
            fields=[
                ('id', models.UUIDField(
                    default=uuid.uuid4, editable=False, primary_key=True, serialize=False,
                )),
                ('status', models.CharField(
                    choices=[
                        ('created', 'Creado'),
                        ('checkout_created', 'Checkout Creado'),
                        ('awaiting_webhook', 'Esperando Webhook'),
                        ('linked', 'Vinculado'),
                        ('activated', 'Activado'),
                        ('failed', 'Fallido'),
                        ('expired', 'Expirado'),
                        ('superseded', 'Superado'),
                    ],
                    default='created',
                    max_length=32,
                )),
                ('provider_mode', models.CharField(default='sandbox', max_length=16)),
                ('provider_preapproval_plan_id', models.CharField(
                    blank=True, max_length=128, null=True, unique=True,
                    help_text='MP preapproval_plan ID. Unique. Used to correlate webhook back to this session.',
                )),
                ('provider_checkout_url', models.URLField(blank=True, max_length=500, null=True)),
                ('idempotency_key', models.CharField(max_length=128, unique=True)),
                ('mp_external_reference', models.CharField(blank=True, max_length=128)),
                ('return_url', models.URLField(blank=True, max_length=500)),
                ('expires_at', models.DateTimeField(blank=True, null=True)),
                ('last_seen_at', models.DateTimeField(blank=True, null=True)),
                ('metadata_json', models.JSONField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='checkout_sessions',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('tenant', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='checkout_sessions',
                    to='business.business',
                )),
                ('plan', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='checkout_sessions',
                    to='billing.plan',
                )),
            ],
            options={'indexes': [
                models.Index(fields=['user', 'plan', 'status'], name='checkout_sess_user_plan_idx'),
                models.Index(fields=['provider_preapproval_plan_id'],  name='checkout_sess_plan_id_idx'),
                models.Index(fields=['status', 'expires_at'],          name='checkout_sess_status_exp_idx'),
            ]},
        ),
        migrations.AddConstraint(
            model_name='mpcheckoutsession',
            constraint=models.UniqueConstraint(
                fields=['user', 'plan'],
                condition=models.Q(status__in=['created', 'checkout_created', 'awaiting_webhook', 'linked']),
                name='uq_checkout_session_open_per_user_plan',
            ),
        ),

        # ── WebhookDelivery ───────────────────────────────────────────────────
        migrations.CreateModel(
            name='WebhookDelivery',
            fields=[
                ('id', models.UUIDField(
                    default=uuid.uuid4, editable=False, primary_key=True, serialize=False,
                )),
                ('provider', models.CharField(default='mercadopago', max_length=32)),
                ('topic', models.CharField(blank=True, max_length=128)),
                ('resource_id', models.CharField(blank=True, max_length=128)),
                ('action', models.CharField(blank=True, max_length=64)),
                ('x_request_id', models.CharField(blank=True, max_length=128)),
                ('x_signature', models.TextField(blank=True)),
                ('signature_valid', models.BooleanField(default=False)),
                ('payload_hash', models.CharField(blank=True, max_length=64)),
                ('headers_json', models.JSONField(default=dict)),
                ('body_json', models.JSONField(default=dict)),
                ('processing_status', models.CharField(
                    choices=[
                        ('received', 'Recibido'),
                        ('duplicated', 'Duplicado'),
                        ('ignored', 'Ignorado'),
                        ('processed', 'Procesado'),
                        ('failed', 'Fallido'),
                        ('dead_letter', 'Dead Letter'),
                    ],
                    default='received',
                    max_length=32,
                )),
                ('error_message', models.TextField(blank=True)),
                ('received_at', models.DateTimeField()),
                ('processed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'indexes': [
                models.Index(fields=['topic', 'resource_id'],           name='wh_delivery_topic_res_idx'),
                models.Index(fields=['processing_status', 'received_at'], name='wh_delivery_stat_recv_idx'),
                models.Index(fields=['x_request_id'],                   name='wh_delivery_xreq_idx'),
                models.Index(fields=['payload_hash'],                   name='wh_delivery_hash_idx'),
            ]},
        ),

        # ── BillingInvoiceEvent ───────────────────────────────────────────────
        migrations.CreateModel(
            name='BillingInvoiceEvent',
            fields=[
                ('id', models.UUIDField(
                    default=uuid.uuid4, editable=False, primary_key=True, serialize=False,
                )),
                ('provider_authorized_payment_id', models.CharField(
                    max_length=128, unique=True,
                    help_text='MP authorized_payment ID. Idempotency key for recurring charges.',
                )),
                ('provider_payment_id', models.CharField(blank=True, max_length=128)),
                ('provider_subscription_id', models.CharField(blank=True, max_length=128)),
                ('amount', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('currency', models.CharField(default='ARS', max_length=3)),
                ('provider_status', models.CharField(blank=True, max_length=32)),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                ('raw_payload_json', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('subscription', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='invoice_events',
                    to='billing.subscriptionv2',
                )),
                ('checkout_session', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='invoice_events',
                    to='billing.mpcheckoutsession',
                )),
                ('webhook_delivery', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='invoice_events',
                    to='billing.webhookdelivery',
                )),
            ],
            options={'indexes': [
                models.Index(fields=['provider_subscription_id'], name='billinginv_sub_id_idx'),
                models.Index(fields=['provider_status', 'created_at'], name='billinginv_stat_created_idx'),
            ]},
        ),

        # ── SubscriptionV2: Phase 3 fields ────────────────────────────────────
        migrations.AddField(
            model_name='subscriptionv2',
            name='checkout_session',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='subscriptions',
                to='billing.mpcheckoutsession',
            ),
        ),
        migrations.AddField(
            model_name='subscriptionv2',
            name='provider_preapproval_plan_id',
            field=models.CharField(
                blank=True, max_length=128, null=True,
                help_text='MP preapproval_plan ID (plan template). Denorm from checkout_session.',
            ),
        ),
        migrations.AddField(
            model_name='subscriptionv2',
            name='is_active',
            field=models.BooleanField(
                default=False,
                help_text='True when the first authorized payment has been confirmed.',
            ),
        ),
        migrations.AddField(
            model_name='subscriptionv2',
            name='raw_snapshot_json',
            field=models.JSONField(blank=True, null=True),
        ),
    ]
