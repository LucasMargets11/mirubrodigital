"""Serializers de la API humana de Leads (LEADS 04A).

Separados de `serializers.py` (contrato máquina Agent → MiRubro). Acá:

- Lectura: bandeja (`LeadListSerializer`) y detalle (`LeadDetailSerializer`)
  con el snapshot del agente en modo read-only. Nunca se exponen
  `payload_hash`, `last_event_id`, credenciales ni internals del canal.
- Escritura: `LeadUpdateSerializer` acepta SOLO campos CRM
  (`status`, `outcome`, `assigned_to`, `customer`, `appointment`); cualquier
  otro campo del payload se rechaza explícitamente (no se ignora en silencio).
- Notas: `LeadNoteSerializer` (mismo contrato que `CustomerNoteSerializer`).
- Historial (LEADS 04B.4): `activity` del detalle, read-only, más reciente
  primero; etiquetas de usuario/cliente/turno resueltas al leer.
"""
from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.appointments.models import Appointment
from apps.customers.models import Customer
from apps.customers.serializers import _author_display_name

from .models import ConversationControl, Lead, LeadActivity, LeadAgentMessage, LeadAgentState, LeadNote, LeadStaffMessage
from .services.activity import record_update_activity, snapshot_for_activity
from .services.assignees import active_memberships, membership_can_view_leads
from .services.notifications import schedule_lead_assigned_notification
from .services.takeover import control_for_lead, conversation_id_for, takeover_enabled

User = get_user_model()

EDITABLE_FIELDS = ('status', 'outcome', 'assigned_to', 'customer', 'appointment')

# Transiciones permitidas (MVP 04A): un Lead cerrado queda cerrado; reabrir
# será un slice aparte. Mantener el mismo estado es un no-op válido.
ALLOWED_TRANSITIONS = {
    Lead.Status.NEW: {Lead.Status.NEW, Lead.Status.IN_PROGRESS, Lead.Status.CLOSED},
    Lead.Status.IN_PROGRESS: {Lead.Status.IN_PROGRESS, Lead.Status.CLOSED},
    Lead.Status.CLOSED: {Lead.Status.CLOSED},
}


def _user_ref(user) -> dict[str, Any] | None:
    if user is None:
        return None
    return {'id': user.pk, 'display_name': _author_display_name(user)}


def _customer_ref(customer: Customer | None) -> dict[str, Any] | None:
    if customer is None:
        return None
    return {'id': str(customer.pk), 'display_name': customer.name}


def _appointment_ref(appointment: Appointment | None) -> dict[str, Any] | None:
    # Referencia mínima para el panel de Leads: sin datos de contacto del turno
    # (`customer_*`, notas, pagos). `status` es el efectivo (un hold vencido
    # se informa `expired` aunque el job todavía no lo haya marcado).
    if appointment is None:
        return None
    return {
        'id': str(appointment.pk),
        'start_at': appointment.start_at,
        'end_at': appointment.end_at,
        'status': appointment.effective_status(),
        'service_name': appointment.service_name,
    }


def _agent_state(lead: Lead) -> LeadAgentState | None:
    try:
        return lead.agent_state
    except LeadAgentState.DoesNotExist:
        return None


class LeadAgentSummarySerializer(serializers.ModelSerializer):
    """Snapshot reducido del agente para la bandeja (read-only)."""

    class Meta:
        model = LeadAgentState
        fields = [
            'patient_name', 'whatsapp_profile_name', 'phone_e164', 'reason', 'preferred_time', 'urgency',
            'agent_status', 'handoff_requested', 'handoff_reasons', 'summary', 'last_message_at',
        ]
        read_only_fields = fields


class LeadAgentStateSerializer(serializers.ModelSerializer):
    """Snapshot completo del agente para el detalle (read-only).

    `agent_instance_id` es el identificador externo del contrato (nunca el
    UUID interno); `channel` es solo el proveedor. Sin `payload_hash` ni
    `last_event_id`.
    """

    agent_instance_id = serializers.CharField(source='agent_instance.external_id', read_only=True)
    channel = serializers.CharField(source='channel.provider', read_only=True)

    class Meta:
        model = LeadAgentState
        fields = [
            'agent_instance_id', 'external_lead_id', 'external_conversation_id', 'previous_external_lead_id',
            'channel', 'phone_e164', 'patient_name', 'whatsapp_profile_name', 'reason', 'preferred_time', 'urgency',
            'agent_status', 'handoff_requested', 'handoff_requested_at', 'handoff_reasons', 'summary',
            'opened_at', 'closed_at', 'close_reason', 'last_message_at', 'applied_version', 'last_synced_at',
        ]
        read_only_fields = fields


class LeadMessageSerializer(serializers.ModelSerializer):
    """Mensaje del historial real de la conversaci\u00f3n (LEADS 05C), solo lectura.

    `authored_by` (MIRUBRO HUMAN MESSAGES) decora los mensajes `sender=staff`
    con quién de recepción los escribió: join local por
    `message_id == external_message_id` contra `LeadStaffMessage`
    (`services.human_messages.authored_by_map`, provisto por la vista vía
    `context['authored_by_map']`). Sin match (p. ej. un mensaje viejo de
    takeover previo a esta feature) cae a un label genérico; nunca null para
    un mensaje de staff.
    """

    authored_by = serializers.SerializerMethodField()

    class Meta:
        model = LeadAgentMessage
        fields = ['id', 'role', 'sender', 'text', 'sent_at', 'status', 'authored_by']
        read_only_fields = fields

    def get_authored_by(self, obj: LeadAgentMessage) -> dict[str, Any] | None:
        if obj.sender != LeadAgentMessage.Sender.STAFF:
            return None
        match = (self.context.get('authored_by_map') or {}).get(obj.external_message_id)
        return match or {'id': None, 'display_name': 'Recepci\u00f3n'}

class LeadSendMessageSerializer(serializers.Serializer):
    """POST de un mensaje de recepción hacia el paciente (MIRUBRO HUMAN MESSAGES).

    Validación local instantánea (vacío/demasiado largo/caracteres
    inválidos); el texto se envía al agente tal cual, sin recortar espacios
    (el contrato lo manda "exactamente como es").
    """

    text = serializers.CharField(
        max_length=LeadStaffMessage.TEXT_MAX_LENGTH, trim_whitespace=False, allow_blank=False,
        error_messages={
            'blank': 'El mensaje no puede estar vacío.',
            'max_length': f'El mensaje no puede superar los {LeadStaffMessage.TEXT_MAX_LENGTH} caracteres.',
        },
    )

    def validate_text(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError('El mensaje no puede estar vacío.')
        if '\x00' in value:
            raise serializers.ValidationError('El mensaje tiene caracteres inválidos.')
        return value

class LeadNoteSerializer(serializers.ModelSerializer):
    """Nota interna del Lead. `author` sale del request, nunca del payload."""

    body = serializers.CharField(
        max_length=LeadNote.BODY_MAX_LENGTH,
        trim_whitespace=True,
        allow_blank=False,
        error_messages={'blank': 'La nota no puede estar vacía.'},
    )
    author = serializers.SerializerMethodField()

    class Meta:
        model = LeadNote
        fields = ['id', 'body', 'author', 'created_at', 'updated_at']
        read_only_fields = ['id', 'author', 'created_at', 'updated_at']

    def get_author(self, obj: LeadNote) -> dict[str, Any] | None:
        if obj.author_id is None:
            return None
        return {'id': str(obj.author_id), 'name': _author_display_name(obj.author)}


class LeadListSerializer(serializers.ModelSerializer):
    assigned_to = serializers.SerializerMethodField()
    customer = serializers.SerializerMethodField()
    agent = serializers.SerializerMethodField()
    needs_attention = serializers.BooleanField(source='attention_pending', read_only=True)
    conversation_state = serializers.SerializerMethodField()

    class Meta:
        model = Lead
        fields = [
            'id', 'source', 'status', 'outcome', 'created_at', 'updated_at', 'needs_attention_at',
            'needs_attention', 'acknowledged_at', 'assigned_to', 'customer', 'agent', 'conversation_state',
        ]
        read_only_fields = fields

    def get_conversation_state(self, obj: Lead) -> str | None:
        # MIRUBRO TAKEOVER 05A: anotado por LeadListView (sin query por fila).
        # Sin conversación del agente → null; sin control todavía → active.
        if _agent_state(obj) is None:
            return None
        return getattr(obj, 'conversation_control_state', None) or ConversationControl.State.ACTIVE

    def get_assigned_to(self, obj: Lead) -> dict[str, Any] | None:
        return _user_ref(obj.assigned_to)

    def get_customer(self, obj: Lead) -> dict[str, Any] | None:
        return _customer_ref(obj.customer)

    def get_agent(self, obj: Lead) -> dict[str, Any] | None:
        state = _agent_state(obj)
        return LeadAgentSummarySerializer(state).data if state is not None else None


class LeadDetailSerializer(serializers.ModelSerializer):
    assigned_to = serializers.SerializerMethodField()
    customer = serializers.SerializerMethodField()
    appointment = serializers.SerializerMethodField()
    closed_by = serializers.SerializerMethodField()
    acknowledged_by = serializers.SerializerMethodField()
    needs_attention = serializers.BooleanField(source='attention_pending', read_only=True)
    agent_state = serializers.SerializerMethodField()
    notes = serializers.SerializerMethodField()
    activity = serializers.SerializerMethodField()
    conversation_control = serializers.SerializerMethodField()

    class Meta:
        model = Lead
        fields = [
            'id', 'source', 'status', 'outcome', 'assigned_to', 'customer', 'appointment', 'needs_attention_at',
            'needs_attention', 'acknowledged_at', 'acknowledged_by',
            'closed_at', 'closed_by', 'created_at', 'updated_at', 'agent_state', 'notes', 'activity',
            'conversation_control',
        ]
        read_only_fields = fields

    def get_assigned_to(self, obj: Lead) -> dict[str, Any] | None:
        return _user_ref(obj.assigned_to)

    def get_customer(self, obj: Lead) -> dict[str, Any] | None:
        return _customer_ref(obj.customer)

    def get_closed_by(self, obj: Lead) -> dict[str, Any] | None:
        return _user_ref(obj.closed_by)

    def get_acknowledged_by(self, obj: Lead) -> dict[str, Any] | None:
        return _user_ref(obj.acknowledged_by)

    def get_appointment(self, obj: Lead) -> dict[str, Any] | None:
        return _appointment_ref(obj.appointment)

    def get_agent_state(self, obj: Lead) -> dict[str, Any] | None:
        state = _agent_state(obj)
        return LeadAgentStateSerializer(state).data if state is not None else None

    def get_notes(self, obj: Lead) -> list[dict[str, Any]]:
        # Usa el prefetch del view (orden -created_at, igual que CustomerNote).
        return LeadNoteSerializer(obj.notes.all(), many=True).data

    def get_activity(self, obj: Lead) -> list[dict[str, Any]]:
        # Usa el prefetch del view (orden del modelo: -created_at, position).
        return serialize_lead_activity(obj, list(obj.activities.all()))

    def get_conversation_control(self, obj: Lead) -> dict[str, Any] | None:
        return serialize_conversation_control(obj)


def serialize_conversation_control(lead: Lead) -> dict[str, Any] | None:
    """Pausa del bot de la conversación del Lead (MIRUBRO TAKEOVER 05A).

    `null` si el Lead no tiene conversación del agente. Sin secretos, event_id,
    request ids ni internals de transporte. `available` = la acción humana se
    puede pedir (flag encendido y conversation id con formato del agente).
    `last_action` dice qué pidió el último comando (para reintentar desde `error`).
    """
    if _agent_state(lead) is None:
        return None
    control = control_for_lead(lead)
    data = {
        'state': ConversationControl.State.ACTIVE,
        'command_version': 0,
        'last_action': None,
        'taken_at': None,
        'taken_by': None,
        'released_at': None,
        'last_error_code': None,
        'available': takeover_enabled() and conversation_id_for(lead) is not None,
    }
    if control is not None:
        data.update({
            'state': control.state,
            'command_version': control.command_version,
            'last_action': control.last_command_action,
            'taken_at': control.taken_at,
            'taken_by': _user_ref(control.taken_by),
            'released_at': control.released_at,
            'last_error_code': control.last_error_code,
        })
    return data


_ACTIVITY_VALUE_FIELD = {
    LeadActivity.Kind.STATUS_CHANGED: 'status',
    LeadActivity.Kind.CLOSED: 'status',
    LeadActivity.Kind.OUTCOME_CHANGED: 'outcome',
    LeadActivity.Kind.ASSIGNED: 'user',
    LeadActivity.Kind.REASSIGNED: 'user',
    LeadActivity.Kind.UNASSIGNED: 'user',
    LeadActivity.Kind.CUSTOMER_LINKED: 'customer',
    LeadActivity.Kind.CUSTOMER_CHANGED: 'customer',
    LeadActivity.Kind.CUSTOMER_UNLINKED: 'customer',
    LeadActivity.Kind.APPOINTMENT_LINKED: 'appointment',
    LeadActivity.Kind.APPOINTMENT_CHANGED: 'appointment',
    LeadActivity.Kind.APPOINTMENT_UNLINKED: 'appointment',
}
_CHOICE_LABELS = {'status': dict(Lead.Status.choices), 'outcome': dict(Lead.Outcome.choices)}


def _choice_ref(field: str, value) -> dict[str, Any] | None:
    if value is None:
        return None
    return {'value': value, 'label': _CHOICE_LABELS[field].get(value, value)}


def serialize_lead_activity(lead: Lead, activities: list[LeadActivity]) -> list[dict[str, Any]]:
    """Eventos del historial con referencias resueltas en bloque.

    Usuarios/clientes/turnos se buscan por los ids guardados (clientes y turnos
    acotados al Business del Lead). Si ya no existen, la referencia conserva
    el `id` con el resto en null: el evento sigue siendo legible.
    """
    ids: dict[str, set] = {'user': set(), 'customer': set(), 'appointment': set()}
    for activity in activities:
        field = _ACTIVITY_VALUE_FIELD.get(activity.kind)
        if field in ids:
            ids[field].update(v for v in (activity.previous_value, activity.new_value) if v is not None)
    users = {u.pk: u for u in User.objects.filter(pk__in=ids['user'])} if ids['user'] else {}
    customers = (
        {str(c.pk): c for c in Customer.objects.filter(pk__in=ids['customer'], business_id=lead.business_id)}
        if ids['customer'] else {}
    )
    appointments = (
        {str(a.pk): a for a in Appointment.objects.filter(pk__in=ids['appointment'], business_id=lead.business_id)}
        if ids['appointment'] else {}
    )

    def ref(field: str | None, value):
        if value is None or field is None:
            return None
        if field in _CHOICE_LABELS:
            return _choice_ref(field, value)
        if field == 'user':
            user = users.get(value)
            return _user_ref(user) if user is not None else {'id': value, 'display_name': None}
        if field == 'customer':
            customer = customers.get(value)
            return _customer_ref(customer) if customer is not None else {'id': value, 'display_name': None}
        appointment = appointments.get(value)
        if appointment is not None:
            return _appointment_ref(appointment)
        return {'id': value, 'start_at': None, 'end_at': None, 'status': None, 'service_name': None}

    rows = []
    for activity in activities:
        field = _ACTIVITY_VALUE_FIELD.get(activity.kind)
        metadata = dict(activity.metadata or {})
        if activity.kind == LeadActivity.Kind.CLOSED:
            metadata['outcome'] = _choice_ref('outcome', metadata.get('outcome'))
        rows.append({
            'id': str(activity.pk),
            'kind': activity.kind,
            'kind_display': activity.get_kind_display(),
            'occurred_at': activity.created_at,
            'actor': _user_ref(activity.actor),
            'previous': ref(field, activity.previous_value),
            'new': ref(field, activity.new_value),
            'metadata': metadata,
        })
    return rows


class LeadUpdateSerializer(serializers.Serializer):
    """PATCH CRM humano. `instance` debe venir bloqueado (`select_for_update`).

    Contexto requerido: `request` (para `closed_by`) y `service` (servicio
    activo del Business, para validar que el asignado pueda ver Leads).
    """

    status = serializers.ChoiceField(choices=Lead.Status.choices, required=False)
    outcome = serializers.ChoiceField(choices=Lead.Outcome.choices, required=False, allow_null=True)
    assigned_to = serializers.IntegerField(required=False, allow_null=True)
    customer = serializers.UUIDField(required=False, allow_null=True)
    appointment = serializers.UUIDField(required=False, allow_null=True)

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError({'non_field_errors': ['Payload inválido.']})
        rejected = sorted(set(data) - set(EDITABLE_FIELDS))
        if rejected:
            raise serializers.ValidationError({field: ['Campo no editable.'] for field in rejected})
        return super().to_internal_value(data)

    def validate_assigned_to(self, value):
        if value is None:
            return None
        lead: Lead = self.instance
        # Conservar la asignación actual siempre es válido (aunque esa persona
        # haya perdido acceso después): editar otro campo no obliga a reasignar.
        if value == lead.assigned_to_id:
            return lead.assigned_to
        # Misma regla que `GET /leads/assignees/` (services.assignees).
        membership = active_memberships(lead.business_id).filter(user_id=value).first()
        # Usuario inexistente o de otro Business: misma respuesta (sin oráculo).
        if membership is None:
            raise serializers.ValidationError('La persona no pertenece a este negocio.')
        if not membership_can_view_leads(membership, self.context['service']):
            raise serializers.ValidationError('La persona no tiene acceso a Leads.')
        return membership.user

    def validate_customer(self, value):
        if value is None:
            return None
        lead: Lead = self.instance
        if value == lead.customer_id:
            return lead.customer
        customer = Customer.objects.filter(pk=value, business_id=lead.business_id).first()
        # Customer de otro Business indistinguible de uno inexistente.
        if customer is None:
            raise serializers.ValidationError('El cliente no existe en este negocio.')
        if not customer.is_active:
            raise serializers.ValidationError('El cliente está dado de baja. Reactivalo desde su ficha o elegí otro.')
        return customer

    def validate_appointment(self, value):
        # LEADS 04B.2: vínculo humano con un turno EXISTENTE. Nunca crea ni
        # modifica el turno, ni toca status/outcome/atención del Lead. Sin
        # filtro por estado (igual que `CustomerReminder.appointment`): un turno
        # cancelado/completado/vencido sigue siendo el registro de lo que pasó.
        # Varios Leads pueden apuntar al mismo turno (FK many-to-one).
        if value is None:
            return None
        lead: Lead = self.instance
        if value == lead.appointment_id:
            return lead.appointment
        appointment = Appointment.objects.filter(pk=value, business_id=lead.business_id).first()
        # Turno de otro Business indistinguible de uno inexistente.
        if appointment is None:
            raise serializers.ValidationError('El turno no existe en este negocio.')
        return appointment

    def validate(self, attrs):
        lead: Lead = self.instance
        current = lead.status
        target = attrs.get('status', current)
        if target not in ALLOWED_TRANSITIONS[current]:
            if current == Lead.Status.CLOSED:
                raise serializers.ValidationError({'status': 'El lead está cerrado y no se puede reabrir.'})
            raise serializers.ValidationError({'status': 'Transición de estado no permitida.'})

        if target == Lead.Status.CLOSED:
            outcome = attrs['outcome'] if 'outcome' in attrs else lead.outcome
            if outcome is None:
                raise serializers.ValidationError({'outcome': 'Elegí un resultado para cerrar el lead.'})
        elif attrs.get('outcome') is not None:
            raise serializers.ValidationError({'outcome': 'El resultado solo se informa al cerrar el lead.'})
        return attrs

    def update(self, instance: Lead, validated_data):
        from django.utils import timezone

        previous = snapshot_for_activity(instance)
        changed: list[str] = []
        for field, value in validated_data.items():
            if getattr(instance, field) != value:
                setattr(instance, field, value)
                changed.append(field)
        if 'status' in changed and instance.status == Lead.Status.CLOSED:
            instance.closed_at = timezone.now()
            instance.closed_by = self.context['request'].user
            changed += ['closed_at', 'closed_by']
        if changed:
            # Solo campos CRM: nunca pisar `needs_attention_at` (lo escribe el
            # receiver) ni `acknowledged_*` (acción propia de reconocer).
            instance.save(update_fields=[*changed, 'updated_at'])
            # LEADS 04B.4: historial en la misma transacción (rollback conjunto).
            record_update_activity(instance, previous, actor=self.context['request'].user)
        if 'assigned_to' in changed:
            # LEADS 04B.3: aviso personal al nuevo asignado (post-commit).
            schedule_lead_assigned_notification(instance, actor=self.context['request'].user)
        return instance
