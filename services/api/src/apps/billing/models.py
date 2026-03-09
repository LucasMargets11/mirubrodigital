from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
import hashlib
import uuid

from apps.business.models import Business


class Plan(models.Model):
    """
    Catalog/billing plan definition.
    Represents an *internal* commercial plan (START, PRO, BUSINESS, etc.).
    Distinct from the ephemeral MP preapproval plan created per checkout session.
    """
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    # Legacy field: kept for backward compat. New flows use MpCheckoutSession.
    interval = models.CharField(max_length=32)  # monthly, yearly
    features_json = models.JSONField(default=dict)
    # Legacy field: kept for backward compat.
    mp_preapproval_plan_id = models.CharField(max_length=128, null=True, blank=True)
    # V2 fields ──────────────────────────────────────────────────────────────
    currency = models.CharField(max_length=3, default='ARS')
    frequency = models.PositiveSmallIntegerField(default=1)
    frequency_type = models.CharField(max_length=16, default='months')  # months / days
    plan_status = models.CharField(
        max_length=16,
        choices=[('active', 'Active'), ('inactive', 'Inactive')],
        default='active',
    )

    def __str__(self):
        return f"{self.name} ({self.code})"

class SubscriptionIntent(models.Model):
    STATUS_CHOICES = [
        ('created', 'Created'),
        ('redirected', 'Redirected'),
        ('confirmed', 'Confirmed'),
        ('failed', 'Failed'),
    ]
    tenant = models.ForeignKey(Business, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    plan_code = models.CharField(max_length=64)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='created')
    mp_init_point = models.URLField(max_length=500, null=True, blank=True)
    mp_preapproval_id = models.CharField(max_length=128, null=True, blank=True)
    # Phase 2B: FK to the SubscriptionV2 created at the same time as this intent.
    # Enables direct traceability without heuristic lookups.
    subscription_v2 = models.ForeignKey(
        'SubscriptionV2',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='intents',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

class PaymentEvent(models.Model):
    provider = models.CharField(max_length=32)
    event_id = models.CharField(max_length=128, unique=True)
    resource_id = models.CharField(max_length=128)
    payload_json = models.JSONField()
    processed_at = models.DateTimeField(auto_now_add=True)


class Module(models.Model):
    VERTICAL_CHOICES = [
        ('commercial', 'Commercial'),
        ('restaurant', 'Restaurant'),
        ('both', 'Both'),
        ('menu_qr', 'Menu QR'),
    ]
    CATEGORY_CHOICES = [
        ('operation', 'Operation'),
        ('admin', 'Admin'),
        ('insights', 'Insights'),
    ]

    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES)
    vertical = models.CharField(max_length=32, choices=VERTICAL_CHOICES)
    
    price_monthly = models.IntegerField(help_text="Price in cents")
    price_yearly = models.IntegerField(help_text="Price in cents", null=True, blank=True)
    
    is_core = models.BooleanField(default=False)
    requires = models.ManyToManyField('self', blank=True, symmetrical=False)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.code})"

class Bundle(models.Model):
    VERTICAL_CHOICES = [
        ('commercial', 'Commercial'),
        ('restaurant', 'Restaurant'),
        ('menu_qr', 'Menu QR'),
    ]
    PRICING_MODE_CHOICES = [
        ('fixed_price', 'Fixed Price'),
        ('discount_percent', 'Discount Percent'),
    ]

    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    vertical = models.CharField(max_length=32, choices=VERTICAL_CHOICES)
    badge = models.CharField(max_length=64, blank=True, null=True)
    
    modules = models.ManyToManyField(Module, related_name='bundles')
    
    pricing_mode = models.CharField(max_length=32, choices=PRICING_MODE_CHOICES)
    fixed_price_monthly = models.IntegerField(null=True, blank=True, help_text="Override price in cents")
    fixed_price_yearly = models.IntegerField(null=True, blank=True, help_text="Override price in cents")
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    is_default_recommended = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class Promotion(models.Model):
    TARGET_TYPE_CHOICES = [
        ('bundle', 'Bundle'),
        ('module', 'Module'),
    ]

    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    applies_to = models.CharField(max_length=32, choices=TARGET_TYPE_CHOICES)
    
    # We use FKs for integrity, serializer can handle code logic
    target_bundle = models.ForeignKey(Bundle, null=True, blank=True, on_delete=models.CASCADE)
    target_module = models.ForeignKey(Module, null=True, blank=True, on_delete=models.CASCADE)
    
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    fixed_override_price = models.IntegerField(null=True, blank=True)
    
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def is_valid(self):
        now = timezone.now()
        if not self.is_active:
            return False
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return True

class Subscription(models.Model):
    PLAN_TYPE_CHOICES = [
        ('bundle', 'Bundle'),
        ('custom', 'Custom'),
    ]
    BILLING_PERIOD_CHOICES = [
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('trial', 'Trial'),
        ('past_due', 'Past Due'),
        ('canceled', 'Canceled'),
    ]

    business = models.OneToOneField(Business, related_name='billing_subscription', on_delete=models.CASCADE)
    
    plan_type = models.CharField(max_length=32, choices=PLAN_TYPE_CHOICES)
    bundle = models.ForeignKey(Bundle, null=True, blank=True, on_delete=models.SET_NULL)
    selected_modules = models.ManyToManyField(Module, blank=True)
    
    billing_period = models.CharField(max_length=32, choices=BILLING_PERIOD_CHOICES)
    currency = models.CharField(max_length=3, default='ARS')
    
    price_snapshot = models.JSONField(default=dict, help_text="Snapshot of pricing at the time of subscription")
    
    plan = models.ForeignKey(Plan, null=True, blank=True, on_delete=models.SET_NULL)
    mp_preapproval_id = models.CharField(max_length=128, null=True, blank=True)
    next_billing_date = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)

    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='active')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.business} - {self.plan_type}"


class PendingSubscriptionChange(models.Model):
    """
    Tracks subscription changes awaiting payment or scheduled for later.
    For Gestión Comercial plan changes, upgrades, and add-on modifications.
    """
    STATUS_CHOICES = [
        ('pending_payment', 'Pending Payment'),
        ('scheduled', 'Scheduled'),  # Downgrades scheduled for next cycle
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('canceled', 'Canceled'),
    ]
    
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='pending_subscription_changes')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    
    # Target configuration
    target_plan_code = models.CharField(max_length=32)
    billing_cycle = models.CharField(max_length=16)  # monthly or yearly
    config_snapshot = models.JSONField(default=dict, help_text="Full configuration: crm, invoicing, branches_extra_qty, seats_extra_qty")
    
    # Pricing snapshot
    line_items = models.JSONField(default=list, help_text="List of line items with description, quantity, unit_price, total")
    total_amount = models.IntegerField(help_text="Total amount in centavos")
    
    # Payment tracking
    requires_checkout = models.BooleanField(default=False)
    mp_preference_id = models.CharField(max_length=128, null=True, blank=True)
    mp_init_point = models.URLField(max_length=500, null=True, blank=True)
    mp_payment_id = models.CharField(max_length=128, null=True, blank=True)
    
    # Status and metadata
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='pending_payment')
    is_upgrade = models.BooleanField(default=False)
    is_downgrade = models.BooleanField(default=False)
    
    # Scheduling
    scheduled_for = models.DateTimeField(null=True, blank=True, help_text="When to apply the change (downgrades)")
    applied_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.business.name} - {self.target_plan_code} ({self.status})"

# ── Phase 2A: SubscriptionV2 ──────────────────────────────────────────────────
#
# Canonical subscription model per Phase 1 v2.0 design.
# Coexists with legacy `billing.Subscription` and `business.Subscription` during transition.
# Key differences from legacy:
#   - FK to Business (not OneToOneField), enabling subscription history.
#   - Full state machine: CHECKOUT_PENDING → TRIALING → ACTIVE → PAST_DUE → SUSPENDED → CANCELED
#   - grace_until, retry_count, cancel_at_period_end for robust billing flow.
#   - external_reference for idempotent Mercado Pago integration.
# Will be renamed to `Subscription` in Phase 2C after legacy models are migrated and dropped.
#
class SubscriptionV2(models.Model):

    class ServiceType(models.TextChoices):
        GESTION       = 'gestion',       'Gestión Comercial'
        RESTAURANTE   = 'restaurante',   'Restaurantes'
        MENU_QR       = 'menu_qr',       'Menú QR'
        MENU_QR_VISUAL = 'menu_qr_visual', 'Menú QR Visual'
        MENU_QR_MARCA  = 'menu_qr_marca',  'Menú QR Marca'

    class Provider(models.TextChoices):
        MERCADOPAGO = 'mercadopago', 'Mercado Pago'
        STRIPE      = 'stripe',      'Stripe'
        MANUAL      = 'manual',      'Manual'

    class Status(models.TextChoices):
        CHECKOUT_PENDING = 'checkout_pending', 'Checkout Pendiente'
        TRIALING         = 'trialing',         'En Trial'
        ACTIVE           = 'active',           'Activo'
        PAST_DUE         = 'past_due',         'Pago Vencido'
        SUSPENDED        = 'suspended',        'Suspendido'
        CANCELED         = 'canceled',         'Cancelado'

    # Terminal statuses: once a subscription reaches CANCELED it cannot be
    # reactivated by a late webhook or a reconciliation run.
    # SUSPENDED is intentionally NOT terminal — it can be reactivated by a
    # successful payment retry.
    TERMINAL_STATUSES = (Status.CANCELED,)

    def can_activate(self) -> bool:
        """True if this subscription may still be activated (not in a terminal state)."""
        return self.status not in self.TERMINAL_STATUSES

    id       = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        Business, on_delete=models.PROTECT, related_name='subscriptions_v2',
    )
    service_type = models.CharField(max_length=32, choices=ServiceType.choices)
    plan_code    = models.CharField(max_length=64, help_text='e.g. gestion_pro_monthly')
    provider     = models.CharField(
        max_length=20, choices=Provider.choices, default=Provider.MERCADOPAGO,
    )
    # Mercado Pago Preapproval ID or equivalent. Sparse unique: allows many NULLs.
    provider_sub_id   = models.CharField(max_length=128, null=True, blank=True, unique=True)
    # Stable reference sent to provider. Format: SUB-{uuid}. Always present.
    external_reference = models.CharField(max_length=64, unique=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.CHECKOUT_PENDING,
    )
    trial_starts_at      = models.DateTimeField(null=True, blank=True)
    trial_ends_at        = models.DateTimeField(null=True, blank=True)
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end   = models.DateTimeField(null=True, blank=True)
    # grace_until: deadline before PAST_DUE transitions to SUSPENDED
    grace_until          = models.DateTimeField(null=True, blank=True)
    # retry_count: incremented per failed payment attempt. Triggers SUSPENDED at threshold.
    retry_count          = models.SmallIntegerField(default=0)
    cancel_at_period_end = models.BooleanField(
        default=False,
        help_text='If True, subscription will not renew at period end.',
    )
    canceled_at   = models.DateTimeField(null=True, blank=True)
    # Snapshot of pricing at subscription time (guards against catalog price changes)
    price_snapshot = models.JSONField(default=dict)
    # Phase 3: checkout session that originated this subscription
    checkout_session = models.ForeignKey(
        'MpCheckoutSession',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='subscriptions',
    )
    # Phase 3: MP plan template ID (denormalised from checkout_session for fast lookup)
    provider_preapproval_plan_id = models.CharField(
        max_length=128, null=True, blank=True,
        help_text='MP preapproval_plan ID (plan template). Denorm from checkout_session.',
    )
    # Phase 3: shortcut flag — True when at least one valid payment has been confirmed
    is_active = models.BooleanField(
        default=False,
        help_text='True when the first authorized payment has been confirmed.',
    )
    # Phase 3: raw MP response snapshot from last authoritative fetch
    raw_snapshot_json = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # Only one non-canceled subscription per business+service at a time.
            # Allows full history of canceled subscriptions.
            models.UniqueConstraint(
                fields=['business', 'service_type'],
                condition=~Q(status='canceled'),
                name='uq_subscriptionv2_active_per_service',
            ),
        ]
        indexes = [
            models.Index(fields=['business', 'status'],           name='subv2_business_status_idx'),
            models.Index(fields=['current_period_end', 'status'], name='subv2_period_end_status_idx'),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"SubV2 · {self.business_id} · {self.service_type} · {self.status}"


# ── Phase 2A: BillingEvent ────────────────────────────────────────────────────
#
# Immutable log of every event received from a payment provider.
# NEVER updated after creation. Append-only.
# `provider_event_id` is the idempotency key: if a duplicate webhook arrives,
# lookup by provider_event_id before processing. If status=PROCESSED → skip.
#
class BillingEvent(models.Model):

    class Provider(models.TextChoices):
        MERCADOPAGO = 'mercadopago', 'Mercado Pago'
        STRIPE      = 'stripe',      'Stripe'
        MANUAL      = 'manual',      'Manual'

    class EventType(models.TextChoices):
        SUBSCRIPTION_CREATED   = 'subscription_created',   'Subscription Created'
        PAYMENT_APPROVED       = 'payment_approved',       'Payment Approved'
        PAYMENT_REJECTED       = 'payment_rejected',       'Payment Rejected'
        SUBSCRIPTION_CANCELLED = 'subscription_cancelled', 'Subscription Cancelled'
        PREAPPROVAL_UPDATED    = 'preapproval_updated',    'Preapproval Updated'
        RECONCILIATION_CHECK   = 'reconciliation_check',   'Reconciliation Check'
        UNKNOWN                = 'unknown',                'Unknown'

    class ProcessingStatus(models.TextChoices):
        RECEIVED   = 'received',   'Recibido'
        PROCESSING = 'processing', 'Procesando'
        PROCESSED  = 'processed',  'Procesado'
        IGNORED    = 'ignored',    'Ignorado'
        ERROR      = 'error',      'Error'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Subscription may not be resolved yet at reception time (race condition on creation)
    subscription = models.ForeignKey(
        SubscriptionV2,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='billing_events',
    )
    # Denormalized for direct queries without joining through SubscriptionV2
    business = models.ForeignKey(
        Business,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='billing_events',
    )
    provider       = models.CharField(max_length=20, choices=Provider.choices)
    # UNIQUE: the idempotency key. Duplicate webhooks from MP are rejected at DB level.
    provider_event_id = models.CharField(
        max_length=128, unique=True,
        help_text='Idempotency key. Unique per provider. e.g. MP notification ID.',
    )
    event_type = models.CharField(max_length=32, choices=EventType.choices, default=EventType.UNKNOWN)
    # Full raw payload from webhook or API poll response
    payload    = models.JSONField(help_text='Raw provider payload. Never modified.')
    status     = models.CharField(
        max_length=16, choices=ProcessingStatus.choices, default=ProcessingStatus.RECEIVED,
    )
    received_at  = models.DateTimeField(help_text='Timestamp when the event was received.')
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(
        blank=True, default='',
        help_text='Stack trace or description if status=ERROR.',
    )

    class Meta:
        indexes = [
            models.Index(fields=['subscription', 'received_at'], name='billingevent_sub_received_idx'),
            models.Index(fields=['status', 'received_at'],       name='bill_evt_stat_recv_idx'),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"BillingEvent · {self.provider_event_id} · {self.status}"


# ── Phase 2A: PaymentAttempt ──────────────────────────────────────────────────
#
# Individual payment/charge attempt record for a SubscriptionV2.
# Enables retry tracking, failure analysis, and reconciliation.
#
class PaymentAttempt(models.Model):

    class Provider(models.TextChoices):
        MERCADOPAGO = 'mercadopago', 'Mercado Pago'
        STRIPE      = 'stripe',      'Stripe'
        MANUAL      = 'manual',      'Manual'

    class Status(models.TextChoices):
        PENDING     = 'pending',     'Pendiente'
        PROCESSING  = 'processing',  'Procesando'
        APPROVED    = 'approved',    'Aprobado'
        REJECTED    = 'rejected',    'Rechazado'
        REFUNDED    = 'refunded',    'Reembolsado'
        CHARGEBACK  = 'chargeback',  'Contracargo'

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(
        SubscriptionV2,
        on_delete=models.PROTECT,
        related_name='payment_attempts',
    )
    # Optional link to the BillingEvent that triggered this attempt
    billing_event = models.ForeignKey(
        BillingEvent,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='payment_attempts',
    )
    provider = models.CharField(max_length=20, choices=Provider.choices)
    # Provider's payment ID (e.g. MP payment_id). Sparse unique.
    external_payment_id = models.CharField(
        max_length=128, null=True, blank=True, unique=True,
        help_text='Provider payment ID. Sparse unique (NULL allowed for pending attempts).',
    )
    # Stable reference we send to the provider. Format: PAY-{uuid}. Always unique.
    external_reference = models.CharField(max_length=64, unique=True)
    amount   = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='ARS')
    status   = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    failure_reason = models.CharField(
        max_length=256, blank=True,
        help_text='Rejection code or description from provider.',
    )
    attempt_at  = models.DateTimeField(help_text='When this payment attempt was initiated.')
    resolved_at = models.DateTimeField(null=True, blank=True)
    # Extra metadata from provider: installments, bank, card brand, etc.
    metadata   = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['subscription', 'attempt_at'], name='payattempt_sub_attempt_idx'),
            models.Index(fields=['status'],                     name='payattempt_status_idx'),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"PaymentAttempt · {self.external_reference} · {self.status}"


# ══════════════════════════════════════════════════════════════════════════════
# Phase 3: Robust subscription flow
# ══════════════════════════════════════════════════════════════════════════════
#
# Design principles:
#   - MpCheckoutSession  : one open session per user+plan (idempotency gate)
#   - WebhookDelivery    : every inbound webhook persisted before processing
#   - BillingInvoiceEvent: every authorized-payment event from MP
#
# Correlation chain:
#   MpCheckoutSession.provider_preapproval_plan_id
#     → (webhook) preapproval.preapproval_plan_id on MP resource
#       → SubscriptionV2.provider_sub_id (preapproval ID = user subscription)
#         → BillingInvoiceEvent.provider_authorized_payment_id
#
# Activation rule:
#   Tenant/plan goes ACTIVE only when the first BillingInvoiceEvent with
#   provider_status='authorized' is confirmed via server-to-server MP fetch.
# ══════════════════════════════════════════════════════════════════════════════


class MpCheckoutSession(models.Model):
    """
    Tracks a single subscription checkout attempt.

    Idempotency contract
    --------------------
    At most ONE session in an "open" status (created / checkout_created /
    awaiting_webhook / linked) may exist per (user, plan) pair.
    This is enforced via a DB-level partial unique constraint.

    Lifecycle
    ---------
    created           → local record exists, no MP plan yet
    checkout_created  → MP plan created, init_point available; user was redirected
    awaiting_webhook  → user returned from MP; waiting for authoritative webhook
    linked            → MP subscription (preapproval) resolved and linked to sub
    activated         → first valid payment confirmed; tenant activated
    failed            → MP plan creation or checkout failed
    expired           → session idle too long without payment confirmation
    superseded        → a newer session replaced this one

    Correlation keys
    ----------------
    provider_preapproval_plan_id  : MP plan template ID — created at checkout_created;
                                    used to find this session from webhook data.
    idempotency_key               : hash(user_id + plan_code); deduplication key for
                                    double-click / retry protection.
    mp_external_reference         : sent as external_reference in the MP plan request so
                                    MP echoes it back; format SESS-<uuid>.
    """

    class Status(models.TextChoices):
        CREATED          = 'created',          'Creado'
        CHECKOUT_CREATED = 'checkout_created',  'Checkout Creado'
        AWAITING_WEBHOOK = 'awaiting_webhook',  'Esperando Webhook'
        LINKED           = 'linked',            'Vinculado'
        ACTIVATED        = 'activated',         'Activado'
        FAILED           = 'failed',            'Fallido'
        EXPIRED          = 'expired',           'Expirado'
        SUPERSEDED       = 'superseded',        'Superado'

    # Statuses that represent an "open" (reusable) session.
    OPEN_STATUSES = (
        Status.CREATED,
        Status.CHECKOUT_CREATED,
        Status.AWAITING_WEBHOOK,
        Status.LINKED,
    )

    # Terminal statuses — once reached, no further transitions are valid.
    TERMINAL_STATUSES = (
        Status.ACTIVATED,
        Status.FAILED,
        Status.EXPIRED,
        Status.SUPERSEDED,
    )

    # State machine: maps current status → set of allowed next statuses.
    _VALID_TRANSITIONS: dict = {
        Status.CREATED:          frozenset({Status.CHECKOUT_CREATED, Status.FAILED, Status.EXPIRED, Status.SUPERSEDED}),
        Status.CHECKOUT_CREATED: frozenset({Status.AWAITING_WEBHOOK, Status.FAILED, Status.EXPIRED, Status.SUPERSEDED}),
        Status.AWAITING_WEBHOOK: frozenset({Status.LINKED,           Status.FAILED, Status.EXPIRED, Status.SUPERSEDED}),
        Status.LINKED:           frozenset({Status.ACTIVATED,        Status.FAILED, Status.EXPIRED, Status.SUPERSEDED}),
        # Terminal — no valid outgoing transitions.
        Status.ACTIVATED:   frozenset(),
        Status.FAILED:      frozenset(),
        Status.EXPIRED:     frozenset(),
        Status.SUPERSEDED:  frozenset(),
    }

    id      = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user    = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='checkout_sessions',
    )
    tenant  = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name='checkout_sessions', null=True, blank=True,
    )
    plan    = models.ForeignKey(
        Plan, on_delete=models.PROTECT, related_name='checkout_sessions',
    )
    status  = models.CharField(
        max_length=32, choices=Status.choices, default=Status.CREATED,
    )
    provider_mode = models.CharField(max_length=16, default='sandbox')  # sandbox / prod

    # ── Correlation keys ──────────────────────────────────────────────────────
    # MP plan template ID. Set when MP plan is created. Unique (one plan per session).
    provider_preapproval_plan_id = models.CharField(
        max_length=128, unique=True, null=True, blank=True,
        help_text='MP preapproval_plan ID. Unique. Used to correlate webhook back to this session.',
    )
    provider_checkout_url = models.URLField(max_length=500, null=True, blank=True)
    # Deterministic key: sha256(user_id + ":" + tenant_id + ":" + plan_code).
    # NOT unique at DB level — the partial unique constraints on open sessions
    # already prevent duplicates; requiring uniqueness here would block creating
    # new sessions for the same user+tenant+plan after a previous one expired.
    idempotency_key = models.CharField(max_length=128, db_index=True)
    # Sent to MP as external_reference for the plan. Format: SESS-<uuid>.
    mp_external_reference = models.CharField(max_length=128, blank=True)

    # ── UX / expiration ───────────────────────────────────────────────────────
    return_url    = models.URLField(max_length=500, blank=True)
    expires_at    = models.DateTimeField(null=True, blank=True)
    last_seen_at  = models.DateTimeField(null=True, blank=True)

    # ── Optional extras ───────────────────────────────────────────────────────
    metadata_json = models.JSONField(null=True, blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'tenant', 'plan', 'status'], name='co_sess_user_tenant_plan_idx'),
            models.Index(fields=['provider_preapproval_plan_id'],      name='checkout_sess_plan_id_idx'),
            models.Index(fields=['status', 'expires_at'],              name='checkout_sess_status_exp_idx'),
        ]
        constraints = [
            # At most one open session per (user, tenant, plan) — covers established tenants.
            # Partial on tenant IS NOT NULL so that PostgreSQL can enforce it
            # (NULL != NULL in unique indexes, so NULL tenants need a separate rule).
            models.UniqueConstraint(
                fields=['user', 'tenant', 'plan'],
                condition=Q(
                    status__in=['created', 'checkout_created', 'awaiting_webhook', 'linked'],
                    tenant__isnull=False,
                ),
                name='uq_checkout_session_open_per_tenant_user_plan',
            ),
            # At most one open session per (user, plan) for the new-signup path
            # where tenant has not been created yet (tenant IS NULL).
            models.UniqueConstraint(
                fields=['user', 'plan'],
                condition=Q(
                    status__in=['created', 'checkout_created', 'awaiting_webhook', 'linked'],
                    tenant__isnull=True,
                ),
                name='uq_checkout_session_open_per_user_plan_notenant',
            ),
        ]

    def transition_to(self, new_status: str, *, save: bool = True) -> bool:
        """
        Advance to ``new_status`` according to the state machine.

        Returns True when the transition was applied, False when the session is
        already in ``new_status`` (no-op).

        Raises ValueError if the requested transition is not allowed — e.g.
        attempting to re-open a terminal session from a late webhook.
        """
        if self.status == new_status:
            return False
        allowed = self._VALID_TRANSITIONS.get(self.status, frozenset())
        if new_status not in allowed:
            allowed_list = sorted(allowed) if allowed else ['none (terminal)']
            raise ValueError(
                f"MpCheckoutSession {self.id}: transition {self.status!r} → "
                f"{new_status!r} is not allowed. "
                f"Allowed from {self.status!r}: {allowed_list}"
            )
        old_status = self.status
        self.status = new_status
        if save:
            self.save(update_fields=['status', 'updated_at'])
        return True

    def is_expired(self) -> bool:
        if self.expires_at and timezone.now() > self.expires_at:
            return True
        return False

    def __str__(self) -> str:  # pragma: no cover
        return f"MpCheckoutSession · {self.id} · {self.status}"


class WebhookDelivery(models.Model):
    """
    Immutable audit log of every inbound webhook call.

    ALWAYS persisted before any business logic runs.
    Deduplication key: (topic + resource_id + x_request_id + payload_hash).

    Processing statuses
    -------------------
    received    : saved, not yet processed
    duplicated  : already seen; business logic skipped
    ignored     : topic not handled
    processed   : business logic ran successfully
    failed      : business logic crashed; error_message populated
    dead_letter : repeated failures; requires manual intervention
    """

    class ProcessingStatus(models.TextChoices):
        RECEIVED    = 'received',    'Recibido'
        DUPLICATED  = 'duplicated',  'Duplicado'
        IGNORED     = 'ignored',     'Ignorado'
        PROCESSED   = 'processed',   'Procesado'
        FAILED      = 'failed',      'Fallido'
        DEAD_LETTER = 'dead_letter', 'Dead Letter'

    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider        = models.CharField(max_length=32, default='mercadopago')
    topic           = models.CharField(max_length=128, blank=True)
    resource_id     = models.CharField(max_length=128, blank=True)
    action          = models.CharField(max_length=64, blank=True)   # e.g. 'payment.created'
    x_request_id    = models.CharField(max_length=128, blank=True)
    x_signature     = models.TextField(blank=True)
    signature_valid = models.BooleanField(default=False)
    # SHA-256 hex of the raw request body. Used for exact-duplicate detection.
    payload_hash    = models.CharField(max_length=64, blank=True)
    headers_json    = models.JSONField(default=dict)
    body_json       = models.JSONField(default=dict)
    processing_status = models.CharField(
        max_length=32, choices=ProcessingStatus.choices, default=ProcessingStatus.RECEIVED,
    )
    error_message   = models.TextField(blank=True)
    received_at     = models.DateTimeField()
    processed_at    = models.DateTimeField(null=True, blank=True)
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['topic', 'resource_id'],           name='wh_delivery_topic_res_idx'),
            models.Index(fields=['processing_status', 'received_at'], name='wh_delivery_stat_recv_idx'),
            models.Index(fields=['x_request_id'],                   name='wh_delivery_xreq_idx'),
            models.Index(fields=['payload_hash'],                   name='wh_delivery_hash_idx'),
        ]

    @classmethod
    def compute_hash(cls, body_bytes: bytes) -> str:
        return hashlib.sha256(body_bytes).hexdigest()

    def __str__(self) -> str:  # pragma: no cover
        return f"WebhookDelivery · {self.topic}/{self.resource_id} · {self.processing_status}"


class BillingInvoiceEvent(models.Model):
    """
    Tracks each authorized-payment / recurring-charge event from MP.

    Idempotency key: provider_authorized_payment_id (unique).

    Lifecycle
    ---------
    One BillingInvoiceEvent is created per `subscription_authorized_payment`
    webhook. The `provider_status` mirrors MP's authorized payment status:
      authorized  → triggers tenant activation (first payment) or period renewal
      pending     → logged, no activation
      cancelled   → logged, no activation
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # May be null briefly if subscription resolution races the webhook.
    subscription = models.ForeignKey(
        'SubscriptionV2',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='invoice_events',
    )
    checkout_session = models.ForeignKey(
        MpCheckoutSession,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='invoice_events',
    )
    webhook_delivery = models.ForeignKey(
        WebhookDelivery,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='invoice_events',
    )

    # ── Primary correlation key ───────────────────────────────────────────────
    # MP authorized_payment ID. Unique — guarantees idempotent upsert.
    provider_authorized_payment_id = models.CharField(
        max_length=128, unique=True,
        help_text='MP authorized_payment ID. Idempotency key for recurring charges.',
    )
    provider_payment_id      = models.CharField(max_length=128, blank=True)
    provider_subscription_id = models.CharField(max_length=128, blank=True)

    amount          = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency        = models.CharField(max_length=3, default='ARS')
    provider_status = models.CharField(max_length=32, blank=True)  # authorized/pending/cancelled
    paid_at         = models.DateTimeField(null=True, blank=True)
    raw_payload_json = models.JSONField(default=dict)
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['provider_subscription_id'], name='billinginv_sub_id_idx'),
            models.Index(fields=['provider_status', 'created_at'], name='billinginv_stat_created_idx'),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"BillingInvoiceEvent · {self.provider_authorized_payment_id} · {self.provider_status}"