"""
AdminNotification — persistent in-app notification model for platform staff.

Covers events across domains (support, billing, reviews, security, system)
so that platform staff can see a unified alert feed without relying on email.

Design constraints:
  - Lives in apps.accounts to avoid circular imports with apps.notifications
    (which is email-only infrastructure).
  - Does NOT trigger send_mail or EmailMessage — purely a database record.
  - Optional deduplication handled in admin_notification_service.py (not here).
"""
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class AdminNotification(models.Model):
    """
    A single notification item visible to platform staff in the admin backoffice.

    Lifecycle:  unread → read → resolved | archived
    """

    # ── Notification type ─────────────────────────────────────────────────────

    class NotifType(models.TextChoices):
        # Support
        SUPPORT_TICKET_CREATED    = 'support_ticket_created',    'Ticket de soporte creado'
        SUPPORT_TICKET_REPLIED    = 'support_ticket_replied',    'Respuesta en ticket de soporte'
        SUPPORT_TICKET_ESCALATED  = 'support_ticket_escalated',  'Ticket escalado'
        SUPPORT_TICKET_OVERDUE    = 'support_ticket_overdue',    'Ticket sin respuesta (vencido)'
        # Billing
        BILLING_PAYMENT_FAILED    = 'billing_payment_failed',    'Pago fallido'
        BILLING_TRIAL_ENDING      = 'billing_trial_ending',      'Trial por vencer'
        BILLING_SUBSCRIPTION_CANCELED = 'billing_subscription_canceled', 'Suscripción cancelada'
        BILLING_SUBSCRIPTION_CREATED  = 'billing_subscription_created',  'Nueva suscripción'
        # Reviews
        REVIEW_REPORTED           = 'review_reported',           'Reseña reportada'
        REVIEW_RESPONSE_PENDING   = 'review_response_pending',   'Reseña sin respuesta'
        # Security
        SECURITY_ADMIN_LOGIN_FAILED   = 'security_admin_login_failed',   'Login de admin fallido'
        SECURITY_MFA_DISABLED         = 'security_mfa_disabled',         'MFA deshabilitado'
        SECURITY_SUSPICIOUS_AUTH      = 'security_suspicious_auth',      'Auth sospechoso'
        SECURITY_MULTIPLE_FAILURES    = 'security_multiple_failures',    'Múltiples fallos de auth'
        # System
        SYSTEM_ERROR              = 'system_error',              'Error del sistema'
        SYSTEM_INFO               = 'system_info',               'Información del sistema'

    # ── Severity ──────────────────────────────────────────────────────────────

    class Severity(models.TextChoices):
        INFO     = 'info',     'Informativo'
        SUCCESS  = 'success',  'Exitoso'
        WARNING  = 'warning',  'Advertencia'
        CRITICAL = 'critical', 'Crítico'

    # ── Status ────────────────────────────────────────────────────────────────

    class Status(models.TextChoices):
        UNREAD   = 'unread',   'No leída'
        READ     = 'read',     'Leída'
        RESOLVED = 'resolved', 'Resuelta'
        ARCHIVED = 'archived', 'Archivada'

    # ── Primary key ───────────────────────────────────────────────────────────

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # ── Core content ──────────────────────────────────────────────────────────

    notif_type = models.CharField(
        max_length=48,
        choices=NotifType.choices,
        help_text='Category of the notification.',
    )
    severity = models.CharField(
        max_length=16,
        choices=Severity.choices,
        default=Severity.INFO,
    )
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True, default='')

    # ── Status + timestamps ───────────────────────────────────────────────────

    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.UNREAD,
        db_index=True,
    )

    read_at     = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    # ── Routing / targeting ───────────────────────────────────────────────────

    # target_role: if set, only staff with this internal_role should see it.
    # Empty string = broadcast to all platform staff.
    target_role = models.CharField(max_length=24, blank=True, default='')

    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='admin_notifications_targeted',
        help_text='If set, only this staff user should see the notification.',
    )

    # ── Related domain object ─────────────────────────────────────────────────

    business = models.ForeignKey(
        'business.Business',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='admin_notifications',
        help_text='The business this notification is about, if applicable.',
    )

    # Generic reference to the triggering object (e.g. 'support_ticket', uuid str)
    related_object_type = models.CharField(max_length=64, blank=True, default='')
    related_object_id   = models.CharField(max_length=64, blank=True, default='')

    action_url = models.CharField(
        max_length=500,
        blank=True,
        default='',
        help_text='Optional URL for the CTA button in the notification item.',
    )

    # ── Deduplication ─────────────────────────────────────────────────────────

    dedupe_key = models.CharField(
        max_length=64,
        blank=True,
        default='',
        db_index=True,
        help_text=(
            'Optional dedup key (SHA-256[:64] of notif_type:related_object_type:related_object_id). '
            'Used by create_admin_notification() to skip duplicate creation within a time window.'
        ),
    )

    # ── Extra metadata ────────────────────────────────────────────────────────

    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text='Additional context. Sensitive keys are stripped before saving.',
    )

    # ── Timestamps ────────────────────────────────────────────────────────────

    created_at = models.DateTimeField(auto_now_add=True)

    # ── Meta ──────────────────────────────────────────────────────────────────

    class Meta:
        app_label = 'accounts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at'],          name='adminnotif_status_ts_idx'),
            models.Index(fields=['target_role', '-created_at'],     name='adminnotif_role_ts_idx'),
            models.Index(fields=['business', '-created_at'],        name='adminnotif_business_ts_idx'),
            models.Index(fields=['related_object_type', 'related_object_id'], name='adminnotif_related_idx'),
        ]

    # ── Helpers ───────────────────────────────────────────────────────────────

    def __str__(self) -> str:
        return f'AdminNotification({self.notif_type}, {self.severity}, {self.status})'

    def mark_read(self) -> None:
        """Idempotent: transition unread → read. Sets read_at once."""
        if self.status == self.Status.UNREAD:
            self.status = self.Status.READ
            self.read_at = timezone.now()
            self.save(update_fields=['status', 'read_at'])

    def mark_resolved(self) -> None:
        """Idempotent: transition unread|read → resolved. Sets resolved_at once."""
        if self.status in (self.Status.UNREAD, self.Status.READ):
            self.status = self.Status.RESOLVED
            self.resolved_at = timezone.now()
            self.save(update_fields=['status', 'resolved_at'])

    def mark_archived(self) -> None:
        """Idempotent: transition any non-archived status → archived. Sets archived_at once."""
        if self.status != self.Status.ARCHIVED:
            self.status = self.Status.ARCHIVED
            self.archived_at = timezone.now()
            self.save(update_fields=['status', 'archived_at'])
