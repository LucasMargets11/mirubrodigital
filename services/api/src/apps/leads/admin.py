from django.contrib import admin

from .models import AgentChannel, AgentCredential, AgentInstance, ConversationControl, Lead, TakeoverCommand


@admin.register(AgentInstance)
class AgentInstanceAdmin(admin.ModelAdmin):
    list_display = ["external_id", "name", "is_enabled", "created_at", "disabled_at"]
    list_filter = ["is_enabled"]
    search_fields = ["external_id", "name"]
    readonly_fields = ["id", "created_at"]
    ordering = ["external_id"]

    def get_readonly_fields(self, request, obj=None):
        # external_id es inmutable una vez creado (AgentInstance.save()).
        if obj is not None:
            return [*self.readonly_fields, "external_id"]
        return self.readonly_fields


@admin.register(AgentCredential)
class AgentCredentialAdmin(admin.ModelAdmin):
    """Solo lectura: el alta/rotación es por `provision_agent` (cifra el
    secreto). `encrypted_secret` nunca se muestra ni se edita."""

    list_display = ["key_id", "agent_instance", "status", "created_at", "revoked_at"]
    list_filter = ["status"]
    search_fields = ["key_id", "agent_instance__external_id"]
    fields = ["id", "agent_instance", "key_id", "status", "created_at", "revoked_at"]
    readonly_fields = fields
    ordering = ["-created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AgentChannel)
class AgentChannelAdmin(admin.ModelAdmin):
    list_display = ["provider", "phone_number_id", "business", "agent_instance", "is_active", "created_at", "deactivated_at"]
    list_filter = ["provider", "is_active"]
    search_fields = ["phone_number_id", "agent_instance__external_id"]
    raw_id_fields = ["business"]
    readonly_fields = ["id", "created_at"]
    ordering = ["-created_at"]


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ["id", "business", "source", "status", "outcome", "needs_attention_at", "created_at"]
    list_filter = ["source", "status", "outcome"]
    raw_id_fields = ["business", "assigned_to", "customer", "appointment", "closed_by", "acknowledged_by"]
    readonly_fields = ["id", "created_at", "updated_at"]
    ordering = ["-created_at"]


class _ReadOnlyAdmin(admin.ModelAdmin):
    """Solo lectura: el estado lo mueven la acción humana y la entrega al agente
    (services.takeover), nunca una edición manual."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ConversationControl)
class ConversationControlAdmin(_ReadOnlyAdmin):
    list_display = ["external_conversation_id", "business", "state", "command_version", "agent_applied_version",
                    "last_error_code", "updated_at"]
    list_filter = ["state"]
    search_fields = ["external_conversation_id"]
    raw_id_fields = ["business", "taken_by"]
    ordering = ["-updated_at"]

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]


@admin.register(TakeoverCommand)
class TakeoverCommandAdmin(_ReadOnlyAdmin):
    # Sin secretos ni payload: el comando no los guarda.
    list_display = ["conversation_control", "version", "action", "status", "result", "attempts", "last_status",
                    "last_error", "next_attempt_at", "created_at"]
    list_filter = ["status", "action", "result"]
    search_fields = ["conversation_control__external_conversation_id", "event_id"]
    raw_id_fields = ["conversation_control", "requested_by", "requested_from_lead"]
    ordering = ["-created_at"]

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]
