"""Leads del agente de WhatsApp (AGENT 02A — fundación del receptor).

Dos dominios separados estructuralmente (ver docs/MIRUBRO_AGENT_RECEIVER_AUDIT.md §8–§9):

- Integración: `AgentInstance` (quién firma), `AgentCredential` (secreto HMAC
  cifrado con Fernet, clave dedicada) y `AgentChannel` (phone_number_id de
  Meta → Business). El tenant SIEMPRE se deriva del canal activo.
- CRM: `Lead` (lo escriben humanos en MiRubro) + `LeadNote`, y
  `LeadAgentState` (réplica del agente, lo escribe solo el sync futuro).

Invariantes que NO se pueden expresar como constraint de DB (cross-table) y
que el receiver service de 02B debe garantizar dentro de su transacción:
- `lead_agent_state.lead.business == lead_agent_state.channel.business`.
- `lead_agent_state.channel.agent_instance == lead_agent_state.agent_instance`.
`LeadAgentState.save()` las verifica igual (patrón `CustomerNote.save()`),
pero `bulk_create`/`update()` no pasan por ahí.
"""
from __future__ import annotations

import uuid

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q

from .crypto import decrypt_agent_secret, encrypt_agent_secret

EXTERNAL_ID_REGEX = r'^[a-z0-9-]{3,64}$'
KEY_ID_REGEX = r'^[A-Za-z0-9_.-]{1,64}$'
PHONE_NUMBER_ID_REGEX = r'^[0-9]{1,32}$'
E164_REGEX = r'^\+[1-9][0-9]{1,14}$'
PAYLOAD_HASH_REGEX = r'^[0-9a-f]{64}$'
# Todo token Fernet empieza con el byte de versión 0x80 + timestamp de 64 bits
# (base64 `gAAAAA` hasta dentro de varios siglos). Barrera barata a nivel DB
# contra persistir el secreto en claro por error.
FERNET_TOKEN_PREFIX = 'gAAAAA'


class AgentInstance(models.Model):
    """Una instalación/deployment del servicio agente.

    `external_id` es el `agent_instance_id` del contrato (lo que viaja en el
    payload). `id` es interno de MiRubro y nunca se expone al agente.
    `external_id` es inmutable una vez creado (las credenciales, canales y
    leads quedan atados a esa identidad).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    external_id = models.CharField(
        max_length=64, unique=True,
        validators=[RegexValidator(EXTERNAL_ID_REGEX, 'external_id inválido: usar [a-z0-9-], 3 a 64 caracteres.')],
    )
    name = models.CharField(max_length=120)
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    disabled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['external_id']
        constraints = [
            models.CheckConstraint(check=Q(external_id__regex=EXTERNAL_ID_REGEX), name='agent_instance_external_id_format'),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding and self.pk is not None:
            stored = type(self).objects.filter(pk=self.pk).values_list('external_id', flat=True).first()
            if stored is not None and stored != self.external_id:
                raise ValueError('AgentInstance.external_id is immutable.')
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f'{self.name} ({self.external_id})'


class AgentCredential(models.Model):
    """Secreto HMAC compartido de una `AgentInstance`.

    El secreto se guarda cifrado (reversible) con `AGENT_SECRET_ENCRYPTION_KEY`;
    nunca en claro. Rotación: nueva credencial `active`, la anterior pasa a
    `retiring` durante la ventana y luego a `revoked`.
    """

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Activa'
        RETIRING = 'retiring', 'En retiro'
        REVOKED = 'revoked', 'Revocada'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent_instance = models.ForeignKey(AgentInstance, related_name='credentials', on_delete=models.CASCADE)
    key_id = models.CharField(
        max_length=64, unique=True,
        validators=[RegexValidator(KEY_ID_REGEX, 'key_id inválido: usar [A-Za-z0-9_.-], 1 a 64 caracteres.')],
    )
    encrypted_secret = models.TextField(editable=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(check=Q(key_id__regex=KEY_ID_REGEX), name='agent_credential_key_id_format'),
            models.CheckConstraint(
                check=Q(status__in=['active', 'retiring', 'revoked']), name='agent_credential_status_valid',
            ),
            models.CheckConstraint(
                check=Q(encrypted_secret__startswith=FERNET_TOKEN_PREFIX), name='agent_credential_secret_encrypted',
            ),
            # revoked ⇔ revoked_at informado.
            models.CheckConstraint(
                check=(Q(status='revoked') & Q(revoked_at__isnull=False)) | (~Q(status='revoked') & Q(revoked_at__isnull=True)),
                name='agent_credential_revoked_at_coherent',
            ),
        ]

    def set_secret(self, plaintext: str) -> None:
        self.encrypted_secret = encrypt_agent_secret(plaintext)

    def get_secret(self) -> str:
        return decrypt_agent_secret(self.encrypted_secret)

    def __str__(self) -> str:
        # Nunca incluir el secreto (ni cifrado): __repr__ de Django usa __str__.
        return f'AgentCredential {self.key_id} ({self.status})'


class AgentChannel(models.Model):
    """Número de WhatsApp (phone_number_id de Meta) atendido por una
    `AgentInstance` para un Business.

    Un `(provider, phone_number_id)` puede estar activo en UN solo registro a
    nivel global. Reasignar = desactivar el canal anterior + crear uno nuevo.
    """

    class Provider(models.TextChoices):
        WHATSAPP_CLOUD = 'whatsapp_cloud', 'WhatsApp Cloud API'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=32, choices=Provider.choices, default=Provider.WHATSAPP_CLOUD)
    phone_number_id = models.CharField(
        max_length=32,
        validators=[RegexValidator(PHONE_NUMBER_ID_REGEX, 'phone_number_id inválido: solo dígitos, 1 a 32.')],
    )
    agent_instance = models.ForeignKey(AgentInstance, related_name='channels', on_delete=models.PROTECT)
    business = models.ForeignKey('business.Business', related_name='agent_channels', on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['business', 'is_active'], name='agent_channel_business_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['provider', 'phone_number_id'], condition=Q(is_active=True),
                name='agent_channel_active_phone_number_unique',
            ),
            models.CheckConstraint(check=Q(phone_number_id__regex=PHONE_NUMBER_ID_REGEX), name='agent_channel_phone_number_id_format'),
            models.CheckConstraint(check=Q(provider__in=['whatsapp_cloud']), name='agent_channel_provider_valid'),
            # Un canal activo no puede tener fecha de desactivación.
            models.CheckConstraint(
                check=Q(is_active=False) | Q(deactivated_at__isnull=True), name='agent_channel_active_not_deactivated',
            ),
        ]

    def __str__(self) -> str:
        state = 'active' if self.is_active else 'inactive'
        return f'{self.provider}:{self.phone_number_id} → business {self.business_id} ({state})'


class Lead(models.Model):
    """Lead CRM: pertenece a MiRubro y lo gestionan humanos.

    El sync del agente solo lo crea con defaults; después nunca toca
    status/outcome/assigned_to/customer/appointment/acknowledged_*. Única
    excepción: `needs_attention_at` cuando el agente pide atención. Los datos
    informados por el bot viven en `LeadAgentState`.

    Atención humana (LEADS 04B.1):
    - `needs_attention_at` (lo escribe solo el receiver): cuándo el agente pidió
      atención por primera vez desde el último reconocimiento. Nunca lo borra
      ni lo edita un humano.
    - `acknowledged_at`/`acknowledged_by` (los escribe solo la acción humana
      de reconocer): cuándo y quién atendió ese pedido.
    - Pendiente ⇔ `needs_attention_at` informado, Lead no cerrado y sin
      reconocimiento posterior (`acknowledged_at < needs_attention_at`). Un
      pedido nuevo del agente después de un reconocimiento mueve
      `needs_attention_at` hacia adelante y lo vuelve pendiente sin tocar los
      datos humanos.

    `assigned_to` debe ser una membership activa del Business: se valida en
    el service/serializer futuro, no acá.
    """

    class Source(models.TextChoices):
        WHATSAPP_AGENT = 'whatsapp_agent', 'Agente de WhatsApp'

    class Status(models.TextChoices):
        NEW = 'new', 'Nuevo'
        IN_PROGRESS = 'in_progress', 'En gestión'
        CLOSED = 'closed', 'Cerrado'

    class Outcome(models.TextChoices):
        BOOKED = 'booked', 'Turno agendado'
        LINKED_CUSTOMER = 'linked_customer', 'Cliente identificado'
        NOT_INTERESTED = 'not_interested', 'No interesado'
        UNREACHABLE = 'unreachable', 'Sin respuesta'
        DUPLICATE = 'duplicate', 'Duplicado'
        SPAM = 'spam', 'Spam'
        OTHER = 'other', 'Otro'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey('business.Business', related_name='leads', on_delete=models.CASCADE)
    source = models.CharField(max_length=32, choices=Source.choices, default=Source.WHATSAPP_AGENT)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NEW)
    outcome = models.CharField(max_length=32, choices=Outcome.choices, null=True, blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='assigned_leads', on_delete=models.SET_NULL, null=True, blank=True,
    )
    customer = models.ForeignKey(
        'customers.Customer', related_name='leads', on_delete=models.SET_NULL, null=True, blank=True,
    )
    appointment = models.ForeignKey(
        'appointments.Appointment', related_name='leads', on_delete=models.SET_NULL, null=True, blank=True,
    )
    needs_attention_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='closed_leads', on_delete=models.SET_NULL, null=True, blank=True,
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='acknowledged_leads', on_delete=models.SET_NULL, null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['business', 'status', '-created_at'], name='lead_business_status_idx'),
        ]
        constraints = [
            models.CheckConstraint(check=Q(source__in=['whatsapp_agent']), name='lead_source_valid'),
            models.CheckConstraint(check=Q(status__in=['new', 'in_progress', 'closed']), name='lead_status_valid'),
            models.CheckConstraint(
                check=Q(outcome__isnull=True) | Q(outcome__in=[
                    'booked', 'linked_customer', 'not_interested', 'unreachable', 'duplicate', 'spam', 'other',
                ]),
                name='lead_outcome_valid',
            ),
            # outcome obligatorio al cerrar y nulo mientras no esté cerrado.
            models.CheckConstraint(
                check=(Q(status='closed') & Q(outcome__isnull=False)) | (~Q(status='closed') & Q(outcome__isnull=True)),
                name='lead_outcome_iff_closed',
            ),
            # Solo se reconoce un pedido de atención que existió.
            models.CheckConstraint(
                check=Q(acknowledged_at__isnull=True) | Q(needs_attention_at__isnull=False),
                name='lead_ack_requires_attention',
            ),
        ]

    @staticmethod
    def attention_pending_q() -> Q:
        """Filtro de Leads con atención pendiente (misma regla que `attention_pending`)."""
        return (
            Q(needs_attention_at__isnull=False)
            & ~Q(status=Lead.Status.CLOSED)
            & (Q(acknowledged_at__isnull=True) | Q(acknowledged_at__lt=F('needs_attention_at')))
        )

    @property
    def attention_acknowledged(self) -> bool:
        """El último pedido de atención ya fue reconocido por un humano."""
        return (
            self.needs_attention_at is not None
            and self.acknowledged_at is not None
            and self.acknowledged_at >= self.needs_attention_at
        )

    @property
    def attention_pending(self) -> bool:
        return (
            self.needs_attention_at is not None
            and self.status != Lead.Status.CLOSED
            and not self.attention_acknowledged
        )

    def save(self, *args, **kwargs):
        # Tenant safety (patrón CustomerNote): customer/appointment del mismo Business.
        if self.customer_id is not None and self.customer.business_id != self.business_id:
            raise ValueError('Lead.customer must belong to lead.business.')
        if self.appointment_id is not None and self.appointment.business_id != self.business_id:
            raise ValueError('Lead.appointment must belong to lead.business.')
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f'Lead {self.pk} ({self.status})'


class LeadAgentState(models.Model):
    """Réplica de lo que informó el agente para un Lead (solo la escribe el sync).

    Identidad externa única por `(agent_instance, external_lead_id)`. No se
    guarda el payload crudo ni headers. Los mensajes de la conversación SÍ se
    guardan, pero aparte: ver `LeadAgentMessage` (LEADS 05C, a pedido explícito
    para el historial del detalle del Lead).
    """

    PATIENT_NAME_MAX_LENGTH = 150
    REASON_MAX_LENGTH = 500
    SUMMARY_MAX_LENGTH = 2000

    class AgentStatus(models.TextChoices):
        ACTIVE = 'active', 'Activa'
        CLOSED = 'closed', 'Cerrada'

    class CloseReason(models.TextChoices):
        IDLE = 'idle', 'Inactividad'
        RECEPTION = 'reception', 'Derivada a recepción'

    lead = models.OneToOneField(Lead, related_name='agent_state', on_delete=models.CASCADE, primary_key=True)

    # Identidad
    agent_instance = models.ForeignKey(AgentInstance, related_name='lead_states', on_delete=models.PROTECT)
    # RESTRICT (no PROTECT): borrar el Business borra canal y leads en la misma cascada.
    channel = models.ForeignKey(AgentChannel, related_name='lead_states', on_delete=models.RESTRICT)
    external_lead_id = models.UUIDField()
    external_conversation_id = models.CharField(max_length=64, db_index=True)
    previous_external_lead_id = models.UUIDField(null=True, blank=True)

    # Snapshot informado por el agente
    patient_name = models.CharField(max_length=PATIENT_NAME_MAX_LENGTH, null=True, blank=True)
    whatsapp_profile_name = models.CharField(max_length=PATIENT_NAME_MAX_LENGTH, null=True, blank=True)
    phone_e164 = models.CharField(
        max_length=16, validators=[RegexValidator(E164_REGEX, 'phone_e164 inválido (formato E.164).')],
    )
    reason = models.CharField(max_length=REASON_MAX_LENGTH, null=True, blank=True)
    preferred_time = models.CharField(max_length=REASON_MAX_LENGTH, null=True, blank=True)
    urgency = models.BooleanField(default=False)
    agent_status = models.CharField(max_length=16, choices=AgentStatus.choices, default=AgentStatus.ACTIVE)
    handoff_requested = models.BooleanField(default=False)
    handoff_requested_at = models.DateTimeField(null=True, blank=True)
    handoff_reasons = models.JSONField(default=list, blank=True)
    summary = models.CharField(max_length=SUMMARY_MAX_LENGTH, null=True, blank=True)

    # Timestamps del agente
    opened_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)
    close_reason = models.CharField(max_length=16, choices=CloseReason.choices, null=True, blank=True)
    last_message_at = models.DateTimeField()

    # Metadata de sync
    applied_version = models.PositiveBigIntegerField()
    payload_hash = models.CharField(max_length=64, blank=True, default='')
    last_event_id = models.UUIDField()
    last_synced_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['agent_instance', 'external_lead_id'], name='lead_agent_state_external_identity_unique'),
            models.CheckConstraint(check=Q(applied_version__gt=0), name='lead_agent_state_version_positive'),
            models.CheckConstraint(
                check=Q(payload_hash='') | Q(payload_hash__regex=PAYLOAD_HASH_REGEX), name='lead_agent_state_payload_hash_format',
            ),
            models.CheckConstraint(check=Q(phone_e164__regex=E164_REGEX), name='lead_agent_state_phone_e164_format'),
            models.CheckConstraint(check=Q(agent_status__in=['active', 'closed']), name='lead_agent_state_agent_status_valid'),
            models.CheckConstraint(
                check=Q(close_reason__isnull=True) | Q(close_reason__in=['idle', 'reception']),
                name='lead_agent_state_close_reason_valid',
            ),
            # Sin handoff no hay motivos de handoff.
            models.CheckConstraint(
                check=Q(handoff_requested=True) | Q(handoff_reasons=[]), name='lead_agent_state_reasons_require_handoff',
            ),
        ]

    def save(self, *args, **kwargs):
        # Invariantes cross-table (ver docstring del módulo): el receiver
        # service de 02B debe garantizarlas; esto es la última barrera.
        if self.channel.business_id != self.lead.business_id:
            raise ValueError('LeadAgentState.channel.business must match lead.business.')
        if self.channel.agent_instance_id != self.agent_instance_id:
            raise ValueError('LeadAgentState.channel.agent_instance must match agent_instance.')
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        # Sin PII (nombre/teléfono): solo identificadores.
        return f'LeadAgentState {self.lead_id} v{self.applied_version}'


class LeadAgentMessage(models.Model):
    """Mensaje de la conversación de WhatsApp de un Lead, replicado por el agente (LEADS 05C).

    El agente manda la ventana de mensajes del episodio del lead
    (openedAt..closedAt) en cada `lead.sync`; acá se guardan por
    `(lead, external_message_id)`, lo que hace reintentos y reenvíos
    idempotentes (upsert, nunca duplica). Solo lectura humana (CRM); no hay
    endpoint de escritura humana. `sender` distingue paciente / bot / staff
    (recepción, mensaje humano enviado por takeover) incluso cuando
    `role=assistant` cubre a los dos últimos.
    """

    TEXT_MAX_LENGTH = 4000

    class Role(models.TextChoices):
        USER = 'user', 'Paciente'
        ASSISTANT = 'assistant', 'Agente'

    class Sender(models.TextChoices):
        PATIENT = 'patient', 'Paciente'
        BOT = 'bot', 'Bot'
        STAFF = 'staff', 'Recepción'

    class Status(models.TextChoices):
        SENT = 'sent', 'Enviado'
        DELIVERED = 'delivered', 'Entregado'
        READ = 'read', 'Leído'
        FAILED = 'failed', 'Fallido'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lead = models.ForeignKey(Lead, related_name='agent_messages', on_delete=models.CASCADE)
    external_message_id = models.CharField(max_length=64)
    role = models.CharField(max_length=16, choices=Role.choices)
    sender = models.CharField(max_length=16, choices=Sender.choices)
    text = models.CharField(max_length=TEXT_MAX_LENGTH)
    sent_at = models.DateTimeField()
    status = models.CharField(max_length=16, choices=Status.choices, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sent_at', 'id']
        constraints = [
            models.UniqueConstraint(fields=['lead', 'external_message_id'], name='lead_agent_message_unique'),
            models.CheckConstraint(check=Q(role__in=['user', 'assistant']), name='lead_agent_message_role_valid'),
            models.CheckConstraint(check=Q(sender__in=['patient', 'bot', 'staff']), name='lead_agent_message_sender_valid'),
            models.CheckConstraint(
                check=Q(status__isnull=True) | Q(status__in=['sent', 'delivered', 'read', 'failed']),
                name='lead_agent_message_status_valid',
            ),
            models.CheckConstraint(check=~Q(text=''), name='lead_agent_message_text_not_empty'),
        ]
        indexes = [
            models.Index(fields=['lead', 'sent_at'], name='lead_agent_message_lead_idx'),
        ]

    def __str__(self) -> str:
        return f'LeadAgentMessage {self.pk} lead={self.lead_id} ({self.role})'


class LeadNote(models.Model):
    """Nota interna del equipo sobre un Lead (mismo patrón que `CustomerNote`).

    `business` se denormaliza y `save()` garantiza que coincide con el del Lead.
    """

    BODY_MAX_LENGTH = 2000

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey('business.Business', related_name='lead_notes', on_delete=models.CASCADE)
    lead = models.ForeignKey(Lead, related_name='notes', on_delete=models.CASCADE)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='lead_notes', on_delete=models.SET_NULL, null=True, blank=True,
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['business', 'lead', '-created_at'], name='lead_note_feed_idx'),
        ]
        constraints = [
            models.CheckConstraint(check=~Q(body=''), name='lead_note_body_not_empty'),
        ]

    def save(self, *args, **kwargs):
        if self.lead_id is not None:
            lead_business_id = self.lead.business_id
            if self.business_id is None:
                self.business_id = lead_business_id
            elif self.business_id != lead_business_id:
                raise ValueError('LeadNote.business must match lead.business.')
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f'LeadNote {self.pk} ({self.lead_id})'


class LeadActivity(models.Model):
    """Historial humano/operativo de un Lead (LEADS 04B.4). Append-only.

    Mismo patrón que `sales.OrderHistory` (una fila por evento, actor FK,
    valores anterior/nuevo) con `business` denormalizado como `LeadNote`.
    Solo lo escriben las acciones humanas de la API CRM, dentro de la misma
    transacción que el cambio: el sync del agente (`LeadAgentState`,
    `needs_attention_at`, duplicate/stale) nunca genera actividad.

    Granularidad: un evento por cambio semántico. Un PATCH con varios cambios
    genera varios eventos con el mismo `created_at` y `position` (orden fijo
    dentro del PATCH). Cerrar es un único evento `closed` (con el `outcome` en
    `metadata`), no `status_changed` + `outcome_changed`.

    `previous_value`/`new_value` guardan solo identificadores crudos (status,
    outcome, user id, UUID de Customer/Appointment); las etiquetas se resuelven
    al leer, así no se duplica PII del cliente en el historial.
    """

    class Kind(models.TextChoices):
        STATUS_CHANGED = 'status_changed', 'Cambio de estado'
        CLOSED = 'closed', 'Lead cerrado'
        OUTCOME_CHANGED = 'outcome_changed', 'Cambio de resultado'
        ASSIGNED = 'assigned', 'Asignado'
        REASSIGNED = 'reassigned', 'Reasignado'
        UNASSIGNED = 'unassigned', 'Desasignado'
        CUSTOMER_LINKED = 'customer_linked', 'Cliente vinculado'
        CUSTOMER_CHANGED = 'customer_changed', 'Cliente cambiado'
        CUSTOMER_UNLINKED = 'customer_unlinked', 'Cliente desvinculado'
        APPOINTMENT_LINKED = 'appointment_linked', 'Turno vinculado'
        APPOINTMENT_CHANGED = 'appointment_changed', 'Turno cambiado'
        APPOINTMENT_UNLINKED = 'appointment_unlinked', 'Turno desvinculado'
        ATTENTION_ACKNOWLEDGED = 'attention_acknowledged', 'Atención reconocida'
        # MIRUBRO TAKEOVER 05A: control humano de la conversación. Se registra
        # en el Lead desde el que se pidió el comando.
        TAKEOVER_REQUESTED = 'takeover_requested', 'Toma de conversación solicitada'
        TAKEOVER_APPLIED = 'takeover_applied', 'Conversación tomada (bot pausado)'
        TAKEOVER_FAILED = 'takeover_failed', 'Falló la toma de conversación'
        RELEASE_REQUESTED = 'release_requested', 'Reanudación del bot solicitada'
        RELEASE_APPLIED = 'release_applied', 'Bot reanudado'
        RELEASE_FAILED = 'release_failed', 'Falló la reanudación del bot'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey('business.Business', related_name='lead_activities', on_delete=models.CASCADE)
    lead = models.ForeignKey(Lead, related_name='activities', on_delete=models.CASCADE)
    kind = models.CharField(max_length=32, choices=Kind.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='lead_activities', on_delete=models.SET_NULL, null=True, blank=True,
    )
    previous_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    position = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField()

    class Meta:
        # Más reciente primero; dentro de un mismo PATCH, en el orden canónico.
        ordering = ['-created_at', 'position']
        indexes = [
            models.Index(fields=['business', 'lead', '-created_at'], name='lead_activity_feed_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(kind__in=[
                    'status_changed', 'closed', 'outcome_changed', 'assigned', 'reassigned', 'unassigned',
                    'customer_linked', 'customer_changed', 'customer_unlinked', 'appointment_linked',
                    'appointment_changed', 'appointment_unlinked', 'attention_acknowledged',
                    'takeover_requested', 'takeover_applied', 'takeover_failed',
                    'release_requested', 'release_applied', 'release_failed',
                ]),
                name='lead_activity_kind_valid',
            ),
        ]

    def save(self, *args, **kwargs):
        if self.lead_id is not None:
            lead_business_id = self.lead.business_id
            if self.business_id is None:
                self.business_id = lead_business_id
            elif self.business_id != lead_business_id:
                raise ValueError('LeadActivity.business must match lead.business.')
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f'LeadActivity {self.kind} ({self.lead_id})'


# ── MIRUBRO TAKEOVER 05A — control humano de la conversación ─────────────────

# Id opaco de la Conversation del agente (Contract V1 §3). El agente resuelve
# los comandos SOLO por este valor; cualquier otro formato le da 404.
EXTERNAL_CONVERSATION_ID_REGEX = r'^wac1_[0-9a-f]{32}$'


class ConversationControl(models.Model):
    """Estado deseado/operativo de la pausa del bot para UNA conversación.

    La pausa es de la Conversation del agente, no del episodio Lead: varios
    Leads (p. ej. uno nuevo tras 72 h) comparten `external_conversation_id` y
    leen esta misma fila. Identidad: `(business, external_conversation_id)`.

    `state` refleja lo que MiRubro SABE, no lo que pidió: `taken` solo después
    del ACK 2xx del agente para el comando vigente. Los comandos viven en
    `TakeoverCommand` (outbox con reintentos); `command_version` es la versión
    del último comando creado (monotónica, nunca se reutiliza).
    """

    class State(models.TextChoices):
        ACTIVE = 'active', 'Bot activo'
        TAKEOVER_PENDING = 'takeover_pending', 'Tomando conversación'
        TAKEN = 'taken', 'Conversación tomada'
        RELEASE_PENDING = 'release_pending', 'Reanudando bot'
        ERROR = 'error', 'Error'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey('business.Business', related_name='conversation_controls', on_delete=models.CASCADE)
    external_conversation_id = models.CharField(
        max_length=64,
        validators=[RegexValidator(EXTERNAL_CONVERSATION_ID_REGEX, 'external_conversation_id inválido.')],
    )
    state = models.CharField(max_length=24, choices=State.choices, default=State.ACTIVE)
    command_version = models.PositiveBigIntegerField(default=0)
    last_command_action = models.CharField(max_length=16, null=True, blank=True)
    last_event_id = models.UUIDField(null=True, blank=True)
    # Mayor `applied_version` informada por el agente (cualquier respuesta 2xx).
    # Si supera `command_version`, MiRubro perdió estado: el próximo comando
    # sale con una versión mayor a ambas (nunca se intenta bajar la del agente).
    agent_applied_version = models.PositiveBigIntegerField(default=0)
    taken_at = models.DateTimeField(null=True, blank=True)
    taken_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='taken_conversations', on_delete=models.SET_NULL, null=True, blank=True,
    )
    released_at = models.DateTimeField(null=True, blank=True)
    last_command_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=48, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(
                fields=['business', 'external_conversation_id'], name='conversation_control_identity_unique',
            ),
            models.CheckConstraint(
                check=Q(external_conversation_id__regex=EXTERNAL_CONVERSATION_ID_REGEX),
                name='conversation_control_external_id_format',
            ),
            models.CheckConstraint(
                check=Q(state__in=['active', 'takeover_pending', 'taken', 'release_pending', 'error']),
                name='conversation_control_state_valid',
            ),
            models.CheckConstraint(
                check=Q(last_command_action__isnull=True) | Q(last_command_action__in=['takeover', 'release']),
                name='conversation_control_last_action_valid',
            ),
            # Sin comandos: estado activo y sin event_id/acción.
            models.CheckConstraint(
                check=(
                    Q(command_version=0, state='active', last_event_id__isnull=True, last_command_action__isnull=True)
                    | Q(command_version__gt=0, last_event_id__isnull=False, last_command_action__isnull=False)
                ),
                name='conversation_control_version_coherent',
            ),
            models.CheckConstraint(
                check=~Q(state='taken') | Q(taken_at__isnull=False), name='conversation_control_taken_has_taken_at',
            ),
        ]

    def __str__(self) -> str:
        return f'ConversationControl {self.external_conversation_id} ({self.state} v{self.command_version})'


class TakeoverCommand(models.Model):
    """Un comando humano takeover/release hacia el agente (outbox durable).

    Se crea en la misma transacción que mueve `ConversationControl` a
    `*_pending`; el HTTP sale después del commit. Los reintentos reusan
    `version`, `event_id` y `occurred_at` (mismo body); solo cambian
    request_id/timestamp/firma. No guarda payload crudo, headers ni PII.
    """

    class Action(models.TextChoices):
        TAKEOVER = 'takeover', 'Tomar conversación'
        RELEASE = 'release', 'Reanudar bot'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendiente'
        DELIVERING = 'delivering', 'Enviando'
        DELIVERED = 'delivered', 'Entregado'
        FAILED = 'failed', 'Fallido'

    class Result(models.TextChoices):
        APPLIED = 'applied', 'Aplicado'
        DUPLICATE = 'duplicate', 'Duplicado'
        STALE = 'stale', 'Obsoleto'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation_control = models.ForeignKey(ConversationControl, related_name='commands', on_delete=models.CASCADE)
    version = models.PositiveBigIntegerField()
    event_id = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    action = models.CharField(max_length=16, choices=Action.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    result = models.CharField(max_length=16, choices=Result.choices, null=True, blank=True)
    occurred_at = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    last_status = models.PositiveSmallIntegerField(null=True, blank=True)
    last_error = models.CharField(max_length=48, null=True, blank=True)
    agent_applied_version = models.PositiveBigIntegerField(null=True, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='takeover_commands', on_delete=models.SET_NULL, null=True, blank=True,
    )
    # Lead desde el que se pidió (para el historial); la conversación puede abarcar varios.
    requested_from_lead = models.ForeignKey(
        Lead, related_name='takeover_commands', on_delete=models.SET_NULL, null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-version']
        indexes = [
            models.Index(fields=['status', 'next_attempt_at'], name='takeover_command_due_idx'),
        ]
        constraints = [
            models.UniqueConstraint(fields=['conversation_control', 'version'], name='takeover_command_version_unique'),
            models.CheckConstraint(check=Q(version__gt=0), name='takeover_command_version_positive'),
            models.CheckConstraint(check=Q(action__in=['takeover', 'release']), name='takeover_command_action_valid'),
            models.CheckConstraint(
                check=Q(status__in=['pending', 'delivering', 'delivered', 'failed']), name='takeover_command_status_valid',
            ),
            models.CheckConstraint(
                check=Q(result__isnull=True) | Q(result__in=['applied', 'duplicate', 'stale']),
                name='takeover_command_result_valid',
            ),
            # delivered ⇔ result + delivered_at.
            models.CheckConstraint(
                check=(Q(status='delivered') & Q(result__isnull=False) & Q(delivered_at__isnull=False))
                | (~Q(status='delivered') & Q(result__isnull=True) & Q(delivered_at__isnull=True)),
                name='takeover_command_delivered_coherent',
            ),
            models.CheckConstraint(
                check=~Q(status='pending') | Q(next_attempt_at__isnull=False), name='takeover_command_pending_scheduled',
            ),
            models.CheckConstraint(
                check=~Q(status='delivering') | Q(lease_until__isnull=False), name='takeover_command_delivering_leased',
            ),
            models.CheckConstraint(
                check=(Q(status='failed') & Q(failed_at__isnull=False)) | (~Q(status='failed') & Q(failed_at__isnull=True)),
                name='takeover_command_failed_coherent',
            ),
        ]

    def __str__(self) -> str:
        return f'TakeoverCommand {self.action} v{self.version} ({self.status})'


# ── MIRUBRO HUMAN MESSAGES — recepción responde al paciente por WhatsApp ────

class LeadStaffMessage(models.Model):
    """Outbox durable de un mensaje escrito por recepción hacia el paciente.

    Mismo patrón que `TakeoverCommand`: outbox con reintentos (skip-locked,
    attempts, lease, backoff). El agente no tiene canal de feedback propio
    para este envío (su respuesta solo dice `queued`/`duplicate`, nunca
    `delivered`/`read`): acá solo se registra si LLEGÓ A ENCOLARSE en el
    agente (`status=delivered` + `result` + `message_id`), nunca si el
    WhatsApp del paciente la recibió. El estado real de entrega llega
    después, solo, vía `lead.sync` → `LeadAgentMessage` (`message_id` de la
    respuesta == `external_message_id` sincronizado; ver
    `services.human_messages.authored_by_map`).

    `client_message_id`/`event_id` se generan una vez al encolar y se
    reutilizan en todos los reintentos HTTP (mismo body, misma identidad
    lógica del mensaje para el agente).
    """

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendiente'
        DELIVERING = 'delivering', 'Enviando'
        DELIVERED = 'delivered', 'Encolado en el agente'
        FAILED = 'failed', 'Fallido'

    class Result(models.TextChoices):
        QUEUED = 'queued', 'Encolado'
        DUPLICATE = 'duplicate', 'Duplicado'

    TEXT_MAX_LENGTH = 4096

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lead = models.ForeignKey(Lead, related_name='staff_messages', on_delete=models.CASCADE)
    client_message_id = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    event_id = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    text = models.CharField(max_length=TEXT_MAX_LENGTH)
    occurred_at = models.DateTimeField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='lead_staff_messages', on_delete=models.SET_NULL, null=True, blank=True,
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    result = models.CharField(max_length=16, choices=Result.choices, null=True, blank=True)
    # `message_id` del agente (contrato MIRUBRO_HUMAN_MESSAGES): nunca es un UUID propio de MiRubro.
    message_id = models.CharField(max_length=64, null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    last_status = models.PositiveSmallIntegerField(null=True, blank=True)
    last_error = models.CharField(max_length=48, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['status', 'next_attempt_at'], name='lead_staff_message_due_idx'),
            models.Index(fields=['lead', 'created_at'], name='lead_staff_message_lead_idx'),
        ]
        constraints = [
            models.CheckConstraint(check=~Q(text=''), name='lead_staff_message_text_not_empty'),
            models.CheckConstraint(
                check=Q(status__in=['pending', 'delivering', 'delivered', 'failed']),
                name='lead_staff_message_status_valid',
            ),
            models.CheckConstraint(
                check=Q(result__isnull=True) | Q(result__in=['queued', 'duplicate']),
                name='lead_staff_message_result_valid',
            ),
            # delivered ⇔ result + delivered_at + message_id (el agente siempre lo informa en 2xx).
            models.CheckConstraint(
                check=(
                    Q(status='delivered') & Q(result__isnull=False) & Q(delivered_at__isnull=False)
                    & Q(message_id__isnull=False)
                )
                | (~Q(status='delivered') & Q(result__isnull=True) & Q(delivered_at__isnull=True)),
                name='lead_staff_message_delivered_coherent',
            ),
            models.CheckConstraint(
                check=~Q(status='pending') | Q(next_attempt_at__isnull=False), name='lead_staff_message_pending_scheduled',
            ),
            models.CheckConstraint(
                check=~Q(status='delivering') | Q(lease_until__isnull=False), name='lead_staff_message_delivering_leased',
            ),
            models.CheckConstraint(
                check=(Q(status='failed') & Q(failed_at__isnull=False)) | (~Q(status='failed') & Q(failed_at__isnull=True)),
                name='lead_staff_message_failed_coherent',
            ),
        ]

    def __str__(self) -> str:
        return f'LeadStaffMessage {self.pk} lead={self.lead_id} ({self.status})'
