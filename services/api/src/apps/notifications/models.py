import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class EmailDelivery(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        BOUNCED = "bounced", "Bounced"
        COMPLAINED = "complained", "Complained"

    class Provider(models.TextChoices):
        AMAZON_SES = "amazon_ses", "Amazon SES"
        DJANGO = "django", "Django Email Backend"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    business = models.ForeignKey(
        "business.Business",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="email_deliveries",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="email_deliveries",
    )

    to_email = models.EmailField(db_index=True)
    from_email = models.CharField(max_length=255)
    subject = models.CharField(max_length=255)
    template_key = models.CharField(max_length=100, db_index=True)

    html_body = models.TextField(blank=True)
    text_body = models.TextField(blank=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    provider = models.CharField(
        max_length=30,
        choices=Provider.choices,
        default=Provider.DJANGO,
        db_index=True,
    )

    provider_message_id = models.CharField(max_length=255, blank=True, db_index=True)
    error_message = models.TextField(blank=True)

    metadata = models.JSONField(default=dict, blank=True)

    queued_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["business", "created_at"]),
            models.Index(fields=["template_key", "created_at"]),
        ]

    def __str__(self):
        return f"{self.template_key} → {self.to_email} [{self.status}]"

    def mark_sending(self):
        self.status = self.Status.SENDING
        self.error_message = ""
        self.save(update_fields=["status", "error_message", "updated_at"])

    def mark_sent(self, provider_message_id=""):
        self.status = self.Status.SENT
        self.provider_message_id = provider_message_id or ""
        self.sent_at = timezone.now()
        self.error_message = ""
        self.save(update_fields=[
            "status",
            "provider_message_id",
            "sent_at",
            "error_message",
            "updated_at",
        ])

    def mark_failed(self, error_message):
        self.status = self.Status.FAILED
        self.error_message = str(error_message)[:5000]
        self.failed_at = timezone.now()
        self.save(update_fields=[
            "status",
            "error_message",
            "failed_at",
            "updated_at",
        ])


class BusinessNotification(models.Model):
    """Notificación interna in-app para el equipo de un Business (Slice 6D).

    A diferencia de `accounts.AdminNotification` (staff de la plataforma) y de
    `EmailDelivery` (emails), esta la ven los miembros del propio negocio
    (ver `business_notifications.RECIPIENT_ROLES` y `KIND_VIEW_PERMISSIONS`). Una fila por evento y por
    Business; el estado de lectura es compartido por el equipo.

    Idempotencia: `UniqueConstraint(business, dedupe_key)`. El creador
    (`business_notifications.create_business_notification`) es un
    get-or-create, así que un webhook repetido nunca duplica el evento.

    Destinatario (LEADS 04B.3): `recipient` vacío = aviso para el equipo (reglas
    de visibilidad por rol/kind). Con `recipient` = aviso personal: solo lo ve
    esa persona (ni owner/admin ven los personales ajenos), así su `read_at` es
    de hecho personal.
    """

    class Kind(models.TextChoices):
        APPOINTMENT_CONFIRMED = "appointment_confirmed", "Reserva confirmada"
        APPOINTMENT_PAYMENT_REVIEW = "appointment_payment_review", "Pago de reserva requiere revisión"
        CUSTOMER_REMINDER_DUE = "customer_reminder_due", "Recordatorio de cliente vencido"
        AGENT_LEAD_HANDOFF = "agent_lead_handoff", "Consulta del agente requiere atención"
        LEAD_ASSIGNED = "lead_assigned", "Lead asignado"

    class Severity(models.TextChoices):
        INFO = "info", "Informativa"
        CRITICAL = "critical", "Prioritaria"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        "business.Business",
        on_delete=models.CASCADE,
        related_name="business_notifications",
    )
    kind = models.CharField(max_length=48, choices=Kind.choices)
    severity = models.CharField(max_length=16, choices=Severity.choices, default=Severity.INFO)
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True, default="")
    # Ruta interna del panel (siempre empieza con /app/); nunca una URL externa.
    action_url = models.CharField(max_length=500, blank=True, default="")
    related_object_type = models.CharField(max_length=64, blank=True, default="")
    related_object_id = models.CharField(max_length=64, blank=True, default="")
    # Datos de contexto mínimos (ids, origen); nunca PII del cliente. No se
    # expone en la API: sirve a soporte/auditoría (CUSTOMER 07C).
    # db_default: un proceso con el código anterior (deploy en curso) que
    # inserte sin esta columna no rompe por NOT NULL.
    metadata = models.JSONField(default=dict, db_default=models.Value({}, output_field=models.JSONField()), blank=True)
    # LEADS 04B.3: null = aviso del Business; con valor = aviso personal.
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="business_notifications_received",
    )
    dedupe_key = models.CharField(max_length=128)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["business", "dedupe_key"], name="business_notification_unique_dedupe"),
        ]
        indexes = [
            models.Index(fields=["business", "-created_at"], name="bizn_business_ts_idx"),
            models.Index(fields=["business", "read_at"], name="bizn_business_read_idx"),
        ]

    def __str__(self):
        return f"BusinessNotification({self.kind}, business={self.business_id})"
