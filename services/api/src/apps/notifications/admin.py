from django.contrib import admin

from .models import BusinessNotification, EmailDelivery


@admin.register(EmailDelivery)
class EmailDeliveryAdmin(admin.ModelAdmin):
    list_display = [
        "template_key",
        "to_email",
        "status",
        "provider",
        "business",
        "user",
        "queued_at",
        "sent_at",
        "failed_at",
        "created_at",
    ]
    list_filter = ["status", "provider", "template_key"]
    search_fields = ["to_email", "subject", "template_key", "provider_message_id"]
    readonly_fields = [
        "id",
        "created_at",
        "updated_at",
        "queued_at",
        "sent_at",
        "failed_at",
        "provider_message_id",
        "html_body",
        "text_body",
        "error_message",
        "metadata",
    ]
    ordering = ["-created_at"]


@admin.register(BusinessNotification)
class BusinessNotificationAdmin(admin.ModelAdmin):
    list_display = ["kind", "severity", "business", "title", "read_at", "created_at"]
    list_filter = ["kind", "severity"]
    search_fields = ["title", "dedupe_key", "related_object_id"]
    readonly_fields = ["id", "created_at", "dedupe_key"]
    ordering = ["-created_at"]
