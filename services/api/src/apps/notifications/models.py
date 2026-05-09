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
