# Phase 2A – Create SubscriptionV2, BillingEvent, PaymentAttempt
#
# SubscriptionV2: canonical subscription model (FK to Business, full state machine).
#                 Coexists with legacy billing.Subscription and business.Subscription.
# BillingEvent:   immutable event log. provider_event_id is idempotency key (UNIQUE).
# PaymentAttempt: individual charge attempt record per SubscriptionV2.
#
# All new tables – fully additive, zero impact on existing models.
# RISK: provider_sub_id unique=True on SubscriptionV2 – safe since table is empty at creation.

import uuid

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0004_pendingsubscriptionchange'),
        # Business FK: needs business app at any state with Business table
        ('business', '0015_phase2a_business_extend'),
    ]

    operations = [
        # ── SubscriptionV2 ────────────────────────────────────────────────────
        migrations.CreateModel(
            name='SubscriptionV2',
            fields=[
                ('id', models.UUIDField(
                    primary_key=True, default=uuid.uuid4, editable=False, serialize=False,
                )),
                ('business', models.ForeignKey(
                    to='business.Business',
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='subscriptions_v2',
                )),
                ('service_type', models.CharField(
                    max_length=32,
                    choices=[
                        ('gestion',       'Gestión Comercial'),
                        ('restaurante',   'Restaurantes'),
                        ('menu_qr',       'Menú QR'),
                        ('menu_qr_visual','Menú QR Visual'),
                        ('menu_qr_marca', 'Menú QR Marca'),
                    ],
                )),
                ('plan_code', models.CharField(max_length=64)),
                ('provider', models.CharField(
                    max_length=20,
                    default='mercadopago',
                    choices=[
                        ('mercadopago', 'Mercado Pago'),
                        ('stripe',      'Stripe'),
                        ('manual',      'Manual'),
                    ],
                )),
                # Sparse unique: unique=True on nullable CharField → PG allows multiple NULLs
                ('provider_sub_id',    models.CharField(max_length=128, null=True, blank=True, unique=True)),
                ('external_reference', models.CharField(max_length=64, unique=True)),
                ('status', models.CharField(
                    max_length=20,
                    default='checkout_pending',
                    choices=[
                        ('checkout_pending', 'Checkout Pendiente'),
                        ('trialing',         'En Trial'),
                        ('active',           'Activo'),
                        ('past_due',         'Pago Vencido'),
                        ('suspended',        'Suspendido'),
                        ('canceled',         'Cancelado'),
                    ],
                )),
                ('trial_starts_at',      models.DateTimeField(null=True, blank=True)),
                ('trial_ends_at',        models.DateTimeField(null=True, blank=True)),
                ('current_period_start', models.DateTimeField(null=True, blank=True)),
                ('current_period_end',   models.DateTimeField(null=True, blank=True)),
                ('grace_until',          models.DateTimeField(null=True, blank=True)),
                ('retry_count',          models.SmallIntegerField(default=0)),
                ('cancel_at_period_end', models.BooleanField(default=False)),
                ('canceled_at',          models.DateTimeField(null=True, blank=True)),
                ('price_snapshot',       models.JSONField(default=dict)),
                ('created_at',           models.DateTimeField(auto_now_add=True)),
                ('updated_at',           models.DateTimeField(auto_now=True)),
            ],
            options={
                'indexes': [
                    models.Index(
                        fields=['business', 'status'],
                        name='subv2_business_status_idx',
                    ),
                    models.Index(
                        fields=['current_period_end', 'status'],
                        name='subv2_period_end_status_idx',
                    ),
                ],
                'constraints': [
                    # One active (non-canceled) subscription per business+service_type.
                    # Multiple canceled rows allowed (history).
                    models.UniqueConstraint(
                        fields=['business', 'service_type'],
                        condition=~Q(status='canceled'),
                        name='uq_subscriptionv2_active_per_service',
                    ),
                ],
            },
        ),

        # ── BillingEvent ──────────────────────────────────────────────────────
        migrations.CreateModel(
            name='BillingEvent',
            fields=[
                ('id', models.UUIDField(
                    primary_key=True, default=uuid.uuid4, editable=False, serialize=False,
                )),
                # Nullable: event may arrive before subscription is resolved (race condition)
                ('subscription', models.ForeignKey(
                    to='billing.SubscriptionV2',
                    on_delete=django.db.models.deletion.SET_NULL,
                    null=True, blank=True,
                    related_name='billing_events',
                )),
                ('business', models.ForeignKey(
                    to='business.Business',
                    on_delete=django.db.models.deletion.SET_NULL,
                    null=True, blank=True,
                    related_name='billing_events',
                )),
                ('provider', models.CharField(
                    max_length=20,
                    choices=[
                        ('mercadopago', 'Mercado Pago'),
                        ('stripe',      'Stripe'),
                        ('manual',      'Manual'),
                    ],
                )),
                # IDEMPOTENCY KEY: duplicate webhooks from MP are rejected at DB level.
                ('provider_event_id', models.CharField(max_length=128, unique=True)),
                ('event_type', models.CharField(
                    max_length=32,
                    default='unknown',
                    choices=[
                        ('subscription_created',   'Subscription Created'),
                        ('payment_approved',       'Payment Approved'),
                        ('payment_rejected',       'Payment Rejected'),
                        ('subscription_cancelled', 'Subscription Cancelled'),
                        ('preapproval_updated',    'Preapproval Updated'),
                        ('reconciliation_check',   'Reconciliation Check'),
                        ('unknown',                'Unknown'),
                    ],
                )),
                ('payload',    models.JSONField()),
                ('status', models.CharField(
                    max_length=16,
                    default='received',
                    choices=[
                        ('received',   'Recibido'),
                        ('processing', 'Procesando'),
                        ('processed',  'Procesado'),
                        ('ignored',    'Ignorado'),
                        ('error',      'Error'),
                    ],
                )),
                ('received_at',   models.DateTimeField()),
                ('processed_at',  models.DateTimeField(null=True, blank=True)),
                ('error_message', models.TextField(blank=True, default='')),
            ],
            options={
                'indexes': [
                    models.Index(
                        fields=['subscription', 'received_at'],
                        name='billingevent_sub_received_idx',
                    ),
                    models.Index(
                        fields=['status', 'received_at'],
                        name='bill_evt_stat_recv_idx',
                    ),
                ],
            },
        ),

        # ── PaymentAttempt ────────────────────────────────────────────────────
        migrations.CreateModel(
            name='PaymentAttempt',
            fields=[
                ('id', models.UUIDField(
                    primary_key=True, default=uuid.uuid4, editable=False, serialize=False,
                )),
                ('subscription', models.ForeignKey(
                    to='billing.SubscriptionV2',
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='payment_attempts',
                )),
                ('billing_event', models.ForeignKey(
                    to='billing.BillingEvent',
                    on_delete=django.db.models.deletion.SET_NULL,
                    null=True, blank=True,
                    related_name='payment_attempts',
                )),
                ('provider', models.CharField(
                    max_length=20,
                    choices=[
                        ('mercadopago', 'Mercado Pago'),
                        ('stripe',      'Stripe'),
                        ('manual',      'Manual'),
                    ],
                )),
                # Sparse unique: NULL for pending attempts; unique once provider assigns an ID
                ('external_payment_id', models.CharField(
                    max_length=128, null=True, blank=True, unique=True,
                )),
                ('external_reference', models.CharField(max_length=64, unique=True)),
                ('amount',   models.DecimalField(max_digits=12, decimal_places=2)),
                ('currency', models.CharField(max_length=3, default='ARS')),
                ('status', models.CharField(
                    max_length=16,
                    default='pending',
                    choices=[
                        ('pending',    'Pendiente'),
                        ('processing', 'Procesando'),
                        ('approved',   'Aprobado'),
                        ('rejected',   'Rechazado'),
                        ('refunded',   'Reembolsado'),
                        ('chargeback', 'Contracargo'),
                    ],
                )),
                ('failure_reason', models.CharField(max_length=256, blank=True)),
                ('attempt_at',  models.DateTimeField()),
                ('resolved_at', models.DateTimeField(null=True, blank=True)),
                ('metadata',    models.JSONField(null=True, blank=True)),
                ('created_at',  models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'indexes': [
                    models.Index(
                        fields=['subscription', 'attempt_at'],
                        name='payattempt_sub_attempt_idx',
                    ),
                    models.Index(
                        fields=['status'],
                        name='payattempt_status_idx',
                    ),
                ],
            },
        ),
    ]
