"""
SupportTicket + TicketMessage models for the admin backoffice.

A ticket is always linked to a Business (client) and optionally to a
SubscriptionV2. Messages form a threaded conversation between platform
staff and are internal-only (tenants never see these).
"""
import uuid

from django.conf import settings
from django.db import models, transaction, IntegrityError


class SupportTicket(models.Model):
    """Internal support ticket created by platform staff."""

    # ── Status machine ────────────────────────────────────────────────────
    STATUS_OPEN = 'open'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_WAITING = 'waiting_on_client'
    STATUS_RESOLVED = 'resolved'
    STATUS_CLOSED = 'closed'

    STATUS_CHOICES = [
        (STATUS_OPEN, 'Abierto'),
        (STATUS_IN_PROGRESS, 'En curso'),
        (STATUS_WAITING, 'Esperando cliente'),
        (STATUS_RESOLVED, 'Resuelto'),
        (STATUS_CLOSED, 'Cerrado'),
    ]

    # ── Priority ──────────────────────────────────────────────────────────
    PRIORITY_LOW = 'low'
    PRIORITY_MEDIUM = 'medium'
    PRIORITY_HIGH = 'high'
    PRIORITY_URGENT = 'urgent'

    PRIORITY_CHOICES = [
        (PRIORITY_LOW, 'Baja'),
        (PRIORITY_MEDIUM, 'Media'),
        (PRIORITY_HIGH, 'Alta'),
        (PRIORITY_URGENT, 'Urgente'),
    ]

    # ── Category ──────────────────────────────────────────────────────────
    CATEGORY_BILLING = 'billing'
    CATEGORY_TECHNICAL = 'technical'
    CATEGORY_ACCOUNT = 'account'
    CATEGORY_FEATURE = 'feature_request'
    CATEGORY_OTHER = 'other'

    CATEGORY_CHOICES = [
        (CATEGORY_BILLING, 'Facturación / Pagos'),
        (CATEGORY_TECHNICAL, 'Problema técnico'),
        (CATEGORY_ACCOUNT, 'Cuenta / Acceso'),
        (CATEGORY_FEATURE, 'Solicitud de funcionalidad'),
        (CATEGORY_OTHER, 'Otro'),
    ]

    # ── Origin ────────────────────────────────────────────────────────────
    ORIGIN_ADMIN = 'admin'
    ORIGIN_TENANT = 'tenant'

    ORIGIN_CHOICES = [
        (ORIGIN_ADMIN, 'Creado por admin'),
        (ORIGIN_TENANT, 'Creado por tenant'),
    ]

    # ── Fields ────────────────────────────────────────────────────────────
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(
        max_length=16,
        unique=True,
        editable=False,
        help_text='Human-readable reference like TK-0001',
    )

    subject = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN, db_index=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default=PRIORITY_MEDIUM, db_index=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default=CATEGORY_OTHER, db_index=True)

    # ── Relations ─────────────────────────────────────────────────────────
    business = models.ForeignKey(
        'business.Business',
        on_delete=models.CASCADE,
        related_name='support_tickets',
    )
    subscription = models.ForeignKey(
        'billing.SubscriptionV2',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='support_tickets',
    )
    contact_email = models.EmailField(
        blank=True,
        help_text='Tenant contact email for this ticket (pre-filled from business owner)',
    )
    origin = models.CharField(
        max_length=10,
        choices=ORIGIN_CHOICES,
        default=ORIGIN_ADMIN,
        db_index=True,
        help_text='Where the ticket was created: admin backoffice or tenant portal.',
    )

    # ── Assignment ────────────────────────────────────────────────────────
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_tickets',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_tickets',
    )

    # ── Timestamps ────────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'priority'], name='ticket_status_prio_idx'),
            models.Index(fields=['business', 'status'], name='ticket_biz_status_idx'),
        ]

    def __str__(self):
        return f'{self.reference} — {self.subject}'

    def save(self, *args, **kwargs):
        if not self.reference:
            max_attempts = 5
            for attempt in range(max_attempts):
                try:
                    with transaction.atomic():
                        self.reference = self._generate_reference()
                        super().save(*args, **kwargs)
                    return
                except IntegrityError:
                    if attempt < max_attempts - 1:
                        self.reference = ''
                        continue
                    raise
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_reference() -> str:
        """Generate next TK-NNNN. Uses SELECT FOR UPDATE to serialise concurrent access."""
        last = (
            SupportTicket.objects
            .select_for_update()
            .filter(reference__startswith='TK-')
            .order_by('-reference')
            .values_list('reference', flat=True)
            .first()
        )
        num = int(last.split('-')[1]) + 1 if last else 1
        return f'TK-{num:04d}'


class TicketMessage(models.Model):
    """A single message within a support ticket thread."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(
        SupportTicket,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='ticket_messages',
    )
    body = models.TextField(max_length=5000)
    is_system = models.BooleanField(
        default=False,
        help_text='True for auto-generated status-change messages',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'Msg on {self.ticket.reference} by {self.author_id}'
